# ---------------------------------------------
# فایل: config.py
# توضیح: تنظیمات و پیکربندی ربات
# ---------------------------------------------

import os
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
load_dotenv("bot_config.env")

class BotConfig:
    """کلاس تنظیمات ربات"""
    
    # تنظیمات اصلی
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
    
    # تنظیمات وبهوک
    USE_WEBHOOK = os.getenv("USE_WEBHOOK", "False").lower() == "true"
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))
    
    # تنظیمات لاگ
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def validate(cls):
        """اعتبارسنجی تنظیمات"""
        if not cls.BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        if not cls.PANEL_API_BASE_URL:
            raise ValueError("PANEL_API_BASE_URL is required")
        if cls.USE_WEBHOOK and not cls.WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL is required when USE_WEBHOOK is True")
        return True
