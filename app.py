import os
import gspread
import requests
import pytz
import schedule
import threading
import time
from datetime import datetime
from flask import Flask, request, abort, render_template
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from oauth2client.service_account import ServiceAccountCredentials

# ===== CONFIG =====
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
DOMAIN = os.getenv("DOMAIN", "https://line-bot-project-hjaq.onrender.com")
ADMIN_PASS = "8264"
BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise ValueError("Missing LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
app = Flask(__name__)

profiles = profiles_ws.get_all_records()
room = state["data"]["ห้อง"]

# ===== GOOGLE SHEETS =====
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gc = gspread.authorize(creds)
SHEET = gc.open("DutyBot")
profiles_ws = SHEET.worksheet("profiles")
duty_ws = SHEET.worksheet("duty_logs")
holidays_ws = SHEET.worksheet("holidays")

user_states = {}

# ===== FLASK ROUTES =====
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/profiles/view")
def view_profiles():
    rows = profiles_ws.get_all_records()
    return render_template("profiles.html", profiles=rows)

@app.route("/duty-logs/view")
def view_duty_logs():
    rows = duty_ws.get_all_records()
    return render_template("duty_logs.html", logs=rows)

@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK", 200

# ===== HELPERS =====
def today_str():
    return datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")

def now_time():
    return datetime.now(BANGKOK_TZ).strftime("%H:%M:%S")

def weekday_th():
    days = {
        "Monday": "จันทร์", "Tuesday": "อังคาร", "Wednesday": "พุธ",
        "Thursday": "พฤหัสบดี", "Friday": "ศุกร์",
        "Saturday": "เสาร์", "Sunday": "อาทิตย์"
    }
    eng = datetime.now(BANGKOK_TZ).strftime("%A")
    return days[eng]

def is_holiday():
    today = today_str()
    holidays = [row["date"] for row in holidays_ws.get_all_records()]
    return today in holidays or weekday_th() in ["เสาร์", "อาทิตย์"]

def check_missing_evidence():
    today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
    weekday = datetime.now(BANGKOK_TZ).strftime("%A")
    today_thai = {"Monday":"จันทร์","Tuesday":"อังคาร","Wednesday":"พุธ","Thursday":"พฤหัสบดี","Friday":"ศุกร์"}.get(weekday)
    if not today_thai:
        return


# ===== LINE MESSAGE HANDLER =====
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = (event.message.text or "").strip()

    # === START PROFILE ===
    if text == "โปรไฟล์":
        records = profiles_ws.get_all_records()
        profile = next((r for r in records if r["userId"] == user_id), None)
        if profile:
            msg = f"""คุณมีข้อมูลอยู่แล้ว:
ชื่อ: {profile['ชื่อ']}
ห้อง: {profile['ห้อง']}
เลขที่: {profile['เลขที่']}
เวรวัน: {profile['เวรวัน']}
บทบาท: {profile['บทบาท']}

คุณต้องการแก้ไขโปรไฟล์ไหม? (ใช่/ไม่)"""
            user_states[user_id] = {"step": 99, "role": profile["บทบาท"], "editing": False}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        else:
            user_states[user_id] = {"step": 0, "data": {"userId": user_id}}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกบทบาท (นักเรียน/อาจารย์/แอดมิน):"))
        return

    # === HANDLE PROFILE STATES ===
    if user_id in user_states:
        state = user_states[user_id]
        step = state["step"]

        if step == 0:  # เลือกบทบาท
            role = text
            if role not in ["นักเรียน", "อาจารย์", "แอดมิน"]:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ กรุณาพิมพ์ว่า นักเรียน / อาจารย์ / แอดมิน"))
                return
            state["role"] = role
            state["data"]["บทบาท"] = role
            if role == "นักเรียน":
                state["step"] = 1
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ:"))
            elif role == "อาจารย์":
                state["step"] = 10
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ:"))
            elif role == "แอดมิน":
                state["step"] = 20
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกรหัสผ่าน:"))
            return

        # --- นักเรียน --- #
        if state["role"] == "นักเรียน":
            if step == 1:
                state["data"]["ชื่อ"] = text
                state["step"] = 2
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            elif step == 2:
                state["data"]["ห้อง"] = text
                state["step"] = 3
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่:"))
            elif step == 3:
                state["data"]["เลขที่"] = text
                state["step"] = 4
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน:"))
            elif step == 4:
                state["data"]["เวรวัน"] = text
                state["data"]["วันที่สมัคร"] = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
                state["data"]["สถานะ"] = "Active"
                save_profile(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกข้อมูลเรียบร้อย"))
                del user_states[user_id]
            return

        # --- อาจารย์ --- #
        if state["role"] == "อาจารย์":
            if step == 10:
                state["data"]["ชื่อ"] = text
                state["step"] = 11
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            elif step == 11:
                state["data"]["ห้อง"] = text
                state["data"]["เลขที่"] = "-"
                state["data"]["เวรวัน"] = "-"
                state["data"]["วันที่สมัคร"] = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
                state["data"]["สถานะ"] = "Active"
                save_profile(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกข้อมูลเรียบร้อย"))
                del user_states[user_id]
            return

        # --- แอดมิน --- #
        if state["role"] == "แอดมิน":
            if step == 20:
                if text != ADMIN_PASS:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รหัสไม่ถูกต้อง"))
                    return
                state["step"] = 21
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ:"))
            elif step == 21:
                state["data"]["ชื่อ"] = text
                state["step"] = 22
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            elif step == 22:
                state["data"]["ห้อง"] = text
                state["step"] = 23
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่:"))
            elif step == 23:
                state["data"]["เลขที่"] = text
                state["step"] = 24
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน:"))
            elif step == 24:
                state["data"]["เวรวัน"] = text
                state["data"]["วันที่สมัคร"] = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
                state["data"]["สถานะ"] = "Active"
                save_profile(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกข้อมูลเรียบร้อย"))
                del user_states[user_id]
            return
    
    # === DUTY SUBMISSION ===
    if text == "หลักฐานการทำเวร":
        records = profiles_ws.get_all_records()
        profile = next((r for r in records if r["userId"] == user_id), None)
        if not profile:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ กรุณาลงทะเบียนโปรไฟล์ก่อน"))
            return

        # ตรวจสอบวันเวลา
        if is_holiday() or profile["เวรวัน"] != weekday_th():
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="วันนี้ไม่ใช่วันเวรของคุณ"))
            return

        now_hhmm = datetime.now(BANGKOK_TZ).strftime("%H:%M")
        if not ("14:40" <= now_hhmm <= "17:00"):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⏰ สามารถส่งได้เฉพาะ 14:40–17:00"))
            return

        # ตรวจสอบว่าส่งแล้วหรือยัง
        duty_today = duty_ws.get_all_records()
        if any(r["ห้อง"] == profile["ห้อง"] and r["วันที่"] == today_str() for r in duty_today):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ห้องนี้ส่งหลักฐานไปแล้ว"))
            return

        # เก็บ state
        user_states[user_id] = {"step": 200, "images": [], "profile": profile}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📷 กรุณาส่งรูป 3 รูป (ทีละรูป)"))
        return

    # === HANDLE IMAGES ===
    if event.message.type == "image" and user_id in user_states:
        state = user_states[user_id]
        if state["step"] == 200:
            message_content = line_bot_api.get_message_content(event.message.id)
            file_path = f"static/uploads/{event.message.id}.jpg"
            with open(file_path, "wb") as f:
                for chunk in message_content.iter_content():
                    f.write(chunk)

            content_url = f"{DOMAIN}/{file_path}"
            state["images"].append(content_url)

            if len(state["images"]) < 3:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"📷 ได้รับรูป {len(state['images'])}/3 กรุณาส่งต่อ"))
            else:
                p = state["profile"]
                duty_ws.append_row([
                    today_str(), p["ห้อง"], p["เวรวัน"], p["เลขที่"],
                    state["images"][0], state["images"][1], state["images"][2],
                    now_time(), "ส่งแล้ว", p["userId"]
                ])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ส่งหลักฐานเรียบร้อยแล้ว"))

                # แจ้งอาจารย์
                teachers = [r for r in profiles_ws.get_all_records() if r["บทบาท"] == "อาจารย์" and r["ห้อง"] == p["ห้อง"]]
                for t in teachers:
                    line_bot_api.push_message(t["userId"], TextSendMessage(
                        text=f"📢 ห้อง {p['ห้อง']} ส่งหลักฐานเวรแล้ว ตรวจสอบได้ที่ {DOMAIN}/duty-logs/view"
                    ))

                del user_states[user_id]
        return

# ===== SCHEDULER (แจ้งเตือน) =====
def job_notify():
    if is_holiday():
        return
    today = weekday_th()
    students = [r for r in profiles_ws.get_all_records() if r["เวรวัน"] == today and r["บทบาท"] == "นักเรียน"]
    for s in students:
        line_bot_api.push_message(s["userId"], TextSendMessage(text=f"📢 วันนี้เป็นวันเวรของคุณ ({today}) อย่าลืมทำเวร!"))

schedule.every().day.at("15:20").do(job_notify)
schedule.every().day.at("15:30").do(job_notify)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(1)

threading.Thread(target=run_schedule, daemon=True).start()

for p in profiles:
    if p["บทบาท"] == "อาจารย์" and p["ห้อง"] == room:
        line_bot_api.push_message(
            p["userId"],
            TextSendMessage(
                text=f"📢 ห้อง {room} ส่งหลักฐานเรียบร้อยแล้ว\nตรวจสอบได้ที่: {domain}/duty-logs/view"
            )
        )

def check_missing_evidence():
    today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
    weekday = datetime.now(BANGKOK_TZ).strftime("%A")
    today_thai = {
        "Monday": "จันทร์",
        "Tuesday": "อังคาร",
        "Wednesday": "พุธ",
        "Thursday": "พฤหัสบดี",
        "Friday": "ศุกร์"
    }.get(weekday)

    if not today_thai:
        return

    # ดึงข้อมูล profiles
    profiles = profiles_ws.get_all_records()

    for p in profiles:
        if p["เวรวัน"] == today_thai and p["บทบาท"] == "นักเรียน":
            room = p["ห้อง"]

            # เช็คว่า duty log วันนี้มีคนส่งแล้วหรือยัง
            logs = duty_logs_ws.get_all_records()
            found = any(
                l["ห้อง"] == room and l["วันที่"] == today
                for l in logs
            )

            if not found:
                # แจ้งอาจารย์ของห้องนี้
                for t in profiles:
                    if t["บทบาท"] == "อาจารย์" and t["ห้อง"] == room:
                        line_bot_api.push_message(
                            t["userId"],
                            TextSendMessage(
                                text=f"⚠️ ห้อง {room} เวรวัน{today_thai} ยังไม่ได้ส่งหลักฐาน"
                            )
                        )

@app.route("/run-check-evidence", methods=["GET"])
def run_check_evidence():
    check_missing_evidence()
    return "Check complete", 200
        

# ===== MAIN =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
