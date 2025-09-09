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

def get_profile_from_sheets(user_id):
    try:
        payload = {"secret": SECRET_CODE, "action": "getProfile", "userId": user_id}
        print("DEBUG: ส่ง request getProfile ->", payload)
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        print("DEBUG: ตอบกลับจาก Apps Script getProfile =", r.text)
        return r.json()
    except Exception as e:
        print("ERROR: get_profile_from_sheets =", e)
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
        }
        if "บทบาท" in profile_data:
            payload["บทบาท"] = profile_data["บทบาท"]

        print("DEBUG: ส่ง request addProfile ->", payload)
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=10)
        print("DEBUG: ตอบกลับจาก Apps Script addProfile =", r.text)
        return r.text
    except Exception as e:
        print("ERROR: save_profile_to_sheets =", e)
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

    print("DEBUG: webhook called, body =", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("ERROR: InvalidSignatureError")
        abort(400)
    return "OK", 200

# ===== Handle Messages =====
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = (event.message.text or "").strip()

    print(f"DEBUG: รับข้อความจาก {user_id} -> {text}")

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

คุณต้องการแก้ไขโปรไฟล์ไหม? (ใช่/ไม่ใช่)"""
            user_states[user_id] = {"step": 99, "role": profile.get("บทบาท"), "data": {"userId": user_id}}
            print("DEBUG: ผู้ใช้มีโปรไฟล์แล้ว -> step=99, role=", profile.get("บทบาท"))
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        else:
            user_states[user_id] = {"step": 0, "data": {"userId": user_id}, "role": None, "editing": False}
            print("DEBUG: ผู้ใช้ยังไม่มีโปรไฟล์ -> step=0")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="กรุณากรอกบทบาทของคุณ (นักเรียน / อาจารย์ / แอดมิน):")
            )
        return

    # ถ้ามี state
    if user_id in user_states:
        state = user_states[user_id]
        step = state["step"]
        print(f"DEBUG: state[{user_id}] =", state)

        # ---------- เลือกบทบาท ----------
        if step == 0:
            role = text
            if role not in ["นักเรียน", "อาจารย์", "แอดมิน"]:
                print("DEBUG: กรอกบทบาทผิด =", role)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ กรุณาพิมพ์ว่า นักเรียน / อาจารย์ / แอดมิน"))
                return
            state["role"] = role
            state["data"]["บทบาท"] = role
            print("DEBUG: เลือกบทบาท =", role)
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

        # ---------- นักเรียน ----------
        if state["role"] == "นักเรียน":
            if step == 1:
                state["data"]["ชื่อ"] = text
                state["step"] = 2
                print("DEBUG: กรอกชื่อ =", text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            elif step == 2:
                state["data"]["ห้อง"] = text
                state["step"] = 3
                print("DEBUG: กรอกห้อง =", text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่:"))
            elif step == 3:
                state["data"]["เลขที่"] = text
                state["step"] = 4
                print("DEBUG: กรอกเลขที่ =", text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน:"))
            elif step == 4:
                state["data"]["เวรวัน"] = text
                print("DEBUG: กรอกเวรวัน =", text)
                result = save_profile_to_sheets(state["data"])
                print("DEBUG: บันทึกโปรไฟล์แล้ว =", result)
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
                print("DEBUG: อาจารย์กรอกชื่อ =", text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            elif step == 11:
                state["data"]["ห้อง"] = text
                state["data"]["เลขที่"] = "-"
                state["data"]["เวรวัน"] = "-"
                print("DEBUG: อาจารย์กรอกห้อง =", text)
                result = save_profile_to_sheets(state["data"])
                print("DEBUG: บันทึกโปรไฟล์ครู =", result)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\nชื่อ: {state['data']['ชื่อ']}\nห้อง: {state['data']['ห้อง']}\nResult: {result}"
                ))
                del user_states[user_id]
            return

        # ---------- แอดมิน ----------
        if state["role"] == "แอดมิน":
            if step == 20:
                if text != ADMIN_PASS:
                    print("DEBUG: รหัสแอดมินผิด =", text)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รหัสไม่ถูกต้อง"))
                    return
                state["step"] = 21
                print("DEBUG: รหัสแอดมินถูกต้อง")
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ:"))
            elif step == 21:
                state["data"]["ชื่อ"] = text
                state["step"] = 22
                print("DEBUG: แอดมินกรอกชื่อ =", text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            elif step == 22:
                state["data"]["ห้อง"] = text
                state["step"] = 23
                print("DEBUG: แอดมินกรอกห้อง =", text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่:"))
            elif step == 23:
                state["data"]["เลขที่"] = text
                state["step"] = 24
                print("DEBUG: แอดมินกรอกเลขที่ =", text)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน:"))
            elif step == 24:
                state["data"]["เวรวัน"] = text
                print("DEBUG: แอดมินกรอกเวรวัน =", text)
                result = save_profile_to_sheets(state["data"])
                print("DEBUG: บันทึกโปรไฟล์แอดมิน =", result)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(
                    text=f"✅ บันทึกข้อมูลเรียบร้อย\nชื่อ: {state['data']['ชื่อ']}\nห้อง: {state['data']['ห้อง']}\nเลขที่: {state['data']['เลขที่']}\nเวรวัน: {state['data']['เวรวัน']}\nResult: {result}"
                ))
                del user_states[user_id]
            return

        # ---------- แก้ไขโปรไฟล์ ----------
        if step == 99:
            print("DEBUG: เข้าสู่ขั้นตอนแก้ไขโปรไฟล์, ข้อความที่ได้รับ =", text)
            answer = text.strip()
            if answer in ["ใช่", "Yes", "yes", "y", "Y"]:
                print("DEBUG: ผู้ใช้เลือก 'ใช่' -> เริ่มแก้ไข role =", state.get("role"))
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
            elif answer in ["ไม่", "ไม่ใช่", "No", "no", "n", "N"]:
                print("DEBUG: ผู้ใช้เลือก 'ไม่' -> ไม่แก้ไข")
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ไม่แก้ไขโปรไฟล์"))
                del user_states[user_id]
            else:
                print("DEBUG: ผู้ใช้ตอบไม่ตรง ->", answer)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❓ กรุณาตอบว่า 'ใช่' หรือ 'ไม่'"))
            return

    # ถ้าไม่มี state
    print("DEBUG: ไม่มี state -> ตอบกลับ default")
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="พิมพ์ 'โปรไฟล์' เพื่อเริ่มตั้งค่า")
    )

# ===== Run =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("DEBUG: เริ่มรัน Flask ที่ port", port)
    app.run(host="0.0.0.0", port=port)
