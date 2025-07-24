#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سیستم polling برای بررسی وضعیت ثبت‌نام کاربران
"""

import asyncio
import logging
import os
import requests
import aiohttp
import json
from datetime import datetime, timedelta
from aiogram import Bot
from app.state_manager import get_user_status, set_user_status
import sys
from config import BotConfig

# تنظیم لاگر
logger = logging.getLogger(__name__)

class PollingSystem:
    def __init__(self, bot: Bot):
        """مقداردهی اولیه"""
        self.bot = bot
        self.panel_api_base_url = os.getenv("PANEL_API_BASE_URL", "http://127.0.0.1:5000")
        self.is_running = False
        self.paused_orders = set()  # سفارش‌هایی که polling برایشان متوقف شده
        self.polling_interval = 300  # افزایش به 5 دقیقه برای کاهش تداخل
        self.previous_statuses = {}  # ذخیره وضعیت قبلی کاربران
        self.previous_order_statuses = {}  # ذخیره وضعیت قبلی سفارشات
        self.notified_orders = set()  # سفارشاتی که اطلاع‌رسانی شده‌اند
        self.notified_orders_file = os.path.join(os.path.dirname(__file__), 'notified_orders.json')
        self.load_notified_orders()
        self.last_menu_update = {}  # زمان آخرین به‌روزرسانی منو برای هر کاربر
        self.connection_retries = 2  # کاهش تعداد تلاش‌های اتصال
        self.retry_delay = 10  # افزایش تاخیر بین تلاش‌ها
        self.last_connection_check = 0  # زمان آخرین بررسی اتصال
        self.connection_check_interval = 60  # افزایش فاصله بررسی اتصال (ثانیه)
        logger = logging.getLogger(__name__)
        logger.info(f"🔧 PollingSystem initialized with panel URL: {self.panel_api_base_url}")
        if not BotConfig.USE_WEBHOOK:
            self.polling_interval = 60  # هر 1 دقیقه یکبار فقط در حالت پولینگ
    
    def load_notified_orders(self):
        """بارگذاری سفارشات اطلاع‌رسانی شده از فایل"""
        try:
            if os.path.exists(self.notified_orders_file):
                with open(self.notified_orders_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.notified_orders = set(data.get('notified_orders', []))
                    logger.info(f"📋 بارگذاری {len(self.notified_orders)} سفارش اطلاع‌رسانی شده")
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری سفارشات اطلاع‌رسانی شده: {e}")
    
    def save_notified_orders(self):
        """ذخیره سفارشات اطلاع‌رسانی شده در فایل"""
        try:
            data = {
                'notified_orders': list(self.notified_orders),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.notified_orders_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 ذخیره {len(self.notified_orders)} سفارش اطلاع‌رسانی شده")
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره سفارشات اطلاع‌رسانی شده: {e}")
    
    async def start_polling(self):
        """شروع polling system"""
        if BotConfig.USE_WEBHOOK:
            logger.info("[POLLING] USE_WEBHOOK فعال است، polling سفارشات غیرفعال شد.")
            return
        logger.info("🚀 شروع سیستم polling...")
        self.is_running = True
        panel_accessible = False
        
        while self.is_running:
            try:
                import time
                current_time = time.time()
                
                # بررسی اتصال به پنل فقط در فواصل مشخص
                if current_time - self.last_connection_check > self.connection_check_interval:
                    panel_accessible = await self.check_panel_connection()
                    self.last_connection_check = current_time
                    
                    if panel_accessible:
                        logger.info("✅ اتصال به پنل برقرار است")
                    else:
                        logger.warning("⚠️ عدم اتصال به پنل - کار در حالت آفلاین")
                
                # همیشه سفارشات را بررسی کن، حتی اگر پنل در دسترس نباشد
                logger.info("🔍 شروع بررسی سفارشات...")
                await self.check_pending_orders()

                # بررسی وضعیت کاربران (مکانیک و مشتری)
                logger.info("🔍 شروع بررسی وضعیت کاربران...")
                await self.check_user_statuses()
                
                if panel_accessible:
                    logger.info("✅ Polling cycle completed successfully")
                else:
                    logger.debug("🔍 Polling cycle completed (offline mode)")
                
                # انتظار قبل از چک بعدی
                logger.info(f"⏳ انتظار {self.polling_interval} ثانیه برای چک بعدی...")
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"❌ خطا در polling loop: {e}")
                await asyncio.sleep(10)  # انتظار بیشتر در صورت خطا
    
    async def check_panel_connection(self):
        """بررسی اتصال به پنل"""
        try:
            # ابتدا سعی کن به endpoint سلامت متصل شوی
            response = requests.get(f"{self.panel_api_base_url}/health", timeout=5)
            if response.status_code == 200:
                logger.debug("✅ اتصال به پنل برقرار است")
                return True
            
            # اگر endpoint سلامت کار نکرد، سعی کن به endpoint اصلی متصل شوی
            response = requests.get(f"{self.panel_api_base_url}/", timeout=5)
            return response.status_code in [200, 302, 404]  # هر کدام از این کدها نشان‌دهنده کارکرد سرور است
            
        except requests.exceptions.ConnectionError:
            logger.debug("🔍 عدم اتصال به پنل")
            return False
        except Exception as e:
            logger.debug(f"🔍 خطا در بررسی اتصال پنل: {e}")
            return False
    
    def stop_polling(self):
        """توقف سیستم polling"""
        self.is_running = False
        logger.info("⏹️ سیستم polling متوقف شد")
    
    async def check_user_statuses(self):
        """بررسی وضعیت کاربران"""
        try:
            # دریافت لیست کاربران فعال
            from app.state_manager import mechanic_order_userinfo, customer_order_userinfo, get_pending_users, user_statuses
            
            # بررسی کاربران در انتظار تایید
            pending_users = get_pending_users()
            all_users = set(mechanic_order_userinfo.keys()) | set(customer_order_userinfo.keys()) | set(pending_users) | set(user_statuses.keys())
            
            logger.info(f"[POLLING] Checking {len(all_users)} users for status updates")
            
            for user_id in all_users:
                await self.check_user_status(user_id)
                    
        except Exception as e:
            logger.error(f"❌ خطا در بررسی وضعیت کاربران: {e}")
    
    def get_pending_users(self):
        """دریافت لیست کاربران با وضعیت pending"""
        from app.state_manager import get_pending_users
        return get_pending_users()
    
    async def check_user_status(self, user_id: int):
        """بررسی وضعیت کاربر"""
        for attempt in range(self.connection_retries):
            try:
                # استفاده از endpoint جدید که هم مکانیک و هم مشتری را بررسی می‌کند
                user_url = f"{self.panel_api_base_url}/mechanics/api/user/status?telegram_id={user_id}"
                user_response = requests.get(user_url, timeout=10)
                
                if user_response.status_code == 200:
                    user_data = user_response.json()
                    if user_data.get('success'):
                        status = user_data.get('status')
                        role = user_data.get('role')
                        commission_percent = user_data.get('commission_percentage', 0)
                        
                        # بررسی تغییر وضعیت
                        previous_status = self.previous_statuses.get(user_id, {})
                        current_status = {'status': status, 'role': role}
                        
                        if previous_status != current_status:
                            logging.info(f"[POLLING] User {user_id} status changed: {previous_status} -> {current_status}, commission: {commission_percent}%")
                            
                            # به‌روزرسانی وضعیت کاربر در حافظه
                            from app.state_manager import set_user_status
                            set_user_status(user_id, role, status)
                            
                            # ذخیره وضعیت جدید
                            self.previous_statuses[user_id] = current_status
                            
                            # اطلاع‌رسانی بر اساس وضعیت جدید
                            if status == 'approved':
                                await self.notify_user_approved(user_id, role, commission_percent)
                                # منو فقط در زمان تایید اولیه به‌روزرسانی می‌شود
                            elif status == 'rejected':
                                await self.notify_user_rejected(user_id, role)
                        else:
                            logging.debug(f"[POLLING] User {user_id} status unchanged: {status}")
                    else:
                        logging.info(f"[POLLING] User {user_id} not found in system")
                else:
                    logging.warning(f"[POLLING] Failed to get user status for {user_id}: {user_response.status_code}")
                
                # اگر موفق بودیم، از حلقه خارج شویم
                break
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"[POLLING] Connection error for user {user_id} (attempt {attempt + 1}/{self.connection_retries}): {e}")
                if attempt < self.connection_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"[POLLING] Failed to check user status for {user_id} after {self.connection_retries} attempts")
            except Exception as e:
                logger.error(f"[POLLING] Error checking user status for {user_id}: {e}")
                break
    
    async def check_mechanic_status(self, user_id: int):
        """بررسی وضعیت مکانیک در پنل"""
        for attempt in range(self.connection_retries):
            try:
                api_url = f"{self.panel_api_base_url}/mechanics/api/status?telegram_id={user_id}"
                logger.info(f"🌐 بررسی API مکانیک {user_id}: {api_url}")
                
                response = requests.get(api_url, timeout=10)
                logger.info(f"📊 Response status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"📊 Response data for user {user_id}: {data}")
                    
                    if data.get('success'):
                        status = data.get('status', 'pending')
                        logger.info(f"📊 Current status: {status}")
                    
                    if status == 'approved':
                        # تایید شده
                        logger.info(f"✅ مکانیک {user_id} تایید شد - به‌روزرسانی وضعیت...")
                        set_user_status(user_id, "mechanic", "approved")
                        await self.notify_user_approved(user_id, "mechanic")
                        logger.info(f"✅ اطلاع‌رسانی تایید به مکانیک {user_id} ارسال شد")
                        
                    elif status == 'rejected':
                        # رد شده
                        logger.info(f"❌ مکانیک {user_id} رد شد - به‌روزرسانی وضعیت...")
                        set_user_status(user_id, "mechanic", "rejected")
                        await self.notify_user_rejected(user_id, "mechanic")
                        logger.info(f"❌ اطلاع‌رسانی رد به مکانیک {user_id} ارسال شد")
                        
                    elif status == 'pending':
                        logger.info(f"⏳ مکانیک {user_id} هنوز در انتظار تایید")
                        
                    else:
                        logger.warning(f"⚠️ وضعیت نامشخص برای مکانیک {user_id}: {status}")
                        
                else:
                    logger.warning(f"⚠️ API response error for mechanic {user_id}: {response.status_code}")
                
                # اگر موفق بودیم، از حلقه خارج شویم
                break
                    
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"[BOT] Connection error for mechanic {user_id} (attempt {attempt + 1}/{self.connection_retries}): {e}")
                if attempt < self.connection_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"[BOT] Failed to check mechanic status for {user_id} after {self.connection_retries} attempts")
            except Exception as e:
                logger.error(f"❌ خطا در بررسی وضعیت مکانیک {user_id}: {e}")
                break
    
    async def check_customer_status(self, user_id: int):
        """بررسی وضعیت مشتری در پنل"""
        for attempt in range(self.connection_retries):
            try:
                response = requests.get(
                    f"{self.panel_api_base_url}/customers/api/status?telegram_id={user_id}",
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get('status')
                    
                    if status == 'approved':
                        # تایید شده
                        set_user_status(user_id, "customer", "approved")
                        await self.notify_user_approved(user_id, "customer")
                        logger.info(f"✅ مشتری {user_id} تایید شد")
                        
                    elif status == 'rejected':
                        # رد شده
                        set_user_status(user_id, "customer", "rejected")
                        await self.notify_user_rejected(user_id, "customer")
                        logger.info(f"❌ مشتری {user_id} رد شد")
                
                # اگر موفق بودیم، از حلقه خارج شویم
                break
                    
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"[BOT] Connection error for customer {user_id} (attempt {attempt + 1}/{self.connection_retries}): {e}")
                if attempt < self.connection_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"[BOT] Failed to check customer status for {user_id} after {self.connection_retries} attempts")
            except Exception as e:
                logger.error(f"❌ خطا در بررسی وضعیت مشتری {user_id}: {e}")
                break
    
    async def notify_user_approved(self, user_id: int, user_type: str, commission_percent: float = 0):
        """اطلاع‌رسانی تایید ثبت‌نام به کاربر"""
        try:
            if user_type == "mechanic":
                message = f"🎉 تبریک! ثبت‌نام شما به عنوان مکانیک تایید شد.\n\n💰 درصد کمیسیون شما: {commission_percent}%\n\nحالا می‌توانید از تمام امکانات ربات استفاده کنید."
            else:
                message = "🎉 تبریک! ثبت‌نام شما به عنوان مشتری تایید شد.\n\nحالا می‌توانید سفارش ثبت کنید."
            
            await self.bot.send_message(user_id, message)
            logger.info(f"📢 اطلاع‌رسانی تایید به کاربر {user_id} ارسال شد")
            
            # ارسال منوی داینامیک یکسان با /start بعد از تایید
            from dynamic_menu import get_main_menu
            menu = get_main_menu(user_id)
            await self.bot.send_message(user_id, "منوی اصلی:", reply_markup=menu)
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال اطلاع‌رسانی تایید به کاربر {user_id}: {e}")
    
    async def notify_user_rejected(self, user_id: int, user_type: str):
        """اطلاع‌رسانی رد ثبت‌نام به کاربر"""
        try:
            message = "😔 متاسفانه ثبت‌نام شما رد شد.\n\nبرای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
            
            await self.bot.send_message(user_id, message)
            logger.info(f"📢 اطلاع‌رسانی رد به کاربر {user_id} ارسال شد")
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال اطلاع‌رسانی رد به کاربر {user_id}: {e}")
    
    # --- متدهای مربوط به سفارشات ---
    
    async def check_pending_orders(self):
        if BotConfig.USE_WEBHOOK:
            logger.info("[POLLING] USE_WEBHOOK فعال است، بررسی سفارشات غیرفعال شد.")
            return
        """بررسی وضعیت سفارشات در انتظار"""
        try:
            # پاک کردن سفارش‌های تکمیل شده از حافظه
            from app.state_manager import clear_completed_orders, get_pending_orders
            clear_completed_orders()
            
            # دریافت سفارش‌های در انتظار
            pending_orders = get_pending_orders()
            logger.info(f"📋 بررسی {len(pending_orders)} سفارش در انتظار...")
            
            for order_id, user_id in pending_orders:
                logger.info(f"🔍 بررسی سفارش {order_id} برای کاربر {user_id}")
                await self.check_order_status(order_id, user_id)
            
            # بررسی سفارشات از receipt_state.json
            await self.check_receipt_state_orders()
                
        except Exception as e:
            logger.error(f"❌ خطا در بررسی سفارشات در انتظار: {e}")
    
    async def check_receipt_state_orders(self):
        """بررسی سفارشات از receipt_state.json"""
        try:
            import json
            import os
            
            receipt_state_file = os.path.join(os.path.dirname(__file__), 'app/receipt_state.json')
            if not os.path.exists(receipt_state_file):
                return
            
            with open(receipt_state_file, 'r', encoding='utf-8') as f:
                receipt_states = json.load(f)
            
            for user_id_str, state_data in receipt_states.items():
                user_id = int(user_id_str)
                order_id = state_data.get('order_id')
                
                if order_id and state_data.get('waiting_for_receipt'):
                    logger.info(f"🔍 بررسی سفارش {order_id} از receipt_state برای کاربر {user_id}")
                    await self.check_order_status(order_id, user_id)
            
            # بررسی سفارشات مستقیماً از API برای کاربران فعال
            await self.check_active_user_orders()
                    
        except Exception as e:
            logger.error(f"❌ خطا در بررسی سفارشات receipt_state: {e}")
    
    async def check_active_user_orders(self):
        """بررسی همه سفارشات از API"""
        try:
            # دریافت همه سفارشات اخیر از API
            api_url = f"{self.panel_api_base_url}/telegram-bot/api/orders?limit=50&status=پرداخت شده"
            
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    orders = data['data']
                    logger.info(f"🔍 بررسی {len(orders)} سفارش با وضعیت 'پرداخت شده'")
                    
                    for order in orders:
                        order_id = order.get('id')
                        status = order.get('status')
                        user_id = order.get('telegram_id') or order.get('user_id')
                        
                        if order_id and user_id and status == 'پرداخت شده':
                            # اگر سفارش قبلاً اطلاع‌رسانی نشده
                            if order_id not in self.notified_orders:
                                logger.info(f"🎯 سفارش {order_id} با وضعیت 'پرداخت شده' یافت شد برای کاربر {user_id}")
                                await self.handle_order_status_change(order_id, user_id, status, order)
                                self.notified_orders.add(order_id)
                                self.previous_order_statuses[order_id] = status
                                self.save_notified_orders()
                            
        except Exception as e:
            logger.error(f"❌ خطا در بررسی سفارشات: {e}")
    
    async def get_pending_orders(self):
        """دریافت لیست سفارشات در انتظار"""
        try:
            # این باید از state manager یا فایل محلی خوانده شود
            from app.state_manager import get_pending_orders
            return get_pending_orders()
        except Exception as e:
            logger.error(f"❌ خطا در دریافت سفارشات pending: {e}")
            return []
    
    async def check_order_status(self, order_id: int, user_id: int):
        if BotConfig.USE_WEBHOOK:
            logger.info(f"[POLLING] USE_WEBHOOK فعال است، بررسی وضعیت سفارش {order_id} غیرفعال شد.")
            return
        """بررسی وضعیت سفارش"""
        for attempt in range(self.connection_retries):
            try:
                # بررسی اتصال به پنل
                if not await self.check_panel_connection():
                    logger.warning(f"⚠️ پنل در دسترس نیست - استفاده از وضعیت آفلاین برای سفارش {order_id}")
                    await self.handle_offline_order_status(order_id, user_id)
                    return
                
                # دریافت وضعیت سفارش از API
                order_url = f"{self.panel_api_base_url}/telegram-bot/api/orders/{order_id}"
                logger.info(f"🌐 بررسی وضعیت سفارش {order_id}: {order_url}")
                
                response = requests.get(order_url, timeout=10)
                
                if response.status_code == 200:
                    order_data = response.json()
                    logger.info(f"📊 پاسخ API سفارش {order_id}: {order_data}")
                    
                    if order_data.get('success'):
                        current_status = order_data.get('data', {}).get('status')
                        logger.info(f"📊 وضعیت فعلی سفارش {order_id}: {current_status}")
                        
                        # بررسی تغییر وضعیت
                        previous_status = self.previous_order_statuses.get(order_id)
                        if previous_status != current_status:
                            logger.info(f"🔄 تغییر وضعیت سفارش {order_id}: {previous_status} -> {current_status}")
                            await self.handle_order_status_change(order_id, user_id, current_status, order_data.get('data', {}))
                            self.previous_order_statuses[order_id] = current_status
                        else:
                            logger.debug(f"📊 وضعیت سفارش {order_id} بدون تغییر: {current_status}")
                        
                        # اگر وضعیت 'پرداخت شده' است و قبلاً اطلاع‌رسانی نشده، پیام ارسال کن
                        if current_status == 'پرداخت شده' and order_id not in self.notified_orders:
                            logger.info(f"🎯 سفارش {order_id} برای اولین بار با وضعیت 'پرداخت شده' یافت شد")
                            await self.handle_order_status_change(order_id, user_id, current_status, order_data.get('data', {}))
                            self.notified_orders.add(order_id)
                            self.previous_order_statuses[order_id] = current_status
                            self.save_notified_orders()
                    else:
                        logger.warning(f"⚠️ API سفارش {order_id} موفق نبود: {order_data}")
                else:
                    logger.warning(f"⚠️ خطا در دریافت وضعیت سفارش {order_id}: {response.status_code}")
                
                # اگر موفق بودیم، از حلقه خارج شویم
                break
                
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"[BOT] Connection error for order {order_id} (attempt {attempt + 1}/{self.connection_retries}): {e}")
                if attempt < self.connection_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"[BOT] Failed to check order status for {order_id} after {self.connection_retries} attempts")
            except Exception as e:
                logger.error(f"❌ خطا در بررسی وضعیت سفارش {order_id}: {e}")
                break
    
    async def handle_offline_order_status(self, order_id: int, user_id: int):
        """مدیریت وضعیت سفارش در حالت آفلاین"""
        try:
            # در حالت آفلاین، وضعیت سفارش را در حافظه نگه دار
            from app.state_manager import set_order_status
            
            # وضعیت پیش‌فرض برای سفارشات در حالت آفلاین
            default_status = "waiting_for_payment"
            set_order_status(user_id, order_id, default_status)
            
            logger.info(f"[BOT] Order {order_id} kept in memory with status: {default_status}")
            
        except Exception as e:
            logger.error(f"[BOT] Error handling offline order status for {order_id}: {e}")
    
    async def handle_order_status_change(self, order_id: int, user_id: int, status: str, order_data: dict):
        """پردازش تغییر وضعیت سفارش"""
        try:
            if status == 'waiting_for_user_confirmation':
                # سفارش تایید شده و منتظر تایید کاربر
                await self.notify_order_approved(order_id, user_id, order_data)
                
            elif status == 'waiting_for_payment':
                # منتظر پرداخت
                await self.notify_payment_required(order_id, user_id, order_data)
                
            elif status == 'payment_confirmed' or status == 'پرداخت شده':
                # پرداخت تایید شده
                await self.notify_payment_confirmed(order_id, user_id, order_data)
                
            elif status == 'completed':
                # سفارش تکمیل شده
                await self.notify_order_completed(order_id, user_id)
                
            elif status == 'rejected':
                # سفارش رد شده
                await self.notify_order_rejected(order_id, user_id)
                
        except Exception as e:
            logger.error(f"❌ خطا در پردازش تغییر وضعیت سفارش {order_id}: {e}")
    
    async def notify_order_approved(self, order_id: int, user_id: int, order_data: dict):
        """اطلاع‌رسانی تایید سفارش به کاربر"""
        try:
            price = order_data.get('price', 0)
            message = f"✅ سفارش شما تایید شد!\n\n💰 مبلغ: {price:,} تومان\n\nآیا قیمت را تایید می‌کنید؟"
            
            # ایجاد کیبورد تایید/رد
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ تایید", callback_data=f"order_final_confirm_{order_id}"),
                    InlineKeyboardButton(text="❌ رد", callback_data=f"order_final_cancel_{order_id}")
                ]
            ])
            
            await self.bot.send_message(user_id, message, reply_markup=keyboard)
            logger.info(f"📢 اطلاع‌رسانی تایید سفارش {order_id} به کاربر {user_id} ارسال شد")
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال اطلاع‌رسانی تایید سفارش {order_id}: {e}")
    
    async def notify_payment_required(self, order_id: int, user_id: int, order_data: dict):
        """اطلاع‌رسانی نیاز به پرداخت"""
        try:
            card_number = order_data.get('card_number', '')
            price = order_data.get('price', 0)
            
            message = f"💳 لطفاً مبلغ {price:,} تومان را به شماره کارت زیر واریز کنید:\n\n💳 {card_number}\n\nپس از واریز، عکس رسید را ارسال کنید."
            
            await self.bot.send_message(user_id, message)
            
            # تنظیم وضعیت انتظار رسید
            from app.handlers.receipt_handlers import set_receipt_waiting_state
            set_receipt_waiting_state(user_id, order_id)
            
            # متوقف کردن polling برای این سفارش تا رسید ارسال شود
            self.pause_order_polling(order_id)
            
            logger.info(f"📢 اطلاع‌رسانی پرداخت سفارش {order_id} به کاربر {user_id} ارسال شد")
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال اطلاع‌رسانی پرداخت سفارش {order_id}: {e}")
    
    async def notify_order_completed(self, order_id: int, user_id: int):
        """اطلاع‌رسانی تکمیل سفارش"""
        try:
            message = f"✅ سفارش شما با موفقیت تکمیل شد!\n\nاز استفاده از خدمات ما متشکریم. 😊"
            
            await self.bot.send_message(user_id, message)
            logger.info(f"📢 اطلاع‌رسانی تکمیل سفارش {order_id} به کاربر {user_id} ارسال شد")
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال اطلاع‌رسانی تکمیل سفارش {order_id}: {e}")
    
    async def notify_order_rejected(self, order_id: int, user_id: int):
        """اطلاع‌رسانی رد سفارش"""
        try:
            message = f"❌ متاسفانه سفارش شما رد شد.\n\nبرای اطلاعات بیشتر با پشتیبانی تماس بگیرید."
            await self.bot.send_message(user_id, message)
            logger.info(f"📢 اطلاع‌رسانی رد سفارش {order_id} به کاربر {user_id} ارسال شد")
            # پاکسازی وضعیت رسید
            from app.state_manager import clear_receipt_state
            clear_receipt_state(user_id)
        except Exception as e:
            logger.error(f"❌ خطا در ارسال اطلاع‌رسانی رد سفارش {order_id}: {e}")
    
    async def notify_payment_confirmed(self, order_id: int, user_id: int, order_data: dict):
        """اطلاع‌رسانی تایید پرداخت به کاربر"""
        try:
            message = f"✅ پرداخت سفارش شماره {order_id} تایید شد!\n\n🎉 سفارش شما نهایی شد و به آدرس شما ارسال خواهد شد.\n\n📦 می‌توانید سفارش جدیدی ثبت کنید."
            await self.bot.send_message(user_id, message)
            logger.info(f"📢 اطلاع‌رسانی تایید پرداخت سفارش {order_id} به کاربر {user_id} ارسال شد")
            # متوقف کردن polling برای این سفارش
            self.pause_order_polling(order_id)
            # پاکسازی وضعیت رسید
            from app.state_manager import clear_receipt_state
            clear_receipt_state(user_id)
        except Exception as e:
            logger.error(f"❌ خطا در ارسال اطلاع‌رسانی تایید پرداخت سفارش {order_id}: {e}")
    
    # --- متدهای کنترل polling ---
    
    def pause_order_polling(self, order_id: int):
        """متوقف کردن polling برای یک سفارش خاص"""
        self.paused_orders.add(order_id)
        logger.info(f"⏸️ Polling برای سفارش {order_id} متوقف شد")
    
    def resume_order_polling(self, order_id: int):
        """ادامه polling برای یک سفارش خاص"""
        self.paused_orders.discard(order_id)
        logger.info(f"▶️ Polling برای سفارش {order_id} ادامه یافت")
    
    async def update_dynamic_menu(self, user_id: int):
        """به‌روزرسانی منوی پویا پس از تایید"""
        try:
            from dynamic_menu import get_main_menu, get_status_message
            
            status_message = get_status_message(user_id)
            menu = get_main_menu(user_id)
            
            await self.bot.send_message(
                user_id, 
                status_message + "\n\nمنوی جدید شما:", 
                reply_markup=menu
            )
            
            logger.info(f"🔄 منوی پویا برای کاربر {user_id} به‌روزرسانی شد")
            
        except Exception as e:
            logger.error(f"❌ خطا در به‌روزرسانی منوی پویا برای کاربر {user_id}: {e}")

    async def update_dynamic_menus(self):
        """به‌روزرسانی منوهای پویا"""
        try:
            # دریافت لیست کاربران فعال
            from app.state_manager import mechanic_order_userinfo, customer_order_userinfo
            
            all_users = set(mechanic_order_userinfo.keys()) | set(customer_order_userinfo.keys())
            
            for user_id in all_users:
                await self.update_user_dynamic_menu(user_id)
                    
        except Exception as e:
            logger.error(f"❌ خطا در به‌روزرسانی منوهای پویا: {e}")
    
    async def send_registration_menu(self, user_id: int):
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="ثبت‌نام به عنوان مکانیک")],
                [KeyboardButton(text="ثبت‌نام به عنوان مشتری")]
            ],
            resize_keyboard=True
        )
        await self.bot.send_message(
            user_id,
            "لطفاً برای استفاده از ربات ابتدا ثبت‌نام کنید:",
            reply_markup=keyboard
        )

    async def update_user_dynamic_menu(self, user_id: int):
        """به‌روزرسانی منوی پویا برای کاربر"""
        try:
            # بررسی اینکه آیا کاربر در حال سفارش است
            if self.is_user_in_order_process(user_id):
                logger.info(f"⏸️ کاربر {user_id} در حال سفارش است - منو تغییر نمی‌کند")
                return
            
            # بررسی زمان آخرین به‌روزرسانی منو
            from datetime import datetime, timedelta
            current_time = datetime.now()
            last_update = self.last_menu_update.get(user_id)
            
            # اگر کمتر از 5 دقیقه از آخرین به‌روزرسانی گذشته، منو را تغییر نده
            if last_update and (current_time - last_update) < timedelta(minutes=5):
                logger.debug(f"⏰ کاربر {user_id} اخیراً منو به‌روزرسانی شده - تغییر نمی‌کند")
                return
            
            # بررسی وضعیت کاربر
            from app.state_manager import get_user_status
            user_status = get_user_status(user_id)
            
            logger.info(f"🔍 بررسی وضعیت کاربر {user_id}: {user_status}")
            
            if user_status:
                status = user_status.get('status')
                role = user_status.get('role')
                
                logger.info(f"📊 وضعیت کاربر {user_id}: status={status}, role={role}")
                
                # اگر کاربر تایید شده است، منوی مناسب را نمایش بده
                if status == 'approved':
                    if role == 'mechanic':
                        logger.info(f"🔧 ارسال منوی مکانیک برای کاربر {user_id}")
                        await self.send_mechanic_menu(user_id)
                    elif role == 'customer':
                        logger.info(f"🛒 ارسال منوی مشتری برای کاربر {user_id}")
                        await self.send_customer_menu(user_id)
                    else:
                        logger.warning(f"⚠️ نقش نامشخص برای کاربر {user_id}: {role}")
                        await self.send_registration_menu(user_id)
                    
                    # ذخیره زمان به‌روزرسانی منو
                    self.last_menu_update[user_id] = current_time
                    return
                else:
                    logger.info(f"⏳ کاربر {user_id} تایید نشده (status={status})")
            
            # اگر کاربر تایید نشده یا وضعیت نامشخص است، منوی ثبت‌نام را نمایش بده
            logger.info(f"📝 ارسال منوی ثبت‌نام برای کاربر {user_id}")
            await self.send_registration_menu(user_id)
            
            # ذخیره زمان به‌روزرسانی منو
            self.last_menu_update[user_id] = current_time
            
        except Exception as e:
            logger.error(f"❌ خطا در به‌روزرسانی منوی پویا برای کاربر {user_id}: {e}")
    
    def is_user_in_order_process(self, user_id: int):
        """بررسی اینکه آیا کاربر در حال سفارش است"""
        try:
            from app.state_manager import mechanic_order_userinfo, customer_order_userinfo
            
            # بررسی در سفارشات مکانیک
            if user_id in mechanic_order_userinfo:
                order_data = mechanic_order_userinfo[user_id]
                status = order_data.get('status')
                # اگر کاربر در حال سفارش است (نه تکمیل شده)
                if status and status not in ['completed', 'پرداخت شده', 'payment_confirmed']:
                    return True
            
            # بررسی در سفارشات مشتری
            if user_id in customer_order_userinfo:
                order_data = customer_order_userinfo[user_id]
                status = order_data.get('status')
                # اگر کاربر در حال سفارش است (نه تکمیل شده)
                if status and status not in ['completed', 'پرداخت شده', 'payment_confirmed']:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ خطا در بررسی وضعیت سفارش کاربر {user_id}: {e}")
            return False
    
    async def send_mechanic_menu(self, user_id: int):
        """ارسال منوی مکانیک"""
        try:
            from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📝 ثبت سفارش")],
                    [KeyboardButton(text="📦 سفارشات من")],
                    [KeyboardButton(text="📞 پشتیبانی")]
                ],
                resize_keyboard=True
            )
            
            await self.bot.send_message(
                user_id,
                "🔧 منوی مکانیک\n\nلطفاً گزینه مورد نظر را انتخاب کنید:",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال منوی مکانیک برای کاربر {user_id}: {e}")
    
    async def send_customer_menu(self, user_id: int):
        """ارسال منوی مشتری"""
        try:
            from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
            
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="📝 ثبت سفارش")],
                    [KeyboardButton(text="📦 سفارشات من")],
                    [KeyboardButton(text="📞 پشتیبانی")]
                ],
                resize_keyboard=True
            )
            
            await self.bot.send_message(
                user_id,
                "🛒 منوی مشتری\n\nلطفاً گزینه مورد نظر را انتخاب کنید:",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"❌ خطا در ارسال منوی مشتری برای کاربر {user_id}: {e}")
