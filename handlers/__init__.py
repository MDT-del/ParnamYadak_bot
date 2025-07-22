# ---------------------------------------------
# فایل: handlers/__init__.py
# توضیح: ماژول هندلرهای ربات
# ---------------------------------------------

from .auth_handlers import register_auth_handlers
from .order_handlers import register_order_handlers
from .support_handlers import register_support_handlers

__all__ = [
    'register_auth_handlers',
    'register_order_handlers', 
    'register_support_handlers'
]
