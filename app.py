from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
import pandas as pd
import io
import os  # เพิ่มการนำเข้า os

# สร้าง Flask แอป
app = Flask(__name__)

# กำหนด LINE API TOKEN และ SECRET
CHANNEL_ACCESS_TOKEN = '5qv+Pci/ZNXOTVH5wjct7yMP8b7HVO/riQ/pWQTZSY8gqDsVhjMhPo59oJEEmYmWwfAPFElAqISBy7QBVdpreR0oyqhix0+tw5pZXoJb/HXYprvcdt2cBDBnqh/kVWc8RRVH+yAWoxZX7ccMKWE3TgdB04t89/1O/w1cDnyilFU='  # แทนที่ด้วย Channel Access Token ของคุณ
CHANNEL_SECRET = '01d856b72692ef4fe43ba42824a1dcba'  # แทนที่ด้วย Channel Secret ของคุณ
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# URL สำหรับดึงข้อมูล CSV
CSV_URL = "https://www.allonline.7eleven.co.th/affiliateExport/?exportName=Item_Stock"

# ฟังก์ชันเพื่อดึงข้อมูลสินค้าจาก CSV
def get_product_info(product_code):
    try:
        response = requests.get(CSV_URL, timeout=10)
        if response.status_code == 200:
            csv_data = response.content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_data))
            
            # พิมพ์คอลัมน์และข้อมูลบางส่วนเพื่อดูว่า CSV ถูกดึงมาถูกต้องหรือไม่
            print("CSV Columns:", df.columns)
            print("CSV Data (First 5 Rows):", df.head())

            # ลบช่องว่างที่ต้นและท้ายของชื่อคอลัมน์
            df.columns = df.columns.str.strip()

            # ตรวจสอบว่า CSV มีคอลัมน์ 'sku' หรือไม่
            if 'sku' in df.columns:
                product_code = str(product_code).strip()  # ลบช่องว่างและแปลงเป็น string
                product = df[df['sku'].astype(str) == product_code]
                if not product.empty:
                    print("Product Found:", product)
                    return product.iloc[0].to_dict()
                else:
                    print(f"No product found for SKU: {product_code}")
            else:
                print("Column 'sku' not found in CSV")
        else:
            print(f"Failed to fetch CSV data, status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error occurred while fetching CSV data: {e}")
    return None

# Endpoint ที่รับ Webhook จาก LINE
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')

    # รับข้อมูล body ของ request
    body = request.get_data(as_text=True)

    # พิมพ์ log ข้อมูลที่ได้รับจาก webhook เพื่อช่วยในการ debug
    print("Request body:", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel secret and access token.")
        abort(400)

    return 'OK', 200

# เมื่อผู้ใช้ส่งข้อความมา
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    print("Received message event")
    product_code = event.message.text.strip()
    product_info = get_product_info(product_code)

    if product_info:
        reply_text = (f"รหัสสินค้า: {product_info['sku']}\n"
                      f"ชื่อสินค้า: {product_info.get('name', 'ไม่ระบุ')}\n"
                      f"จำนวนสต็อก: {product_info.get('itemStock', 'ไม่ระบุ')} ชิ้น")
    else:
        reply_text = "ไม่พบข้อมูลสินค้าตามรหัสที่คุณกรอกมา"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        print("Reply message sent")
    except Exception as e:
        print(f"Error occurred while sending message: {e}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
