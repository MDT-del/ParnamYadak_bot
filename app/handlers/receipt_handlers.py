#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
هندلرهای مربوط به آپلود رسید پرداخت
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
import logging
import aiohttp
from aiogram import types
from aiogram.types import Message
import tempfile
import json
from app.state_manager import get_receipt_state, set_receipt_state, clear_receipt_state

# تنظیم لاگر
logger = logging.getLogger(__name__)

# فایل state برای نگهداری وضعیت انتظار رسید
RECEIPT_STATE_FILE = os.path.join(os.path.dirname(__file__), '../receipt_state.json')

# بررسی مسیر فایل و ایجاد آن در صورت نیاز
if not os.path.exists(RECEIPT_STATE_FILE):
    try:
        # ایجاد فایل خالی
        with open(RECEIPT_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
        logger.info(f"[RECEIPT_HANDLER] Created new receipt state file: {RECEIPT_STATE_FILE}")
    except Exception as e:
        logger.error(f"[RECEIPT_HANDLER] Error creating receipt state file: {e}")

# اضافه کردن لاگ برای بررسی مسیر فایل
logger.info(f"[RECEIPT_HANDLER] RECEIPT_STATE_FILE path: {RECEIPT_STATE_FILE}")
logger.info(f"[RECEIPT_HANDLER] File exists: {os.path.exists(RECEIPT_STATE_FILE)}")

# اضافه کردن لاگ بیشتر برای بررسی محتوای فایل
if os.path.exists(RECEIPT_STATE_FILE):
    try:
        with open(RECEIPT_STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"[RECEIPT_HANDLER] File content: {data}")
    except Exception as e:
        logger.error(f"[RECEIPT_HANDLER] Error reading file: {e}")

def set_receipt_waiting_state(user_id: int, order_id: int):
    """تنظیم وضعیت انتظار رسید برای کاربر"""
    set_receipt_state(user_id, order_id)
    logger.info(f"📝 وضعیت انتظار رسید برای کاربر {user_id} و سفارش {order_id} تنظیم شد (state_manager) ")
    logger.info(f"📝 Current states: {get_receipt_state(user_id)}")

def get_receipt_waiting_state(user_id: int):
    """دریافت وضعیت انتظار رسید کاربر"""
    return get_receipt_state(user_id)

def clear_receipt_waiting_state(user_id: int):
    """پاک کردن وضعیت انتظار رسید کاربر"""
    clear_receipt_state(user_id)
    logger.info(f"🗑️ وضعیت انتظار رسید برای کاربر {user_id} پاک شد (state_manager)")
    logger.info(f"🗑️ Current states: {get_receipt_state(user_id)}")

async def receipt_photo_handler(message: Message):
    """هندلر دریافت عکس رسید پرداخت"""
    user_id = message.from_user.id
    
    try:
        # اضافه کردن لاگ برای تست
        logger.info(f"[RECEIPT_HANDLER] PHOTO HANDLER CALLED: user_id={user_id}")
        
        # بررسی اینکه آیا کاربر در انتظار ارسال رسید است
        receipt_state = get_receipt_waiting_state(user_id)
        
        logger.info(f"[RECEIPT_HANDLER] BEFORE: user_id={user_id}, state={receipt_state}")
        logger.info(f"[RECEIPT_HANDLER] Current states: {get_receipt_state(user_id)}")
        logger.info(f"[RECEIPT_HANDLER] TEST LOG - این لاگ باید نمایش داده شود")
        
        # بررسی وضعیت - اگر state == 'await_receipt' یا waiting_for_receipt == True
        if not receipt_state or (not receipt_state.get('waiting_for_receipt') and receipt_state.get('state') != 'await_receipt'):
            # کاربر در انتظار رسید نیست
            logger.info(f"[RECEIPT_HANDLER] INVALID STATE: user_id={user_id}, state={receipt_state}")
            await message.answer("لطفاً ابتدا سفارش خود را ثبت کنید و پس از تایید، رسید پرداخت را ارسال نمایید.")
            return
        
        # اضافه کردن لاگ جدید برای تست
        logger.info(f"[RECEIPT_HANDLER] VALID STATE FOUND: user_id={user_id}, order_id={receipt_state.get('order_id')}")
        
        order_id = receipt_state.get('order_id')
        if not order_id:
            logger.error(f"❌ order_id برای کاربر {user_id} یافت نشد")
            await message.answer("❌ خطا در شناسایی سفارش. لطفاً مجدداً تلاش کنید.")
            return
        
        # بررسی اینکه پیام شامل عکس است
        if not message.photo:
            await message.answer("❌ لطفاً فقط عکس رسید پرداخت را ارسال کنید.")
            return
        
        await message.answer("⏳ در حال آپلود رسید پرداخت...")
        logger.info(f"[RECEIPT_HANDLER] شروع آپلود رسید برای سفارش {order_id}")
        
        # دانلود عکس از تلگرام
        photo = message.photo[-1]  # بزرگترین سایز عکس
        file_info = await message.bot.get_file(photo.file_id)
        
        # ایجاد پوشه bot_receipts اگر وجود ندارد
        receipts_dir = os.path.join(os.path.dirname(__file__), '../../app/static/bot_receipts')
        os.makedirs(receipts_dir, exist_ok=True)
        
        # ذخیره فایل در مسیر مشخص شده
        file_path = os.path.join(receipts_dir, f'receipt_{order_id}_{user_id}.jpg')
        
        try:
            # دانلود فایل
            await message.bot.download_file(file_info.file_path, file_path)
            
            # آپلود رسید به پنل
            success = await upload_receipt_to_panel(order_id, file_path)
            
            if success:
                await message.answer("✅ رسید پرداخت با موفقیت ارسال شد!\n\nمنتظر بررسی و تایید نهایی ادمین باشید.")
                
                # پاک کردن وضعیت انتظار رسید
                clear_receipt_waiting_state(user_id)
                
                # ادامه polling برای این سفارش
                await resume_order_polling_after_receipt(order_id)
                
                logger.info(f"🔄 Polling برای سفارش {order_id} ادامه یافت")
                logger.info(f"[RECEIPT_HANDLER] رسید با موفقیت آپلود شد")
                
            else:
                await message.answer("❌ خطا در ارسال رسید. لطفاً مجدداً تلاش کنید.")
                logger.info(f"[RECEIPT_HANDLER] خطا در آپلود رسید")
                
        except Exception as e:
            logger.error(f"❌ خطا در دانلود یا آپلود رسید: {e}")
            await message.answer("❌ خطا در پردازش رسید. لطفاً مجدداً تلاش کنید.")
                
    except Exception as e:
        logger.error(f"❌ خطا در پردازش رسید پرداخت: {e}")
        if message:
            await message.answer("❌ خطا در پردازش رسید. لطفاً مجدداً تلاش کنید.")

async def receipt_text_handler(message: Message):
    """هندلر پیام‌های متنی در حالت انتظار رسید"""
    user_id = message.from_user.id
    
    try:
        # بررسی اینکه آیا کاربر در انتظار ارسال رسید است
        receipt_state = get_receipt_waiting_state(user_id)
        
        if receipt_state and (receipt_state.get('waiting_for_receipt') or receipt_state.get('state') == 'await_receipt'):
            await message.answer("❌ لطفاً فقط عکس رسید پرداخت را ارسال کنید. پیام‌های متنی در این مرحله پذیرفته نمی‌شود.")
            return
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش پیام متنی: {e}")

async def receipt_document_handler(message: Message):
    """هندلر فایل‌های مستند در حالت انتظار رسید"""
    user_id = message.from_user.id
    
    try:
        # بررسی اینکه آیا کاربر در انتظار ارسال رسید است
        receipt_state = get_receipt_waiting_state(user_id)
        
        if receipt_state and (receipt_state.get('waiting_for_receipt') or receipt_state.get('state') == 'await_receipt'):
            await message.answer("❌ لطفاً فقط عکس رسید پرداخت را ارسال کنید. فایل‌های مستند در این مرحله پذیرفته نمی‌شود.")
            return
        
    except Exception as e:
        logger.error(f"❌ خطا در پردازش فایل مستند: {e}")

async def upload_receipt_to_panel(order_id: int, file_path: str):
    """آپلود رسید پرداخت به پنل"""
    try:
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        if not PANEL_API_BASE_URL:
            logger.error("❌ PANEL_API_BASE_URL تنظیم نشده است")
            return False
        
        url = f"{PANEL_API_BASE_URL}/telegram-bot/api/orders/{order_id}/upload_receipt"
        
        # بررسی وجود فایل
        if not os.path.exists(file_path):
            logger.error(f"❌ فایل رسید یافت نشد: {file_path}")
            return False
        
        # خواندن فایل
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # آپلود فایل به پنل
        async with aiohttp.ClientSession() as session:
            # تنظیم form data برای آپلود فایل
            form_data = aiohttp.FormData()
            form_data.add_field('receipt_image', file_data, 
                              filename=os.path.basename(file_path), 
                              content_type='image/jpeg')
            
            async with session.post(
                url,
                data=form_data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('success'):
                        logger.info(f"✅ رسید سفارش {order_id} با موفقیت آپلود شد")
                        return True
                    else:
                        logger.error(f"❌ خطا در آپلود رسید: {result.get('message', 'نامشخص')}")
                        return False
                else:
                    logger.error(f"❌ خطا در آپلود رسید: HTTP {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"❌ خطا در آپلود رسید به پنل: {e}")
        return False

# متغیر سراسری برای نگهداری مرجع به polling system
_global_polling_system = None

# متغیر سراسری برای نگهداری وضعیت انتظار رسید (به جای فایل JSON)
_receipt_waiting_states = {}

# اضافه کردن لاگ برای بررسی مقدار اولیه
logger.info(f"[RECEIPT_HANDLER] Initial _receipt_waiting_states: {_receipt_waiting_states}")

def set_global_polling_system(polling_system):
    """تنظیم مرجع سراسری به polling system"""
    global _global_polling_system
    _global_polling_system = polling_system

async def resume_order_polling_after_receipt(order_id: int):
    """ادامه polling پس از آپلود رسید"""
    try:
        global _global_polling_system
        if _global_polling_system:
            _global_polling_system.resume_order_polling(order_id)
            logger.info(f"▶️ Polling برای سفارش {order_id} ادامه یافت")
        else:
            logger.warning(f"⚠️ Polling system در دسترس نیست برای ادامه polling سفارش {order_id}")
    except Exception as e:
        logger.error(f"❌ خطا در ادامه polling برای سفارش {order_id}: {e}")

def register_receipt_handlers(dp):
    """ثبت هندلرهای مربوط به رسید"""
    # هندلر برای دریافت عکس (فقط زمانی که کاربر در انتظار رسید است)
    dp.message.register(
        receipt_photo_handler, 
        lambda message: message.photo is not None and get_receipt_waiting_state(message.from_user.id) is not None
    )
    
    # هندلر برای پیام‌های متنی در حالت انتظار رسید
    dp.message.register(
        receipt_text_handler,
        lambda message: message.text and get_receipt_waiting_state(message.from_user.id) is not None
    )

    # هندلر برای فایل‌های مستند در حالت انتظار رسید
    dp.message.register(
        receipt_document_handler,
        lambda message: message.document and get_receipt_waiting_state(message.from_user.id) is not None
    )
    
    logger.info("📝 هندلرهای رسید پرداخت ثبت شدند")
