#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سیستم منوی داینامیک بر اساس وضعیت کاربر
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
# Import from the correct state manager
try:
    from app.state_manager import get_user_status
except ImportError:
    # Fallback if state manager not available
    def get_user_status(user_id):
        return None

def get_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    """دریافت منوی اصلی بر اساس وضعیت کاربر"""
    
    # بررسی وضعیت کاربر
    user_status = get_user_status(user_id)
    
    if not user_status:
        # کاربر ثبت‌نام نکرده
        return get_guest_menu()
    
    if user_status.get('status') == 'pending':
        # کاربر در انتظار تایید
        return get_pending_menu()
    
    if user_status.get('status') == 'approved':
        # کاربر تایید شده
        user_type = user_status.get('role')  # mechanic یا customer
        if user_type == 'mechanic':
            return get_mechanic_menu()
        elif user_type == 'customer':
            return get_customer_menu()
    
    if user_status.get('status') == 'rejected':
        # کاربر رد شده
        return get_rejected_menu()
    
    # پیش‌فرض
    return get_guest_menu()

def get_guest_menu() -> ReplyKeyboardMarkup:
    """منوی کاربران ثبت‌نام نکرده"""
    keyboard = [
        [KeyboardButton(text="👨‍🔧 ثبت‌نام مکانیک")],
        [KeyboardButton(text="👤 ثبت‌نام مشتری")]
        # حذف دکمه پشتیبانی از منوی مهمان
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_pending_menu() -> ReplyKeyboardMarkup:
    """منوی کاربران در انتظار تایید"""
    keyboard = [
        [KeyboardButton(text="⏳ وضعیت ثبت‌نام")],
        [KeyboardButton(text="📞 پشتیبانی")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_mechanic_menu() -> ReplyKeyboardMarkup:
    """منوی مکانیک‌های تایید شده"""
    keyboard = [
        [KeyboardButton(text="📝 ثبت سفارش"), KeyboardButton(text="📦 سفارشات من")],
        [KeyboardButton(text="📞 پشتیبانی")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_customer_menu() -> ReplyKeyboardMarkup:
    """منوی مشتری‌های تایید شده"""
    keyboard = [
        [KeyboardButton(text="📝 ثبت سفارش"), KeyboardButton(text="📦 سفارشات من")],
        [KeyboardButton(text="📞 پشتیبانی")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_rejected_menu() -> ReplyKeyboardMarkup:
    """منوی کاربران رد شده"""
    keyboard = [
        [KeyboardButton(text="🔄 ثبت‌نام مجدد")],
        [KeyboardButton(text="📞 پشتیبانی")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_status_message(user_id: int) -> str:
    """دریافت پیام وضعیت کاربر"""
    user_status = get_user_status(user_id)
    
    if not user_status:
        return "شما هنوز ثبت‌نام نکرده‌اید. لطفاً ابتدا ثبت‌نام کنید."
    
    status = user_status.get('status')
    user_type = user_status.get('role')  # mechanic یا customer
    
    type_text = "مکانیک" if user_type == "mechanic" else "مشتری"
    
    if status == 'pending':
        return f"⏳ ثبت‌نام شما به عنوان {type_text} در حال بررسی است.\nلطفاً منتظر تایید ادمین باشید."
    
    elif status == 'approved':
        return f"✅ ثبت‌نام شما به عنوان {type_text} تایید شده است.\nمی‌توانید از تمام امکانات ربات استفاده کنید."
    
    elif status == 'rejected':
        return f"❌ متاسفانه ثبت‌نام شما به عنوان {type_text} رد شده است.\nبرای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
    
    return "وضعیت نامشخص"
