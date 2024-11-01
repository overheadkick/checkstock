# แก้ไขฟังก์ชัน handle_message
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        message_id = event.message.id
        user_message = event.message.text.strip().lower()
        user_id = event.source.user_id

        # ตรวจสอบว่าเป็นคำสั่ง monitor หรือไม่
        if user_message.startswith("monitor"):
            skus = user_message.split("\n")[1:]  # ดึง SKU จากบรรทัดใหม่
            if len(skus) == 0:
                skus = user_message.split()[1:]  # ดึง SKU จากคำสั่ง monitor <sku>
            
            skus = [sku.strip() for sku in skus if sku.strip().isdigit() and len(sku.strip()) == 9]

            if not skus:
                # กรณีไม่มี SKU ที่ถูกต้อง
                reply_text = "คำสั่งไม่ถูกต้อง กรุณาตรวจสอบว่าเป็นตัวเลข 9 หลักหรือไม่มีตัวอักษรผสม\nหากต้องการตรวจสอบหลายรายการ กรุณาระบุ SKU โดยขึ้นบรรทัดใหม่เพื่อแยกแต่ละ SKU"
                line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
                return

            reply_text = "กำลังตรวจสอบข้อมูลสินค้ารหัส:\n{}\nกรุณารอสักครู่...".format("\n".join(skus))
            line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))

            # เรียกฟังก์ชัน monitor SKU หลังจากตอบกลับ
            add_sku_to_monitor(user_id, skus)

        # ฟังก์ชันอื่นๆ เช่น unmonitor, list monitor ก็แก้ไขคล้ายกัน
        # ...

    except LineBotApiError as e:
        print("Error occurred while handling message:", e)
        traceback.print_exc()
    except Exception as e:
        print("An unexpected error occurred in handle_message:", e)
        traceback.print_exc()

# แก้ไขฟังก์ชัน add_sku_to_monitor ให้ push_message()
def add_sku_to_monitor(user_id, skus):
    current_monitored_skus = [sku for sku, users in monitoring_skus.items() if user_id in users]
    if len(current_monitored_skus) + len(skus) > 5:
        reply_text = "คุณสามารถ monitor สินค้าได้สูงสุด 5 รายการเท่านั้น กรุณายกเลิกการ monitor สินค้าบางรายการก่อน"
        line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
        return

    product_info_list = get_product_info(skus)
    if product_info_list is None:
        product_info_list = []

    for product_info in product_info_list:
        sku = product_info['sku']
        if sku in current_monitored_skus:
            reply_text = f"คุณกำลัง monitor สินค้ารหัส {sku} อยู่แล้ว"
            line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
            continue

        if product_info.get("itemStock") != "ไม่ระบุ":
            item_stock = int(product_info["itemStock"])
            if item_stock == 0:
                reply_text = f"สินค้ารหัส {sku} หมดสต็อกแล้ว ไม่สามารถ monitor ได้ในขณะนี้"
                line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
                continue

            # เพิ่ม SKU ไปยัง monitoring_skus
            if sku in monitoring_skus:
                monitoring_skus[sku].append(user_id)
            else:
                monitoring_skus[sku] = [user_id]

            reply_text = f"ระบบได้เริ่มต้น monitor สินค้ารหัส {sku} แล้ว เราจะแจ้งเตือนคุณเมื่อสินค้ากำลังจะหมด"
            line_bot_api.push_message(user_id, TextSendMessage(text=reply_text))
