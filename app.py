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

monitoring_skus = {}

# ฟังก์ชันเพื่อดึงข้อมูลสินค้าจาก CSV
def get_product_info(product_codes):
    # Implementation for getting product info
    pass

# ฟังก์ชันเพื่อเก็บ SKU ที่ต้องการ monitor
def add_sku_to_monitor(user_id, skus):
    # Implementation for adding SKUs to monitor
    pass

# ฟังก์ชันเพื่อยกเลิกการ monitor SKU
def remove_sku_from_monitor(user_id, skus):
    # Implementation for removing SKUs from monitor
    pass

# เมื่อผู้ใช้ส่งข้อความมา
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_message = event.message.text.strip().lower()
        user_id = event.source.user_id

        if user_message.isdigit() and len(user_message) == 9:
            # ตรวจสอบว่าข้อความนั้นเป็นตัวเลข 9 หลัก
            handle_stock_inquiry(event)

        elif user_message.startswith("monitor"):
            skus = user_message.replace("monitor", "").strip()
            if skus:
                skus = skus.split()  # แยก SKU ด้วยช่องว่างหรือตามบรรทัด
            else:
                skus = user_message.split("\n")[1:]  # แยก SKU ตามบรรทัด

            skus = [sku.strip() for sku in skus if sku.strip().isdigit() and len(sku.strip()) == 9]
            if skus:
                add_sku_to_monitor(user_id, skus)
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="คำสั่งไม่ถูกต้อง กรุณาระบุ SKU ที่ถูกต้อง (ตัวเลข 9 หลัก)"))

        elif user_message == "unmonitor all":
            remove_sku_from_monitor(user_id, ["all"])

        elif user_message == "list monitor":
            monitored_skus = [sku for sku, users in monitoring_skus.items() if user_id in users]
            if monitored_skus:
                reply_text = "รายการ SKU ที่คุณกำลัง monitor อยู่:\n" + "\n".join(monitored_skus)
            else:
                reply_text = "คุณไม่ได้ monitor SKU ใดอยู่ในขณะนี้"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

        elif user_message == "help":
            guide_text = """
**คู่มือการใช้งานคำสั่ง LINE Bot สำหรับตรวจสอบและ monitor สินค้า**

**1. ตรวจสอบสต็อกสินค้า**
   - ระบุ SKU ที่ต้องการตรวจสอบ โดยแยกแต่ละ SKU ด้วยการขึ้นบรรทัดใหม่
   - ตัวอย่างการใช้งาน:
     123456010
     654321009

**2. Monitor สินค้า**
   - คำสั่ง: monitor <SKU>
   - ตัวอย่างการใช้งาน:
     monitor 123456010 654321009

**3. ยกเลิกการ Monitor สินค้า**
   - คำสั่ง: unmonitor <SKU>
   - ตัวอย่างการใช้งาน:
     unmonitor 123456010 654321009

**4. ยกเลิกการ Monitor ทั้งหมด**
   - คำสั่ง: unmonitor all

**5. ตรวจสอบรายการที่กำลัง Monitor**
   - คำสั่ง: list monitor

**6. เรียกดูคู่มือการใช้งาน**
   - คำสั่ง: help
"""
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=guide_text))

        else:
            # ข้อความไม่ถูกต้อง
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="คำสั่งไม่ถูกต้อง กรุณาลองใหม่อีกครั้ง"))

    except LineBotApiError as e:
        print("Error occurred while handling message:", e)
        traceback.print_exc()
    except Exception as e:
        print("An unexpected error occurred in handle_message:", e)
        traceback.print_exc()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
