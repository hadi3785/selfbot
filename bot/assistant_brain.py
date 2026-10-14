"""
مغزِ دستیار (Assistant Brain) - منطقِ خالصِ triage پیام‌ها بدون وابستگی به Telethon.

سه مصرف‌کننده دارد:
  1. اتوپایلوت (handlers/autopilot.py): پیامِ دریافتی → تصمیم (مهم/یادآوری/اینباکس)
  2. یادآوریِ طبیعی (handlers/scheduler.py): متنِ آزاد → due_at
  3. اینباکسِ هوشمند (handlers/inbox.py): خلاصه‌سازی/دسته‌بندیِ AI

هر تابعِ AI یک fallbackِ رگولار دارد تا بدونِ AI_API_KEY هم سیستم کار کند.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
from typing import Any

from . import ai
from .config import TIMEZONE_OFFSET

logger = logging.getLogger("selfbot.assistant_brain")


# ---------------------------------------------------------------- زمانِ فارسی
_WEEKDAYS = {"شنبه": 0, "یکشنبه": 1, "دوشنبه": 2, "سهشنبه": 3, "سه‌شنبه": 3,
             "چهارشنبه": 4, "پنجشنبه": 5, "جمعه": 6}


def parse_natural_time(text: str, now: dt.datetime | None = None) -> dt.datetime | None:
    """
    استخراجِ زمان از متنِ فارسیِ طبیعی (بدون AI):
      «فردا ساعت ۵» / «فردا 17:00» / «۲ ساعت دیگه» / «30 دقیقه دیگر»
      «پس‌فردا» / «امروز 21:30» / «ساعت 8 شب»
    خروجی: datetime با timezone (UTC) یا None.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    local_now = now + dt.timedelta(hours=TIMEZONE_OFFSET)
    t = text.replace("۰","0").replace("۱","1").replace("۲","2").replace("۳","3") \
            .replace("۴","4").replace("۵","5").replace("۶","6").replace("۷","7") \
            .replace("۸","8").replace("۹","9")

    def local_to_utc(hour: int, minute: int, day_offset: int = 0) -> dt.datetime:
        base = local_now.replace(minute=minute, second=0, microsecond=0)
        base = base + dt.timedelta(days=day_offset)
        if hour < 24:
            base = base.replace(hour=hour)
        # اگه زمان مشخص‌شده گذشته → فردا
        if base <= local_now and day_offset == 0:
            base += dt.timedelta(days=1)
        return (base - dt.timedelta(hours=TIMEZONE_OFFSET)).replace(tzinfo=dt.timezone.utc)

    # HH:MM مطلق
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h < 24 and 0 <= mi < 60:
            off = 0
            if "فردا" in t: off = 1
            elif "پس‌فردا" in t or "پسفردا" in t: off = 2
            return local_to_utc(h, mi, off)

    # «X ساعت/دقیقه/ثانیه دیگه/دیگر»
    m = re.search(r"(\d+)\s*(ثانیه|دقیقه|ساعت|روز)\s*(دیگه|دیگر)?", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"ثانیه": 1, "دقیقه": 60, "ساعت": 3600, "روز": 86400}[unit] * n
        return now + dt.timedelta(seconds=delta)

    # «ساعت X (صبح/عصر/شب)» + فردا/امروز/پس‌فردا
    m = re.search(r"ساعت\s*(\d{1,2})", t)
    if m:
        h = int(m.group(1))
        off = 0
        if "فردا" in t and "پس" not in t.split("فردا")[0][-3:]: off = 1
        if "پس‌فردا" in t or "پسفردا" in t: off = 2
        if re.search(r"(شب|عصر)", t) and h < 12: h += 12
        if h == 12 and re.search(r"(ظهر)", t): pass
        return local_to_utc(h, 0, off)

    # «فردا» بدون ساعت → 9 صبحِ فردا
    if "فردا" in t:
        return local_to_utc(9, 0, 1)
    if "پس‌فردا" in t or "پسفردا" in t:
        return local_to_utc(9, 0, 2)
    return None


# ---------------------------------------------------------------- triage
_TRIAGE_SYSTEM = (
    "تو دستیارِ شخصیِ یک سلف‌بات تلگرامی هستی. به فارسی و فقط با JSON پاسخ بده، "
    'بدون هیچ متنِ اضافه. ساختار: {"importance": 0-2, "needs_reply": true/false, '
    '"event": null یا {"due_at": "YYYY-MM-DDTHH:MM:SS", "title": "..."}، '
    '"reason": "یک جمله"}. importance: 2=مهم/فوری، 1=عادی، 0=تبلیغ/بی‌اهمیت. '
    "اگر پیام شامل قرار/جلسه/یادآوری/ددلاین است event بساز؛ در غیر این صورت null."
)


async def triage_message(text: str) -> dict[str, Any]:
    """
    پیامِ دریافتی → دسته‌بندی ساختاریافته.
    بدونِ AI: importance از کلیدواژه؛ needs_reply=جمله‌ی پرسشی/خطاب؛ event از parse_natural_time.
    """
    fallback = _triage_fallback(text)
    try:
        out = await ai.ask_ai(
            [
                {"role": "system", "content": _TRIAGE_SYSTEM},
                {"role": "user", "content": text[:2000]},
            ],
            max_tokens=220,
        )
        data = _extract_json(out)
        if not isinstance(data, dict):
            return fallback
        return {
            "importance": max(0, min(2, int(data.get("importance") or 0))),
            "needs_reply": bool(data.get("needs_reply")),
            "event": data.get("event") if isinstance(data.get("event"), dict) else None,
            "reason": str(data.get("reason") or "")[:200],
            "source": "ai",
        }
    except Exception:  # AI خاموش/خراب → fallback ساکت
        return fallback


_URGENT_WORDS = ("فوری", "مهم", "اضطراری", "یدت نره", "یادت نره", "ددلاین", "جلسه", "قرار", "سقط", "حتما")
_QUESTION_HINTS = ("؟", "?", "میشه", "می‌شه", "لطفا", "چیه", "چطور", "کجاست", "میخوام", "می‌خوام")


def _triage_fallback(text: str) -> dict[str, Any]:
    low = text.lower()
    importance = 2 if any(w in low for w in _URGENT_WORDS) else 0
    needs_reply = any(w in low for w in _QUESTION_HINTS)
    due = parse_natural_time(text)
    event = None
    if due and any(w in low for w in ("جلسه", "قرار", "یادت نره", "یادآوری", "ددلاین", "بده", "کن")):
        event = {"due_at": due.isoformat(), "title": text[:120]}
    return {
        "importance": importance,
        "needs_reply": needs_reply,
        "event": event,
        "reason": "تحلیلِ محلی (بدون AI)",
        "source": "local",
    }


def _extract_json(text: str):
    """JSON را از داخلِ متنِ احتمالاً مارک‌دارِ مدل بیرون می‌کشد."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def summarize_inbox(blob: str) -> str:
    """خلاصه‌ی کوتاهِ آیتم‌های اینباکس (حداکثر ~۱۰۰۰ بایت) برای `.اینباکس خلاصه`."""
    out = await ai.ask_ai(
        [
            {
                "role": "system",
                "content": (
                    "پیام‌های ذخیره‌شده‌ی اینباکسِ یک مدیر را می‌بینی. به فارسی، حداکثر ۸ خط، "
                    "خلاصه‌ی موضوعی بده: گروه‌بندی بر اساس موضوع/فرستنده، پیام‌های فوری را "
                    "اول بگو، و آخر یک خطِ «اقدام پیشنهادی». بدون مقدمه."
                ),
            },
            {"role": "user", "content": blob[:6000]},
        ],
        max_tokens=350,
    )
    return out.strip()


async def summarize_search(query: str, blob: str) -> str:
    """جستجوی فوق‌هوشمند: نتایجِ خام → دسته‌بندی + حذفِ تکراری + خلاصه."""
    out = await ai.ask_ai(
        [
            {
                "role": "system",
                "content": (
                    "نتایجِ خامِ یک جستجوی تلگرامی را برای عبارتِ کاربر می‌بینی. به فارسی، "
                    "خروجیِ ساختاریافته: ۱) مهم‌ترین یافته‌ها (حداکثر ۵ خط)، ۲) «📌 جزئیات» "
                    "بسته به سوال (مثل آخرین قیمت/تاریخ ذکرشده)، ۳) «🧠 خلاصه» یک خط. "
                    "مواردِ تکراری را فقط یک‌بار بگو. حداکثر ۱۲ خط."
                ),
            },
            {"role": "user", "content": f"عبارتِ جستجو: {query}\n\nنتایج:\n{blob[:5500]}"},
        ],
        max_tokens=450,
    )
    return out.strip()


# ---------------------------------------------------------------- strip
_TIME_PHRASE_RE = re.compile(
    r"(?:پس‌فردا|پسفردا|فردا|امروز)\s*(?:ساعت\s*\d{1,2}(?::\d{2})?\s*(?:صبح|ظهر|عصر|شب)?)?"
    r"|\d+\s*(?:ثانیه|دقیقه|ساعت|روز)\s*(?:دیگه|دیگر)"
)


def strip_time_phrase(text: str) -> str:
    """متنِ یادآوری را از عبارتِ زمانی خالی می‌کند («فردا ساعت ۸ جلسه برو» → «جلسه برو»)."""
    t = _TIME_PHRASE_RE.sub(" ", text)
    t = re.sub(r"\s+", " ", t).strip(" ،,.-")
    return t or text.strip()

