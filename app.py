import os
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, abort, jsonify, render_template
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import pytz

# ===== LINE Bot Config =====
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
BANGKOK_TZ = pytz.timezone("Asia/Bangkok")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise ValueError("Missing LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

app = Flask(__name__)

DB_NAME = "data.db"
ADMIN_PASS = "8264"
user_states = {}   # เก็บ state ของผู้ใช้

# ===== DB Helper =====
def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        userId TEXT PRIMARY KEY,
        ชื่อ TEXT,
        ห้อง TEXT,
        เลขที่ TEXT,
        บทบาท TEXT,
        เวรวัน TEXT,
        วันที่สมัคร TEXT,
        สถานะ TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS duty_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        userId TEXT,
        วันที่ TEXT,
        ห้อง TEXT,
        เวรวัน TEXT,
        เลขที่ผู้ส่ง TEXT,
        url1 TEXT,
        url2 TEXT,
        url3 TEXT,
        เวลา TEXT,
        สถานะ TEXT
    )
    """)

    conn.commit()
    conn.close()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/profiles/view")
def view_profiles():
    rows = query_db("SELECT * FROM profiles")
    profiles = [dict(r) for r in rows]
    return render_template("profiles.html", profiles=profiles)

@app.route("/duty-logs/view")
def view_duty_logs():
    rows = query_db("SELECT * FROM duty_logs ORDER BY วันที่ DESC")
    logs = [dict(r) for r in rows]
    return render_template("duty_logs.html", logs=logs)

@app.route("/init-db")
def init_database():
    init_db()
    return "DB initialized", 200


# ===== API Routes =====
@app.route("/profiles", methods=["GET"])
def get_profiles():
    rows = query_db("SELECT * FROM profiles")
    profiles = [dict(r) for r in rows]
    return jsonify({"ok": True, "profiles": profiles})

@app.route("/profiles/<userId>", methods=["GET"])
def get_profile(userId):
    row = query_db("SELECT * FROM profiles WHERE userId=?", (userId,), one=True)
    if row:
        return jsonify({"ok": True, "profile": dict(row)})
    return jsonify({"ok": False, "error": "Not found"})

@app.route("/profiles", methods=["POST"])
def add_profile():
    data = request.json
    query_db("""INSERT OR REPLACE INTO profiles
        (userId, ชื่อ, ห้อง, เลขที่, บทบาท, เวรวัน, วันที่สมัคร, สถานะ)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["userId"], data["ชื่อ"], data["ห้อง"], data["เลขที่"],
            data["บทบาท"], data["เวรวัน"],
            datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d"),
            "Active"
        )
    )
    return jsonify({"ok": True, "msg": "Profile saved"})

@app.route("/duty-logs", methods=["GET"])
def get_duty_logs():
    rows = query_db("SELECT * FROM duty_logs ORDER BY วันที่ DESC")
    logs = [dict(r) for r in rows]
    return jsonify({"ok": True, "logs": logs})

@app.route("/duty-logs", methods=["POST"])
def add_duty_log():
    data = request.json
    today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")

    # เช็คว่าห้องนี้มีการส่งแล้วหรือยัง
    row = query_db("SELECT * FROM duty_logs WHERE ห้อง=? AND วันที่=?",
                   (data["ห้อง"], today), one=True)
    if row:
        return jsonify({"ok": False, "error": "already submitted"})

    query_db("""INSERT INTO duty_logs
        (userId, วันที่, ห้อง, เวรวัน, เลขที่ผู้ส่ง, url1, url2, url3, เวลา, สถานะ)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["userId"], today, data["ห้อง"], data["เวรวัน"], data["เลขที่"],
            data.get("url1",""), data.get("url2",""), data.get("url3",""),
            datetime.now(BANGKOK_TZ).strftime("%H:%M:%S"),
            "ส่งแล้ว"
        )
    )
    return jsonify({"ok": True, "msg": "Duty log saved"})

# ===== LINE Webhook =====
@app.route("/webhook", methods=["POST"])
def webhook():
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
        row = query_db("SELECT * FROM profiles WHERE userId=?", (user_id,), one=True)
        if row:
            profile = dict(row)
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
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text="กรุณากรอกบทบาทของคุณ (นักเรียน / อาจารย์ / แอดมิน):"))
        return

    # มี state อยู่แล้ว → กำลังสมัคร
    if user_id in user_states:
        state = user_states[user_id]
        step = state["step"]

        # ---------- แก้ไขโปรไฟล์ ----------
        if step == 99:
            if text in ["ใช่","Yes","yes"]:
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
                query_db("""INSERT OR REPLACE INTO profiles
                    (userId, ชื่อ, ห้อง, เลขที่, บทบาท, เวรวัน, วันที่สมัคร, สถานะ)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id, state["data"]["ชื่อ"], state["data"]["ห้อง"], state["data"]["เลขที่"],
                        "นักเรียน", state["data"]["เวรวัน"],
                        datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d"), "Active"
                    )
                )
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกข้อมูลเรียบร้อย"))
                del user_states[user_id]
            return

        # ---------- อาจารย์ ----------
        if state["role"] == "อาจารย์":
            if step == 10:
                state["data"]["ชื่อ"] = text
                state["step"] = 11
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="กรุณากรอกห้อง:"))
            elif step == 11:
                state["data"]["ห้อง"] = text
                query_db("""INSERT OR REPLACE INTO profiles
                    (userId, ชื่อ, ห้อง, เลขที่, บทบาท, เวรวัน, วันที่สมัคร, สถานะ)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id, state["data"]["ชื่อ"], state["data"]["ห้อง"], "-", "อาจารย์", "-",
                        datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d"), "Active"
                    )
                )
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกข้อมูลเรียบร้อย"))
                del user_states[user_id]
            return

        # ---------- แอดมิน ----------
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
                query_db("""INSERT OR REPLACE INTO profiles
                    (userId, ชื่อ, ห้อง, เลขที่, บทบาท, เวรวัน, วันที่สมัคร, สถานะ)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        user_id, state["data"]["ชื่อ"], state["data"]["ห้อง"], state["data"]["เลขที่"],
                        "แอดมิน", state["data"]["เวรวัน"],
                        datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d"), "Active"
                    )
                )
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ บันทึกข้อมูลเรียบร้อย"))
                del user_states[user_id]
            return

    # ผู้ใช้สั่ง "หลักฐานการทำเวร"
    if text == "หลักฐานการทำเวร":
        profile = query_db("SELECT * FROM profiles WHERE userId=?", (user_id,), one=True)
        if not profile:
            line_bot_api.reply_message(event.reply_token,
                TextSendMessage(text="❌ กรุณาลงทะเบียนโปรไฟล์ก่อน"))
            return

        today = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")
        weekday = datetime.now(BANGKOK_TZ).strftime("%A")  # Monday, Tuesday,...

        # เช็คว่าเวรวันตรงกับวันนี้หรือไม่
        if profile["เวรวัน"] not in ["จันทร์","อังคาร","พุธ","พฤหัสบดี","ศุกร์"]:
            line_bot_api.reply_message(event.reply_token,
                TextSendMessage(text="วันนี้ไม่ใช่วันเวรของคุณ"))
            return

        # เช็คว่ามีการส่งแล้วหรือยัง
        row = query_db("SELECT * FROM duty_logs WHERE ห้อง=? AND วันที่=?",
                       (profile["ห้อง"], today), one=True)
        if row:
            line_bot_api.reply_message(event.reply_token,
                TextSendMessage(text="❌ ห้องนี้ส่งหลักฐานไปแล้ว"))
            return

        # ให้ user ส่งรูป 3 รูป
        user_states[user_id] = {
            "step": 200,
            "data": {
                "userId": user_id,
                "ห้อง": profile["ห้อง"],
                "เวรวัน": profile["เวรวัน"],
                "เลขที่": profile["เลขที่"]
            },
            "images": []
        }
        line_bot_api.reply_message(event.reply_token,
            TextSendMessage(text="กรุณาส่งรูปภาพ 3 รูป (ทีละรูป)"))
        return

    # รับรูปภาพจาก user กรณีส่งหลักฐาน
    if event.message.type == "image" and user_id in user_states:
        state = user_states[user_id]
        if state["step"] == 200:
        # โหลดไฟล์จริงจาก LINE
            message_content = line_bot_api.get_message_content(event.message.id)
            file_path = f"static/uploads/{event.message.id}.jpg"
            with open(file_path, "wb") as f:
                for chunk in message_content.iter_content():
                    f.write(chunk)

        # gen URL สำหรับเก็บใน DB
            domain = os.getenv("DOMAIN", "https://your-app.onrender.com")
            content_url = f"{domain}/{file_path}"

            state["images"].append(content_url)

            if len(state["images"]) < 3:
                line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"📷 ได้รับรูป {len(state['images'])}/3 กรุณาส่งต่อ")
                )
            else:
            # บันทึกลง DB
                query_db("""INSERT INTO duty_logs
                    (userId, วันที่, ห้อง, เวรวัน, เลขที่ผู้ส่ง, url1, url2, url3, เวลา, สถานะ)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        state["data"]["userId"],
                        datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d"),
                        state["data"]["ห้อง"],
                        state["data"]["เวรวัน"],
                        state["data"]["เลขที่"],
                        state["images"][0], state["images"][1], state["images"][2],
                        datetime.now(BANGKOK_TZ).strftime("%H:%M:%S"),
                        "ส่งแล้ว"
                    )
                )
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="✅ ส่งหลักฐานเรียบร้อยแล้ว")
                )
                del user_states[user_id]



# ===== Run =====
if __name__ == "__main__":
    init_db()  # สร้าง DB ครั้งแรก
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
