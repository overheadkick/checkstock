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

# ฟังก์ชันเพื่อยกเลิกการ monitor SKU
def remove_sku_from_monitor(user_id, skus):
    if "all" in skus:
        # ยกเลิกการ monitor ทั้งหมดสำหรับผู้ใช้
        skus_to_remove = [sku for sku, users in monitoring_skus.items() if user_id in users]
    else:
        skus_to_remove = skus

    for sku in skus_to_remove:
        if sku in monitoring_skus:
            if user_id in monitoring_skus[sku]:
                monitoring_skus[sku].remove(user_id)
                if not monitoring_skus[sku]:
                    del monitoring_skus[sku]  # ลบ SKU ออกจาก monitoring_skus หากไม่มีผู้ใช้ monitor แล้ว
                print(f"Stopped monitoring SKU {sku} for user {user_id}")
                reply_text = f"ระบบได้ยกเลิกการ monitor สินค้ารหัส {sku} เรียบร้อยแล้ว"
                try:
                    line_bot_api.push_message(
                        user_id,
                        TextSendMessage(text=reply_text)
                    )
                except LineBotApiError as e:
                    print("Error occurred while sending message:", e)
                    traceback.print_exc()

# ฟังก์ชันตรวจสอบสต็อกสินค้า
def monitor_stock():
    while True:
        for sku, user_ids in list(monitoring_skus.items()):
            product_info = get_product_info([sku])
            if product_info and product_info[0].get("itemStock") != "ไม่ระบุ":
                item_stock = int(product_info[0]["itemStock"])

                # ตรวจสอบจำนวนสต็อกและส่งการแจ้งเตือน
                print(f"Checking stock for SKU {sku}, current stock: {item_stock}")
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

# ฟังก์ชันเพื่อให้เซิร์ฟเวอร์ตื่นอยู่เสมอ
def keep_server_awake():
    while True:
        try:
            # ส่ง request ไปยังตัวเองเพื่อให้ server ตื่นอยู่
            response = requests.get("http://127.0.0.1:10000/")
            print(f"Keep alive request sent, status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"Error during keep alive request: {e}")

        sleep(300)  # ส่งทุกๆ 5 นาที

# Endpoint ที่รับ Webhook จาก LINE
@app.route("/", methods=['GET'])
def home():
    return "OK", 200

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
            reply_text = f"กำลังตรวจสอบข้อมูลสินค้ารหัส {' '.join(skus)} กรุณารอสักครู่..."
            try:
                line_bot_api.push_message(
                    user_id,
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
            add_sku_to_monitor(user_id, skus)

        elif user_message.startswith("unmonitor"):
            skus = user_message.split()[1:]  # ดึง SKU หลายตัวจากข้อความ โดยแยกตามช่องว่าง
            skus = [sku.strip() for sku in skus]  # ลบช่องว่างรอบๆ SKU
            remove_sku_from_monitor(user_id, skus)

        elif user_message == "unmonitor all":
            remove_sku_from_monitor(user_id, ["all"])

        elif user_message == "list monitor":
            # แสดงรายการ SKU ที่ผู้ใช้กำลัง monitor อยู่
            monitored_skus = [sku for sku, users in monitoring_skus.items() if user_id in users]
            if monitored_skus:
                reply_text = "รายการ SKU ที่คุณกำลัง monitor อยู่:\n" + "\n".join(monitored_skus)
            else:
                reply_text = "คุณไม่ได้ monitor SKU ใดอยู่ในขณะนี้"
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=reply_text)
            )

        elif user_message == "help":
            # แสดงคู่มือการใช้งาน
            reply_text = (
                "**คู่มือการใช้งานคำสั่ง LINE Bot สำหรับตรวจสอบและ monitor สินค้า**\n\n"
                "**1. ตรวจสอบสต็อกสินค้า**\n"
                "   - คำสั่ง: ระบุ SKU โดยแยกแต่ละ SKU ด้วยการขึ้นบรรทัดใหม่\n"
                "   - คำอธิบาย: ใช้เพื่อเช็คข้อมูลสต็อกสินค้าที่ระบุ โดย Bot จะส่งข้อมูลชื่อสินค้าและจำนวนสต็อกให้\n"
                "   - ตัวอย่างการใช้งาน:\n"
                "     123456010\n"
                "     654321009\n\n"
                "**2. Monitor สินค้า**\n"
                "   - คำสั่ง: monitor <SKU>\n"
                "   - คำอธิบาย: ใช้เพื่อเริ่มต้น monitor SKU ที่ต้องการ โดยเมื่อสินค้าใกล้จะหมดหรือหมดแล้ว Bot จะทำการแจ้งเตือนผู้ใช้\n"
                "   - ตัวอย่างการใช้งาน:\n"
                "     monitor 123456010 654321009\n\n"
                "**3. ยกเลิกการ Monitor สินค้า**\n"
                "   - คำสั่ง: unmonitor <SKU>\n"
                "   - คำอธิบาย: ใช้เพื่อยกเลิกการ monitor SKU ที่ระบุ\n"
                "   - ตัวอย่างการใช้งาน:\n"
                "     unmonitor 123456010 654321009\n\n"
                "**4. ยกเลิกการ Monitor ทั้งหมด**\n"
                "   - คำสั่ง: unmonitor all\n"
                "   - คำอธิบาย: ใช้เพื่อยกเลิกการ monitor SKU ทั้งหมดที่กำลัง monitor อยู่ในขณะนั้น\n"
                "   - ตัวอย่างการใช้งาน:\n"
                "     unmonitor all\n\n"
                "**5. ตรวจสอบรายการที่กำลัง Monitor**\n"
                "   - คำสั่ง: list monitor\n"
                "   - คำอธิบาย: ใช้เพื่อตรวจสอบรายการ SKU ที่ผู้ใช้กำลัง monitor อยู่ในขณะนั้น\n"
                "   - ตัวอย่างการใช้งาน:\n"
                "     list monitor\n\n"
                "**6. เรียกดูคู่มือการใช้งาน**\n"
                "   - คำสั่ง: help\n"
                "   - คำอธิบาย: ใช้เพื่อเรียกดูคู่มือการใช้งานคำสั่งทั้งหมดของ LINE Bot\n"
                "   - ตัวอย่างการใช้งาน:\n"
                "     help\n\n"
                "**หมายเหตุ:**\n"
                "- สามารถ monitor SKU ได้สูงสุด 5 รายการ หากต้องการ monitor รายการใหม่ ต้องยกเลิกบางรายการก่อน\n"
                "- หากมี SKU ซ้ำในคำสั่ง monitor จะนับเพียงครั้งเดียว"
            )
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text=reply_text)
            )

        elif all(sku.strip().isalnum() and len(sku.strip()) == 9 for sku in user_message.split()):
            # กรณีที่ผู้ใช้ส่งข้อความเป็น SKU หลายตัว โดยแยกตามช่องว่าง
            handle_stock_inquiry(event)

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

# ฟังก์ชันแยกสำหรับการค้นหาสินค้า (เดิม)
def handle_stock_inquiry(event):
    user_id = event.source.user_id
    product_codes = event.message.text.split()
    product_codes = [code.strip() for code in product_codes]
    reply_text = "กำลังตรวจสอบข้อมูลสินค้าของคุณ กรุณารอสักครู่..."

    # ส่งข้อความให้ผู้ใช้เพื่อแจ้งว่ากำลังดำเนินการ
    try:
        line_bot_api.push_message(
            user_id,
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

# เริ่มต้น Thread สำหรับ keep server awake
keep_alive_thread = threading.Thread(target=keep_server_awake, daemon=True)
keep_alive_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=False)
