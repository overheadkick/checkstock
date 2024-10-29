from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
import pandas as pd
import io
import os
import traceback

app = Flask(__name__)

# กำหนด LINE API TOKEN และ SECRET
CHANNEL_ACCESS_TOKEN = '5qv+Pci/ZNXOTVH5wjct7yMP8b7HVO/riQ/pWQTZSY8gqDsVhjMhPo59oJEEmYmWwfAPFElAqISBy7QBVdpreR0oyqhix0+tw5pZXoJb/HXYprvcdt2cBDBnqh/kVWc8RRVH+yAWoxZX7ccMKWE3TgdB04t89/1O/w1cDnyilFU='
CHANNEL_SECRET = '01d856b72692ef4fe43ba42824a1dcba'
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# URL สำหรับดึงข้อมูล CSV
CSV_URL = "https://www.allonline.7eleven.co.th/affiliateExport/?exportName=Item_Stock"

# ฟังก์ชันเพื่อดึงข้อมูลสินค้าจาก CSV
def get_product_info(product_codes):
    try:
        response = requests.get(CSV_URL, timeout=10)
        if response.status_code == 200:
            csv_data = response.content.decode('utf-8')
            df = pd.read_csv(io.StringIO(csv_data))
            df.columns = df.columns.str.strip()

            # ตรวจสอบว่า CSV มีคอลัมน์ 'sku' หรือไม่
            if 'sku' in df.columns:
                df['sku'] = df['sku'].astype(str).str.strip()  # แปลงคอลัมน์ sku เป็นสตริงและลบช่องว่าง
                results = []

                for product_code in product_codes:
                    product_code = product_code.strip()  # ลบช่องว่างที่ต้นและท้ายของ SKU แต่ละตัว
                    product = df[df['sku'] == product_code]
                    if not product.empty:
                        results.append(product.iloc[0].to_dict())
                    else:
                        results.append({"sku": product_code, "name": "ไม่พบข้อมูล", "itemStock": "ไม่ระบุ"})

                return results
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
    body = request.get_data(as_text=True)
    print("Request body:", body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel secret and access token.")
        abort(400)
    except Exception as e:
        print("An unexpected error occurred:", e)
        traceback.print_exc()
        abort(500)

    return 'OK', 200

# เมื่อผู้ใช้ส่งข้อความมา
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        print("Received message event")
        # แยก SKU หลายตัวออกจากข้อความที่ผู้ใช้ส่งมา โดยใช้เครื่องหมายจุลภาคเป็นตัวแบ่ง
        product_codes = event.message.text.split(',')

        # ตรวจสอบว่าได้ตอบกลับไปแล้วหรือไม่
        if hasattr(event, 'replied') and event.replied:
            print("Message already replied. Skipping duplicate handling.")
            return

        # ตอบกลับทันทีเพื่อไม่ให้ reply_token หมดอายุ
        reply_text = "กำลังตรวจสอบข้อมูลสินค้าของคุณ กรุณารอสักครู่..."
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
            print("Reply message sent immediately to avoid token expiry")
            event.replied = True  # ระบุว่าฟังก์ชันได้ตอบกลับแล้ว
        except LineBotApiError as e:
            # จับข้อยกเว้นเมื่อการใช้ reply_token ไม่สำเร็จ
            print("Error occurred while replying with reply_token:", e)
            traceback.print_exc()
            return

        # หลังจากนั้นค่อยประมวลผลข้อมูลสินค้า
        product_info_list = get_product_info(product_codes)
        if product_info_list:
            follow_up_text = ""
            for product_info in product_info_list:
                follow_up_text += (f"รหัสสินค้า: {product_info['sku']}\n"
                                   f"ชื่อสินค้า: {product_info.get('name', 'ไม่ระบุ')}\n"
                                   f"จำนวนสต็อก: {product_info.get('itemStock', 'ไม่ระบุ')} ชิ้น\n\n")
        else:
            follow_up_text = "ไม่พบข้อมูลสินค้าตามรหัสที่คุณกรอกมา"

        # ส่งข้อความติดตามด้วย push_message
        try:
            line_bot_api.push_message(
                event.source.user_id,
                TextSendMessage(text=follow_up_text.strip())
            )
            print("Follow-up message sent")
        except LineBotApiError as e:
            # จับข้อยกเว้นเมื่อการใช้ push_message ไม่สำเร็จ
            print("Error occurred while sending push_message:", e)
            traceback.print_exc()

    except Exception as e:
        # แสดงรายละเอียดข้อผิดพลาดที่เกิดขึ้น
        print("An unexpected error occurred in handle_message:", e)
        traceback.print_exc()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
