# ---------------------------------------------
# فایل: handlers/order_handlers.py
# توضیح: هندلرهای سفارش‌گیری
# ---------------------------------------------

import logging
import asyncio
import aiohttp
import os
import json
from aiogram import types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.state_manager import (
    get_user_status, check_user_status_from_server, get_dynamic_menu,
    mechanic_order_userinfo, customer_order_userinfo, customer_order_states
)
from app.utils import format_amount
import datetime
import pytz
import requests
import tempfile

async def mechanic_menu_handler(message: types.Message):
    """هندلر منوی مکانیک‌ها"""
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        return
    user_id = getattr(getattr(message, 'from_user', None), 'id', None)
    if user_id is None:
        return
    
    # بررسی سفارش‌های در انتظار پرداخت (فقط اگر کاربر در حال ثبت سفارش نیست)
    from app.state_manager import mechanic_order_userinfo, customer_order_userinfo
    if user_id not in mechanic_order_userinfo and user_id not in customer_order_userinfo:
        pending_order = await check_pending_payment_orders(user_id)
        if pending_order:
            await show_pending_payment_order(message, pending_order)
            return
    
    if hasattr(message, 'text') and message.text == "📝 ثبت سفارش":
        # بررسی وضعیت مکانیک
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        api_url = f"{PANEL_API_BASE_URL}/mechanics/api/user/status?telegram_id={user_id}"
        try:
            response = requests.get(api_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('status') == 'approved':
                    # مکانیک تایید شده است
                    role = data.get('role', 'mechanic')
                    from app.state_manager import set_user_status
                    set_user_status(user_id, role, 'approved')
                    
                    # شروع فرآیند ثبت سفارش
                    mechanic_order_userinfo[user_id] = {"step": "product_name", "current_item": {}, "items": []}
                    await message.answer("لطفاً نام محصول اول و کیفیت (ایرانی ، شرکتی ، وارداتی )آن را وارد کنید:📝")
                    logging.info(f"[BOT] Mechanic {user_id} started multi-item order process.")
                    return
                else:
                    await message.answer("❌ شما هنوز تایید نشده‌اید. لطفاً منتظر تایید ادمین باشید.")
                    return
            else:
                await message.answer("❌ خطا در بررسی وضعیت شما. لطفاً دوباره تلاش کنید.")
                return
        except Exception as e:
            logging.error(f"Error checking mechanic status: {e}")
            await message.answer("❌ خطا در اتصال به سرور. لطفاً دوباره تلاش کنید.")
            return
        
    elif hasattr(message, 'text') and message.text == "📦 سفارشات من":
        # نمایش تاریخچه سفارشات مکانیک
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        api_url = f"{PANEL_API_BASE_URL}/telegram-bot/api/orders?telegram_id={user_id}&limit=10"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') and data.get('data'):
                            orders = data['data']
                            if not orders:
                                await message.answer("شما هیچ سفارشی ثبت نکرده‌اید.")
                                return
                            msg = "✉️ تاریخچه سفارشات اخیر شما:\n\n"
                            for idx, order in enumerate(orders, 1):
                                items = order.get('items', [])
                                if items:
                                    for item in items:
                                        msg += f"{idx}. {item.get('product_name', 'نامشخص')} - تعداد: {item.get('quantity', 0)}\n"
                                        msg += f"   وضعیت: {order.get('status_display', 'نامشخص')}\n\n"
                            await message.answer(msg)
                        else:
                            await message.answer("هیچ سفارشی یافت نشد یا خطا در دریافت اطلاعات.")
                    else:
                        await message.answer("خطا در ارتباط با سرور. لطفاً مجدداً تلاش کنید.")
        except Exception as e:
            await message.answer("خطا در دریافت تاریخچه سفارشات.")
            logging.error(f"[BOT] Error fetching order history for user {user_id}: {e}")
    
    elif hasattr(message, 'text') and message.text == "👤 پروفایل من":
        # نمایش اطلاعات پروفایل
        await message.answer("👤 اطلاعات پروفایل شما:\n\nاین بخش در حال توسعه است.")
    
    elif hasattr(message, 'text') and message.text == "📞 پشتیبانی":
        # نمایش اطلاعات پشتیبانی
        await message.answer("📞 برای ارتباط با پشتیبانی:\n\n📱 شماره تماس: 09123456789\n📧 ایمیل: support@nikayadak.com")

async def mechanic_order_text_handler(message: types.Message):
    """هندلر متن‌های سفارش مکانیک"""
    user_id = message.from_user.id
    
    # بررسی اینکه آیا کاربر در حال ثبت سفارش است
    is_mechanic = user_id in mechanic_order_userinfo
    is_customer = user_id in customer_order_userinfo
    
    if not is_mechanic and not is_customer:
        return
    
    # انتخاب order_userinfo مناسب
    order_userinfo = mechanic_order_userinfo if is_mechanic else customer_order_userinfo
    order_data = order_userinfo[user_id]
    step = order_data.get('step', '')
    
    if step == 'product_name':
        # دریافت نام و توضیحات محصول
        product_text = message.text.strip()
        
        # ذخیره نام محصول
        if 'current_item' not in order_data:
            order_data['current_item'] = {}
        order_data['current_item']['product_name'] = product_text
        
        # تغییر مرحله به دریافت تعداد
        order_data['step'] = 'quantity'
        
        await message.answer("🔢 لطفاً تعداد مورد نیاز را وارد کنید:")
        
    elif step == 'quantity':
        # دریافت تعداد
        try:
            quantity = int(message.text.strip())
            if quantity <= 0:
                await message.answer("❌ تعداد باید عدد مثبت باشد. لطفاً دوباره وارد کنید:")
                return
            
            # ذخیره تعداد
            order_data['current_item']['quantity'] = quantity
            
            # پرسیدن درباره عکس
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ بله، عکس دارم", callback_data=f"photo_yes_{user_id}")],
                [InlineKeyboardButton(text="❌ خیر، عکس ندارم", callback_data=f"photo_no_{user_id}")]
            ])
            
            await message.answer("📷 آیا عکس محصول دارید؟", reply_markup=keyboard)
            
        except ValueError:
            await message.answer("❌ لطفاً یک عدد معتبر وارد کنید:")
            
    else:
        # اگر در مرحله نامشخصی هستیم، دوباره شروع کنیم
        order_data['step'] = 'product_name'
        order_data['current_item'] = {}
        await message.answer("لطفاً نام محصول اول و کیفیت (ایرانی ، شرکتی ، وارداتی )آن را وارد کنید:📝")

async def mechanic_order_photo_handler(message: types.Message):
    """هندلر عکس‌های سفارش"""
    user_id = message.from_user.id
    
    # بررسی اینکه آیا کاربر در حال ثبت سفارش است
    is_mechanic = user_id in mechanic_order_userinfo
    is_customer = user_id in customer_order_userinfo
    
    if not is_mechanic and not is_customer:
        return
    
    # انتخاب order_userinfo مناسب
    order_userinfo = mechanic_order_userinfo if is_mechanic else customer_order_userinfo
    order_data = order_userinfo[user_id]
    step = order_data.get('step', '')
    
    if step == 'waiting_photo':
        # ذخیره عکس
        if 'current_item' not in order_data:
            order_data['current_item'] = {}
        
        # ذخیره file_id عکس
        if message.photo:
            order_data['current_item']['photo_file_id'] = message.photo[-1].file_id
        
        await message.answer("✅ عکس دریافت شد!")
        
        # پرسیدن برای ادامه یا پایان
        await ask_continue_or_finish(message, user_id)
        
    else:
        await message.answer("❌ در حال حاضر نیازی به عکس نیست.")

async def ask_continue_or_finish(message: types.Message, user_id: int):
    """پرسیدن از کاربر برای ادامه یا پایان سفارش"""
    # بررسی اینکه آیا کاربر در حال ثبت سفارش است
    is_mechanic = user_id in mechanic_order_userinfo
    is_customer = user_id in customer_order_userinfo
    
    if not is_mechanic and not is_customer:
        await message.answer("❌ شما در حال ثبت سفارش نیستید.")
        return
    
    # انتخاب order_userinfo مناسب
    order_userinfo = mechanic_order_userinfo if is_mechanic else customer_order_userinfo
    order_data = order_userinfo[user_id]
    
    # ذخیره آیتم فعلی
    current_item = order_data.get('current_item', {})
    if current_item.get('product_name') and current_item.get('quantity'):
        if 'items' not in order_data:
            order_data['items'] = []
        # کپی کامل آیتم شامل عکس
        item_copy = current_item.copy()
        if 'photo_file_id' in current_item:
            item_copy['photo_file_id'] = current_item['photo_file_id']
        order_data['items'].append(item_copy)
        logging.info(f"[BOT] Added item to order: {item_copy}")
    
    # پاک کردن آیتم فعلی
    order_data['current_item'] = {}
    
    # نمایش گزینه‌ها
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="+ اضافه آیتم جدید", callback_data=f"add_item_{user_id}")],
        [InlineKeyboardButton(text="پایان و مشاهده سفارش", callback_data=f"finish_order_{user_id}")]
    ])
    
    await message.answer("آیا می‌خواهید آیتم جدیدی اضافه کنید یا سفارش را نهایی کنید؟", reply_markup=keyboard)

async def order_callback_handler(callback_query: types.CallbackQuery):
    """هندلر callback های سفارش (عکس، اضافه آیتم، پایان)"""
    if not callback_query.data:
        return
        
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    # بررسی اینکه آیا کاربر در حال ثبت سفارش است
    is_mechanic = user_id in mechanic_order_userinfo
    is_customer = user_id in customer_order_userinfo
    
    if not is_mechanic and not is_customer:
        await callback_query.answer("❌ شما در حال ثبت سفارش نیستید.")
        return
    
    # انتخاب order_userinfo مناسب
    order_userinfo = mechanic_order_userinfo if is_mechanic else customer_order_userinfo
    
    if data.startswith("photo_yes_"):
        # کاربر عکس دارد
        order_data = order_userinfo[user_id]
        order_data['step'] = 'waiting_photo'
        if callback_query.message:
            await callback_query.message.answer("📷 لطفاً عکس محصول را ارسال کنید:")
            
    elif data.startswith("photo_no_"):
        # کاربر عکس ندارد
        if callback_query.message:
            await ask_continue_or_finish(callback_query.message, user_id)
            
    elif data.startswith("add_item_"):
        # اضافه کردن آیتم جدید
        order_data = order_userinfo[user_id]
        
        # ذخیره آیتم فعلی
        current_item = order_data.get('current_item', {})
        if current_item.get('product_name') and current_item.get('quantity'):
            if 'items' not in order_data:
                order_data['items'] = []
            # کپی کامل آیتم شامل عکس
            item_copy = current_item.copy()
            if 'photo_file_id' in current_item:
                item_copy['photo_file_id'] = current_item['photo_file_id']
            order_data['items'].append(item_copy)
            logging.info(f"[BOT] Added item to order in callback: {item_copy}")
        
        # شروع آیتم جدید
        order_data['current_item'] = {}
        order_data['step'] = 'product_name'
        
        if callback_query.message:
            await callback_query.message.answer("لطفاً نام محصول اول و کیفیت (ایرانی ، شرکتی ، وارداتی )آن را وارد کنید:📝")
            
    elif data.startswith("finish_order_"):
        # پایان سفارش و نمایش خلاصه
        order_data = order_userinfo[user_id]
        
        # ذخیره آیتم آخر
        current_item = order_data.get('current_item', {})
        if current_item.get('product_name') and current_item.get('quantity'):
            if 'items' not in order_data:
                order_data['items'] = []
            # کپی کامل آیتم شامل عکس
            item_copy = current_item.copy()
            if 'photo_file_id' in current_item:
                item_copy['photo_file_id'] = current_item['photo_file_id']
            order_data['items'].append(item_copy)
            logging.info(f"[BOT] Added final item to order: {item_copy}")
        
        # نمایش خلاصه سفارش
        await show_order_summary(callback_query.message, user_id)
    
    await callback_query.answer()

async def show_order_summary(message: types.Message, user_id: int):
    """نمایش خلاصه سفارش برای تایید نهایی"""
    # بررسی اینکه آیا کاربر در حال ثبت سفارش است
    is_mechanic = user_id in mechanic_order_userinfo
    is_customer = user_id in customer_order_userinfo
    
    if not is_mechanic and not is_customer:
        await message.answer("❌ شما در حال ثبت سفارش نیستید.")
        return
    
    # انتخاب order_userinfo مناسب
    order_userinfo = mechanic_order_userinfo if is_mechanic else customer_order_userinfo
    order_data = order_userinfo[user_id]
    items = order_data.get('items', [])
    
    if not items:
        await message.answer("❌ هیچ آیتمی در سفارش وجود ندارد.")
        return
    
    # ساخت متن خلاصه
    summary = "📋 خلاصه سفارش شما:\n\n"
    
    for idx, item in enumerate(items, 1):
        summary += f"{idx}. 📝 {item['product_name']}\n"
        summary += f"   🔢 تعداد: {item['quantity']}\n"
        if item.get('photo_file_id'):
            summary += f"   📷 عکس: ✅\n"
        else:
            summary += f"   📷 عکس: ❌\n"
        summary += "\n"
    
    summary += "آیا اطلاعات صحیح است؟"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و ارسال سفارش", callback_data=f"final_confirm_{user_id}")],
        [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"final_cancel_{user_id}")]
    ])
    
    await message.answer(summary, reply_markup=keyboard)

async def final_order_callback_handler(callback_query: types.CallbackQuery):
    """هندلر تایید نهایی سفارش"""
    if not callback_query.data:
        return
    user_id = callback_query.from_user.id
    is_mechanic = user_id in mechanic_order_userinfo
    is_customer = user_id in customer_order_userinfo
    if not is_mechanic and not is_customer:
        await callback_query.answer("❌ شما در حال ثبت سفارش نیستید.")
        return
    order_userinfo = mechanic_order_userinfo if is_mechanic else customer_order_userinfo
    if callback_query.data.startswith("final_confirm_"):
        logging.info(f"[BOT] final_order_callback_handler called for user {user_id}")
        order_data = order_userinfo[user_id]
        items = order_data.get('items', [])
        if not items:
            if callback_query.message:
                await callback_query.message.answer("❌ هیچ آیتمی در سفارش وجود ندارد.")
            return
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        # آماده‌سازی داده‌ها و فایل‌ها
        formatted_items = []
        files = {}
        for idx, item in enumerate(items):
            formatted_item = {
                'product_name': item.get('product_name', ''),
                'quantity': item.get('quantity', 0),
                'unit_price': item.get('unit_price', 0),
                'total_price': item.get('total_price', 0),
                'photo': None
            }
            if item.get('photo_file_id'):
                # دانلود عکس از تلگرام و ذخیره موقت
                try:
                    photo_file_id = item['photo_file_id']
                    photo = await callback_query.bot.get_file(photo_file_id)
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                        await callback_query.bot.download_file(photo.file_path, tmp.name)
                        files[f'item_{idx+1}_photo'] = open(tmp.name, 'rb')
                        formatted_item['photo'] = f'item_{idx+1}_photo'  # فقط کلید فایل
                except Exception as e:
                    logging.error(f"[BOT] Error downloading product photo: {e}")
            formatted_items.append(formatted_item)
        # آماده‌سازی فرم دیتا
        from aiohttp import FormData
        form = FormData()
        if is_mechanic:
            form.add_field('mechanic_id', str(user_id))
        else:
            form.add_field('customer_id', str(user_id))
        form.add_field('items', json.dumps(formatted_items), content_type='application/json')
        for key, file in files.items():
            form.add_field(key, file, filename=f'{key}.jpg', content_type='image/jpeg')
        try:
            # بررسی تایید کاربر
            check_url = f"{PANEL_API_BASE_URL}/mechanics/api/user/status?telegram_id={user_id}" if is_mechanic else f"{PANEL_API_BASE_URL}/customers/api/user/status?telegram_id={user_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(check_url) as check_resp:
                    if check_resp.status == 200:
                        user_data = await check_resp.json()
                        if not user_data.get('success') or user_data.get('status') != 'approved':
                            if callback_query.message:
                                await callback_query.message.answer("❌ شما مجاز به ثبت سفارش نیستید. لطفاً منتظر تایید ادمین باشید.")
                            return
                    else:
                        if callback_query.message:
                            await callback_query.message.answer("❌ خطا در بررسی وضعیت کاربر.")
                        return
            # ارسال سفارش به پنل با فایل‌ها
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{PANEL_API_BASE_URL}/bot-orders/api/create_order",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        response_data = await resp.json()
                        if response_data.get('success'):
                            order_id = response_data.get('order_id')
                            # دریافت نام سفارش‌دهنده از user_data
                            customer_name = user_data.get('full_name') or user_data.get('name') or "بدون نام"
                            await send_order_notification(order_id, customer_name)
                            from app.handlers.receipt_handlers import set_receipt_waiting_state
                            set_receipt_waiting_state(user_id, order_id)
                            asyncio.create_task(check_order_status_periodically(order_id, user_id, callback_query.bot))
                            if callback_query.message:
                                await callback_query.message.answer(
                                    f"✅ سفارش شما ثبت شد.\nشناسه سفارش: {order_id}\nمنتظر تایید ادمین هستیم. به محض تایید، قیمت‌ها و جزئیات پرداخت برای شما ارسال خواهد شد.\n\n"
                                )
                            del order_userinfo[user_id]
                            logging.info(f"[BOT] Order {order_id} submitted successfully by {'mechanic' if is_mechanic else 'customer'} {user_id}")
                            # ارسال اعلان به پنل پس از ثبت سفارش موفق
                            try:
                                PANEL_API_URL = "https://panel.parnamyadak.ir/api/notify_order_created"
                                notify_data = {
                                    "order_id": order_id,
                                    "telegram_id": user_id,
                                    "role": 'mechanic' if is_mechanic else 'customer'
                                }
                                async with aiohttp.ClientSession() as session:
                                    await session.post(PANEL_API_URL, json=notify_data)
                            except Exception as e:
                                logging.error(f"[BOT] Error notifying panel about order creation: {e}")
                        else:
                            error_msg = response_data.get('message', 'خطای نامشخص')
                            if callback_query.message:
                                await callback_query.message.answer(f"❌ خطا در ثبت سفارش: {error_msg}")
                    elif resp.status == 400:
                        response_data = await resp.json()
                        error_msg = response_data.get('message', 'خطای نامشخص')
                        if callback_query.message:
                            await callback_query.message.answer(f"❌ خطا در ثبت سفارش: {error_msg}")
                    else:
                        if callback_query.message:
                            await callback_query.message.answer("❌ خطا در ارتباط با سرور.")
        except Exception as e:
            logging.error(f"[BOT] Error submitting order for {'mechanic' if is_mechanic else 'customer'} {user_id}: {e}")
            if callback_query.message:
                await callback_query.message.answer("❌ خطا در ثبت سفارش.")
        finally:
            # بستن فایل‌های موقت
            for f in files.values():
                try:
                    f.close()
                    os.unlink(f.name)
                except Exception:
                    pass
    elif callback_query.data.startswith("final_cancel_"):
        if user_id in order_userinfo:
            del order_userinfo[user_id]
            if callback_query.message:
                await callback_query.message.answer("❌ سفارش لغو شد.")
    await callback_query.answer()

async def order_confirm_callback_handler(callback_query: types.CallbackQuery):
    """هندلر تایید سفارش"""
    if not callback_query.data:
        return
        
    user_id = callback_query.from_user.id
    
    if callback_query.data.startswith("order_confirm_"):
        # تایید سفارش
        logging.info(f"[BOT] order_confirm_callback_handler called for user {user_id}")
        if user_id in mechanic_order_userinfo:
            logging.info(f"[BOT] User {user_id} is in mechanic_order_userinfo")
            order_data = mechanic_order_userinfo[user_id]
            logging.info(f"[BOT] Mechanic order_data: {order_data}")
        elif user_id in customer_order_userinfo:
            logging.info(f"[BOT] User {user_id} is in customer_order_userinfo")
            order_data = customer_order_userinfo[user_id]
            logging.info(f"[BOT] Customer order_data: {order_data}")
            # اگر کاربر مشتری است، از final_order_callback_handler استفاده کن
            await final_order_callback_handler(callback_query)
            return
        else:
            logging.warning(f"[BOT] User {user_id} is not in any order state")
            if callback_query.message:
                await callback_query.message.answer("❌ شما در حال ثبت سفارش نیستید.")
            return
            
            # آماده‌سازی payload برای پنل
            PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
            order_payload = {
                'mechanic_id': user_id,
                'items': [{
                    'product_name': order_data['product_name'],
                    'quantity': order_data['quantity']
                }],
                'status': 'pending'
            }
            
            try:
                # آماده‌سازی payload برای API جدید
                items = order_data.get('items', [])
                if not items and 'product_name' in order_data and 'quantity' in order_data:
                    # اگر items خالی است اما product_name و quantity موجود است
                    items = [{
                        'product_name': order_data['product_name'],
                        'quantity': order_data['quantity']
                    }]
                
                # تبدیل آیتم‌ها به فرمت مناسب با عکس‌ها
                formatted_items = []
                for item in items:
                    formatted_item = {
                        'product_name': item.get('product_name', ''),
                        'quantity': item.get('quantity', 0),
                        'unit_price': item.get('unit_price', 0),
                        'total_price': item.get('total_price', 0),
                        'photo': item.get('photo_file_id', None)  # اضافه کردن عکس محصول
                    }
                    formatted_items.append(formatted_item)
                
                order_payload_fixed = {
                    'mechanic_id': user_id,
                    'items': formatted_items
                }
                
                # اضافه کردن لاگ برای debug
                logging.info(f"[BOT] Sending order payload: {order_payload_fixed}")
                logging.info(f"[BOT] Original order_data: {order_data}")
                logging.info(f"[BOT] Items with photos: {formatted_items}")
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{PANEL_API_BASE_URL}/telegram-bot/api/bot/orders",
                        json=order_payload_fixed,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            response_data = await resp.json()
                            if response_data.get('success'):
                                order_id = response_data.get('order_id')
                                
                                # ارسال اعلان سفارش جدید به پنل
                                await send_order_notification(order_id)
                                
                                # تنظیم وضعیت انتظار رسید برای کاربر
                                from app.handlers.receipt_handlers import set_receipt_waiting_state
                                set_receipt_waiting_state(user_id, order_id)
                                
                                if callback_query.message:
                                    await callback_query.message.answer(
                                        f"✅ سفارش شما با موفقیت ثبت شد.\nشناسه سفارش: {order_id}\nمنتظر تایید ادمین باشید.\n\n"
                                        "💡 نکته: اگر قبلاً پرداخت کرده‌اید، می‌توانید رسید پرداخت را ارسال کنید."
                                    )
                                
                                # پاک کردن state
                                del mechanic_order_userinfo[user_id]
                                
                                logging.info(f"[BOT] Order {order_id} submitted successfully by mechanic {user_id}")
                                
                            else:
                                if callback_query.message:
                                    await callback_query.message.answer("❌ خطا در ثبت سفارش. لطفاً مجدداً تلاش کنید.")
                        else:
                            if callback_query.message:
                                await callback_query.message.answer("❌ خطا در ارتباط با سرور.")
                            
            except Exception as e:
                logging.error(f"[BOT] Error submitting order for mechanic {user_id}: {e}")
                if callback_query.message:
                    await callback_query.message.answer("❌ خطا در ثبت سفارش.")
                    
    elif callback_query.data.startswith("order_cancel_"):
        # لغو سفارش
        if user_id in mechanic_order_userinfo:
            del mechanic_order_userinfo[user_id]
            if callback_query.message:
                await callback_query.message.answer("❌ سفارش لغو شد.")
    
    await callback_query.answer()

async def get_product_prices(product_names: list):
    """دریافت قیمت محصولات از پنل"""
    try:
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PANEL_API_BASE_URL}/telegram-bot/api/bot/products/prices",
                json={'products': product_names},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logging.error(f"❌ خطا در دریافت قیمت‌ها: {resp.status}")
                    return {'success': False, 'message': 'خطا در دریافت قیمت‌ها'}
                    
    except Exception as e:
        logging.error(f"❌ خطا در دریافت قیمت‌ها: {e}")
        return {'success': False, 'message': 'خطا در دریافت قیمت‌ها'}


async def send_order_notification(order_id: int, customer_name: str = ""):
    """ارسال اعلان سفارش جدید به پنل"""
    try:
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        notification_data = {
            'order_id': order_id,
            'customer_name': customer_name
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PANEL_API_BASE_URL}/notifications/api/order-registered",
                json=notification_data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    logging.info(f"📢 اعلان سفارش جدید {order_id} به پنل ارسال شد")
                else:
                    logging.error(f"❌ خطا در ارسال اعلان سفارش {order_id}: {resp.status}")
                    
    except Exception as e:
        logging.error(f"❌ خطا در ارسال اعلان سفارش {order_id}: {e}")

async def check_pending_payment_orders(user_id: int):
    """بررسی سفارش‌های در انتظار پرداخت کاربر"""
    try:
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        
        # بررسی سفارش‌های با وضعیت‌های مختلف که کاربر نباید سفارش جدید ثبت کند
        pending_statuses = [
            'در انتظار پرداخت',
            'در انتظار تایید پرداخت', 
            'در انتظار تایید کاربر',
            'تایید شده'
        ]
        
        for status in pending_statuses:
            api_url = f"{PANEL_API_BASE_URL}/telegram-bot/api/orders?telegram_id={user_id}&status={status}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') and data.get('data'):
                            orders = data['data']
                            if orders:
                                # اگر سفارشی با این وضعیت پیدا شد، آن را برگردان
                                order = orders[0]
                                logging.info(f"[BOT] Found pending order for user {user_id} with status: {status}")
                                return order
        
        # اگر هیچ سفارش در انتظاری پیدا نشد، null برگردان
        logging.info(f"[BOT] No pending orders found for user {user_id}")
        return None
        
    except Exception as e:
        logging.error(f"[BOT] Error checking pending payment orders for user {user_id}: {e}")
        return None

async def show_pending_payment_order(message: types.Message, order_data: dict):
    """نمایش سفارش در انتظار پرداخت"""
    try:
        # تعریف user_id از message
        user_id = None
        if message and hasattr(message, 'from_user') and message.from_user:
            user_id = message.from_user.id
        
        order_id = order_data.get('id')
        items = order_data.get('items', [])
        total_amount = order_data.get('total_amount', 0)
        status = order_data.get('status', 'نامشخص')
        
        # حذف .0 از انتهای مبلغ کل
        total_amount_clean = int(total_amount) if total_amount else 0
        
        # پیام بر اساس وضعیت سفارش
        if status == 'در انتظار پرداخت':
            msg = f"⚠️ شما سفارش شماره {order_id} در انتظار پرداخت دارید!\n\n"
            msg += "📋 لیست سفارش:\n"
            
            # محاسبه مجدد مجموع قیمت‌ها
            calculated_total = 0
            
            for item in items:
                product_name = item.get('product_name', '')
                quantity = item.get('quantity', 0)
                unit_price = item.get('unit_price', 0)
                
                # حذف .0 از قیمت واحد
                unit_price_clean = int(unit_price) if unit_price else 0
                item_total = quantity * unit_price_clean
                calculated_total += item_total
                
                msg += f"• {product_name}: {quantity} عدد × {unit_price_clean:,} تومان = {item_total:,} تومان\n"
            
            # استفاده از مجموع محاسبه شده اگر total_amount صفر باشد
            final_total = calculated_total if total_amount_clean == 0 else total_amount_clean
            
            msg += f"\n💰 مبلغ کل: {final_total:,} تومان\n\n"
            msg += "💳 لطفاً رسید واریز را ارسال کنید تا سفارش شما پردازش شود."
            
            # تنظیم وضعیت انتظار رسید
            if user_id:
                from app.handlers.receipt_handlers import set_receipt_waiting_state
                set_receipt_waiting_state(user_id, order_id)
            
        elif status == 'در انتظار تایید پرداخت':
            msg = f"⏳ سفارش شماره {order_id} شما در انتظار تایید پرداخت است.\n\n"
            msg += "✅ رسید پرداخت شما دریافت شده و در حال بررسی توسط ادمین است.\n"
            msg += "🔔 به محض تایید، به شما اطلاع داده خواهد شد."
            
        elif status == 'در انتظار تایید کاربر':
            msg = f"⏳ سفارش شماره {order_id} شما در انتظار تایید نهایی است.\n\n"
            msg += "📋 لطفاً جزئیات سفارش را بررسی کنید:\n"
            
            for item in items:
                product_name = item.get('product_name', '')
                quantity = item.get('quantity', 0)
                unit_price = item.get('unit_price', 0)
                unit_price_clean = int(unit_price) if unit_price else 0
                item_total = quantity * unit_price_clean
                msg += f"• {product_name}: {quantity} عدد × {unit_price_clean:,} تومان = {item_total:,} تومان\n"
            
            msg += f"\n💰 مبلغ کل: {total_amount_clean:,} تومان\n\n"
            msg += "آیا این سفارش را تایید می‌کنید؟"
            
            # ایجاد کیبورد تایید/رد
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ تایید", callback_data=f"order_final_confirm_{order_id}"),
                    InlineKeyboardButton(text="❌ رد", callback_data=f"order_final_cancel_{order_id}")
                ]
            ])
            
            await message.answer(msg, reply_markup=keyboard)
            return
            
        elif status == 'تایید شده':
            msg = f"✅ سفارش شماره {order_id} شما تایید شده است!\n\n"
            msg += "💰 مبلغ قابل پرداخت:\n"
            
            for item in items:
                product_name = item.get('product_name', '')
                quantity = item.get('quantity', 0)
                unit_price = item.get('unit_price', 0)
                unit_price_clean = int(unit_price) if unit_price else 0
                item_total = quantity * unit_price_clean
                msg += f"• {product_name}: {quantity} عدد × {unit_price_clean:,} تومان = {item_total:,} تومان\n"
            
            msg += f"\n💰 مبلغ کل: {total_amount_clean:,} تومان\n\n"
            msg += "💳 لطفاً رسید واریز را ارسال کنید."
            
            # تنظیم وضعیت انتظار رسید
            if user_id:
                from app.handlers.receipt_handlers import set_receipt_waiting_state
                set_receipt_waiting_state(user_id, order_id)
            
        else:
            msg = f"⚠️ شما سفارش شماره {order_id} با وضعیت '{status}' دارید.\n\n"
            msg += "لطفاً منتظر بمانید تا فرآیند این سفارش تکمیل شود."
        
        await message.answer(msg)
        if user_id:
            logging.info(f"[BOT] User {user_id} redirected to pending order {order_id} with status: {status}")
        
    except Exception as e:
        logging.error(f"[BOT] Error showing pending payment order: {e}")
        await message.answer("❌ خطا در نمایش سفارش در انتظار پرداخت.")

async def check_paid_orders_status(user_id: int):
    """بررسی وضعیت سفارش‌های پرداخت شده و اطلاع‌رسانی به کاربر"""
    try:
        # بررسی اینکه آیا کاربر در حال ثبت سفارش است
        from app.state_manager import mechanic_order_userinfo, customer_order_userinfo
        
        if user_id in mechanic_order_userinfo or user_id in customer_order_userinfo:
            logging.info(f"[BOT] User {user_id} is currently placing an order - skipping payment check")
            return
        
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        
        # بررسی سفارش‌های با وضعیت "پرداخت شده"
        api_url = f"{PANEL_API_BASE_URL}/telegram-bot/api/orders?telegram_id={user_id}&status=پرداخت شده"
        
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success') and data.get('data'):
                        orders = data['data']
                        if orders:
                            # اگر سفارش پرداخت شده وجود دارد، اطلاع‌رسانی کن
                            order = orders[0]
                            order_id = order.get('id')
                            items = order.get('items', [])
                            
                            msg = f"✅ سفارش شماره {order_id} شما با موفقیت پرداخت شد!\n\n"
                            msg += "📦 محصولات سفارش شده:\n"
                            
                            for item in items:
                                product_name = item.get('product_name', '')
                                quantity = item.get('quantity', 0)
                                msg += f"• {product_name}: {quantity} عدد\n"
                            
                            msg += "\n🚚 سفارش شما به آدرس ثبت شده ارسال خواهد شد.\n"
                            msg += "📞 در صورت نیاز به اطلاعات بیشتر، با پشتیبانی تماس بگیرید."
                            
                            # ارسال پیام به کاربر
                            try:
                                from aiogram import Bot
                                from config import BotConfig
                                bot = Bot(token=BotConfig.BOT_TOKEN)
                                await bot.send_message(user_id, msg)
                                
                                # پاک کردن سفارش از حافظه
                                try:
                                    from app.state_manager import clear_user_order_state
                                    clear_user_order_state(user_id)
                                except Exception as e:
                                    logging.warning(f"[BOT] Could not clear user order state for {user_id}: {e}")
                                
                                logging.info(f"[BOT] Payment confirmation sent to user {user_id} for order {order_id}")
                                
                            except Exception as e:
                                logging.error(f"[BOT] Error sending payment confirmation to user {user_id}: {e}")
                            
    except Exception as e:
        logging.error(f"[BOT] Error checking paid orders status for user {user_id}: {e}")

def register_order_handlers(dp):
    """ثبت handler های سفارش"""
    # Handler های منوی اصلی
    dp.message.register(mechanic_menu_handler, lambda message: message.text in ["📝 ثبت سفارش", "📦 سفارشات من", "👤 پروفایل من", "📞 پشتیبانی"])
    dp.message.register(customer_menu_handler, lambda message: message.text in ["📝 ثبت سفارش", "📦 سفارشات من", "📞 پشتیبانی"])
    
    # Handler های پردازش متن و عکس سفارش (برای مکانیک و مشتری)
    dp.message.register(mechanic_order_text_handler, lambda message: (message.from_user.id in mechanic_order_userinfo or message.from_user.id in customer_order_userinfo) and not message.photo)
    dp.message.register(mechanic_order_photo_handler, lambda message: (message.from_user.id in mechanic_order_userinfo or message.from_user.id in customer_order_userinfo) and message.photo)
    
    # Handler های callback
    dp.callback_query.register(order_callback_handler, lambda c: c.data and any(c.data.startswith(prefix) for prefix in ["photo_", "add_item_", "finish_order_"]))
    dp.callback_query.register(final_order_callback_handler, lambda c: c.data and (c.data.startswith("final_confirm_") or c.data.startswith("final_cancel_")))
    
    # Handler callback برای تایید/لغو سفارش
    dp.callback_query.register(
        order_final_callback_handler, 
        lambda c: c.data.startswith("order_final_confirm_") or c.data.startswith("order_final_cancel_")
    )
    
    # Handler callback برای تایید/لغو پرداخت
    dp.callback_query.register(
        payment_callback_handler,
        lambda c: c.data.startswith("confirm_payment_") or c.data.startswith("cancel_order_")
    )

async def customer_menu_handler(message: types.Message):
    """هندلر منوی مشتریان"""
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        return
    user_id = getattr(getattr(message, 'from_user', None), 'id', None)
    if user_id is None:
        return
    
    # بررسی سفارش‌های در انتظار پرداخت (فقط اگر کاربر در حال ثبت سفارش نیست)
    from app.state_manager import mechanic_order_userinfo, customer_order_userinfo
    if user_id not in mechanic_order_userinfo and user_id not in customer_order_userinfo:
        pending_order = await check_pending_payment_orders(user_id)
        if pending_order:
            await show_pending_payment_order(message, pending_order)
            return
    
    if hasattr(message, 'text') and message.text == "📝 ثبت سفارش":
        customer_order_userinfo[user_id] = {"step": "product_name", "current_item": {}, "items": []}
        await message.answer("لطفاً نام محصول اول و کیفیت (ایرانی ، شرکتی ، وارداتی )آن را وارد کنید:📝")
        logging.info(f"[BOT] Customer {user_id} started multi-item order process.")
        
    elif hasattr(message, 'text') and message.text == "📦 سفارشات من":
        # نمایش تاریخچه سفارشات مشتری
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        api_url = f"{PANEL_API_BASE_URL}/telegram-bot/api/orders?telegram_id={user_id}&limit=10"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') and data.get('data'):
                            orders = data['data']
                            if not orders:
                                await message.answer("شما هیچ سفارشی ثبت نکرده‌اید.")
                                return
                            msg = "✉️ تاریخچه سفارشات اخیر شما:\n\n"
                            for idx, order in enumerate(orders, 1):
                                items = order.get('items', [])
                                if items:
                                    for item in items:
                                        msg += f"{idx}. {item.get('product_name', 'نامشخص')} - تعداد: {item.get('quantity', 0)}\n"
                                        msg += f"   وضعیت: {order.get('status_display', 'نامشخص')}\n\n"
                            await message.answer(msg)
                        else:
                            await message.answer("هیچ سفارشی یافت نشد یا خطا در دریافت اطلاعات.")
                    else:
                        await message.answer("خطا در ارتباط با سرور. لطفاً مجدداً تلاش کنید.")
        except Exception as e:
            await message.answer("خطا در دریافت تاریخچه سفارشات.")
            logging.error(f"[BOT] Error fetching order history for user {user_id}: {e}")
    
    # elif hasattr(message, 'text') and message.text == "📞 پشتیبانی":
    #     # نمایش اطلاعات پشتیبانی
    #     await message.answer("📞 برای ارتباط با پشتیبانی:\n\n📱 شماره تماس: 09123456789\n📧 ایمیل: support@nikayadak.com")

async def order_final_callback_handler(callback_query: types.CallbackQuery):
    """هندلر تایید/لغو نهایی سفارش"""
    import logging
    user_id = callback_query.from_user.id
    data = callback_query.data
    bot = callback_query.bot
    await callback_query.answer()
    
    # استخراج order_id از callback_data
    if data.startswith("order_final_confirm_"):
        order_id = int(data.split("_")[-1])
        # اطلاع به پنل که سفارش تایید شد
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        url = f"{PANEL_API_BASE_URL}/bot-orders/api/order_status/{order_id}/confirm"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"telegram_id": user_id}) as resp:
                    if resp.status == 200:
                        await callback_query.message.answer("✅ سفارش تایید شد. منتظر پردازش باشید.")
                        # شروع چک کردن وضعیت سفارش
                        asyncio.create_task(check_order_status_periodically(order_id, user_id, bot))
                    else:
                        await callback_query.message.answer("خطا در تایید سفارش. لطفاً مجدداً تلاش کنید.")
        except Exception as e:
            logging.error(f"[BOT] Error confirming order: {e}")
            await callback_query.message.answer("خطا در ارتباط با سرور.")
    elif data.startswith("order_final_cancel_"):
        order_id = int(data.split("_")[-1])
        # اطلاع به پنل که سفارش لغو شد
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        url = f"{PANEL_API_BASE_URL}/bot-orders/api/order_status/{order_id}/cancel"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"telegram_id": user_id, "cancel": True}) as resp:
                    if resp.status == 200:
                        await callback_query.message.answer("سفارش لغو شد.")
                    else:
                        await callback_query.message.answer("خطا در لغو سفارش. لطفاً مجدداً تلاش کنید.")
        except Exception as e:
            logging.error(f"[BOT] Error cancelling order: {e}")
            await callback_query.message.answer("خطا در ارتباط با سرور.")

async def check_order_status_periodically(order_id, user_id, bot):
    """چک کردن وضعیت سفارش به صورت دوره‌ای"""
    import logging
    PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
    status_url = f"{PANEL_API_BASE_URL}/telegram-bot/api/orders/{order_id}"
    last_status = None
    
    while True:
        await asyncio.sleep(30)  # چک هر 30 ثانیه
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(status_url) as resp:
                    if resp.status == 200:
                        response_data = await resp.json()
                        if response_data.get('success'):
                            data = response_data.get('data', {})
                            logging.info(f"[BOT] Checked order status for {user_id} order {order_id}: {data}")
                            
                            current_status = data.get("status")
                            if current_status != last_status:
                                last_status = current_status
                                
                                if current_status == "در انتظار تایید کاربر":
                                    # ادمین سفارش را تایید کرده و قیمت‌ها را وارد کرده
                                    await show_order_summary_with_prices(order_id, user_id, bot, data)
                                    
                                elif current_status == "در انتظار پرداخت":
                                    # کاربر سفارش را تایید کرده
                                    await show_payment_details(order_id, user_id, bot, data)
                                    
                                elif current_status == "در انتظار تایید پرداخت":
                                    # کاربر رسید را ارسال کرده
                                    await bot.send_message(user_id, "✅ رسید پرداخت شما دریافت شد و در حال بررسی است.")
                                    
                                elif current_status == "تکمیل شده":
                                    await bot.send_message(user_id, "✅ سفارش شما با موفقیت تکمیل شد و به آدرس شما ارسال خواهد شد!")
                                    logging.info(f"[BOT] Order completion notification sent to user {user_id}")
                                    break
                                    
                                elif current_status == "لغو شده":
                                    await bot.send_message(user_id, "❌ سفارش شما لغو شد.")
                                    logging.info(f"[BOT] Order cancellation notification sent to user {user_id}")
                                    break
                    else:
                        logging.warning(f"[BOT] Status check failed for order {order_id}: status={resp.status}")
                        
        except Exception as e:
            logging.error(f"[BOT] Exception in order status check for {order_id}: {e}")


async def show_order_summary_with_prices(order_id, user_id, bot, order_data):
    """نمایش خلاصه سفارش با قیمت‌ها"""
    try:
        items = order_data.get('items', [])
        total_amount = order_data.get('total_amount', 0)
        
        # اگر قیمت‌ها صفر هستند، از API دریافت کن
        if not items or all(item.get('unit_price', 0) == 0 for item in items):
            PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{PANEL_API_BASE_URL}/telegram-bot/api/orders/{order_id}") as resp:
                        if resp.status == 200:
                            response_data = await resp.json()
                            if response_data.get('success'):
                                order_data = response_data.get('data', {})
                                items = order_data.get('items', [])
                                total_amount = order_data.get('total_amount', 0)
                                logging.info(f"[BOT] Retrieved order data from API: {order_data}")
                            else:
                                logging.error(f"[BOT] API returned error: {response_data}")
                        else:
                            logging.error(f"[BOT] API request failed with status {resp.status}")
            except Exception as e:
                logging.error(f"[BOT] Error fetching order data from API: {e}")
        
        summary_msg = f"✅ سفارش شما تایید شد!\nشناسه سفارش: {order_id}\n\n📋 خلاصه سفارش:\n"
        
        for item in items:
            product_name = item.get('product_name', '')
            quantity = item.get('quantity', 0)
            unit_price = item.get('unit_price', 0)
            status = item.get('status', 'موجود')
            item_total = quantity * unit_price
            
            # نمایش وضعیت عدم موجودی
            if status == 'عدم موجودی':
                summary_msg += f"• {product_name}: {quantity} عدد ❌ عدم موجودی\n"
            elif unit_price == 0:
                summary_msg += f"• {product_name}: {quantity} عدد × قیمت در حال تعیین = در حال بررسی\n"
            else:
                summary_msg += f"• {product_name}: {quantity} عدد × {int(unit_price):,} تومان = {int(item_total):,} تومان\n"
        
        # حذف .0 از انتهای مبلغ کل
        total_amount_clean = int(total_amount) if total_amount else 0
        if total_amount_clean == 0:
            summary_msg += f"\n💰 مبلغ کل: در حال محاسبه\n\n"
        else:
            summary_msg += f"\n💰 مبلغ کل: {total_amount_clean:,} تومان\n\n"
        summary_msg += "آیا می‌خواهید این سفارش را تایید کنید؟"
        
        # دکمه‌های تایید/لغو
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data=f"confirm_payment_{order_id}")],
            [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"cancel_order_{order_id}")]
        ])
        
        await bot.send_message(user_id, summary_msg, reply_markup=keyboard)
        logging.info(f"[BOT] Order summary with prices sent to user {user_id} for order {order_id}")
        
    except Exception as e:
        logging.error(f"[BOT] Error showing order summary for {order_id}: {e}")


async def show_payment_details(order_id, user_id, bot, order_data):
    """نمایش جزئیات پرداخت"""
    try:
        total_amount = order_data.get('total_amount', 0)
        card_number = order_data.get('card_number', '')
        card_holder = order_data.get('card_holder', '')
        bank = order_data.get('bank', '')
        
        # حذف .0 از انتهای مبلغ
        total_amount_clean = int(total_amount) if total_amount else 0
        
        payment_msg = (
            "💳 سفارش شما تایید شد!\n\n"
            "لطفاً مبلغ سفارش را به شماره کارت زیر واریز کنید و رسید را ارسال نمایید:\n"
            f"<b>{card_number}</b>\n"
            f"به نام: <b>{card_holder}</b>\n"
            f"{bank}\n"
            f"مبلغ: <b>{total_amount_clean:,}</b> تومان\n\n"
            "پس از واریز، عکس یا فایل رسید پرداخت را ارسال کنید."
        )
        
        await bot.send_message(user_id, payment_msg, parse_mode="HTML")
        
        # تنظیم وضعیت انتظار رسید
        from app.handlers.receipt_handlers import set_receipt_waiting_state
        set_receipt_waiting_state(user_id, order_id)
        
        logging.info(f"[BOT] Payment details sent to user {user_id} for order {order_id}")
        
    except Exception as e:
        logging.error(f"[BOT] Error showing payment details for {order_id}: {e}")


async def payment_callback_handler(callback_query: types.CallbackQuery):
    """هندلر تایید/لغو پرداخت"""
    if not callback_query.data:
        return
        
    user_id = callback_query.from_user.id
    
    if callback_query.data.startswith("confirm_payment_"):
        # تایید پرداخت
        order_id = callback_query.data.split("_")[-1]
        
        try:
            PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
            
            # بروزرسانی وضعیت سفارش به "در انتظار پرداخت"
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{PANEL_API_BASE_URL}/telegram-bot/api/orders/{order_id}/status",
                    json={'status': 'در انتظار پرداخت'},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        if callback_query.message:
                            await callback_query.message.answer(
                                f"✅ سفارش شما تایید شد.\nشناسه سفارش: {order_id}\n"
                                "جزئیات پرداخت به زودی برای شما ارسال خواهد شد."
                            )
                    else:
                        if callback_query.message:
                            await callback_query.message.answer("❌ خطا در تایید سفارش.")
                            
        except Exception as e:
            logging.error(f"[BOT] Error confirming payment for order {order_id}: {e}")
            if callback_query.message:
                await callback_query.message.answer("❌ خطا در تایید سفارش.")
                
    elif callback_query.data.startswith("cancel_order_"):
        # لغو سفارش
        order_id = callback_query.data.split("_")[-1]
        
        try:
            PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
            
            # بروزرسانی وضعیت سفارش به "لغو شده"
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{PANEL_API_BASE_URL}/telegram-bot/api/orders/{order_id}/status",
                    json={'status': 'لغو شده'},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        if callback_query.message:
                            await callback_query.message.answer("❌ سفارش لغو شد.")
                    else:
                        if callback_query.message:
                            await callback_query.message.answer("❌ خطا در لغو سفارش.")
                            
        except Exception as e:
            logging.error(f"[BOT] Error canceling order {order_id}: {e}")
            if callback_query.message:
                await callback_query.message.answer("❌ خطا در لغو سفارش.")
    
    await callback_query.answer()


