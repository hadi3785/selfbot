"""
تستدیقات ورودی برای دستورات سلف‌بات.
تستدیقات امنیتی برای جلوگیری از حملات استفاده کننده‌ان.
"""
import re
from typing import Optional


def validate_time_format(time_str: str) -> bool:
    """بررسی از معتبر بودن فرمت HH:MM."""
    return bool(re.match(r"^(\d{1,2}):(\d{2})$", time_str.strip()))


def validate_date_format(date_str: str) -> bool:
    """بررسی از معتبر بودن فرمت YYYY-MM-DD."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", date_str.strip()))


def sanitize_text(text: str, max_length: int = 4000) -> str:
    """پاکسازی متن برای ارسال تلگرام."""
    if not text:
        return ""
    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length] + "..."
    return text


def validate_chat_id(chat_id) -> Optional[int]:
    """تستدیق و تبدیل عددی chat_id."""
    try:
        cid = int(chat_id)
        if cid == 0:
            return None
        return cid
    except (TypeError, ValueError):
        return None


def validate_username(username: str) -> bool:
    """بررسی از معتبر بودن نام کاربری."""
    if not username:
        return False
    # نام کاربری تلگرام: 5-32 کاراکتر از حروف لاتین و اعداد اضافی
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9_]{4,31}$", username))


def validate_command_args(args: str, min_length: int = 1, max_length: int = 1000) -> bool:
    """بررسی از آرگومان دستور."""
    if not args:
        return min_length == 0
    args = args.strip()
    return min_length <= len(args) <= max_length
