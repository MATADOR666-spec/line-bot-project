from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ใส่ Token/Secret ของคุณตรงนี้
LINE_CHANNEL_ACCESS_TOKEN = "cMVOGkL006pgWyPC05nJOSD0oGOYo+6d2if8muZW8lc6/Jp+QzUYPNvf6334bvH+43119o+m26XvBFaAD+mCJzVq6BF5OhOu4ZTRjnA89lPk+cBJ3g6SnbB++pw941jj9KZ2U/uyCZhtRNSC/aqtlwdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "b22543fb3525a0bcd84886ab25822602"

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text))  # ตอบกลับเหมือนที่ส่งมา

if __name__ == "__main__":
    app.run(port=5000, debug=True)