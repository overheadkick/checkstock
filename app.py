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
    return None

# ฟังก์ชันเพื่อเก็บ SKU ที่ต้องการ monitor
def add_sku_to_monitor(user_id, sku):
    product_info = get_product_info([sku])
    if product_info and product_info[0].get("itemStock") != "ไม่ระบุ":
        item_stock = int(product_info[0]["itemStock"])
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
            return False

        if sku in monitoring_skus:
            monitoring_skus[sku].append(user_id)
        else:
            monitoring_skus[sku] = [user_id]
        print(f"Monitoring SKU {sku} for user {user_id}")
        return True
    else:
        # หากไม่มีข้อมูลสินค้าหรือมีข้อผิดพลาด
        reply_text = f"ไม่พบข้อมูลสินค้ารหัส {sku}"
        try:
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=reply_text)
            )
        except LineBotApiError as e:
            print("Error occurred while sending message:", e)
            traceback.print_exc()
        return False

# ฟังก์ชันเพื่อยกเลิกการ monitor SKU
def remove_sku_from_monitor(user_id, sku):
    if sku in monitoring_skus:
        if user_id in monitoring_skus[sku]:
            monitoring_skus[sku].remove(user_id)
            if not monitoring_skus[sku]:
                del monitoring_skus[sku]  # ลบ SKU ออกจาก monitoring_skus หากไม่มีผู้ใช้ monitor แล้ว
            print(f"Stopped monitoring SKU {sku} for user {user_id}")

# ฟังก์ชันตรวจสอบสต็อกสินค้า
def monitor_stock():
    while True:
        for sku, user_ids in list(monitoring_skus.items()):
            product_info = get_product_info([sku])
            if product_info and product_info[0].get("itemStock") != "ไม่ระบุ":
                item_stock = int(product_info[0]["itemStock"])
                
                # ตรวจสอบจำนวนสต็อกและส่งการแจ้งเตือน
                if item_stock == 0:
                    # สินค้าหมด แจ้งเตือนผู้ใช้
                    for user_id in user_ids:
                        try:
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text=f"แจ้งเตือน: สินค้ารหัส {sku} หมดสต็อกแล้ว!")
                            )
                            print(f"Notification sent to user {user_id} for SKU {sku} (out of stock)")
                        except LineBotApiError as e:
                            print(f"Error occurred while sending notification to user {user_id}:", e)
                            traceback.print_exc()
                    
                    # ลบ SKU ออกจากรายการ monitor เนื่องจากสินค้าหมดแล้ว
                    del monitoring_skus[sku]

                elif item_stock < 10:
                    # สินค้ากำลังจะหมด แจ้งเตือนผู้ใช้
                    for user_id in user_ids:
                        try:
                            line_bot_api.push_message(
                                user_id,
                                TextSendMessage(text=f"แจ้งเตือน: สินค้ารหัส {sku} ใกล้หมดแล้ว! คงเหลือ {item_stock} ชิ้น")
                            )
                            print(f"Notification sent to user {user_id} for SKU {sku} (low stock)")
                        except LineBotApiError as e:
                            print(f"Error occurred while sending notification to user {user_id}:", e)
                            traceback.print_exc()

        sleep(600)  # ตรวจสอบทุกๆ 10 นาที

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
            sku = user_message.split(" ")[1]  # ดึง SKU จากข้อความ
            # ตอบกลับผู้ใช้ก่อนเพื่อยืนยันการเริ่ม monitor
            reply_text = f"กำลังตรวจสอบข้อมูลสินค้ารหัส {sku} กรุณารอสักครู่..."
            try:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_text)
                )
            except LineBotApiError as e:
                # หาก reply token ไม่สามารถใช้งานได้ (เช่นหมดอายุ) ใช้ push_message แทน
                print("Reply token expired, using push_message instead.")
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=reply_text)
                )

            # เพิ่ม SKU ไปยัง monitor หลังจากตอบกลับผู้ใช้
            success = add_sku_to_monitor(user_id, sku)

            # หากสามารถ monitor ได้จึงตอบกลับผู้ใช้เพื่อยืนยันการ monitor
            if success:
                follow_up_text = f"ระบบได้เริ่มต้น monitor สินค้ารหัส {sku} แล้ว เราจะแจ้งเตือนคุณเมื่อสินค้ากำลังจะหมด"
                try:
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text=follow_up_text)
                    )
                except LineBotApiError as e:
                    print("Error occurred while sending follow-up message:", e)
                    traceback.print_exc()

        elif user_message.startswith("unmonitor"):
            sku = user_message.split(" ")[1]  # ดึง SKU จากข้อความ
            remove_sku_from_monitor(user_id, sku)

            # ตอบกลับผู้ใช้เพื่อยืนยันการยกเลิก monitor
            reply_text = f"ระบบได้ยกเลิกการ monitor สินค้ารหัส {sku} เรียบร้อยแล้ว"
            try:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_text)
                )
            except LineBotApiError as e:
                # หาก reply token ไม่สามารถใช้งานได้ (เช่นหมดอายุ) ใช้ push_message แทน
                print("Reply token expired, using push_message instead.")
                line_bot_api.push_message(
                    user_id,
                    TextSendMessage(text=reply_text)
                )

        else:
            # กรณีข้อความอื่นๆ (เช่นการค้นหาสินค้า)
            handle_stock_inquiry(event)

    except LineBotApiError as e:
        print("Error occurred while handling message:", e)
        traceback.print_exc()
    except Exception as e:
        print("An unexpected error occurred in handle_message:", e)
        traceback.print_exc()

# ฟังก์ชันแยกสำหรับการค้นหาสินค้า (เดิม)
def handle_stock_inquiry(event):
    user_id = event.source.user_id
    product_codes = event.message.text.split(',')
    reply_text = "กำลังตรวจสอบข้อมูลสินค้าของคุณ กรุณารอสักครู่..."

    # ส่งข้อความให้ผู้ใช้เพื่อแจ้งว่ากำลังดำเนินการ
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        # หาก reply token ไม่สามารถใช้งานได้ (เช่นหมดอายุ) ใช้ push_message แทน
        print("Reply token expired, using push_message instead.")
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=reply_text)
        )

    # ดึงข้อมูลสินค้าและส่งข้อความติดตามผลให้ผู้ใช้
    product_info_list = get_product_info(product_codes)
    if product_info_list:
        follow_up_text = ""
        for product_info in product_info_list:
            follow_up_text += (f"รหัสสินค้า: {product_info['sku']}\n"
                               f"ชื่อสินค้า: {product_info.get('name', 'ไม่ระบุ')}\n"
                               f"จำนวนสต็อก: {product_info.get('itemStock', 'ไม่ระบุ')} ชิ้น\n\n")
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=follow_up_text.strip())
        )
    else:
        follow_up_text = "ไม่พบข้อมูลสินค้าตามรหัสที่คุณกรอกมา"
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=follow_up_text)
        )

# เริ่มต้น Thread สำหรับ monitor stock
monitor_thread = threading.Thread(target=monitor_stock, daemon=True)
monitor_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
