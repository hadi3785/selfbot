"""
ذخیره‌سازی گزارش فعالیت روزانه - از طریق Repository Layer.

شمارشِ پیام‌ها (record_message_activity) رو *هر* پیامِ ورودیِ گروه صدا می‌زنه؛
دقیقاً به‌همون دلیلی که bot/storage/stats_store.py توضیح داده (بدونِ query
اضافه به دیتابیس روی هر پیام)، این یکی هم سینک و فقط روی یه بافرِ درون‌حافظه‌ای
کار می‌کنه. flush_message_activity() - که توسطِ همون ورکرِ دوره‌ایِ
stats_saver در bot/handlers/stats.py صدا زده می‌شه - بافر رو تخلیه و در
PostgreSQL ذخیره می‌کنه. بقیه‌ی رویدادها (هشدار/حذف/عضوِ جدید/خارج‌شده) خیلی
کم‌تکرارترن (چندبار در روز، نه روی هر پیام) پس همچنان مستقیم و بی‌واسطه به
دیتابیس نوشته می‌شن.
"""
import datetime as dt
import logging
from typing import List, Optional

from ..repositories import activity_repo

logger = logging.getLogger("selfbot.storage.activity_store")

# (chat_id, "YYYY-MM-DD") -> تعدادِ پیامِ هنوز flush نشده
_pending_messages: dict[tuple[int, str], int] = {}


def record_message_activity(chat_id: int) -> None:
    """سینک - فقط بافرِ درون‌حافظه‌ای رو افزایش می‌ده، هیچ I/O ای انجام نمی‌ده."""
    date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    key = (chat_id, date)
    _pending_messages[key] = _pending_messages.get(key, 0) + 1


async def flush_message_activity() -> None:
    """بافرِ شمارشِ پیام‌ها رو در PostgreSQL ذخیره می‌کنه (هر STATS_SAVE_INTERVAL ثانیه)."""
    if not _pending_messages:
        return
    # اول بافر رو خالی می‌کنیم تا پیام‌های جدیدی که حین flush می‌رسن با نوبتِ
    # بعدی جمع بشن، نه این‌که موقعِ iterate کردن گم بشن یا دوبار شمرده بشن.
    items = list(_pending_messages.items())
    _pending_messages.clear()
    for (chat_id, date), count in items:
        try:
            await activity_repo.increment_messages(chat_id, count, date)
        except Exception:
            # برگرداندنِ شمارش به بافر تا دورِ بعد دوباره تلاش شود (عدمِ گم‌شدنِ آمار)
            _pending_messages[(chat_id, date)] = _pending_messages.get((chat_id, date), 0) + count
            logger.exception("خطا در ذخیره‌ی شمارشِ پیام‌های چت %s", chat_id)


async def increment_messages(chat_id: int, count: int = 1) -> None:
    """نوشتنِ مستقیم و بی‌واسطه (بدونِ بافر) - برای فراخوانی‌های کم‌تکرار/دستی."""
    return await activity_repo.increment_messages(chat_id, count)


async def increment_warnings(chat_id: int, count: int = 1) -> None:
    return await activity_repo.increment_warnings(chat_id, count)


async def increment_deleted(chat_id: int, count: int = 1) -> None:
    return await activity_repo.increment_deleted(chat_id, count)


async def increment_joined(chat_id: int, count: int = 1) -> None:
    return await activity_repo.increment_joined(chat_id, count)


async def increment_left(chat_id: int, count: int = 1) -> None:
    return await activity_repo.increment_left(chat_id, count)


def get_pending_message_count(chat_id: int) -> int:
    """تعدادِ پیام‌هایی که هنوز flush نشدن، برای «امروز» - برای گزارش‌های لحظه‌ای."""
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    return _pending_messages.get((chat_id, today), 0)


async def get_summary(chat_id: int, days: int = 7) -> dict:
    summary = await activity_repo.get_summary(chat_id, days)
    # پیام‌هایی که هنوز flush نشدن (تا ۶۰ ثانیه‌ی اخیر) رو هم برای «امروز» اضافه
    # می‌کنیم تا .گزارش/.آمارگراف حتی بینِ دو flush هم عددِ به‌روز نشون بده.
    pending_today = get_pending_message_count(chat_id)
    if pending_today:
        summary["total_messages"] += pending_today
    return summary