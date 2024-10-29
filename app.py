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
            success = add_sku_to_monitor(user_id, sku)

            # หากสามารถ monitor ได้จึงตอบกลับผู้ใช้เพื่อยืนยันการ monitor
            if success:
                reply_text = f"ระบบได้เริ่มต้น monitor สินค้ารหัส {sku} แล้ว เราจะแจ้งเตือนคุณเมื่อสินค้ากำลังจะหมด"
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
