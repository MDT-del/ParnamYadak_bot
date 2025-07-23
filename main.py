# ---------------------------------------------
# فایل: main.py
# توضیح: فایل اصلی ربات با ساختار ماژولار و پشتیبانی از webhook/polling
# ---------------------------------------------

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import sys
import os
import socket

# اضافه کردن مسیر پروژه به sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# وارد کردن تنظیمات و هندلرها
from config import BotConfig
from handlers.auth_handlers import register_auth_handlers
from handlers.order_handlers import register_order_handlers
from handlers.support_handlers import register_support_handlers
from app.handlers.receipt_handlers import register_receipt_handlers
from dynamic_menu import get_main_menu
from polling_system import PollingSystem

def check_internet_connection():
    """بررسی اتصال اینترنت"""
    try:
        # تست اتصال به سرور تلگرام
        socket.create_connection(("api.telegram.org", 443), timeout=10)
        return True
    except OSError:
        return False

def setup_logging():
    """تنظیم سیستم لاگ"""
    # تنظیم فرمت فارسی برای لاگ
    class PersianFormatter(logging.Formatter):
        def format(self, record):
            # ترجمه سطوح لاگ به فارسی
            level_translations = {
                'DEBUG': 'اشکال‌زدایی',
                'INFO': 'اطلاعات',
                'WARNING': 'هشدار',
                'ERROR': 'خطا',
                'CRITICAL': 'بحرانی'
            }
            record.levelname = level_translations.get(record.levelname, record.levelname)
            return super().format(record)
    
    # پاک کردن تمام handler های قبلی برای جلوگیری از تکرار
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # تنظیم handler برای کنسول
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(PersianFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    console_handler.setLevel(logging.INFO)
    
    # تنظیم handler برای فایل
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setFormatter(PersianFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    file_handler.setLevel(logging.DEBUG)
    
    # تنظیم root logger
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    # تنظیم logger مخصوص ربات - بدون propagation
    bot_logger = logging.getLogger('bot')
    bot_logger.setLevel(logging.INFO)
    bot_logger.propagate = False  # جلوگیری از تکرار لاگ‌ها
    
    # تنظیم logger های دیگر هم بدون propagation
    for logger_name in ['polling_system', 'app.handlers.receipt_handlers', 'aiogram', 'root', 'bot']:
        logger = logging.getLogger(logger_name)
        logger.propagate = False
    
    return bot_logger

async def setup_bot_and_dispatcher():
    """تنظیم ربات و dispatcher"""
    logger = setup_logging()
    logger.info("🤖 سیستم لاگ ربات راه‌اندازی شد")
    
    # تنظیم ربات بدون پارامتر timeout (سازگار با aiogram v3)
    bot = Bot(token=BotConfig.BOT_TOKEN)
    dp = Dispatcher()
    
    # ثبت handlers
    register_auth_handlers(dp)
    register_order_handlers(dp)
    register_support_handlers(dp)
    register_receipt_handlers(dp)
    
    logger.info("✅ تمام handlers ثبت شدند")
    
    return bot, dp, logger

async def start_polling(bot: Bot, dp: Dispatcher, logger):
    """شروع polling ربات"""
    logger.info("🚀 شروع polling ربات...")
    
    max_retries = 5
    retry_delay = 10  # ثانیه
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 تلاش {attempt + 1} از {max_retries} برای اتصال به تلگرام...")
            
            # تست اتصال قبل از شروع polling
            me = await bot.get_me()
            logger.info(f"✅ اتصال به تلگرام برقرار شد. ربات: @{me.username}")
            
            # شروع polling
            await dp.start_polling(bot, skip_updates=True)
            break
            
        except Exception as e:
            logger.error(f"❌ خطا در تلاش {attempt + 1}: {e}")
            
            if attempt < max_retries - 1:
                logger.info(f"⏳ انتظار {retry_delay} ثانیه قبل از تلاش بعدی...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # افزایش زمان انتظار
            else:
                logger.error("❌ تمام تلاش‌ها ناموفق بود. ربات متوقف می‌شود.")
                raise

async def start_webhook(bot: Bot, dp: Dispatcher):
    """شروع webhook mode"""
    logging.info("[BOT] Starting in webhook mode...")
    
    try:
        # حذف webhook قبلی (در صورت وجود)
        await bot.delete_webhook(drop_pending_updates=True)
        
        # تنظیم webhook جدید
        webhook_url = f"{BotConfig.WEBHOOK_URL}{BotConfig.WEBHOOK_PATH}"
        await bot.set_webhook(webhook_url)
        logging.info(f"[BOT] Webhook set to: {webhook_url}")
        
        # ایجاد اپلیکیشن aiohttp
        app = web.Application()
        
        # تنظیم webhook handler
        webhook_requests_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
        )
        webhook_requests_handler.register(app, path=BotConfig.WEBHOOK_PATH)
        
        # تنظیم اپلیکیشن
        setup_application(app, dp, bot=bot)
        
        # اضافه کردن route برای health check
        async def health_check(request):
            return web.Response(text="Bot is running!")
        
        app.router.add_get('/health', health_check)
        
        # شروع سرور
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(
            runner, 
            host=BotConfig.WEBHOOK_HOST, 
            port=BotConfig.WEBHOOK_PORT
        )
        await site.start()
        
        logging.info(f"[BOT] Webhook server started on {BotConfig.WEBHOOK_HOST}:{BotConfig.WEBHOOK_PORT}")
        
        # نگه داشتن سرور
        try:
            await asyncio.Future()  # run forever
        except KeyboardInterrupt:
            logging.info("[BOT] Received interrupt signal")
        finally:
            await runner.cleanup()
            await bot.delete_webhook()
            
    except Exception as e:
        logging.error(f"[BOT] Error in webhook mode: {e}")
        raise

async def main():
    """تابع اصلی برای راه‌اندازی ربات"""
    try:
        # بررسی اتصال اینترنت
        logger = setup_logging()
        logger.info("🔍 بررسی اتصال اینترنت...")
        
        if not check_internet_connection():
            logger.error("❌ اتصال اینترنت برقرار نیست. لطفاً اتصال خود را بررسی کنید.")
            print("❌ اتصال اینترنت برقرار نیست. لطفاً اتصال خود را بررسی کنید.")
            return
        
        logger.info("✅ اتصال اینترنت برقرار است.")
        
        # تنظیم ربات و dispatcher
        bot, dp, logger = await setup_bot_and_dispatcher()
        
        # شروع سیستم polling برای بررسی وضعیت کاربران و سفارشات
        from polling_system import PollingSystem
        polling_system = PollingSystem(bot)
        
        # تنظیم مرجع سراسری برای استفاده در receipt handlers
        from app.handlers.receipt_handlers import set_global_polling_system
        set_global_polling_system(polling_system)
        
        logger.info("🤖 ربات با موفقیت استارت شد!")
        print("🤖 ربات با موفقیت استارت شد!")  # اضافه کردن print برای اطمینان
        
        from config import BotConfig
        if BotConfig.USE_WEBHOOK:
            # فقط وبهوک اجرا شود
            await start_webhook(bot, dp)
        else:
            # فقط پولینگ و سیستم پولینگ کاربران اجرا شود
            await asyncio.gather(
                start_polling(bot, dp, logger),
                polling_system.start_polling()
            )
        
    except Exception as e:
        print(f"❌ خطا در راه‌اندازی ربات: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("[BOT] Bot stopped by user")
    except Exception as e:
        logging.error(f"[BOT] Unexpected error: {e}")
        sys.exit(1)
