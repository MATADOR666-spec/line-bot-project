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
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxHWblbbwVoNL5o8UNGlnIbBywnrWEuH-RRvfd-NKdzBkNPAD8RQaBvrcZW0sVWwoiVBg/exec"
SECRET_CODE = "my_secret_code"
ADMIN_PASS = "8264"

# ===== เก็บ state ของผู้ใช้ =====
user_states = {}  
# โครงสร้าง: { userId: {"step": int, "data": {...}, "role": str, "editing": bool} }

def save_profile_to_sheets(profile_data):
    try:
        payload = {
            "secret": SECRET_CODE,
            "userId": profile_data.get("userId"),
            "ชื่อ": profile_data.get("ชื่อ"),
            "ห้อง": profile_data.get("ห้อง"),
            "เลขที่": profile_data.get("เลขที่"),
            "เวรวัน": profile_data.get("เวรวัน"),
        }
        # ✅ ส่ง role เฉพาะตอนสมัครครั้งแรก
        if "บทบาท" in profile_data:
            payload["บทบาท"] = profile_data["บทบาท"]

        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        return r.text
    except Exception as e:
        return str(e)

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

    # เริ่มต้น: ผู้ใช้พิมพ์ "โปรไฟล์"
    if text == "โปรไฟล์":
        if user_id not in user_states:
            user_states[user_id] = {
                "step": 0,
                "data": {"userId": user_id},
                "role": None,
                "editing": False
            }
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณากรอกบทบาทของคุณ (นักเรียน / อาจารย์ / แอดมิน):")
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="คุณต้องการแก้ไขโปรไฟล์ไหม? (ใช่/ไม่ใช่)")
            )
            user_states[user_id]["step"] = 99
        return

    # ถ้ามี state
    if user_id in user_states:
        state = user_states[user_id]
        step = state["step"]

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
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ เช่น (ธนชัย นันทะโย)"))
            elif role == "อาจารย์":
                state["step"] = 10
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ เช่น (ครูสมชาย)"))
            elif role == "แอดมิน":
                state["step"] = 20
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกรหัสผ่าน:"))
            return

        # ---------- นักเรียน ----------
        if state["role"] == "นักเรียน":
            if step == 1:
                state["data"]["ชื่อ"] = text
                state["step"] = 2
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง เช่น (5/4)"))
            elif step == 2:
                state["data"]["ห้อง"] = text
                state["step"] = 3
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่ เช่น (12)"))
            elif step == 3:
                state["data"]["เลขที่"] = text
                state["step"] = 4
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน เช่น (จันทร์)"))
            elif step == 4:
                state["data"]["เวรวัน"] = text
                result = save_profile_to_sheets(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\nชื่อ: {state['data']['ชื่อ']}\nห้อง: {state['data']['ห้อง']}\nเลขที่: {state['data']['เลขที่']}\nเวรวัน: {state['data']['เวรวัน']}\nResult: {result}"
                ))
                del user_states[user_id]
            return

        # ---------- อาจารย์ ----------
        if state["role"] == "อาจารย์":
            if step == 10:
                state["data"]["ชื่อ"] = text
                state["step"] = 11
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง เช่น (5/4)"))
            elif step == 11:
                state["data"]["ห้อง"] = text
                state["data"]["เลขที่"] = "-"
                state["data"]["เวรวัน"] = "-"
                result = save_profile_to_sheets(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\nชื่อ: {state['data']['ชื่อ']}\nห้อง: {state['data']['ห้อง']}\nResult: {result}"
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
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ เช่น (สมชาย แอดมิน)"))
            elif step == 21:
                state["data"]["ชื่อ"] = text
                state["step"] = 22
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง เช่น (5/4)"))
            elif step == 22:
                state["data"]["ห้อง"] = text
                state["step"] = 23
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่ เช่น (12)"))
            elif step == 23:
                state["data"]["เลขที่"] = text
                state["step"] = 24
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน เช่น (จันทร์)"))
            elif step == 24:
                state["data"]["เวรวัน"] = text
                result = save_profile_to_sheets(state["data"])
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\nชื่อ: {state['data']['ชื่อ']}\nห้อง: {state['data']['ห้อง']}\nเลขที่: {state['data']['เลขที่']}\nเวรวัน: {state['data']['เวรวัน']}\nResult: {result}"
                ))
                del user_states[user_id]
            return

        # ---------- แก้ไขโปรไฟล์ ----------
        if step == 99:
            if text == "ใช่":
                role = state["role"]
                state["editing"] = True
                if role == "นักเรียน":
                    state["step"] = 1
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่:"))
                elif role == "อาจารย์":
                    state["step"] = 10
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่:"))
                elif role == "แอดมิน":
                    state["step"] = 21
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่:"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ไม่แก้ไขโปรไฟล์"))
                del user_states[user_id]
            return

    # ถ้าไม่มี state เลย
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="พิมพ์ 'โปรไฟล์' เพื่อเริ่มตั้งค่า")
    )

# ===== Run =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
