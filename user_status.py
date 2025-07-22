#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مدیریت وضعیت کاربران ربات
"""

import json
import os
import logging
from typing import Dict, List, Tuple, Optional

# تنظیم لاگر
logger = logging.getLogger(__name__)

# مسیر فایل ذخیره وضعیت کاربران
USER_STATUS_FILE = os.path.join(os.path.dirname(__file__), 'user_status.json')

def load_user_statuses() -> Dict:
    """بارگیری وضعیت کاربران از فایل"""
    try:
        if os.path.exists(USER_STATUS_FILE):
            with open(USER_STATUS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        logger.error(f"❌ خطا در بارگیری وضعیت کاربران: {e}")
        return {}

def save_user_statuses(statuses: Dict):
    """ذخیره وضعیت کاربران در فایل"""
    try:
        with open(USER_STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(statuses, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره وضعیت کاربران: {e}")

def get_user_status(user_id: int) -> Optional[Dict]:
    """دریافت وضعیت یک کاربر"""
    try:
        statuses = load_user_statuses()
        return statuses.get(str(user_id))
    except Exception as e:
        logger.error(f"❌ خطا در دریافت وضعیت کاربر {user_id}: {e}")
        return None

def set_user_status(user_id: int, user_type: str, status: str):
    """تنظیم وضعیت یک کاربر"""
    try:
        statuses = load_user_statuses()
        statuses[str(user_id)] = {
            'type': user_type,  # 'mechanic' or 'customer'
            'status': status,   # 'pending', 'approved', 'rejected'
            'updated_at': str(int(time.time()))
        }
        save_user_statuses(statuses)
        logger.info(f"✅ وضعیت کاربر {user_id} به {user_type}/{status} تغییر کرد")
    except Exception as e:
        logger.error(f"❌ خطا در تنظیم وضعیت کاربر {user_id}: {e}")

def get_pending_users() -> List[Tuple[int, str]]:
    """دریافت لیست کاربران با وضعیت pending"""
    try:
        statuses = load_user_statuses()
        pending_users = []
        
        for user_id_str, user_data in statuses.items():
            if user_data.get('status') == 'pending':
                user_id = int(user_id_str)
                user_type = user_data.get('type')
                pending_users.append((user_id, user_type))
        
        return pending_users
    except Exception as e:
        logger.error(f"❌ خطا در دریافت کاربران pending: {e}")
        return []

def is_user_approved(user_id: int) -> bool:
    """بررسی اینکه آیا کاربر تایید شده است"""
    try:
        user_status = get_user_status(user_id)
        return user_status and user_status.get('status') == 'approved'
    except Exception as e:
        logger.error(f"❌ خطا در بررسی تایید کاربر {user_id}: {e}")
        return False

def get_user_type(user_id: int) -> Optional[str]:
    """دریافت نوع کاربر (mechanic یا customer)"""
    try:
        user_status = get_user_status(user_id)
        return user_status.get('type') if user_status else None
    except Exception as e:
        logger.error(f"❌ خطا در دریافت نوع کاربر {user_id}: {e}")
        return None

def remove_user_status(user_id: int):
    """حذف وضعیت یک کاربر"""
    try:
        statuses = load_user_statuses()
        if str(user_id) in statuses:
            del statuses[str(user_id)]
            save_user_statuses(statuses)
            logger.info(f"✅ وضعیت کاربر {user_id} حذف شد")
    except Exception as e:
        logger.error(f"❌ خطا در حذف وضعیت کاربر {user_id}: {e}")

# اضافه کردن import time
import time
