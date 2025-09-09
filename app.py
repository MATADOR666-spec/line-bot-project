import os
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# ===== LINE Bot Config =====
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise ValueError("Missing LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

app = Flask(__name__)

# ===== Google Apps Script Config =====
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxPHd662S-mygVh3mDRkR3YCF2RBnjlboCnJymaXh254CpX5WR29DBijVKdCiXZVTgVAw/exec"
SECRET_CODE = "my_secret_code"
ADMIN_PASS = "8264"

# ===== เก็บ state ของผู้ใช้ =====
user_states = {}  
# { userId: {"step": int, "data": {...}, "role": str, "editing": bool} }

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
        payload = {
            "secret": SECRET_CODE,
            "action": "addProfile",
            "userId": profile_data.get("userId"),
            "ชื่อ": profile_data.get("ชื่อ"),
            "ห้อง": profile_data.get("ห้อง"),
            "เลขที่": profile_data.get("เลขที่"),
            "เวรวัน": profile_data.get("เวรวัน"),
            "บทบาท": profile_data.get("บทบาท"),
        }
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ===== Routes =====
@app.route("/", methods=["GET"])
def home():
    return "ok", 200

@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return "Webhook OK", 200

    signature = request.headers.get("X-Line-Signature", "")
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
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกบทบาทของคุณ (นักเรียน / อาจารย์ / แอดมิน):"))
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
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่ (เช่น .ธนชัย นันทะโย.):"))
                elif role == "อาจารย์":
                    state["step"] = 10
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่ (เช่น .อาจารย์มัน.):"))
                elif role == "แอดมิน":
                    state["step"] = 21
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่ (เช่น .ธนชัย นันทะโย.):"))
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
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ (เช่น .ธนชัย นันทะโย.):"))
            elif role == "อาจารย์":
                state["step"] = 10
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ (เช่น .อาจารย์มัน.):"))
            elif role == "แอดมิน":
                state["step"] = 20
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกรหัสผ่าน:"))
            return

        # ---------- นักเรียน ----------
        if state["role"] == "นักเรียน":
            if step == 1:
                state["data"]["ชื่อ"] = text
                state["step"] = 2
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง (เช่น ถ้าอยู่ห้อง5/4 ให้เขียน .54.):"))
            elif step == 2:
                state["data"]["ห้อง"] = text
                state["step"] = 3
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่ (เช่น .8.):"))
            elif step == 3:
                state["data"]["เลขที่"] = text
                state["step"] = 4
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน (เช่น ถ้าอยู่วันพุธ ให้เขียน .พุธ.):"))
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
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง (เช่น ถ้าอยู่ห้อง5/4 ให้เขียน .54.):"))
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

    # ถ้าไม่มี state และไม่พิมพ์ "โปรไฟล์"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="")
    )

# ===== Run =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
