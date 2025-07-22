# توابع کمکی عمومی برای ربات تلگرام پرنام یدک

def format_amount(amount):
    """فرمت کردن مبلغ به صورت 1,234,567"""
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)

# توابع کمکی دیگر را بعداً اضافه می‌کنم 