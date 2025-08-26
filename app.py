import os
import json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# อ่านค่า token/secret จาก Environment Variables
CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise ValueError("Environment variables LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET are missing!")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

app = Flask(__name__)

# Health check
@app.route("/", methods=["GET"])
def home():
    return "ok", 200

# จุดรับ webhook
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

# จัดการข้อความ
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = (event.message.text or "").strip()

    if text == "โปรไฟล์":
        profile = line_bot_api.get_profile(event.source.user_id)
        reply = f"ชื่อ: {profile.display_name}\nuserId: {profile.user_id}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="พิมพ์ 'โปรไฟล์' เพื่อลองทดสอบครับ")
        )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)