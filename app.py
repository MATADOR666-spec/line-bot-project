import os
import requests
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
import pytz
import base64

# ===== LINE Bot Config =====
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise ValueError("Missing LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

app = Flask(__name__)

# ===== Google Apps Script Config =====
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbwHNNOqy2QPycsroR_soj1JQeiENC-AtxMDLtJiAiLoj9g6T22qOBtk9j9nCq34Lprjxw/exec"
SECRET_CODE = "my_secret_code"
ADMIN_PASS = "8264"

# ===== เก็บ state =====
user_states = {}

# ===== Helper =====
def get_profile_from_sheets(user_id):
    try:
        payload = {"secret": SECRET_CODE, "action": "getProfile", "userId": user_id}
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def save_profile_to_sheets(profile_data):
    try:
        payload = {"secret": SECRET_CODE, "action": "addProfile", **profile_data}
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_all_profiles():
    try:
        payload = {"secret": SECRET_CODE, "action": "getAllProfiles"}
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def is_holiday(today_date):
    try:
        payload = {"secret": SECRET_CODE, "action": "isHoliday", "date": today_date}
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.json().get("isHoliday", False)
    except Exception as e:
        return False

def save_duty_log(log_data):
    try:
        payload = {"secret": SECRET_CODE, "action": "addDutyLog", **log_data}
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

def check_duty_log(room, date):
    try:
        payload = {"secret": SECRET_CODE, "action": "checkDutyLog", "ห้อง": room, "date": date}
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ===== ระบบแจ้งเตือนเวร =====
def send_duty_reminder():
    today = datetime.now(BANGKOK_TZ)
    today_name = today.strftime("%A")
    today_thai = {
        "Monday": "จันทร์", "Tuesday": "อังคาร", "Wednesday": "พุธ",
        "Thursday": "พฤหัสบดี", "Friday": "ศุกร์",
        "Saturday": "เสาร์", "Sunday": "อาทิตย์"
    }[today_name]

    today_date = today.strftime("%Y-%m-%d")

    if today_name in ["Saturday", "Sunday"] or is_holiday(today_date):
        return

    data = get_all_profiles()
    if not data.get("ok"):
        return

    for p in data["profiles"]:
        if str(p.get("เวรวัน", "")).strip() == today_thai:
            user_id = p["userId"]
            msg = f"📢 แจ้งเตือนเวรประจำวัน{today_thai}\nชื่อ: {p.get('ชื่อ')}\nห้อง: {p.get('ห้อง')}"
            try:
                line_bot_api.push_message(user_id, TextSendMessage(text=msg))
            except Exception as e:
                print("ERROR push:", e)

@app.route("/run-reminder", methods=["GET"])
def run_reminder():
    send_duty_reminder()
    return "Reminder sent", 200

# ===== ตรวจ 17:00 ว่ายังไม่ส่งหลักฐาน =====
def check_missing_evidence():
    today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
    today_name = datetime.now(BANGKOK_TZ).strftime("%A")
    today_thai = {"Monday":"จันทร์","Tuesday":"อังคาร","Wednesday":"พุธ","Thursday":"พฤหัสบดี","Friday":"ศุกร์"}.get(today_name)
    if not today_thai: return

    data = get_all_profiles()
    if not data.get("ok"): return

    for p in data["profiles"]:
        if str(p.get("เวรวัน")) == today_thai:
            r = check_duty_log(p["ห้อง"], today)
            if not r.get("found"):
                for t in data["profiles"]:
                    if t.get("บทบาท") == "อาจารย์" and str(t.get("ห้อง")) == str(p["ห้อง"]):
                        line_bot_api.push_message(t["userId"], TextSendMessage(
                            text=f"⚠️ ห้อง {p['ห้อง']} เวรวัน{today_thai} ยังไม่ได้ส่งหลักฐาน"
                        ))

@app.route("/run-check-evidence", methods=["GET"])
def run_check_evidence():
    check_missing_evidence()
    return "Check complete", 200

# ===== Routes =====
@app.route("/", methods=["GET"])
def home():
    return "ok", 200

@app.route("/webhook", methods=["POST","GET"])
def webhook():
    if request.method == "GET": return "Webhook OK", 200
    signature = request.headers.get("X-Line-Signature","")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK", 200

# ===== Handle Messages =====
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = (event.message.text or "").strip()

    # เริ่มจากพิมพ์ "โปรไฟล์"
    if text == "โปรไฟล์":
        result = get_profile_from_sheets(user_id)
        if result.get("ok") and "profile" in result:
            profile = result["profile"]
            msg = f"""คุณมีข้อมูลอยู่แล้ว:
ชื่อ: {profile.get("ชื่อ")}
ห้อง: {profile.get("ห้อง")}
เลขที่: {profile.get("เลขที่")}
เวรวัน: {profile.get("เวรวัน")}
บทบาท: {profile.get("บทบาท")}

คุณต้องการแก้ไขโปรไฟล์ไหม? (ใช่/ไม่)"""
            user_states[user_id] = {
                "step": 99,
                "role": profile.get("บทบาท"),
                "data": {"userId": user_id},
                "editing": False
            }
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        else:
            user_states[user_id] = {"step": 0, "data": {"userId": user_id}, "role": None, "editing": False}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกบทบาทของคุณ ให้พิมพ์บทบาทตามต่อไปนี้ (นักเรียน / อาจารย์ / แอดมิน):"))
        return

    # ถ้ามี state
    if user_id in user_states:
        state = user_states[user_id]
        step = state["step"]

        # ---------- ขั้นตอนแก้ไขโปรไฟล์ ----------
        if step == 99:
            answer = text.strip()
            if answer in ["ใช่", "Yes", "yes", "y", "Y"]:
                role = state["role"]
                state["editing"] = True
                if role == "นักเรียน":
                    state["step"] = 1
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่ พิมพ์ชื่อของคุณ (เช่น .ธนชัย นันทะโย.):"))
                elif role == "อาจารย์":
                    state["step"] = 10
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่ พิมพ์ชื่อของคุณ (เช่น .อาจารย์มัน.):"))
                elif role == "แอดมิน":
                    state["step"] = 21
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่ พิมพ์ชื่อของคุณ (เช่น .ธนชัย นันทะโย.):"))
            elif answer in ["ไม่", "ไม่ใช่", "No", "no", "n", "N"]:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ไม่แก้ไขโปรไฟล์"))
                del user_states[user_id]
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❓ กรุณาตอบว่า 'ใช่' หรือ 'ไม่'"))
            return

        # ---------- เลือกบทบาท ----------
        if step == 0:
            role = text
            if role not in ["นักเรียน", "อาจารย์", "แอดมิน"]:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ กรุณาพิมพ์ว่า นักเรียน / อาจารย์ / แอดมิน"))
                return
            state["role"] = role
            state["data"]["บทบาท"] = role
            if role == "นักเรียน":
                state["step"] = 1
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ พิมพ์ชื่อของคุณ (เช่น .ธนชัย นันทะโย.):"))
            elif role == "อาจารย์":
                state["step"] = 10
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ พิมพ์ชื่อของคุณ (เช่น .อาจารย์มัน.):"))
            elif role == "แอดมิน":
                state["step"] = 20
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกรหัสผ่าน:"))
            return

        # ---------- นักเรียน ----------
        if state["role"] == "นักเรียน":
            if step == 1:
                state["data"]["ชื่อ"] = text
                state["step"] = 2
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง พิมพ์ห้องของคุณ (เช่น ถ้าอยู่ห้อง5/4 ให้เขียน .54.):"))
            elif step == 2:
                state["data"]["ห้อง"] = text
                state["step"] = 3
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่ พิมพ์เลขที่ของคุณ (เช่น .8.):"))
            elif step == 3:
                state["data"]["เลขที่"] = text
                state["step"] = 4
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน พิมพ์เวรวันของคุณ (เช่น ถ้าอยู่วันพุธ ให้เขียน .พุธ.):"))
            elif step == 4:
                state["data"]["เวรวัน"] = text
                result = save_profile_to_sheets(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\n{result}"
                ))
                del user_states[user_id]
            return

        # ---------- อาจารย์ ----------
        if state["role"] == "อาจารย์":
            if step == 10:
                state["data"]["ชื่อ"] = text
                state["step"] = 11
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง พิมพ์ห้องของคุณ (เช่น ถ้าอยู่ห้อง5/4 ให้เขียน .54.):"))
            elif step == 11:
                state["data"]["ห้อง"] = text
                state["data"]["เลขที่"] = "-"
                state["data"]["เวรวัน"] = "-"
                result = save_profile_to_sheets(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\n{result}"
                ))
                del user_states[user_id]
            return

        # ---------- แอดมิน ----------
        if state["role"] == "แอดมิน":
            if step == 20:
                if text != ADMIN_PASS:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รหัสไม่ถูกต้อง"))
                    return
                state["step"] = 21
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ (เช่น .ธนชัย นันทะโย.):"))
            elif step == 21:
                state["data"]["ชื่อ"] = text
                state["step"] = 22
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง (เช่น ถ้าอยู่ห้อง5/4 ให้เขียน .54.):"))
            elif step == 22:
                state["data"]["ห้อง"] = text
                state["step"] = 23
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่ (เช่น .8.):"))
            elif step == 23:
                state["data"]["เลขที่"] = text
                state["step"] = 24
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน (เช่น ถ้าอยู่วันพุธ ให้เขียน .พุธ.):"))
            elif step == 24:
                state["data"]["เวรวัน"] = text
                result = save_profile_to_sheets(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\n{result}"
                ))
                del user_states[user_id]
            return

    # เริ่มส่งหลักฐาน
    if text == "หลักฐานการทำเวร":
        now = datetime.now(BANGKOK_TZ).strftime("%H:%M")
        if not ("00:40" <= now <= "17:00"):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ส่งได้เฉพาะเวลา 14:40 - 17:00"))
            return

        result = get_profile_from_sheets(user_id)
        if not result.get("ok"): return
        profile = result["profile"]

       # เช็คว่า role ถูกต้อง
        if profile.get("บทบาท") not in ["นักเรียน", "แอดมิน"]:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ เฉพาะนักเรียนและแอดมินเท่านั้นที่ส่งหลักฐานได้"))
            return

        today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
        r = check_duty_log(profile["ห้อง"], today)
        if r.get("found"):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ห้องนี้ส่งหลักฐานแล้ว"))
            return

        # เก็บ role ด้วย
        user_states[user_id] = {
            "step": "evidence",
            "data": profile,
            "evidence": [],
            "role": profile.get("บทบาท"),
            "editing": False
        }

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📸 กรุณาส่งรูป 3 รูปต่อไปนี้"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    if user_id not in user_states or user_states[user_id].get("step") != "evidence":
        return

    state = user_states[user_id]

    # โหลดรูปจาก LINE
    content = line_bot_api.get_message_content(event.message.id)
    img_data = b"".join([chunk for chunk in content.iter_content()])

    # แปลงเป็น base64
    img_b64 = base64.b64encode(img_data).decode("utf-8")

    # ส่ง JSON ไป Apps Script
    payload = {
        "secret": SECRET_CODE,
        "action": "uploadEvidence",
        "userId": user_id,
        "fileName": f"evidence_{len(state['evidence'])+1}.jpg",
        "fileData": img_b64
    }

    try:
        res = requests.post(APPS_SCRIPT_URL, json=payload, timeout=20)
        print("📡 Upload status:", res.status_code, res.text)
        result = res.json()
    except Exception as e:
        print("❌ Upload error:", e)
        line_bot_api.push_message(user_id, TextSendMessage(text="❌ เกิดข้อผิดพลาดตอนอัพโหลดรูป"))
        return

    if not result.get("ok"):
        line_bot_api.push_message(user_id, TextSendMessage(text="❌ อัพโหลดรูปไม่สำเร็จ: " + str(result)))
        return

    # เก็บ URL ที่ได้
    state["evidence"].append(result["url"])

    # ถ้าครบ 3 รูปแล้ว
    if len(state["evidence"]) == 3:
        today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
        log = {
            "userId": user_id,
            "ห้อง": state["data"]["ห้อง"],
            "เวรวัน": state["data"]["เวรวัน"],
            "วันที่": today,
            "เลขที่ผู้ส่ง": state["data"]["เลขที่"],
            "URL รูปที่1": state["evidence"][0],
            "URL รูปที่2": state["evidence"][1],
            "URL รูปที่3": state["evidence"][2],
            "เวลา": datetime.now(BANGKOK_TZ).strftime("%H:%M"),
            "สถานะ": "Submitted"
        }

        res = requests.post(APPS_SCRIPT_URL, json={"secret": SECRET_CODE, "action": "addDutyLog", **log})
        result = res.json()

        if result.get("ok"):
            line_bot_api.push_message(user_id, TextSendMessage(text="✅ ส่งหลักฐานครบแล้ว"))
        else:
            line_bot_api.push_message(user_id, TextSendMessage(text="❌ ห้องนี้มีการส่งไปแล้ว"))

        del user_states[user_id]


# ===== Run =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT",8000))
    app.run(host="0.0.0.0", port=port)
