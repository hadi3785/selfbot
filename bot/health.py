"""
Health Monitor - وضعیت سنجی تمام بخش‌های سلف‌بات.

نمایش وضعیت هر Worker و سرویس متصل (Telegram, PostgreSQL, AI) - و همه‌ی
Workerهای پس‌زمینه به‌صورتِ خودکار/پویا (نه یه لیستِ ثابت)، از رویِ همون
چیزی که خودشون از طریقِ update_worker_status() گزارش می‌دن. برای این‌که یه
Worker جدید توی `.سلامت` دیده بشه، کافیه از همون تابع استفاده کنه - نیازی
به دست‌زدن به این فایل نیست؛ فقط برای یه اسمِ نمایشیِ بهتر (به‌جایِ خودِ
کلیدِ داخلی) می‌تونی به WORKER_DISPLAY_NAMES یه ورودی اضافه کنی.
"""

import time
import logging
from typing import Dict, Any, Optional

from sqlalchemy import text

from . import runtime, config
from .db.engine import session_scope

logger = logging.getLogger("selfbot.health")

# ذخیره آخرین وضعیت هر سرویس برای تشخیص تغییرات
_last_health: Dict[str, Any] = {}
_worker_status: Dict[str, Dict[str, Any]] = {}

# یه Worker اگه بیش از این مدت (ثانیه) هیچ تیکی نزنه، «مرده» حساب می‌شه.
# همه‌ی Workerهای فعلی حداکثر هر ۶۰ ثانیه یک‌بار تیک می‌زنن، پس ۳۰۰ ثانیه
# (۵ برابرِ کندترینِ فاصله) یه حاشیه‌ی امنِ معقوله.
WORKER_STALE_SECONDS = 300

WORKER_DISPLAY_NAMES = {
    "scheduler": "Scheduler",
    "autopost": "Autopost",
    "assistant": "Assistant",
    "stats": "Statistics",
    "daily_digest": "Daily Digest",
    "message_tracker_cleanup": "Message Tracker",
    "price_alert": "Price Alerts",
}


def get_uptime() -> str:
    """زمان اجرای سلف‌بات از شروع."""
    elapsed = time.time() - runtime.START_TIME
    days = int(elapsed // 86400)
    hours = int((elapsed % 86400) // 3600)
    minutes = int((elapsed % 3600) // 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"


def format_status(status: bool) -> str:
    return "🟢 OK" if status else "🔴 FAIL"


async def check_telegram() -> bool:
    """بررسی اتصال به تلگرام با ارسال درخواست ساده."""
    try:
        me = await runtime.client.get_me()
        return me is not None
    except Exception:
        return False


async def check_postgresql() -> bool:
    """بررسی اتصال به PostgreSQL."""
    try:
        async with session_scope() as session:
            # یک کوئری ساده برای تست اتصال
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False


async def check_ai() -> bool:
    """بررسی در دسترس‌بودن سرویس AI (فقط اگه API Key تنظیم شده)."""
    if not config.AI_API_KEY:
        return True  # غیرفعال ولی مشکل نداره
    try:
        from . import ai
        # یک درخواست کوچک برای تست
        await ai.ask_ai(
            [{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        return True
    except Exception:
        return False


def check_worker(worker_name: str) -> bool:
    """
    یه Worker رو «سالم» حساب می‌کنه اگه: (۱) حداقل یه‌بار توی
    WORKER_STALE_SECONDS ثانیه‌ی اخیر تیک زده باشه، *و* (۲) آخرین تیکش
    status="error" نبوده باشه - قبلاً فقط شرطِ (۱) چک می‌شد، یعنی Workerی
    که هر دور با خطا مواجه می‌شه ولی هنوز «زنده»ست (تیک می‌زنه) همیشه 🟢
    نشون داده می‌شد، حتی وقتی هر بار fail می‌کرد.
    """
    info = _worker_status.get(worker_name, {})
    last_run = info.get("last_run")
    if last_run is None:
        return False
    if time.time() - last_run > WORKER_STALE_SECONDS:
        return False
    if info.get("status") == "error":
        return False
    return True


async def get_health_report() -> Dict[str, Any]:
    """گزارش کامل وضعیت سلامت."""
    results = {
        "telegram": await check_telegram(),
        "postgresql": await check_postgresql(),
        "ai": await check_ai(),
    }
    # همه‌ی Workerهایی که تا الان حداقل یه‌بار update_worker_status صدا
    # زدن رو خودکار اضافه می‌کنه - نیازی به لیستِ ثابت نیست، پس Workerِ
    # جدید فراموش نمی‌شه.
    for worker_name in _worker_status:
        results[worker_name] = check_worker(worker_name)

    ok_count = sum(1 for v in results.values() if v)
    total = len(results)

    return {
        "status": results,
        "summary": f"{ok_count}/{total} OK",
        "uptime": get_uptime(),
        "timestamp": time.time(),
    }


def format_health_report(report: Dict[str, Any]) -> str:
    """تبدیل گزارش به متن زیبا برای نمایش در تلگرام."""
    lines = ["📊 **وضعیت سلامت**"]
    lines.append(f"⏱ **Uptime:** {report['uptime']}")
    lines.append(f"📈 **خلاصه:** {report['summary']}")
    lines.append("")

    core_map = {"telegram": "Telegram", "postgresql": "PostgreSQL", "ai": "AI"}
    unhealthy_workers = []

    for key, display in core_map.items():
        ok = report["status"].get(key, False)
        icon = "🟢" if ok else "🔴"
        lines.append(f"{icon} **{display}**")

    lines.append("")
    lines.append("**Workerهای پس‌زمینه:**")
    worker_keys = [k for k in report["status"] if k not in core_map]
    if not worker_keys:
        lines.append("   (هنوز هیچ Workerی تیک نزده)")
    for key in worker_keys:
        ok = report["status"][key]
        display = WORKER_DISPLAY_NAMES.get(key, key)
        icon = "🟢" if ok else "🔴"
        lines.append(f"{icon} **{display}**")
        if not ok:
            unhealthy_workers.append(key)

    # اطلاعاتِ دقیق‌تر برای هر Workerِ خراب (نه فقط scheduler مثلِ قبل)
    for key in unhealthy_workers:
        info = _worker_status.get(key, {})
        display = WORKER_DISPLAY_NAMES.get(key, key)
        if info.get("last_error"):
            err_preview = info["last_error"][:100]
            lines.append(f"   └ {display} - آخرین خطا: {err_preview}")
        if info.get("last_run"):
            elapsed = time.time() - info["last_run"]
            lines.append(f"   └ {display} - آخرین اجرا: {int(elapsed)} ثانیه پیش")

    return "\n".join(lines)


def update_worker_status(worker_name: str, status: str, error: Optional[str] = None):
    """
    به‌روزرسانی وضعیت یک Worker.
    توسط خود Workerها صدا زده می‌شه.
    """
    now = time.time()
    if worker_name not in _worker_status:
        _worker_status[worker_name] = {}

    _worker_status[worker_name]["last_run"] = now
    _worker_status[worker_name]["status"] = status
    if error:
        _worker_status[worker_name]["last_error"] = error
        _worker_status[worker_name]["error_count"] = _worker_status[worker_name].get("error_count", 0) + 1
    else:
        _worker_status[worker_name]["error_count"] = 0
