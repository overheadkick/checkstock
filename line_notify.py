import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import requests
import csv
from io import StringIO

app = Flask(__name__)

# LINE Bot configuration
CHANNEL_ACCESS_TOKEN = 'sKG20t60VbCAHxW4FLCbTv0wBxcjefCFQdkkKxTJy4x'
CHANNEL_SECRET = '01d856b72692ef4fe43ba42824a1dcba'

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

def get_sku_details(sku, url):
    response = requests.get(url)
    
    if response.status_code == 200:
        response.encoding = 'utf-8-sig'
        csv_text = response.text
        csv_file = StringIO(csv_text)
        reader = csv.DictReader(csv_file)
        
        for row in reader:
            if row.get('sku') == sku:
                return row
    
    return None

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
    user_message = event.message.text
    
    if user_message.startswith('SKU:'):
        sku = user_message.split(':')[1].strip()
        url = 'https://www.allonline.7eleven.co.th/affiliateExport/?exportName=Item_Stock'
        
        sku_details = get_sku_details(sku, url)
        
        if sku_details:
            reply_message = (
                f"รายละเอียดสินค้า:\n"
                f"รหัส SKU: {sku}\n"
                f"ชื่อสินค้า: {sku_details.get('name')}\n"
                f"จำนวนสินค้าในสต็อก: {sku_details.get('itemStock')}"
            )
        else:
            reply_message = 'ไม่พบข้อมูลสินค้าที่ระบุ'
    else:
        reply_message = 'กรุณาส่งข้อความในรูปแบบ "SKU:รหัสสินค้า" เพื่อตรวจสอบสต็อก'
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_message)
    )

if __name__ == "__main__":
    app.run(debug=True)