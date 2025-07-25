# مدیریت وضعیت کاربران و مکانیک‌ها در ربات تلگرام پرنام یدک

# import بلااستفاده حذف شد

# مثال تابع مدیریت state (بقیه توابع بعداً اضافه می‌شوند)
async def get_user_state(user_id, storage):
    """دریافت وضعیت فعلی کاربر از storage"""
    return await storage.get_state(user=user_id)

async def set_user_state(user_id, state, storage):
    """تنظیم وضعیت جدید برای کاربر در storage"""
    await storage.set_state(user=user_id, state=state)

async def clear_user_state(user_id, storage):
    """پاک کردن وضعیت کاربر از storage"""
    await storage.reset_state(user=user_id)

# توابع state دیگر (مثلاً get_mechanic_state و ...) بعداً اضافه می‌شوند 

# متغیرهای حافظه
mechanic_order_userinfo = {}
customer_order_userinfo = {}
user_db = {}
user_statuses = {}

# وضعیت مکانیک‌ها (در حافظه)
mechanic_states = {}

# --- سفارش‌گذاری مکانیک و مشتری (بازنویسی شده) ---
mechanic_order_userinfo = {}
customer_order_userinfo = {}

# --- پشتیبانی و ثبت‌نام مشتری ---
support_states = {}
customer_register_states = {}
customer_order_states = {}

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import aiohttp
import os
import json

# وضعیت کاربر را از حافظه دریافت کن

def get_user_status(user_id: int):
    """دریافت وضعیت کاربر"""
    return user_statuses.get(user_id)

async def check_user_status_from_server(user_id: int):
    """بررسی وضعیت کاربر از سرور"""
    try:
        import os
        import aiohttp
        
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        
        # استفاده از endpoint جدید که هم مکانیک و هم مشتری را بررسی می‌کند
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PANEL_API_BASE_URL}/mechanics/api/user/status?telegram_id={user_id}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success'):
                        status_data = {
                            'status': data.get('status'),
                            'role': data.get('role')  # mechanic یا customer
                        }
                        # ذخیره در حافظه
                        set_user_status(user_id, data.get('role'), data.get('status'))
                        return status_data
                        
        return None
        
    except Exception as e:
        import logging
        logging.error(f"[STATE] Error checking user status from server: {e}")
        return None

def set_user_status(user_id: int, role: str, status: str):
    """تنظیم وضعیت کاربر با role و status جداگانه"""
    status_data = {
        'role': role,
        'status': status
    }
    user_statuses[user_id] = status_data
    import logging
    logging.info(f"[STATE] Set user {user_id} status: {status_data}")

def clear_user_status(user_id: int):
    """پاک کردن وضعیت کاربر از حافظه"""
    if user_id in user_statuses:
        del user_statuses[user_id]
        import logging
        logging.info(f"[STATE] Cleared user {user_id} status")

def get_pending_users():
    """دریافت لیست کاربران با وضعیت pending"""
    pending_users = []
    for user_id, data in user_statuses.items():
        if data.get('status') == 'pending':
            pending_users.append(user_id)
    return pending_users

def get_pending_orders():
    """دریافت لیست سفارشات در انتظار بررسی (فقط سفارشات غیر پرداخت شده)"""
    pending_orders = []
    
    # بررسی سفارشات مکانیک
    for user_id, order_data in mechanic_order_userinfo.items():
        status = order_data.get('status')
        # فقط سفارش‌هایی که هنوز در انتظار هستند (نه پرداخت شده)
        if status and status not in ['completed', 'پرداخت شده', 'payment_confirmed']:
            order_id = order_data.get('order_id')
            if order_id:
                pending_orders.append((order_id, user_id))
    
    # بررسی سفارشات مشتری
    for user_id, order_data in customer_order_userinfo.items():
        status = order_data.get('status')
        # فقط سفارش‌هایی که هنوز در انتظار هستند (نه پرداخت شده)
        if status and status not in ['completed', 'پرداخت شده', 'payment_confirmed']:
            order_id = order_data.get('order_id')
            if order_id:
                pending_orders.append((order_id, user_id))
    
    return pending_orders

def set_order_status(user_id: int, order_id: int, status: str):
    """تنظیم وضعیت سفارش"""
    # بررسی در سفارشات مکانیک
    if user_id in mechanic_order_userinfo:
        mechanic_order_userinfo[user_id]['status'] = status
        mechanic_order_userinfo[user_id]['order_id'] = order_id
        
        # اگر سفارش پرداخت شده یا تکمیل شده، آن را از لیست pending حذف کن
        if status in ['completed', 'پرداخت شده', 'payment_confirmed']:
            # حذف از mechanic_order_userinfo
            if user_id in mechanic_order_userinfo:
                del mechanic_order_userinfo[user_id]
    
    # بررسی در سفارشات مشتری
    if user_id in customer_order_userinfo:
        customer_order_userinfo[user_id]['status'] = status
        customer_order_userinfo[user_id]['order_id'] = order_id
        
        # اگر سفارش پرداخت شده یا تکمیل شده، آن را از لیست pending حذف کن
        if status in ['completed', 'پرداخت شده', 'payment_confirmed']:
            # حذف از customer_order_userinfo
            if user_id in customer_order_userinfo:
                del customer_order_userinfo[user_id]

def clear_completed_orders():
    """پاک کردن سفارش‌های تکمیل شده از حافظه"""
    # پاک کردن سفارشات مکانیک که تکمیل شده‌اند
    completed_mechanic_users = []
    for user_id, order_data in mechanic_order_userinfo.items():
        status = order_data.get('status')
        if status in ['completed', 'پرداخت شده', 'payment_confirmed']:
            completed_mechanic_users.append(user_id)
    
    for user_id in completed_mechanic_users:
        del mechanic_order_userinfo[user_id]
    
    # پاک کردن سفارشات مشتری که تکمیل شده‌اند
    completed_customer_users = []
    for user_id, order_data in customer_order_userinfo.items():
        status = order_data.get('status')
        if status in ['completed', 'پرداخت شده', 'payment_confirmed']:
            completed_customer_users.append(user_id)
    
    for user_id in completed_customer_users:
        del customer_order_userinfo[user_id]
    
    return len(completed_mechanic_users) + len(completed_customer_users)

def clear_user_order_state(user_id: int):
    """پاک کردن وضعیت سفارش کاربر از حافظه"""
    # پاک کردن از سفارشات مکانیک
    if user_id in mechanic_order_userinfo:
        del mechanic_order_userinfo[user_id]
    
    # پاک کردن از سفارشات مشتری
    if user_id in customer_order_userinfo:
        del customer_order_userinfo[user_id]
    
    import logging
    logging.info(f"[STATE] Cleared order state for user {user_id}")

# منوی داینامیک بر اساس وضعیت کاربر
def get_mechanic_state_local(user_id: int):
    """دریافت وضعیت محلی مکانیک از فایل JSON"""
    try:
        import json
        import os
        
        state_file = os.path.join(os.path.dirname(__file__), 'mechanic_state.json')
        
        if not os.path.exists(state_file):
            return None
            
        with open(state_file, 'r', encoding='utf-8') as f:
            states = json.load(f)
            
        return states.get(str(user_id))
        
    except Exception as e:
        import logging
        logging.error(f"[STATE_MANAGER] Error getting local mechanic state: {e}")
        return None

async def get_dynamic_menu(user_id: int):
    # ابتدا از حافظه محلی بررسی کن
    user = get_user_status(user_id)
    
    # اگر در حافظه نبود، از سرور دریافت کن
    if not user:
        user = await check_user_status_from_server(user_id)
    
    if not user:
        # کاربر ثبت‌نام نکرده
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🧑‍💼 ثبت‌نام مشتری"), KeyboardButton(text="🔧 ��بت‌نام مکانیک")]
            ],
            resize_keyboard=True
        )
    # کاربر ثبت‌نام کرده
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 سفارشات من"), KeyboardButton(text="📝 ثبت سفارش")],
            [KeyboardButton(text="💬 پشتیبانی")]
        ],
        resize_keyboard=True
    )

import os
import json

RECEIPT_STATE_FILE = os.path.join(os.path.dirname(__file__), 'receipt_state.json')

def get_receipt_state(user_id):
    """دریافت وضعیت انتظار رسید کاربر از فایل"""
    if not os.path.exists(RECEIPT_STATE_FILE):
        return None
    with open(RECEIPT_STATE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get(str(user_id))

def set_receipt_state(user_id, order_id):
    """تنظیم وضعیت انتظار رسید برای کاربر در فایل"""
    data = {}
    if os.path.exists(RECEIPT_STATE_FILE):
        with open(RECEIPT_STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    data[str(user_id)] = {
        'order_id': order_id,
        'state': 'await_receipt',
        'waiting_for_receipt': True
    }
    with open(RECEIPT_STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clear_receipt_state(user_id):
    """پاک کردن وضعیت انتظار رسید کاربر از فایل"""
    if not os.path.exists(RECEIPT_STATE_FILE):
        return
    with open(RECEIPT_STATE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if str(user_id) in data:
        del data[str(user_id)]
        with open(RECEIPT_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

# --- مدیریت سفارشات پرداخت شده ---
NOTIFIED_ORDERS_FILE = os.path.join(os.path.dirname(__file__), 'notified_orders.json')

def is_order_payment_notified(order_id):
    """بررسی اینکه آیا سفارش قبلاً پرداخت شده اطلاع‌رسانی شده"""
    if not os.path.exists(NOTIFIED_ORDERS_FILE):
        return False
    
    try:
        with open(NOTIFIED_ORDERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return str(order_id) in data.get('notified_orders', [])
    except Exception as e:
        import logging
        logging.error(f"Error checking notified orders: {e}")
        return False

def mark_order_payment_notified(order_id):
    """علامت‌گذاری سفارش به عنوان پرداخت شده اطلاع‌رسانی شده"""
    data = {'notified_orders': []}
    
    if os.path.exists(NOTIFIED_ORDERS_FILE):
        try:
            with open(NOTIFIED_ORDERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {'notified_orders': []}
    
    if 'notified_orders' not in data:
        data['notified_orders'] = []
    
    if str(order_id) not in data['notified_orders']:
        data['notified_orders'].append(str(order_id))
        
        # نگه داشتن فقط 1000 سفارش اخیر برای جلوگیری از بزرگ شدن فایل
        if len(data['notified_orders']) > 1000:
            data['notified_orders'] = data['notified_orders'][-1000:]
        
        try:
            with open(NOTIFIED_ORDERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            import logging
            logging.info(f"✅ سفارش {order_id} به عنوان پرداخت شده اطلاع‌رسانی شده علامت‌گذاری شد")
        except Exception as e:
            import logging
            logging.error(f"Error marking order as notified: {e}")

def get_notified_orders():
    """دریافت لیست سفارشات اطلاع‌رسانی شده"""
    if not os.path.exists(NOTIFIED_ORDERS_FILE):
        return []
    
    try:
        with open(NOTIFIED_ORDERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('notified_orders', [])
    except Exception as e:
        import logging
        logging.error(f"Error getting notified orders: {e}")
        return []