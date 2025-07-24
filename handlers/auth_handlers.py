# ---------------------------------------------
# فایل: handlers/auth_handlers.py
# توضیح: هندلرهای احراز هویت و ثبت‌نام
# ---------------------------------------------

import logging
from aiogram import types, F
from aiogram.filters import Command, CommandObject
from app.state_manager import (
    get_user_status, set_user_status, check_user_status_from_server, 
    get_dynamic_menu, mechanic_states, customer_register_states
)
from app.utils import format_amount
import aiohttp
import requests
import ssl
import os

async def check_and_update_user_status_from_panel(user_id: int):
    """بررسی و به‌روزرسانی وضعیت کاربر از پنل"""
    import requests
    from app.state_manager import set_user_status
    
    panel_api_base_url = os.getenv("PANEL_API_BASE_URL")
    logging.info(f"🌐 PANEL_API_BASE_URL: {panel_api_base_url}")
    
    if not panel_api_base_url:
        logging.warning("⚠️ PANEL_API_BASE_URL تنظیم نشده")
        return
    
    try:
        # استفاده از endpoint جدید که هم مکانیک و هم مشتری را بررسی می‌کند
        user_url = f"{panel_api_base_url}/mechanics/api/user/status?telegram_id={user_id}"
        logging.info(f"👤 Checking user API: {user_url}")
        
        try:
            user_response = requests.get(user_url, timeout=5)
            logging.info(f"📊 User API response: {user_response.status_code}")
            
            if user_response.status_code == 200:
                data = user_response.json()
                logging.info(f"📊 User data: {data}")
                
                # بررسی success و status
                if data.get('success'):
                    status = data.get('status', 'pending')
                    role = data.get('role', 'customer')
                    logging.info(f"📊 User status: {status}, role: {role}")
                    
                    if status in ['approved', 'rejected', 'pending']:
                        set_user_status(user_id, role, status)
                        logging.info(f"✅ وضعیت کاربر {user_id} به‌روزرسانی شد: {role} - {status}")
                        return
                else:
                    logging.info(f"❌ User API success=false: {data}")
            else:
                logging.info(f"❌ User API returned {user_response.status_code}: {user_response.text[:200]}")
                
        except Exception as e:
            logging.info(f"❌ User API error: {e}")
            
        # اگر هیچ وضعیتی پیدا نشد، کاربر جدید است
        logging.info(f"🆕 کاربر {user_id} جدید است - هیچ وضعیتی در پنل پیدا نشد")
        
    except Exception as e:
        logging.error(f"❌ خطا در بررسی وضعیت کاربر {user_id} از پنل: {e}")

async def start_handler(message: types.Message):
    """هندلر شروع ربات با بررسی وضعیت از پنل"""
    import os
    import requests
    from dynamic_menu import get_main_menu, get_status_message
    from app.state_manager import set_user_status
    
    user_id = message.from_user.id
    logging.info(f"🚀 Start handler called for user {user_id}")
    
    # پیام خوش‌آمدگویی
    await message.answer("🔧 سلام! به ربات نیکا یدک خوش آمدید")
    
    # بررسی وضعیت کاربر از پنل
    logging.info(f"🔍 Checking user {user_id} status from panel...")
    await check_and_update_user_status_from_panel(user_id)
    
    # نمایش منوی داینامیک (فقط یکبار)
    menu = get_main_menu(user_id)
    await message.answer("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=menu)

async def status_check_handler(message: types.Message):
    """هندلر بررسی وضعیت ثبت‌نام"""
    from dynamic_menu import get_status_message, get_main_menu
    
    user_id = message.from_user.id
    
    # نمایش وضعیت کاربر
    status_message = get_status_message(user_id)
    await message.answer(status_message)
    
    # نمایش منوی به‌روزشده
    menu = get_main_menu(user_id)
    await message.answer("منوی اصلی:", reply_markup=menu)

async def mechanic_register_start(message: types.Message):
    """شروع ثبت‌نام مکانیک"""
    logger = logging.getLogger(__name__)
    
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        logger.error("❌ پیام نامعتبر در mechanic_register_start")
        return
    user = message.from_user
    if not user or not hasattr(user, 'id') or user.id is None:
        logger.error("❌ کاربر نامعتبر در mechanic_register_start")
        await message.answer("خطا: کاربر معتبر نیست.")
        return
    
    logger.info(f"🎆 شروع ثبت‌نام مکانیک برای کاربر {user.id}")
    mechanic_states[user.id] = {"step": "full_name", "data": {}}
    logger.info(f"📋 حالت مکانیک {user.id} ذخیره شد - حالت‌های فعلی: {list(mechanic_states.keys())}")
    await message.answer("لطفاً نام کامل خود را وارد کنید:")

async def mechanic_register_process(message: types.Message):
    """پردازش ثبت‌نام مکانیک"""
    logger = logging.getLogger(__name__)
    
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        logger.error("❌ پیام نامعتبر در mechanic_register_process")
        return
    user = message.from_user
    if not user or not hasattr(user, 'id') or user.id is None:
        logger.error("❌ کاربر نامعتبر در mechanic_register_process")
        return
    
    logger.info(f"📝 پردازش پیام برای مکانیک {user.id}: '{message.text}'")
    
    state = mechanic_states.get(user.id)
    if not state:
        logger.warning(f"⚠️ حالت مکانیک {user.id} یافت نشد - حالت‌های موجود: {list(mechanic_states.keys())}")
        return
    
    step = state["step"]
    data = state["data"]
    logger.info(f"🔄 مرحله فعلی مکانیک {user.id}: {step}")
    
    if step == "full_name":
        if hasattr(message, 'text') and message.text:
            data["full_name"] = message.text.strip()
            state["step"] = "mobile"
            await message.answer("لطفاً شماره موبایل خود را وارد کنید:")
    elif step == "mobile":
        if hasattr(message, 'text') and message.text:
            data["mobile"] = message.text.strip()
            state["step"] = "card_number"
            await message.answer("💳 لطفاً شماره کارت بانکی خود را وارد کنید:")
    elif step == "card_number":
        if hasattr(message, 'text') and message.text:
            data["card_number"] = message.text.strip()
            state["step"] = "sheba_number"
            await message.answer("🏦 لطفاً شماره شبا خود را وارد کنید:")
    elif step == "sheba_number":
        if hasattr(message, 'text') and message.text:
            data["sheba_number"] = message.text.strip()
            state["step"] = "address"
            await message.answer("لطفاً آدرس کامل تعمیرگاه خود را وارد کنید:")
    elif step == "address":
        if hasattr(message, 'text') and message.text:
            data["address"] = message.text.strip()
            state["step"] = "business_license"
            logger.info(f"📝 آدرس مکانیک {user.id} دریافت شد: {data['address']}")
            await message.answer("📜 حالا لطفاً عکس جواز کسب خود را ارسال کنید:")
    elif step == "business_license":
        if hasattr(message, 'photo') and message.photo:
            # دریافت عکس جواز کسب
            photo = message.photo[-1]  # بزرگترین سایز عکس
            data["business_license_file_id"] = photo.file_id
            logger.info(f"📷 عکس جواز کسب مکانیک {user.id} دریافت شد: {photo.file_id}")
            # ارسال اطلاعات به API
            await submit_mechanic_registration(message, user.id, data)
            mechanic_states.pop(user.id, None)
        else:
            logger.warning(f"⚠️ مکانیک {user.id} عکس ارسال نکرد")
            await message.answer("⚠️ لطفاً عکس جواز کسب خود را ارسال کنید.")

async def submit_mechanic_registration(message, user_id, data):
    """ارسال اطلاعات ثبت‌نام مکانیک به پنل"""
    logger = logging.getLogger(__name__)
    PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
    
    # بررسی کامل بودن اطلاعات (بر اساس مدل پنل)
    required_fields = ['full_name', 'mobile', 'card_number', 'sheba_number', 'address', 'business_license_file_id']
    missing_fields = []
    
    # لاگ کردن تمام اطلاعات دریافتی برای اشکال‌زدایی
    logger.info(f"🔍 بررسی اطلاعات دریافتی برای مکانیک {user_id}:")
    for field in required_fields:
        value = data.get(field, 'موجود نیست')
        logger.info(f"  - {field}: '{value}'")
        if not data.get(field) or (isinstance(data.get(field), str) and not data.get(field).strip()):
            missing_fields.append(field)
    
    if missing_fields:
        logger.error(f"⚠️ فیلدهای ناقص برای مکانیک {user_id}: {missing_fields}")
        logger.error(f"📋 تمام اطلاعات موجود: {data}")
        await message.answer(f"⚠️ اطلاعات ناقص است. فیلدهای مفقود: {', '.join(missing_fields)}\nلطفاً مجدداً تلاش کنید.")
        return
    
    # تقسیم نام کامل به نام و نام خانوادگی
    full_name = data.get('full_name', '').strip()
    name_parts = full_name.split(' ', 1)
    first_name = name_parts[0] if name_parts else ''
    last_name = name_parts[1] if len(name_parts) > 1 else ''
    
    payload = {
        'telegram_id': user_id,
        'first_name': first_name,
        'last_name': last_name,
        'phone_number': data.get('mobile', '').strip(),
        'card_number': data.get('card_number', '').strip(),
        'sheba_number': data.get('sheba_number', '').strip(),
        'shop_address': data.get('address', '').strip(),
        'username': message.from_user.username or ''
    }
    
    logger.info(f"📝 ارسال درخواست ثبت‌نام مکانیک {user_id} به پنل...")
    logger.info(f"📋 Payload: {payload}")
    
    try:
        # دانلود عکس جواز کسب از تلگرام
        bot_instance = message.bot
        file_info = await bot_instance.get_file(data.get('business_license_file_id'))
        file_path = file_info.file_path
        file_url = f"https://api.telegram.org/file/bot{bot_instance.token}/{file_path}"
        
        # دانلود فایل
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(file_url) as resp:
                if resp.status == 200:
                    file_content = await resp.read()
                    file_extension = file_path.split('.')[-1] if '.' in file_path else 'jpg'
                    filename = f"license_{user_id}.{file_extension}"
                    
                    # ارسال به پنل با multipart/form-data
                    files = {
                        'business_license_image': (filename, file_content, f'image/{file_extension}')
                    }
                    
                    # حذف file_id از payload و اضافه کردن سایر فیلدها
                    form_data = payload.copy()
                    
                    response = requests.post(
                        f"{PANEL_API_BASE_URL}/mechanics/api/register",
                        data=form_data,
                        files=files,
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        resp_data = response.json()
                        if resp_data.get('success'):
                            mechanic_id = resp_data.get('id')  # API returns 'id' not 'mechanic_id'
                            set_user_status(user_id, "mechanic", "pending")
                            logger.info(f"✅ ثبت‌نام مکانیک {user_id} موفقیت‌آمیز بود - شناسه: {mechanic_id}")
                            
                            # ارسال نوتیفیکیشن به پنل
                            try:
                                notification_data = {
                                    'mechanic_id': mechanic_id,
                                    'telegram_id': user_id,
                                    'first_name': data.get('first_name', ''),
                                    'last_name': data.get('last_name', ''),
                                    'phone_number': data.get('phone_number', '')
                                }
                                notification_response = requests.post(
                                    f"{PANEL_API_BASE_URL}/notifications/api/mechanic-registered",
                                    json=notification_data,
                                    timeout=10
                                )
                                if notification_response.status_code == 200:
                                    logger.info(f"📢 نوتیفیکیشن ثبت‌نام مکانیک {user_id} (ID: {mechanic_id}) به پنل ارسال شد")
                                else:
                                    logger.error(f"❌ خطا در ارسال نوتیفیکیشن به پنل: {notification_response.status_code}")
                            except Exception as e:
                                logger.error(f"❌ خطا در ارسال نوتیفیکیشن به پنل: {e}")
                            
                            await message.answer("✅ اطلاعات شما با موفقیت ثبت شد. منتظر تایید ادمین باشید.")
                        else:
                            error_msg = resp_data.get('message', 'خطای نامشخص')
                            logger.error(f"❌ خطا در ثبت‌نام مکانیک {user_id}: {error_msg}")
                            await message.answer(f"❌ خطا در ثبت‌نام: {error_msg}")
                    else:
                        logger.error(f"❌ خطا در ارسال درخواست به پنل - کد وضعیت: {response.status_code}")
                        try:
                            error_data = response.json()
                            error_msg = error_data.get('message', 'خطای نامشخص')
                        except:
                            error_msg = f"خطای HTTP {response.status_code}"
                        await message.answer(f"❌ خطا در ثبت‌نام: {error_msg}")
                else:
                    logger.error(f"❌ خطا در ارتباط با پنل - کد وضعیت: {resp.status}")
                    await message.answer("❌ خطا در ارتباط با سرور. لطفاً مجدداً تلاش کنید.")
    except Exception as e:
        logger.error(f"💥 خطای غیرمنتظره در ثبت‌نام مکانیک {user_id}: {e}")
        await message.answer("❌ خطا در ارتباط با سرور. لطفاً مجدداً تلاش کنید.")

async def customer_register_start(message: types.Message):
    """شروع ثبت‌نام مشتری"""
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        return
    user_id = getattr(getattr(message, 'from_user', None), 'id', None)
    if user_id is None:
        return
    customer_register_states[user_id] = {'step': 'first_name', 'data': {}}
    await message.answer("لطفاً نام خود را وارد کنید:")

async def customer_register_process(message: types.Message):
    """پردازش ثبت‌نام مشتری"""
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        return
    user_id = getattr(getattr(message, 'from_user', None), 'id', None)
    if user_id is None:
        return
    if user_id not in customer_register_states:
        return
    state = customer_register_states[user_id]
    step = state['step']
    data = state['data']
    
    if step == 'first_name':
        data['first_name'] = message.text.strip()
        state['step'] = 'phone_number'
        await message.answer("شماره تلفن خود را وارد کنید:")
    elif step == 'phone_number':
        data['phone_number'] = message.text.strip()
        state['step'] = 'province'
        await message.answer("استان خود را وارد کنید:")
    elif step == 'province':
        data['province'] = message.text.strip()
        state['step'] = 'city'
        await message.answer("شهر خود را وارد کنید:")
    elif step == 'city':
        data['city'] = message.text.strip()
        state['step'] = 'postal_code'
        await message.answer("کد پستی خود را وارد کنید:")
    elif step == 'postal_code':
        data['postal_code'] = message.text.strip()
        state['step'] = 'address'
        await message.answer("آدرس کامل خود را وارد کنید:")
    elif step == 'address':
        data['address'] = message.text.strip()
        # ارسال اطلاعات به API
        await customer_register_submit(message, user_id, data)
        customer_register_states.pop(user_id, None)

async def customer_register_submit(message, user_id, data):
    """ارسال اطلاعات ثبت‌نام مشتری به پنل"""
    PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
    payload = {
        'telegram_id': user_id,
        'first_name': data.get('first_name', ''),
        'last_name': '',  # اضافه کردن last_name
        'phone_number': data.get('phone_number', ''),
        'province': data.get('province', ''),
        'city': data.get('city', ''),
        'postal_code': data.get('postal_code', ''),
        'address': data.get('address', ''),  # اضافه کردن آدرس
        'username': message.from_user.username or ''
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{PANEL_API_BASE_URL}/customers/api/register", json=payload) as resp:
                if resp.status == 200:
                    resp_data = await resp.json()
                    if resp_data.get('success'):
                        # پیام تبریک و منو داینامیک
                        await message.answer("🎉 ثبت‌نام شما با موفقیت انجام شد! به خانواده پارنام یدک خوش آمدید.")
                        await message.answer("از منوی زیر یکی از گزینه‌ها را انتخاب کنید:", reply_markup=await get_dynamic_menu(user_id))
                    else:
                        await message.answer(f"خطا در ثبت‌نام: {resp_data.get('message', '')}")
                else:
                    await message.answer("خطا در ارتباط با سرور. لطفاً مجدداً تلاش کنید.")
    except Exception as e:
        await message.answer("خطا در ارتباط با سرور.")

async def approve_handler(message: types.Message, command: CommandObject):
    """تایید مکانیک توسط ادمین"""
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        return
    user = message.from_user
    if not user or not hasattr(user, 'id') or user.id is None:
        return
    if not command.args or not command.args.isdigit():
        await message.answer("فرمت صحیح: /approve <user_id>")
        return
    user_id = int(command.args)
    set_user_status(user_id, "mechanic", "approved")
    try:
        # دریافت اطلاعات مکانیک از پنل برای نمایش درصد کمیسیون
        PANEL_API_BASE_URL = os.getenv("PANEL_API_BASE_URL")
        commission_percent = "N/A"
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{PANEL_API_BASE_URL}/mechanics/api/status?telegram_id={user_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('success') and data.get('data'):
                            commission_percent = data['data'].get('commission_percent', 'N/A')
        except Exception as e:
            logging.warning(f"[BOT] Could not fetch commission percent for mechanic {user_id}: {e}")
        
        # پیام تایید با درصد کمیسیون
        approval_message = f"✅ اطلاعات شما توسط ادمین تایید شد!\n\n💰 درصد کمیسیون شما: {commission_percent}%\n\nاکنون می‌توانید از منوی زیر استفاده کنید:"
        
        # ارسال پیام با منوی داینامیک
        await message.bot.send_message(user_id, approval_message, reply_markup=await get_dynamic_menu(user_id))
        
        logging.info(f"[BOT] Approval sent to mechanic: telegram_id={user_id}, commission={commission_percent}%")
        await message.answer(f"کاربر {user_id} تایید شد و پیام با درصد کمیسیون {commission_percent}% ارسال شد.")
    except Exception as e:
        logging.error(f"[BOT] Error sending approval to mechanic: {e}")
        await message.answer(f"خطا در ارسال پیام به کاربر: {e}")

async def reject_handler(message: types.Message, command: CommandObject):
    """رد مکانیک توسط ادمین"""
    if not message or not hasattr(message, 'from_user') or not hasattr(message.from_user, 'id') or not hasattr(message, 'answer'):
        return
    user = message.from_user
    if not user or not hasattr(user, 'id') or user.id is None:
        return
    if not command.args or not command.args.isdigit():
        await message.answer("فرمت صحیح: /reject <user_id>")
        return
    user_id = int(command.args)
    set_user_status(user_id, "mechanic", "rejected")
    try:
        await message.bot.send_message(user_id, "❌ اطلاعات شما توسط ادمین رد شد. برای پیگیری با پشتیبانی تماس بگیرید.", reply_markup=await get_dynamic_menu(user_id))
        logging.info(f"[BOT] Rejection sent to mechanic: telegram_id={user_id}")
        await message.answer(f"کاربر {user_id} رد شد و پیام ارسال شد.")
    except Exception as e:
        logging.error(f"[BOT] Error sending rejection to mechanic: {e}")
        await message.answer(f"خطا در ارسال پیام به کاربر: {e}")

# Support handler حذف شد - از support_handlers.py استفاده می‌شود

def register_auth_handlers(dp):
    """ثبت هندلرهای احراز هویت"""
    dp.message.register(start_handler, Command("start"))
    dp.message.register(status_check_handler, F.text == "⏳ وضعیت ثبت‌نام")
    
    # دکمه‌های ثبت‌نام - با متن صحیح از dynamic_menu
    dp.message.register(mechanic_register_start, F.text == "👨‍🔧 ثبت‌نام مکانیک")
    dp.message.register(customer_register_start, F.text == "👤 ثبت‌نام مشتری")
    
    # دکمه پشتیبانی - از support_handlers.py استفاده می‌شود
    try:
        from handlers.support_handlers import simple_support_handler
        dp.message.register(simple_support_handler, F.text == "📞 پشتیبانی")
    except ImportError:
        logging.warning("Support handlers not found, skipping support button registration")
    
    # هندلرهای پردازش ثبت‌نام (متن و عکس) - با فیلتر دقیق‌تر
    dp.message.register(mechanic_register_process, lambda m: m and hasattr(m, 'from_user') and m.from_user and hasattr(m.from_user, 'id') and m.from_user.id in mechanic_states and ((hasattr(m, 'text') and m.text and not m.text.startswith("/") and m.text not in ["📝 ثبت سفارش", "📦 سفارشات من", "📞 پشتیبانی"]) or (hasattr(m, 'photo') and m.photo)))
    dp.message.register(customer_register_process, lambda m: m and hasattr(m, 'from_user') and m.from_user and hasattr(m.from_user, 'id') and m.from_user.id in customer_register_states and hasattr(m, 'text') and m.text and not m.text.startswith("/") and m.text not in ["📝 ثبت سفارش", "📦 سفارشات من", "📞 پشتیبانی"])
    
    # هندلرهای ادمین
    dp.message.register(approve_handler, Command("approve"))
    dp.message.register(reject_handler, Command("reject"))
