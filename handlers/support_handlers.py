# ---------------------------------------------
# فایل: handlers/support_handlers.py
# توضیح: هندلرهای پشتیبانی
# ---------------------------------------------

from aiogram import types, F

async def simple_support_handler(message: types.Message):
    """هندلر پشتیبانی ساده"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        if not message or not hasattr(message, 'from_user') or not message.from_user:
            logger.error("Invalid message format in support handler")
            return
            
        user_id = message.from_user.id
        logger.info(f"Support request from user {user_id}")
        
        # بررسی وضعیت کاربر
        from app.state_manager import get_mechanic_state_local
        state = get_mechanic_state_local(user_id)
        
        logger.info(f"User {user_id} state: {state}")
        
        # متن پیش‌فرض پشتیبانی
        support_text = (
            "🤝 پشتیبانی پرنام یدک\n\n"
            "برای ارتباط با پشتیبانی می‌توانید با شماره‌های زیر تماس حاصل فرمایید:\n\n"
            "📞 09185296330 - قادری\n\n"
            "📞 09960449631 - صیدی\n\n"
            "\n📌 ساعات پاسخگویی: 9 صبح تا 10 شب"
        )
        
        # اگر کاربر در حال انتظار رسید پرداخت است، پیام مخصوص نمایش داده شود
        if state and state.get("step") == "await_receipt":
            support_text += (
                "\n\n⚠️ توجه: شما در حال حاضر در انتظار تایید رسید پرداخت هستید. "
                "لطفاً فقط در صورت لزوم با پشتیبانی تماس بگیرید."
            )
        
        await message.answer(support_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in support handler: {e}", exc_info=True)
        await message.answer("⛔ خطا در نمایش اطلاعات پشتیبانی. لطفاً دقایقی دیگر مجدداً تلاش کنید.")

def register_support_handlers(dp):
    """ثبت هندلرهای پشتیبانی"""
    dp.message.register(simple_support_handler, F.text == "📞 پشتیبانی")
