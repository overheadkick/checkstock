import threading
from time import sleep
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

# Dictionary สำหรับเก็บข้อมูล SKU ที่ผู้ใช้ต้องการ monitor
monitoring_skus = {}

# Set เก็บข้อความที่เคยตอบไปแล้ว เพื่อลดการตอบซ้ำ
processed_messages = set()

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
    return []

# ฟังก์ชันเพื่อเก็บ SKU ที่ต้องการ monitor
def add_sku_to_monitor(user_id, skus):
    current_monitored_skus = [sku for sku, users in monitoring_skus.items() if user_id in users]
    if len(current_monitored_skus) + len(skus) > 5:
        reply_text = "คุณสามารถ monitor สินค้าได้สูงสุด 5 รายการเท่านั้น กรุณายกเลิกการ monitor สินค้าบางรายการก่อน"
        try:
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=reply_text)
            )
        except LineBotApiError as e:
            print("Error occurred while sending message:", e)
            traceback.print_exc()
        return

    product_info_list = get_product_info(skus)
    if product_info_list is None:
        product_info_list = []

    for product_info in product_info_list:
        sku = product_info['sku']
        if sku in current_monitored_skus:
            reply_text = f"คุณกำลัง monitor สินค้ารหัส {sku} อยู่แล้ว"
            try:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=reply_text)
                )
            except LineBotApiError as e:
                print("Error occurred while sending message:", e)
                traceback.print_exc()
            continue

        if product_info.get("itemStock") != "ไม่ระบุ":
            item_stock = int(product_info["itemStock"])
            if item_stock == 0:
                # หากสินค้าหมดสต็อกแล้ว แจ้งให้ผู้ใช้ทราบว่าไม่สามารถ monitor ได้
                reply_text = f"สินค้ารหัส {sku} หมดสต็อกแล้ว ไม่สามารถ monitor ได้ในขณะนี้"
                try:
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text=reply_text)
                    )
                except LineBotApiError as e:
                    print("Error occurred while sending message:", e)
                    traceback.print_exc()
                continue

            if sku in monitoring_skus:
                monitoring_skus[sku].append(user_id)
            else:
                monitoring_skus[sku] = [user_id]
            print(f"Monitoring SKU {sku} for user {user_id}")
            reply_text = f"ระบบได้เริ่มต้น monitor สินค้ารหัส {sku} แล้ว เราจะแจ้งเตือนคุณเมื่อสินค้ากำลังจะหมด"
            try:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=reply_text)
                )
            except LineBotApiError as e:
                print("Error occurred while sending follow-up message:", e)
                traceback.print_exc()

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
        message_id = event.message.id
        user_message = event.message.text.strip().lower()
        user_id = event.source.user_id

        # ตรวจสอบว่าข้อความนี้เคยถูกประมวลผลแล้วหรือไม่
        if message_id in processed_messages:
            print("Duplicate message detected. Skipping processing.")
            return

        # เพิ่ม message_id ลงใน processed_messages เพื่อป้องกันการประมวลผลซ้ำ
        processed_messages.add(message_id)

        if user_message.startswith("monitor"):
            skus = user_message.split()[1:]  # ดึง SKU หลายตัวจากข้อความ โดยแยกตามช่องว่าง
            skus = [sku.strip() for sku in skus]  # ลบช่องว่างรอบๆ SKU
            # ตอบกลับผู้ใช้ก่อนเพื่อยืนยันการเริ่ม monitor
            reply_text = "กำลังตรวจสอบข้อมูลสินค้ารหัส {} กรุณารอสักครู่...".format("\n".join(skus))
            try:
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=reply_text)
                )
            except LineBotApiError as e:
                print("Error occurred while sending message:", e)
                traceback.print_exc()

            # เพิ่ม SKU ไปยัง monitor หลังจากตอบกลับผู้ใช้
            add_sku_to_monitor(user_id, skus)

        else:
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text="คำสั่งไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง")
            )

    except LineBotApiError as e:
        print("Error occurred while handling message:", e)
        traceback.print_exc()
    except Exception as e:
        print("An unexpected error occurred in handle_message:", e)
        traceback.print_exc()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
