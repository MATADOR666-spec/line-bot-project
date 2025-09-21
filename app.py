import os
import requests
from flask import Flask, request, jsonify, render_template
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage
from datetime import datetime, time
import pytz
import sqlite3

DB_NAME = "data.db"

def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv


# ===== LINE Config =====
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

app = Flask(__name__)
BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

# ===== Google Sheets API (Apps Script endpoint) =====
SHEET_API_URL = os.getenv("SHEET_API_URL", "https://script.google.com/macros/s/AKfycbwHNNOqy2QPycsroR_soj1JQeiENC-AtxMDLtJiAiLoj9g6T22qOBtk9j9nCq34Lprjxw/exec")
ADMIN_PASS = "8264"

# ===== Helper =====
def get_profiles():
    try:
        r = requests.get(SHEET_API_URL)
        print("status:", r.status_code)
        print("response text:", r.text)  # 👈 log เพื่อตรวจว่า API ส่งอะไรจริง ๆ
        if r.status_code == 200:
            return r.json().get("profiles", [])
    except Exception as e:
        print("get_profiles error:", e)
    return []


def is_holiday(date_str):
    try:
        r = requests.get(f"{SHEET_API_URL}?sheet=Holidays")
        if r.status_code != 200:
            return False
        holidays = r.json().get("data", [])
        return any(h["วันที่"] == date_str for h in holidays)
    except:
        return False

def save_profile(profile_data):
    profile_data["secret"] = "my_secret_code"  # ต้องตรงกับ SECRET ใน Apps Script
    r = requests.post(SHEET_API_URL, json=profile_data)
    print("save_profile request:", profile_data)
    print("save_profile response:", r.text)
    return r.json()




# ===== Routes =====
@app.route("/")
def index():
    return render_template("duty_logs.html")

@app.route("/duty-logs/view")
def view_duty_logs():
    rows = query_db("SELECT * FROM duty_logs ORDER BY วันที่ DESC, เวลา DESC")
    logs = [dict(r) for r in rows]
    return render_template("duty_logs.html", logs=logs)

@app.route("/schedule")
def schedule():
    return render_template("schedule.html")

# ===== Webhook =====
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return "OK"

# เก็บ state การสนทนา
user_states = {}

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    profiles = get_profiles()
    profile = next((p for p in profiles if p["userId"] == user_id), None)

    # ========== ดูโปรไฟล์ ==========
    if text == "โปรไฟล์":
        if profile:
            msg = f"""📌 โปรไฟล์ของคุณ:
ชื่อ: {profile['ชื่อ']}
ห้อง: {profile['ห้อง']}
เลขที่: {profile['เลขที่']}
เวรวัน: {profile['เวรวัน']}
บทบาท: {profile['บทบาท']}

คุณต้องการแก้ไขโปรไฟล์ไหม? (ใช่/ไม่)"""
            user_states[user_id] = {"step": "edit_confirm", "profile": profile}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=msg))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text="ยังไม่มีข้อมูลในระบบ ❌\nกรุณากรอกบทบาทของคุณ (นักเรียน / อาจารย์ / แอดมิน):"))
            user_states[user_id] = {"step": "choose_role", "data": {"userId": user_id}}
        return

    # ========== สมัครโปรไฟล์ ==========
    if user_id in user_states:
        state = user_states[user_id]
        step = state["step"]

        # --- เลือกบทบาท ---
        if step == "choose_role":
            if text not in ["นักเรียน", "อาจารย์", "แอดมิน"]:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณาพิมพ์ว่า นักเรียน / อาจารย์ / แอดมิน เท่านั้น"))
                return

            state["data"]["บทบาท"] = text
            if text == "นักเรียน":
                state["step"] = "student_name"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ:"))
            elif text == "อาจารย์":
                state["step"] = "teacher_name"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อ:"))
            elif text == "แอดมิน":
                state["step"] = "admin_pass"
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกรหัสผ่าน:"))
            return

        # --- แอดมินตรวจสอบรหัส ---
        if step == "admin_pass":
            if text != ADMIN_PASS:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ รหัสผ่านไม่ถูกต้อง"))
                return
            state["step"] = "student_name"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="รหัสถูกต้อง ✅\nกรุณากรอกชื่อ:"))
            return

        # --- นักเรียน / แอดมิน ---
        if step == "student_name":
            state["data"]["ชื่อ"] = text
            state["step"] = "student_room"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            return

        if step == "student_room":
            state["data"]["ห้อง"] = text
            state["step"] = "student_number"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเลขที่:"))
            return

        if step == "student_number":
            state["data"]["เลขที่"] = text
            state["step"] = "student_dutyday"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกเวรวัน (จันทร์-ศุกร์):"))
            return

        if step == "student_dutyday":
            state["data"]["เวรวัน"] = text
            state["data"]["วันที่สมัคร"] = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
            state["data"]["สถานะ"] = "Active"
            save_profile(state["data"])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกโปรไฟล์เรียบร้อยแล้ว"))
            del user_states[user_id]
            return

        # --- อาจารย์ ---
        if step == "teacher_name":
            state["data"]["ชื่อ"] = text
            state["step"] = "teacher_room"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            return

        if step == "teacher_room":
            state["data"]["ห้อง"] = text
            state["data"]["เลขที่"] = "-"
            state["data"]["เวรวัน"] = "-"
            state["data"]["วันที่สมัคร"] = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
            state["data"]["สถานะ"] = "Active"
            save_profile(state["data"])
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกโปรไฟล์เรียบร้อยแล้ว"))
            del user_states[user_id]
            return

        # --- แก้ไขโปรไฟล์ ---
        if step == "edit_confirm":
            if text.lower() in ["ใช่", "yes", "y"]:
                role = state["profile"]["บทบาท"]
                if role == "นักเรียน" or role == "แอดมิน":
                    state["step"] = "student_name"
                    state["data"] = {"userId": user_id, "บทบาท": role}
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่:"))
                elif role == "อาจารย์":
                    state["step"] = "teacher_name"
                    state["data"] = {"userId": user_id, "บทบาท": role}
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกชื่อใหม่:"))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ยกเลิกการแก้ไขโปรไฟล์"))
                del user_states[user_id]
            return
    
    # เริ่มต้นส่ง
    if text == "หลักฐานการทำเวร":
        profile = next((p for p in profiles if p["userId"] == user_id), None)
        if not profile:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ กรุณาลงทะเบียนโปรไฟล์ก่อน"))
            return

        today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
        today_thai = {
            "Monday": "จันทร์", "Tuesday": "อังคาร", "Wednesday": "พุธ",
            "Thursday": "พฤหัสบดี", "Friday": "ศุกร์"
        }.get(datetime.now(BANGKOK_TZ).strftime("%A"))

    # ไม่ตรงเวรวัน
        if profile["เวรวัน"] != today_thai:
            line_bot_api.reply_message(event.reply_token,
                TextSendMessage(text=f"❌ วันนี้ไม่ใช่วันเวรของคุณ (เวรวัน {profile['เวรวัน']})"))
            return

    # เวลา
        now = datetime.now(BANGKOK_TZ).strftime("%H:%M")
        if not ("14:40" <= now <= "17:00"):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ส่งได้เฉพาะเวลา 14:40–17:00"))
            return

    # เช็คส่งแล้ว
        row = query_db("SELECT * FROM duty_logs WHERE ห้อง=? AND วันที่=?", (profile["ห้อง"], today), one=True)
        if row:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ ห้องนี้ส่งหลักฐานแล้ว"))
            return

    # ให้ user ส่งรูป
        user_states[user_id] = {"step": "send_evidence", "data": profile, "images": []}
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📷 กรุณาส่งรูปภาพ 3 รูป (ทีละรูป)"))

@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    if user_id not in user_states or user_states[user_id]["step"] != "send_evidence":
        return

    state = user_states[user_id]
    os.makedirs("static/uploads", exist_ok=True)

    # โหลดไฟล์จาก LINE
    message_content = line_bot_api.get_message_content(event.message.id)
    file_path = f"static/uploads/{event.message.id}.jpg"
    with open(file_path, "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    # gen URL
    domain = os.getenv("DOMAIN", "https://line-bot-project-hjaq.onrender.com")
    url = f"{domain}/{file_path}"
    state["images"].append(url)

    # ถ้ายังไม่ครบ
    if len(state["images"]) < 3:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(
            text=f"📸 ได้รับแล้ว {len(state['images'])}/3 กรุณาส่งต่อ"))
        return

    # ครบ 3 → บันทึก DB
    query_db("""INSERT INTO duty_logs
        (userId, วันที่, ห้อง, เวรวัน, เลขที่ผู้ส่ง, url1, url2, url3, เวลา, สถานะ)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d"),
            state["data"]["ห้อง"],
            state["data"]["เวรวัน"],
            state["data"]["เลขที่"],
            state["images"][0], state["images"][1], state["images"][2],
            datetime.now(BANGKOK_TZ).strftime("%H:%M"),
            "ส่งแล้ว"
        )
    )

    # แจ้งอาจารย์
    teachers = query_db("SELECT * FROM profiles WHERE ห้อง=? AND บทบาท='อาจารย์'", (state["data"]["ห้อง"],))
    for t in teachers:
        line_bot_api.push_message(
            t["userId"],
            TextSendMessage(text=f"✅ ห้อง {state['data']['ห้อง']} เวรวัน{state['data']['เวรวัน']} ส่งหลักฐานครบแล้ว\nดูได้ที่ {domain}/duty-logs/view")
        )

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ ส่งหลักฐานครบแล้ว"))
    del user_states[user_id]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)