"""۸) منشی چت: پاسخِ خودکارِ هوشمند با تشخیصِ ترکیبیِ آنلاین/آفلاین

بازطراحیِ کامل این بخش. تشخیصِ «آفلاین‌بودن» (که تعیین می‌کنه منشی خودش کِی
روشن/خاموش بشه) از دو سیگنالِ کاملاً محلی تشکیل شده - بدونِ هیچ درخواستی به
تلگرام، پس هیچ‌وقت هم FloodWait نمی‌گیره:

  ۱) زمان‌بندی: پنجره‌های ثابتِ ساعتی که خودت تعریف می‌کنی (مثلاً خواب:
     ۲۳:۰۰ تا ۰۸:۰۰). داخلِ این بازه‌ها، صرف‌نظر از فعالیتِ اخیرت، منشی
     همیشه روشنه - چون یعنی «قطعاً در دسترس نیستم».
  ۲) فعالیت: اگه الان توی هیچ پنجره‌ای نباشیم، بر اساسِ آخرین باری که یه
     نشونه‌ی واقعی از حضورت دیده شده تصمیم می‌گیریم. این نشونه از **دو** جا
     میاد (نسبت به قبل، این تفاوتِ اصلیه):
       الف) هر پیامِ خروجیِ واقعی - از هر دستگاهی (نه فقط همین اسکریپت)،
            چون تلگرام پیام‌های خروجیِ خودت رو بینِ همه‌ی سشن‌های اکانت
            sync می‌کنه و این سشن هم همون آپدیت رو می‌بینه.
       ب) خوندنِ پیام از هر دستگاهی (Read Receipt رویِ Inbox). صرفِ
          بازکردن و دیدنِ پیام‌ها از گوشی/دسکتاپ - حتی بدونِ فرستادنِ
          چیزی - هم دقیقاً به‌همون اندازه نشونه‌ی حضوره. این سیگنال قبلاً
          چک نمی‌شد؛ نبودش باعث می‌شد کسی که بیشتر می‌خونه تا تایپ کنه،
          زودتر از واقعیت «آفلاین» حساب بشه و منشی وسطِ حضورش روشن بشه.
     بعدِ ASSISTANT_ONLINE_THRESHOLD ثانیه سکوت (نه پیام، نه خوندن) از هر دو
     منبع، آفلاین حساب می‌شی و منشی روشن می‌شه.

زمان‌بندی یه لایه‌ی «حتماً روشن» روی همون تشخیصِ رفتاریه، نه جایگزینش: اگه
هیچ پنجره‌ای تعریف نکنی، رفتار فقط بر اساسِ سیگنالِ فعالیته.

نکته‌ی مهم‌تر: قبلاً enabled فقط هر ASSISTANT_CHECK_INTERVAL ثانیه، توسطِ یه
تسکِ پس‌زمینه‌ی جدا (assistant_status_watcher) بازمحاسبه می‌شد - یعنی اگه اون
تسک به هر دلیلی (یه استثنای پیش‌بینی‌نشده، بدونِ try/except دورش) می‌مرد،
enabled برای همیشه روی همون مقدارِ آخر گیر می‌کرد و هیچ‌وقت دیگه «فهمیدنِ
آفلاین‌شدن» اتفاق نمی‌افتاد - دقیقاً همون رفتاری که باعثِ گزارشِ «وقتی آفلاین
می‌شم جواب نمی‌ده» می‌شه. الان دو تا اصلاح داره:
  • خودِ assistant_autoreply (پایینِ همین فایل) قبل از هر تصمیمی، یه‌بار
    دیگه enabled رو از رویِ همون سیگنال‌های محلی تازه محاسبه می‌کنه - یعنی
    صحتِ رفتار دیگه به سلامتِ اون تسکِ پس‌زمینه‌ی جدا گره نخورده؛ حتی اگه اون
    تسک بمیره، خودِ لحظه‌ی پاسخ‌دادن هنوز درست تصمیم می‌گیره.
  • بدنه‌ی حلقه‌ی assistant_status_watcher هم توی try/except پیچیده شده،
    پس یه استثنای پیش‌بینی‌نشده دیگه نمی‌تونه کلِ تسک رو برای همیشه بکشه -
    فقط لاگ می‌شه و دورِ بعدی طبقِ معمول ادامه پیدا می‌کنه.

چرا به‌جای این‌ها از خودِ تلگرام نمی‌پرسیم کدوم سشن‌هام الان وصلن
(account.getAuthorizations)؟ چون این متد برای پرسوجوی مکرر/همیشگی طراحی
نشده و دیر یا زود با FloodWaitError ریت‌لیمیت می‌شه؛ و چون خودِ سشنِ همین
اسکریپت هم (که برای کارکردنِ منشی لازمه وصل باشه) به‌عنوانِ یه سشنِ فعال
حساب می‌شه، حتی جوابِ سالمِ اون درخواست هم چیزِ قابل‌اتکایی نشون نمی‌داد.
به‌جاش کاملاً به رفتارِ خودت (فرستادن/خوندن) تکیه می‌کنیم.

قفلِ دستی (`.منشی روشن`/`.منشی خاموش`) هنوز کاملاً بالادستِ هر دو سیگنالِ
بالاست: وقتی auto_detect=False باشه، نه فعالیت نه زمان‌بندی هیچ‌کدوم دست به
enabled نمی‌زنن؛ فقط `.منشی خودکار` برش می‌گردونه. جزئیاتِ پنجره‌های
زمان‌بندی با `.منشی زمان‌بندی` مدیریت می‌شن.
"""
import asyncio
import logging
import re
from collections import deque
from datetime import datetime, timedelta, timezone

from telethon import events

from .. import ai, config, runtime
from ..config import PREFIX
from ..runtime import client
from ..storage.assistant_store import (
    add_schedule_window,
    assistant_state,
    clear_schedule_windows,
    remove_schedule_window,
    save_assistant,
)
from ..storage.stats_store import record_error as _record_error
from ..utils import pat
from . import audio

logger = logging.getLogger("selfbot.handlers.assistant")

# آخرین باری که یه نشونه‌ی واقعیِ حضور (پیامِ خروجی یا خوندنِ پیام، از هر
# دستگاهی) دیده شده - تنها منبعِ تشخیصِ آنلاین/آفلاینِ این فایل. datetime.min
# یعنی «از استارتِ پروسه هنوز هیچی ندیدیم» -> بلافاصله «آفلاین» حساب می‌شه،
# که همون فرضِ امنِ پیش‌فرضه (تا وقتی خلافش ثابت بشه).
_last_self_activity = datetime.min.replace(tzinfo=timezone.utc)

# نوعِ آخرین نشونه‌ی فعالیت - فقط برای نمایش توی `.منشی وضعیت` (تشخیص از این
# استفاده نمی‌کنه، صرفاً کمک می‌کنه بفهمی چرا الان روشن/خاموشه).
_last_self_activity_kind = ""
_ACTIVITY_KIND_FA = {
    "message": "فرستادنِ پیامِ واقعی",
    "read": "خوندنِ پیام (از هر دستگاهی)",
    "": "هنوز هیچ نشونه‌ای دیده نشده (از استارتِ پروسه)",
}

# --------------------------------------------------- لایه‌ی سشن‌های فعال ---
# دومین (و دقیق‌ترین) منبعِ تشخیص: account.getAuthorizations برای هر سشنِ
# اکانت (گوشی/دسکتاپ/وب) date_active برمی‌گردونه - آخرین باری که اون سشن
# واقعاً کاری کرده. بیشینه‌ی این مقادیر روی همه‌ی سشن‌ها یعنی «آخرین فعالیتِ
# انسانیِ اکانت از هر دستگاهی»، حتی اگه این پروسه اصلاً چیزی ندیده باشه.
# datetime.min یعنی هنوز هیچ poll موفقی نداشتیم.
# --- لایه‌ی وضعیتِ واقعی (آنلاین/آفلاینِ پروفایل) ---
# وضعیتی که تلگرام توی اپ نشون می‌ده: «آنلاین» یا «آخرین بازدید X دقیقه پیش».
# اگر تلگرام بگه آنلاین → منشی خاموش؛ به‌محضِ آفلاین‌شدن → روشن. بدونِ هیچ
# تکیه‌ای بر پیام‌ها.
_last_profile_status_online: bool | None = None   # None = هنوز نمی‌دونیم
_last_assistant_reply_at: datetime | None = None  # آخرین باری که منشی خودش پیام فرستاد
_last_status_poll_ok = datetime.min.replace(tzinfo=timezone.utc)
_status_poll_failures = 0
_status_poll_flood_until = 0.0

_last_session_seen = datetime.min.replace(tzinfo=timezone.utc)
_last_session_poll_ok = datetime.min.replace(tzinfo=timezone.utc)  # آخرین poll موفق
_session_poll_failures = 0          # شمارنده‌ی خطاهای متوالیِ poll
_session_poll_flood_until = 0.0     # timestampِ epoch تا وقتی که flood/خطا رو با backoff منتظر بمونیم
_last_session_kind_fa = "—"

_ACTIVITY_KIND_FA_NOTE = {
    "message": "فرستادنِ پیامِ واقعی",
    "read": "خوندنِ پیام (از هر دستگاهی)",
    "session": "فعالیتِ سشن‌های اکانت (هر دستگاهی)",
}

# شمارنده‌ی «همین الان دارم توی این چت auto-reply می‌فرستم» (chat_id -> تعداد
# درحال‌ارسال). قبل از فرستادنِ پاسخ (نه بعدش) پر می‌شه تا خودِ پاسخِ منشی
# به‌غلط به‌عنوانِ «کاربر همین الان پیام فرستاد/خوند» حساب نشه و بلافاصله
# خودش رو خاموش نکنه.
_auto_reply_in_flight: dict[int, int] = {}

# حافظه‌ی مکالمه‌ایِ منشی (فقط برای حالتِ هوش‌مصنوعی): به ازای هر
# (chat_id, sender_id) یه deque از پیام‌های اخیر (کاربر+منشی) نگه می‌داریم و
# موقعِ ساختنِ پرامپت، قبل از پیامِ جدید به AI می‌دیمش. فقط در حافظه‌ی
# پروسه‌ست (نه دیتابیس)، با ری‌استارت پاک می‌شه، و با ASSISTANT_HISTORY_LIMIT
# محدود می‌شه.
_conv_history: dict[tuple[int, int], deque] = {}


def _history_key(chat_id: int, sender_id: int) -> tuple[int, int]:
    return (chat_id, sender_id)


def _get_history_messages(key: tuple[int, int]) -> list[dict]:
    if config.ASSISTANT_HISTORY_LIMIT <= 0:
        return []
    return list(_conv_history.get(key, ()))


def _remember_exchange(key: tuple[int, int], user_text: str, assistant_text: str) -> None:
    limit = config.ASSISTANT_HISTORY_LIMIT
    if limit <= 0:
        return
    dq = _conv_history.get(key)
    if dq is None:
        dq = deque(maxlen=limit)
        _conv_history[key] = dq
    elif dq.maxlen != limit:
        dq = deque(dq, maxlen=limit)
        _conv_history[key] = dq
    dq.append({"role": "user", "content": user_text})
    dq.append({"role": "assistant", "content": assistant_text})


def _clear_all_history() -> int:
    count = len(_conv_history)
    _conv_history.clear()
    return count


_ASSISTANT_MODE_FA = {
    "auto": "خودکار (همه‌جا)",
    "mention": "فقط با منشن/ریپلای",
    "pm": "فقط پیوی",
    "groups": "فقط گروه‌ها",
}

# ورودیِ کاربر برای «حالت پاسخ» -> کلید داخلیِ همیشگی (auto/mention/pm/groups).
_ASSISTANT_MODE_ALIASES = {
    "خودکار": "auto", "auto": "auto",
    "منشن": "mention", "mention": "mention",
    "پیوی": "pm", "pm": "pm",
    "گروه‌ها": "groups", "گروهها": "groups", "groups": "groups",
}


# ---------------------------------------------------------- زمان‌بندی ---
# پنجره‌ها با دقیقه‌ی «از نیمه‌شب» (۰ تا ۱۴۳۹) ذخیره/محاسبه می‌شن، نه
# datetime.time - چون تنها چیزی که لازم داریم مقایسه‌ی عددیِ «الان کجای
# شبانه‌روزم» با یه بازه‌ست، و اینجوری از دردسرِ DST/timezone-aware هم در
# امان می‌مونیم. زمانِ محلی با همون قراردادِ scheduler.py/daily_digest.py
# حساب می‌شه (config.TIMEZONE_OFFSET، پیش‌فرض تهران).
_CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _local_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=config.TIMEZONE_OFFSET)


def _minute_of_day(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


def _parse_clock(raw: str) -> int | None:
    """ورودیِ «HH:MM» رو به دقیقه‌ی از نیمه‌شب تبدیل می‌کنه؛ نامعتبر بود -> None."""
    m = _CLOCK_RE.match(raw.strip())
    if not m:
        return None
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh * 60 + mm


def _format_clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _window_contains(start_minute: int, end_minute: int, minute: int) -> bool:
    """
    آیا `minute` (دقیقه‌ی از نیمه‌شب) داخلِ بازه‌ی [start_minute, end_minute]
    هست؟ هر دو سر inclusive-ان. اگه end_minute از start_minute کمتر باشه یعنی
    بازه از نیمه‌شب رد می‌شه (مثلاً ۲۳:۰۰ تا ۰۸:۰۰ -> start=1380, end=480).
    """
    if start_minute <= end_minute:
        return start_minute <= minute <= end_minute
    return minute >= start_minute or minute <= end_minute


def _active_schedule_window(minute: int) -> dict | None:
    """اولین پنجره‌ای که الان توش هستیم (اگه لایه‌ی زمان‌بندی فعال باشه)، وگرنه None.

    دسترسیِ start_minute/end_minute با .get (نه [...]) دفاعیه: یه ردیفِ
    ناقص/خراب توی این لیست نباید بتونه کلِ محاسبه (و در نتیجه کلِ حلقه‌ی
    assistant_status_watcher یا خودِ assistant_autoreply) رو با استثنا متوقف
    کنه - فقط همون یه پنجره نادیده گرفته می‌شه.
    """
    if not assistant_state["schedule_enabled"]:
        return None
    for window in assistant_state["schedule_windows"]:
        start = window.get("start_minute") if isinstance(window, dict) else None
        end = window.get("end_minute") if isinstance(window, dict) else None
        if start is None or end is None:
            continue
        if _window_contains(start, end, minute):
            return window
    return None


def _current_signal_reason() -> tuple[str, dict | None]:
    """
    فقط برای تصمیم‌گیری/نمایش - خودش چیزی رو تغییر نمی‌ده. اگه الان داخلِ یه
    پنجره‌ی زمان‌بندی‌شده‌ایم ("schedule", window)، وگرنه ("activity", None)
    یعنی تصمیم بر اساسِ همون سیگنالِ فعالیته.
    """
    window = _active_schedule_window(_minute_of_day(_local_now()))
    if window is not None:
        return "schedule", window
    return "activity", None


def _seconds_since_activity() -> float:
    """سکوت از دیدِ سیگنال‌های محلی (پیام/ریید) - لایه‌ی بلادرنگ."""
    return (datetime.now(timezone.utc) - _last_self_activity).total_seconds()


def _seconds_since_session() -> float:
    """سکوت از دیدِ date_active سشن‌های اکانت (لایه‌ی دقیق؛ هر دستگاهی).

    اگه poll از کار افتاده باشه (خطای مکرر/FloodWait) یا داده‌شده از سقفِ
    ASSISTANT_SESSION_MAX_AGE کهنه‌تر باشه، یعنی این لایه الان قابلِ اعتماد
    نیست و باید مثهِ «همیشه‌آنلاین» (۰ ثانیه) رفتار نکنه؛ به‌جاش None برمی‌گردونیم
    تا تصمیم فقط بر اساسِ لایه‌ی محلی گرفته بشه - نه نشونه‌ی کهنه.
    """
    if _last_session_poll_ok == datetime.min.replace(tzinfo=timezone.utc):
        return None  # هنوز هیچ poll موفقی نبوده
    age = (datetime.now(timezone.utc) - _last_session_poll_ok).total_seconds()
    if age > config.ASSISTANT_SESSION_MAX_AGE:
        return None
    return (datetime.now(timezone.utc) - _last_session_seen).total_seconds()


def _assistant_status_text():
    status = "روشن ✅" if assistant_state["enabled"] else "خاموش ❌"
    mode_fa = _ASSISTANT_MODE_FA.get(assistant_state["mode"], assistant_state["mode"])
    if assistant_state["auto_detect"]:
        kind, window = _current_signal_reason()
        if kind == "schedule":
            reason_text = (
                f"الان به‌خاطرِ بازه‌ی زمان‌بندیِ «{window.get('label') or 'بدون‌برچسب'}» "
                f"({_format_clock(window['start_minute'])}–{_format_clock(window['end_minute'])}) روشنه"
            )
        elif config.ASSISTANT_PRESENCE_MODE == "status":
            # حالتِ پیش‌فرض: تصمیم فقط با وضعیتِ آنلاین/آفلاینِ پروفایل
            if _last_profile_status_online is None:
                reason_text = "هنوز وضعیت از تلگرام پرسیده نشده (چند ثانیه بعد از استارت)"
            elif _last_profile_status_online:
                reason_text = "تلگرام می‌گه آنلاینی → منشی خاموش"
            else:
                reason_text = "تلگرام می‌گه آفلاینی → منشی روشن"
        else:
            local_gap = _seconds_since_activity()
            session_gap = _seconds_since_session()
            sess_thr = config.ASSISTANT_SESSION_ONLINE_THRESHOLD
            local_online = local_gap is not None and local_gap < config.ASSISTANT_ONLINE_THRESHOLD
            session_online = bool(sess_thr) and session_gap is not None and session_gap < sess_thr
            if local_gap is None and session_gap is None:
                reason_text = "هنوز هیچ نشونه‌ای از استارت دیده نشده"
            elif local_online or session_online:
                src = "هر دو" if (local_online and session_online) else ("محلی" if local_online else "سشن‌ها")
                gap = local_gap if local_online else session_gap
                reason_text = f"تو آنلاینی ({src}) — {int(gap)} ثانیه پیش"
            else:
                local_note = f"محلی: {int(local_gap)}s" if local_gap is not None else "محلی: —"
                session_note = (
                    f"سشن‌ها: {int(session_gap)}s" if session_gap is not None
                    else ("سشن‌ها: خاموش" if not sess_thr else "سشن‌ها: —")
                )
                reason_text = (
                    f"بی‌سیگنال — {local_note} | {session_note} "
                    f"(آستانه‌ها: {config.ASSISTANT_ONLINE_THRESHOLD}s محلی / {sess_thr}s سشن)"
                )
        if config.ASSISTANT_PRESENCE_MODE == "status":
            control_line = f"خودکار — از رویِ وضعیتِ آنلاین/آفلاینِ پروفایل ({reason_text})"
        else:
            control_line = f"خودکار ({reason_text})"
        footer = (
            f"با `{PREFIX}منشی روشن` یا `{PREFIX}منشی خاموش` می‌تونی دستی قفلش کنی "
            "(از اون به بعد حتی اگه آنلاین/آفلاین بشی یا داخلِ بازه‌ی زمان‌بندی باشی، تشخیص خودکار دیگه دست بهش نمی‌زنه)."
        )
    else:
        control_line = "دستی 🔒 (قفل‌شده - نه فعالیت نه زمان‌بندی روش تاثیری نداره)"
        footer = f"برای برگردوندن به تشخیص خودکار: `{PREFIX}منشی خودکار`"

    windows = assistant_state["schedule_windows"]
    if not windows:
        schedule_summary = "تعریف نشده"
    else:
        layer = "فعال ✅" if assistant_state["schedule_enabled"] else "غیرفعال ❌ (موقتاً خاموش)"
        schedule_summary = f"{len(windows)} بازه، {layer}"

    return (
        "🤖 **منشی چت**\n\n"
        f"• وضعیت: {status}\n"
        f"• کنترل: {control_line}\n"
        f"• حالت پاسخ: {mode_fa}\n"
        f"• تأخیر پاسخ: {assistant_state['delay']} ثانیه\n"
        f"• منبعِ پاسخ: {'هوش مصنوعی 🤖' if assistant_state['ai_mode'] else 'متنِ ثابت'}\n"
        f"• محدودیتِ پاسخ: "
        f"{'بدون محدودیت - به همه‌ی پیام‌ها جواب می‌ده' if assistant_state['ai_mode'] else 'فقط یک‌بار به هر نفر در هر نشست'}\n"
        f"• حافظه‌ی مکالمه: "
        f"{f'تا {config.ASSISTANT_HISTORY_LIMIT} پیامِ آخرِ هر مکالمه ({len(_conv_history)} مکالمه فعال)' if config.ASSISTANT_HISTORY_LIMIT > 0 else 'خاموش'}\n"
        f"• متن ثابت (fallback): {assistant_state['text'] or '(تنظیم نشده)'}\n"
        f"• زمان‌بندی: {schedule_summary} (جزئیات: `{PREFIX}منشی زمان‌بندی`)\n"
        f"• چت‌های مستثنی: {len(assistant_state['exclude'])}\n"
        f"• چت‌های همیشه‌فعال: {len(assistant_state['include'])}\n\n"
        f"{footer}"
    )


def _schedule_status_text() -> str:
    windows = assistant_state["schedule_windows"]
    header = "🗓 **زمان‌بندیِ منشیِ خودکار**\n\n"
    layer_state = (
        "فعال ✅" if assistant_state["schedule_enabled"]
        else "غیرفعال ❌ (بازه‌ها حذف نشدن، فقط موقتاً بی‌اثرن)"
    )
    state_line = f"وضعیتِ لایه: {layer_state}\n\n"

    if not windows:
        body = (
            "هیچ بازه‌ای تعریف نشده - یعنی منشیِ خودکار فقط بر اساسِ فعالیتِ اخیرت تصمیم می‌گیره.\n\n"
            f"افزودن: `{PREFIX}منشی زمان‌بندی افزودن 23:00 08:00 خواب`\n"
            "(یعنی از ۲۳:۰۰ تا ۰۸:۰۰، صرف‌نظر از فعالیتِ اخیرت، منشی روشن می‌مونه)"
        )
        return header + state_line + body

    now_minute = _minute_of_day(_local_now())
    lines = []
    for i, w in enumerate(windows, start=1):
        active = assistant_state["schedule_enabled"] and _window_contains(
            w["start_minute"], w["end_minute"], now_minute
        )
        mark = " ← الان فعال" if active else ""
        label = w["label"] or "بدون‌برچسب"
        lines.append(f"{i}. {label}: {_format_clock(w['start_minute'])}–{_format_clock(w['end_minute'])}{mark}")

    footer = (
        f"\n\nافزودنِ بازه‌ی دیگه: `{PREFIX}منشی زمان‌بندی افزودن HH:MM HH:MM [برچسب]`\n"
        f"حذفِ یکی: `{PREFIX}منشی زمان‌بندی حذف <شماره>`\n"
        f"پاک‌کردنِ همه: `{PREFIX}منشی زمان‌بندی پاک`\n"
        f"روشن/خاموشِ کلِ این لایه: `{PREFIX}منشی زمان‌بندی روشن` / `{PREFIX}منشی زمان‌بندی خاموش`"
    )
    return header + state_line + "\n".join(lines) + footer


def _assistant_should_respond(event):
    if event.is_channel and not event.is_group:
        return False  # کانال‌های برادکست رو نادیده بگیر
    chat_id = event.chat_id
    if chat_id in assistant_state["exclude"]:
        return False
    if chat_id in assistant_state["include"]:
        return True
    mode = assistant_state["mode"]
    if mode == "auto":
        return True
    if mode == "pm":
        return event.is_private
    if mode == "groups":
        return event.is_group
    if mode == "mention":
        if event.is_private:
            return True
        return bool(getattr(event.message, "mentioned", False))
    return False


def _safe_recompute() -> None:
    """
    فقط برای مسیرهایی که نباید به‌خاطرِ یه استثنای غیرمنتظره کلاً متوقف بشن
    (مثل assistant_autoreply، درست وسطِ رسیدنِ یه پیام). خودِ
    _recompute_enabled_from_signals با دیتای عادی هیچ‌وقت نباید استثنا بده
    (نگاهِ سخت‌گیریِ .get توی _active_schedule_window)، ولی اگه به هر دلیلی
    (مثلاً حالتِ درون‌حافظه‌ای دستکاری‌شده) استثنایی داد، اینجا لاگ می‌شه و
    از آخرین enabled شناخته‌شده استفاده می‌کنیم - نه این‌که کلِ پاسخ‌دادن
    متوقف بشه.

    در حالتِ تشخیصِ «status» کلاً کاری نمی‌کنه: اونجا تصمیم فقط با وضعیتِ
    آنلاین/آفلاینِ پروفایل گرفته می‌شه (pollerِ وضعیت)، نه با پیام‌ها.
    """
    if config.ASSISTANT_PRESENCE_MODE == "status":
        return
    try:
        _recompute_enabled_from_signals()
    except Exception:
        _record_error()
        logger.exception("خطا در بازبینیِ آنیِ وضعیتِ منشی - از آخرین مقدارِ شناخته‌شده استفاده می‌شه")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["منشی", "assistant"])))
async def assistant_handler(event):
    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if not sub or sub in ("وضعیت", "status"):
        # چک‌کردنِ وضعیت هم یه فرصتِ رایگانه برای این‌که enabled از رویِ
        # سیگنال‌های فعلی (نه لزوماً آخرین بارِ اجرای تسکِ پس‌زمینه) تازه بشه.
        # این‌کار _last_self_activity رو دست نمی‌زنه (فقط ازش می‌خونه)، پس
        # مثلِ خودِ فرستادنِ این دستور، تایمرِ سکوت رو ریست نمی‌کنه.
        if assistant_state["auto_detect"]:
            _safe_recompute()
        return await event.edit(_assistant_status_text())

    if sub in ("روشن", "on"):
        assistant_state["enabled"] = True
        assistant_state["auto_detect"] = False  # قفل دستی - تشخیص خودکار دیگه دست بهش نمی‌زنه
        assistant_state["replied"] = set()
        await save_assistant()
        return await event.edit(_assistant_status_text())

    if sub in ("خاموش", "off"):
        assistant_state["enabled"] = False
        assistant_state["auto_detect"] = False  # قفل دستی - حتی اگه آفلاین بشی خاموش می‌مونه
        await save_assistant()
        return await event.edit(_assistant_status_text())

    if sub in ("خودکار", "auto"):
        assistant_state["auto_detect"] = True
        _safe_recompute()
        await save_assistant()
        return await event.edit(
            "✅ تشخیص خودکار آنلاین/آفلاین دوباره فعال شد.\n"
            "از این به بعد روشن/خاموش‌بودن منشی خودش بر اساسِ آنلاین/آفلاین‌بودنت و بازه‌های زمان‌بندی‌شده مدیریت می‌شه.\n\n"
            + _assistant_status_text()
        )

    if sub in ("زمانبندی", "زمان‌بندی", "schedule"):
        args = rest.split(maxsplit=1)
        action = args[0].lower() if args else ""
        tail = args[1] if len(args) > 1 else ""

        if not action or action in ("وضعیت", "status", "لیست", "list"):
            return await event.edit(_schedule_status_text())

        if action in ("افزودن", "add"):
            parts2 = tail.split(maxsplit=2)
            if len(parts2) < 2:
                return await event.edit(f"مثال: `{PREFIX}منشی زمان‌بندی افزودن 23:00 08:00 خواب`")
            start = _parse_clock(parts2[0])
            end = _parse_clock(parts2[1])
            if start is None or end is None:
                return await event.edit("⛔ فرمتِ ساعت نامعتبره؛ باید HH:MM باشه (مثلاً 23:00).")
            if start == end:
                return await event.edit("⛔ ساعتِ شروع و پایان نمی‌تونن یکی باشن.")
            if len(assistant_state["schedule_windows"]) >= config.ASSISTANT_SCHEDULE_MAX_WINDOWS:
                return await event.edit(
                    f"⛔ سقفِ تعدادِ بازه‌ها ({config.ASSISTANT_SCHEDULE_MAX_WINDOWS} تا) پره؛ "
                    f"یکی رو حذف کن (`{PREFIX}منشی زمان‌بندی حذف <شماره>`) یا اول پاکشون کن."
                )
            label = parts2[2].strip() if len(parts2) > 2 else ""
            await add_schedule_window(label, start, end)
            if assistant_state["auto_detect"]:
                _safe_recompute()
            span = f"{_format_clock(start)}–{_format_clock(end)}"
            return await event.edit(
                f"✅ بازه‌ی «{label or 'بدون‌برچسب'}» ({span}) اضافه شد.\n\n" + _schedule_status_text()
            )

        if action in ("حذف", "remove", "delete"):
            if not tail.strip().isdigit():
                return await event.edit(
                    f"مثال: `{PREFIX}منشی زمان‌بندی حذف 1` (شماره رو از `{PREFIX}منشی زمان‌بندی` ببین)"
                )
            idx = int(tail.strip())
            windows = assistant_state["schedule_windows"]
            if not (1 <= idx <= len(windows)):
                return await event.edit("⛔ همچین شماره‌ای توی لیست نیست.")
            target = windows[idx - 1]
            await remove_schedule_window(target["id"])
            if assistant_state["auto_detect"]:
                _safe_recompute()
            return await event.edit(
                f"🗑 بازه‌ی «{target['label'] or 'بدون‌برچسب'}» حذف شد.\n\n" + _schedule_status_text()
            )

        if action in ("پاک", "clear"):
            n = await clear_schedule_windows()
            if assistant_state["auto_detect"]:
                _safe_recompute()
            return await event.edit(f"🗑 {n} بازه پاک شد." if n else "لیستِ بازه‌ها از قبل هم خالی بود.")

        if action in ("روشن", "on"):
            assistant_state["schedule_enabled"] = True
            if assistant_state["auto_detect"]:
                _safe_recompute()
            await save_assistant()
            return await event.edit("✅ لایه‌ی زمان‌بندی فعال شد.\n\n" + _schedule_status_text())

        if action in ("خاموش", "off"):
            assistant_state["schedule_enabled"] = False
            if assistant_state["auto_detect"]:
                _safe_recompute()
            await save_assistant()
            return await event.edit("❌ لایه‌ی زمان‌بندی غیرفعال شد (بازه‌ها حذف نشدن، فقط موقتاً بی‌اثرن).")

        return await event.edit(f"دستور نامعتبره. راهنما: `{PREFIX}منشی زمان‌بندی`")

    if sub in ("متن", "text"):
        text = rest
        if not text and event.is_reply:
            reply = await event.get_reply_message()
            text = reply.raw_text or ""
        if not text:
            return await event.edit(f"مثال: `{PREFIX}منشی متن سلام، فعلاً آنلاین نیستم`")
        assistant_state["text"] = text
        await save_assistant()
        return await event.edit("✅ متن پاسخ ذخیره شد")

    if sub in ("تأخیر", "تاخیر", "delay"):
        if not rest.strip().isdigit():
            return await event.edit(f"مثال: `{PREFIX}منشی تأخیر 3`")
        assistant_state["delay"] = max(int(rest.strip()), 0)
        await save_assistant()
        return await event.edit(f"✅ تأخیر روی {assistant_state['delay']} ثانیه تنظیم شد")

    if sub in ("حالت", "mode"):
        m_raw = rest.strip().lower()
        m = _ASSISTANT_MODE_ALIASES.get(m_raw)
        if not m:
            return await event.edit(f"مثال: `{PREFIX}منشی حالت خودکار` (خودکار/منشن/پیوی/گروه‌ها)")
        assistant_state["mode"] = m
        await save_assistant()
        warn = ""
        if m == "auto":
            warn = (
                "\n⚠️ توجه: توی این حالت به همه‌ی پیام‌های هر چتی (حتی بدون تگ/ریپلای) "
                "جواب می‌ده - توی گروه‌های شلوغ ممکنه شبیه اسپم به‌نظر برسه."
            )
        return await event.edit(f"✅ حالت روی `{_ASSISTANT_MODE_FA[m]}` تنظیم شد{warn}")

    if sub in ("هوش‌مصنوعی", "هوشمصنوعی", "ai"):
        opt = rest.strip().lower()
        if opt in ("روشن", "on"):
            assistant_state["ai_mode"] = True
            await save_assistant()
            return await event.edit(
                "✅ پاسخِ خودکارِ منشی از این به بعد به‌جای متنِ ثابت، با هوش مصنوعی تولید می‌شه.\n"
                "⚠️ توی این حالت به **همه‌ی** پیام‌ها جواب می‌ده (نه فقط یک‌بار به هر نفر) - "
                "توی چت‌های شلوغ ممکنه هزینه/تعدادِ درخواستِ زیادی به سرویسِ AI بزنه.\n"
                "⚠️ نیازمندِ `AI_API_KEY` ست‌شده‌ست؛ اگه ست نباشه یا خطا بده، خودکار به متنِ ثابتِ فعلی fallback می‌کنه.\n"
                f"🧠 هر مکالمه تا {config.ASSISTANT_HISTORY_LIMIT} پیامِ آخرش رو به‌عنوانِ حافظه به مدل می‌ده "
                "تا جواب‌ها پیوسته باشن (با `ASSISTANT_HISTORY_LIMIT` قابلِ تنظیمه؛ برای پاک‌کردنش: "
                f"`{PREFIX}منشی حافظه پاک`)."
            )
        if opt in ("خاموش", "off"):
            assistant_state["ai_mode"] = False
            await save_assistant()
            return await event.edit("❌ پاسخِ منشی دوباره فقط از متنِ ثابت استفاده می‌کنه (یک‌بار به هر نفر)")
        status = "روشن ✅" if assistant_state["ai_mode"] else "خاموش ❌"
        return await event.edit(
            f"🤖 وضعیتِ پاسخِ هوش‌مصنوعیِ منشی: {status}\n\n"
            f"`{PREFIX}منشی هوش‌مصنوعی روشن` / `{PREFIX}منشی هوش‌مصنوعی خاموش`\n"
            "توی این حالت به همه‌ی پیام‌ها جواب می‌ده (نه فقط یک‌بار به هر نفر).\n"
            "برای سوال/خلاصه‌سازیِ دستی (جدا از منشی) هم می‌تونی از "
            f"`{PREFIX}پرسش` و `{PREFIX}خلاصه` استفاده کنی."
        )

    if sub in ("مستثنی", "exclude"):
        assistant_state["exclude"].add(event.chat_id)
        assistant_state["include"].discard(event.chat_id)
        await save_assistant()
        return await event.edit("🚫 این چت مستثنی شد (منشی اینجا پاسخ نمی‌ده)")

    if sub in ("شامل", "include"):
        assistant_state["include"].add(event.chat_id)
        assistant_state["exclude"].discard(event.chat_id)
        await save_assistant()
        return await event.edit("✅ این چت به لیست همیشه‌فعال اضافه شد")

    if sub in ("پاک", "clear"):
        assistant_state["include"].clear()
        assistant_state["exclude"].clear()
        await save_assistant()
        return await event.edit("🗑 لیست مستثنی/شامل پاک شد")

    if sub in ("حافظه", "history"):
        if rest.strip().lower() in ("پاک", "clear"):
            n = _clear_all_history()
            return await event.edit(f"🗑 حافظه‌ی مکالمه‌ی {n} چت پاک شد")
        if config.ASSISTANT_HISTORY_LIMIT <= 0:
            return await event.edit(
                "🧠 حافظه‌ی مکالمه‌ی منشی خاموشه (`ASSISTANT_HISTORY_LIMIT=0`)."
            )
        return await event.edit(
            f"🧠 حافظه‌ی مکالمه: تا {config.ASSISTANT_HISTORY_LIMIT} پیامِ آخرِ هر مکالمه "
            f"({len(_conv_history)} مکالمه فعال)\n"
            f"برای پاک‌کردن: `{PREFIX}منشی حافظه پاک`"
        )

    await event.edit(f"دستور نامعتبره. برای وضعیت کامل: `{PREFIX}منشی`")


_ASSISTANT_AI_SYSTEM = (
    "شما دستیارِ شخصیِ صاحبِ این اکانتِ تلگرام هستید و دارید وقتی صاحبِ اکانت "
    "آفلاین/مشغوله به‌جاش به پیام‌ها پاسخِ کوتاه و مؤدبانه می‌دید. پاسخ رو خیلی "
    "کوتاه (حداکثر ۲-۳ جمله) و به همون زبانِ پیامِ ورودی بده، بدون مقدمه‌چینی."
)


@client.on(events.NewMessage(incoming=True))
async def assistant_autoreply(event):
    # تنها تفاوتِ اصلیِ این نسخه: قبل از این‌که اصلاً به enabled نگاه کنیم،
    # یه‌بار دیگه (کاملاً محلی و رایگان - بدونِ I/O) از رویِ سیگنال‌های فعلی
    # بازمحاسبه‌اش می‌کنیم. یعنی صحتِ تصمیم دیگه وابسته به این نیست که آخرین
    # دورِ اجرای assistant_status_watcher (تسکِ پس‌زمینه) کِی بوده یا حتی
    # اصلاً هنوز زنده‌ست - همین‌جا، درست لحظه‌ی رسیدنِ پیام، دوباره چک می‌شه.
    if assistant_state["auto_detect"]:
        _safe_recompute()

    if not assistant_state["enabled"]:
        return
    if not assistant_state["ai_mode"] and not assistant_state["text"]:
        return
    sender_id = event.sender_id
    if sender_id is None or sender_id == runtime.SELF_ID:
        return
    if not _assistant_should_respond(event):
        return

    key = (event.chat_id, sender_id)
    if not assistant_state["ai_mode"]:
        # حالتِ متنِ ثابت: فقط یک‌بار به هر نفر توی هر نشست، تا اسپم نشه.
        if key in assistant_state["replied"]:
            return
        assistant_state["replied"].add(key)
    # حالتِ هوش‌مصنوعی: هیچ محدودیتی نداره - به تک‌تکِ پیام‌ها جواب می‌ده،
    # چون هر جواب بر اساسِ همون پیامِ مشخص تولید می‌شه (نه یه متنِ تکراری).

    try:
        delay = assistant_state["delay"]
        if delay > 0:
            async with client.action(event.chat_id, "typing"):
                await asyncio.sleep(delay)

        reply_text = assistant_state["text"]
        used_ai = False
        if assistant_state["ai_mode"]:
            try:
                incoming_text = event.raw_text or ""
                if not incoming_text and audio.is_audio_message(event.message):
                    # پیامِ ورودی صوتیه؛ قبل از دادن به AI خودمون رونویسی می‌کنیم.
                    try:
                        incoming_text = await audio.transcribe_message(event.message)
                    except (ai.AIDisabledError, ai.AIRequestError):
                        incoming_text = ""
                incoming_text = incoming_text or "(بدون متن)"
                hist_key = _history_key(event.chat_id, sender_id)
                # 🧠 خاطراتِ مرتبطِ حافظه‌ی هوشمند بر اساسِ متنِ پیامِ ورودی
                _system_prompt = _ASSISTANT_AI_SYSTEM
                try:
                    _memory_block = await ai.build_memory_context(incoming_text, max_chars=800)
                except Exception:
                    _memory_block = ""
                if _memory_block:
                    _system_prompt = _ASSISTANT_AI_SYSTEM + "\n\n" + _memory_block
                messages = [
                    {"role": "system", "content": _system_prompt},
                    *_get_history_messages(hist_key),
                    {"role": "user", "content": incoming_text},
                ]
                ai_answer = await ai.ask_ai(messages, max_tokens=300)
                if ai_answer:
                    reply_text = ai_answer
                    used_ai = True
                    _remember_exchange(hist_key, incoming_text, ai_answer)
            except (ai.AIDisabledError, ai.AIRequestError):
                _record_error()
                logger.exception("خطا در پاسخِ هوش‌مصنوعیِ منشی - fallback به متنِ ثابت")

        if not reply_text:
            return  # نه متنِ ثابتی هست، نه AI جواب داد

        # فقط وقتی پاسخ واقعاً از AI اومده باشه (نه متنِ ثابتِ خودِ owner)
        # برچسبِ مخفیِ «نوشته‌شده با AI» بهش اضافه می‌شه.
        entities = None
        if used_ai:
            reply_text, entities = ai.tag_ai_text(reply_text)

        # قبل از await (نه بعدش) مارک می‌کنیم: آپدیتِ «پیامِ خروجیِ جدید»/
        # «خوندنِ پیام» که خودِ همین event.reply() تولید می‌کنه، ممکنه به‌عنوانِ
        # یه تسکِ جدا زودتر از برگشتنِ این await پردازش بشه - اگه *بعد* از
        # reply() مارک می‌کردیم، ممکن بود اون یکی به‌غلط «خودِ کاربر همین الان
        # فعالیت کرد» حساب بشه و بلافاصله منشی رو خاموش کنه.
        global _last_assistant_reply_at
        _last_assistant_reply_at = datetime.now(timezone.utc)
        _auto_reply_in_flight[event.chat_id] = _auto_reply_in_flight.get(event.chat_id, 0) + 1
        try:
            await event.reply(reply_text, formatting_entities=entities)
        finally:
            remaining = _auto_reply_in_flight.get(event.chat_id, 1) - 1
            if remaining <= 0:
                _auto_reply_in_flight.pop(event.chat_id, None)
            else:
                _auto_reply_in_flight[event.chat_id] = remaining
    except Exception:
        _record_error()
        logger.exception("خطا در پاسخ خودکار منشی")


def _mark_activity(kind: str) -> None:
    """
    ثبتِ «همین الان یه نشونه‌ی واقعی از حضورم دیده شد» - از دو هندلرِ پایین
    صدا زده می‌شه (پیامِ خروجی / خوندنِ پیام). هر دو یعنی «الان دارم از
    تلگرام استفاده می‌کنم»، فقط با شکلِ متفاوت؛ auto_detect=True باشه، بلافاصله
    enabled هم از روش بازمحاسبه می‌شه (نه صبر تا دورِ بعدیِ تسکِ پس‌زمینه).
    """
    global _last_self_activity, _last_self_activity_kind
    _last_self_activity = datetime.now(timezone.utc)
    _last_self_activity_kind = kind
    # در حالتِ «status» فعال/غیرفعال‌شدن فقط از وضعیتِ آنلاین/آفلاینِ پروفایل
    # تعیین می‌شه (نه از پیام‌ها) - پس اینجا enabled رو دست نمی‌زنیم.
    if assistant_state["auto_detect"] and config.ASSISTANT_PRESENCE_MODE != "status":
        _safe_recompute()


@client.on(events.NewMessage(outgoing=True))
async def assistant_self_activity_watcher(event):
    """
    هر پیامِ خروجیِ واقعی (چه از همین اسکریپت، چه از گوشی/دسکتاپت - تلگرام
    پیام‌های خروجیِ خودت رو بینِ همه‌ی سشن‌های اکانت sync می‌کنه و این هندلر
    هم همون آپدیت رو می‌بینه) رو به‌عنوانِ «الان پشتِ اکانتم» در نظر می‌گیره.
    """
    if _auto_reply_in_flight.get(event.chat_id, 0) > 0:
        # این خودِ منشیه که داره توی همین چت auto-reply می‌ده، نه کاربر - نادیده بگیر.
        return

    raw = (event.raw_text or "").strip()
    if raw.startswith(PREFIX):
        # این یه دستورِ کنترلیِ خودِ سلف‌بات (مثلِ `.منشی خودکار` یا حتی صرفِ
        # چک‌کردنِ وضعیت با `.منشی`) - نه یه پیامِ واقعی به یه نفر. اگه این‌ها
        # رو هم «فعالیت» حساب می‌کردیم، هر بار که برای عوض‌کردنِ حالت یا
        # چک‌کردنِ وضعیت تایپ می‌کردید، تایمرِ سکوت ریست می‌شد - و همین باعث
        # می‌شد بعدِ برگردوندن به حالتِ خودکار، منشی تا ابد روشن نشه. دستورهای
        # کنترلی نباید نشونه‌ی «الان دارم چت می‌کنم» باشن.
        return

    _mark_activity("message")


@client.on(events.MessageRead(inbox=True))
async def assistant_self_read_watcher(event):
    """
    Read Receipt رویِ Inbox (یعنی پیام‌هایی که *به* شما رسیده‌ن، حالا از یکی
    از سشن‌هاتون - گوشی/دسکتاپ/همین اسکریپت - خونده‌شده حساب می‌شن). این هم
    مثلِ پیامِ خروجی، بینِ همه‌ی سشن‌های یک اکانت sync می‌شه؛ پس صرفِ بازکردنِ
    یه چت و دیدنِ پیام‌هاش - حتی بدونِ فرستادنِ جواب - هم نشونه‌ی معتبریه که
    الان پشتِ اکانتی. هیچ‌جای این پروژه خودش صراحتاً پیامی رو read-acknowledge
    نمی‌کنه (send_read_acknowledge جایی صدا زده نمی‌شه)، پس این آپدیت همیشه از
    یه اقدامِ واقعیِ انسانی میاد، نه از خودِ ربات.
    """
    if _auto_reply_in_flight.get(event.chat_id, 0) > 0:
        # احتیاطِ اضافه: اگه فرستادنِ پاسخِ خودِ منشی هم به‌عنوانِ عوارضِ جانبی
        # باعثِ آپدیتِ read بشه، نباید این رو با فعالیتِ واقعیِ کاربر اشتباه
        # بگیریم - دقیقاً همون گاردِ هندلرِ پیامِ خروجیِ بالا.
        return
    _mark_activity("read")


def _recompute_enabled_from_signals() -> None:
    """
    فقط وقتی auto_detect=True صدا زده می‌شه (نه موقعِ قفلِ دستی). دو سیگنالِ
    کاملاً محلی رو ترکیب می‌کنه:

      ۱) اگه الان داخلِ یه بازه‌ی زمان‌بندی‌شده باشیم -> همیشه روشن، صرف‌نظر
         از فعالیتِ اخیر.
      ۲) وگرنه -> بر اساسِ همون تایمرِ سکوت/فعالیتِ (پیام یا خوندن) تصمیم
         می‌گیریم.

    هیچ درخواستی به تلگرام نمی‌زنه، پس هیچ‌وقت نمی‌تونه FloodWait بده. هر
    باری که enabled واقعاً عوض می‌شه، یه خطِ لاگِ info هم ثبت می‌شه - برای
    این‌که موقعِ عیب‌یابی (مثلاً از لاگِ Railway) بشه دید دقیقاً کِی و چرا
    روشن/خاموش شده.
    """
    kind, window = _current_signal_reason()
    if kind == "schedule":
        new_enabled = True
        reason = f"بازه‌ی زمان‌بندیِ «{(window or {}).get('label') or 'بدون‌برچسب'}»"
    else:
        # دو لایه با دو آستانه‌ی جدا:
        #  - لایه‌ی محلی (پیام/خوندن از همین سشن‌های اکانت): آستانه‌ی معمول
        #    (ASSISTANT_ONLINE_THRESHOLD) — سیگنالِ قوی و مطمئن.
        #  - لایه‌ی سشن (date_active سشن‌های غیر-current): آستانه‌ی بزرگ‌تر
        #    (ASSISTANT_SESSION_ONLINE_THRESHOLD، پیش‌فرض ۵۴۰ ثانیه) چون سشن‌های
        #    بازِ دسکتاپ/وب گاهی فعالیت‌های ریزِ پس‌زمینه ثبت می‌کنند و نباید
        #    به‌تنهایی جلوی روشن‌شدنِ منشی رو بگیرن.
        # خاموش‌کردنِ لایه‌ی سشن: ASSISTANT_SESSION_ONLINE_THRESHOLD=0
        local_gap = _seconds_since_activity()
        session_gap = _seconds_since_session()
        sess_threshold = config.ASSISTANT_SESSION_ONLINE_THRESHOLD
        sess_counts = bool(sess_threshold)  # ۰ یعنی لایه‌ی سشن کلاً کنار

        local_online = local_gap is not None and local_gap < config.ASSISTANT_ONLINE_THRESHOLD
        session_online = (
            sess_counts and session_gap is not None
            and session_gap < sess_threshold
        )
        online = local_online or session_online

        if local_gap is None and session_gap is None:
            reason = "هنوز هیچ سیگنالی از استارت دیده نشده"
        elif online:
            if local_online and session_online:
                src_fa = "هر دو منبع"
            elif session_online:
                src_fa = "سشن‌های اکانت"
            else:
                src_fa = "سیگنالِ محلی"
            gap = local_gap if local_online else session_gap
            thr = config.ASSISTANT_ONLINE_THRESHOLD if local_online else sess_threshold
            reason = f"{int(gap)} ثانیه پیش فعالیتی از {src_fa} دیدیم (آستانه {int(thr)}s)"
        else:
            parts = [f"محلی: {int(local_gap)}s" if local_gap is not None else "محلی: —"]
            parts.append(
                f"سشن‌ها: {int(session_gap)}s" if session_gap is not None
                else ("سشن‌ها: خاموش" if not sess_counts else "سشن‌ها: —")
            )
            reason = (
                "بی‌سیگنال — " + " | ".join(parts)
                + f" (آستانه‌ها: {config.ASSISTANT_ONLINE_THRESHOLD}s / {sess_threshold}s)"
            )

        new_enabled = not online

    if new_enabled != assistant_state["enabled"]:
        if new_enabled:
            assistant_state["replied"] = set()  # نشست تازه = دوباره به همه جواب بده
        assistant_state["enabled"] = new_enabled
        logger.info("منشی %s شد - دلیل: %s", "روشن" if new_enabled else "خاموش", reason)


async def assistant_status_watcher():
    """
    هر چند ثانیه یک‌بار (ASSISTANT_CHECK_INTERVAL) وضعیتِ enabled رو بر اساسِ
    زمان‌بندی + آخرین نشونه‌ی فعالیت بازبینی می‌کنه - برای این‌که وضعیت حتی
    وقتی هیچ پیامی نمی‌رسه هم (مثلاً برای نمایشِ صحیح توی `.منشی وضعیت`) تازه
    بمونه. تصمیمِ واقعیِ «پاسخ بدم یا نه» دیگه به این حلقه وابسته نیست (نگاهِ
    assistant_autoreply)، ولی این حلقه هنوز برای این‌که وضعیت بدونِ نیاز به
    رسیدنِ پیام هم به‌روز بمونه لازمه.

    بدنه‌ی حلقه توی try/except پیچیده شده: قبلاً یه استثنای پیش‌بینی‌نشده
    می‌تونست کلِ این تسک رو برای همیشه بکشه (asyncio یه تسکِ crash‌کرده رو
    خودش دوباره اجرا نمی‌کنه) و enabled دیگه هیچ‌وقت از این مسیر بازبینی
    نمی‌شد. الان خطا فقط لاگ/ثبت می‌شه و دورِ بعدی طبقِ معمول ادامه پیدا
    می‌کنه - این حلقه دیگه هیچ‌وقت به‌طورِ کامل نمی‌میره.

    اگه با `.منشی روشن` یا `.منشی خاموش` دستی قفلش کرده باشی (auto_detect
    خاموش)، این تابع اصلاً دست به enabled نمی‌زنه.
    """
    from .. import health
    while True:
        try:
            # در حالتِ «status» این حلقه نباید از رویِ سیگنال‌های پیام تصمیم
            # بگیره (تصمیم با pollerِ وضعیتِ پروفایله)؛ فقط زمان‌بندی رو چک
            # می‌کنیم که اگر داخلِ بازه‌ی «حتماً روشن» بودیم، روشن بشه.
            if assistant_state["auto_detect"] and config.ASSISTANT_PRESENCE_MODE != "status":
                _recompute_enabled_from_signals()
            elif assistant_state["auto_detect"]:
                kind, window = _current_signal_reason()
                if kind == "schedule" and not assistant_state["enabled"]:
                    assistant_state["enabled"] = True
                    logger.info(
                        "منشی روشن شد - بازه‌ی زمان‌بندیِ «%s»",
                        (window or {}).get("label") or "بدون‌برچسب",
                    )
            health.update_worker_status("assistant", "ok")
        except Exception as exc:
            _record_error()
            logger.exception(
                "خطا در تسکِ پس‌زمینه‌ی منشی - نادیده گرفته شد و در دورِ بعدی دوباره امتحان می‌شه"
            )
            try:
                health.update_worker_status("assistant", "error", error=str(exc))
            except Exception:
                pass
        await asyncio.sleep(config.ASSISTANT_CHECK_INTERVAL)


async def _poll_session_activity() -> bool:
    """
    یک‌بار account.getAuthorizations رو صدا می‌زنه و max(date_active) روی
    همه‌ی سشن‌ها رو به‌عنوانِ آخرین فعالیتِ انسانی ثبت می‌کنه.

    true یعنی poll موفق بود؛ false یعنی امشب نه (خطا/FloodWait) - caller
    backoff رو مدیریت می‌کنه. خودِ این تابع هرگز استثنا به بیرون نمی‌ده.
    """
    global _last_session_seen, _last_session_poll_ok, _session_poll_failures
    global _session_poll_flood_until
    import time as _time
    import logging as _log
    from telethon import functions, errors as _errors

    now_epoch = _time.time()
    if now_epoch < _session_poll_flood_until:
        return False
    try:
        result = await client(functions.account.GetAuthorizationsRequest())
    except _errors.FloodWaitError as e:
        wait = min(max(e.seconds, 30), 600)
        _session_poll_flood_until = now_epoch + wait + 30
        logger.warning("poll سشن‌ها FloodWait داد - %s ثانیه صبر می‌کنیم", wait)
        return False
    except Exception:
        _session_poll_failures += 1
        backoff = min(60 * _session_poll_failures, 600)
        _session_poll_flood_until = now_epoch + backoff
        _record_error()
        logger.warning(
            "poll سشن‌ها fail شد (تلاش متوالی %s) - %s ثانیه backoff",
            _session_poll_failures, backoff, exc_info=True,
        )
        return False

    _session_poll_failures = 0
    now = datetime.now(timezone.utc)
    newest = None
    for auth in getattr(result, "authorizations", []) or []:
        # ⚠️ سشنِ current (همین پروسه‌ی سلف‌بات) باید حذف بشه: date_active اون
        # با هر درخواستِ خودِ بات (از جمله همین poll) تازه می‌شه و اگه شمرده بشه،
        # همیشه «تو آنلاینی» جعل می‌کنه و منشی هیچ‌وقت روشن نمی‌شه. فقط سشن‌های
        # واقعاً انسانی (گوشی/دسکتاپ/وبِ خودت) معیارِ حضورن - درسِ گرفته‌شده از
        # نسخه‌ی قدیمی تک‌فایلی.
        if getattr(auth, "current", False):
            continue
        active = getattr(auth, "date_active", None)
        if active is None:
            continue
        if active.tzinfo is None:
            active = active.replace(tzinfo=timezone.utc)
        if newest is None or active > newest:
            newest = active
    if newest is not None:
        _last_session_seen = max(_last_session_seen, newest)
    _last_session_poll_ok = now
    return True


async def assistant_session_poller():
    """
    لایه‌ی دومِ تشخیصِ حضور: با فاصله‌ی ASSISTANT_SESSION_POLL_INTERVAL ثانیه،
    date_active سشن‌های اکانت رو چک می‌کنه. حتی اگه این پروسه هیچ پیامی ندیده
    باشه، هر تعاملِ تو با اپ تلگرام (توی هر دستگاهی) اینجا ثبت می‌شه - پس
    منشی دیگه وسطِ حضورت (مثلاً وقتی فقط داری می‌خونی و چیزی نمی‌فرستی)
    روشن نمی‌شه.
    """
    from .. import health
    await asyncio.sleep(10)  # بذار اتصالِ اولیه جا بیفته
    while True:
        try:
            if (
                config.ASSISTANT_PRESENCE_MODE == "signals"
                and assistant_state["auto_detect"]
            ):
                ok = await _poll_session_activity()
                health.update_worker_status(
                    "assistant_session_poll", "ok" if ok else "degraded"
                )
            else:
                health.update_worker_status("assistant_session_poll", "idle")
        except Exception as exc:
            _record_error()
            logger.exception("خطا در poller سشن‌های منشی - دورِ بعد ادامه می‌دیم")
            try:
                health.update_worker_status(
                    "assistant_session_poll", "error", error=str(exc)
                )
            except Exception:
                pass
        await asyncio.sleep(config.ASSISTANT_SESSION_POLL_INTERVAL)


async def _poll_profile_status() -> bool:
    """
    یک‌بار وضعیتِ آنلاین/آفلاینِ خودم رو از تلگرام می‌پرسه (همون چیزی که
    توی اپِ دیگران دیده می‌شه: «آنلاین» یا «آخرین بازدید …»).

    true = poll موفق (نتیجه در _last_profile_status_online ثبت شد)
    false = این دور نه (خطا/FloodWait) - caller backoff رو مدیریت می‌کنه.
    """
    global _last_profile_status_online, _last_status_poll_ok
    global _status_poll_failures, _status_poll_flood_until
    import time as _time
    from telethon import functions, errors as _errors
    from telethon.tl.types import UserStatusOffline

    now_epoch = _time.time()
    if now_epoch < _status_poll_flood_until:
        return False
    try:
        me = await client.get_me()
        full = await client(functions.users.GetFullUserRequest(id=me))
        user = full.users[0] if getattr(full, "users", None) else me
        status = getattr(user, "status", None)
        # UserStatusOnline → آنلاین؛ UserStatusOffline → آفلاین (هرچقدر هم
        # was_online قدیمی باشه، تلگرام دیگه «آنلاین» نشونش نمی‌ده پس ما هم
        # آفلاین حساب می‌کنیم - به‌محضِ عوض‌شدنِ لیبل). بقیه‌ی حالت‌ها
        # (UserStatusRecently و …) یعنی مخفی/آفلاین از دیدِ لیبل.
        _last_profile_status_online = not isinstance(status, UserStatusOffline)
    except _errors.FloodWaitError as e:
        wait = min(max(e.seconds, 30), 600)
        _status_poll_flood_until = now_epoch + wait + 30
        logger.warning("poll وضعیتِ پروفایل FloodWait داد - %s ثانیه صبر می‌کنیم", wait)
        return False
    except Exception:
        _status_poll_failures += 1
        backoff = min(60 * _status_poll_failures, 600)
        _status_poll_flood_until = now_epoch + backoff
        _record_error()
        logger.warning(
            "poll وضعیتِ پروفایل fail شد (تلاش متوالی %s) - %s ثانیه backoff",
            _status_poll_failures, backoff, exc_info=True,
        )
        return False

    _status_poll_failures = 0
    _last_status_poll_ok = datetime.now(timezone.utc)
    return True


async def assistant_status_poller():
    """
    حالتِ پیش‌فرضِ تشخیص: هر ASSISTANT_STATUS_POLL_INTERVAL ثانیه مستقیم
    «آنلاین بودنِ» خودت رو از تلگرام می‌پرسه و منشی رو به‌محضِ آفلاین‌شدنت
    روشن می‌کنه (و به‌محضِ آنلاین‌شدنت خاموش). تصمیم به پیام‌های تو هیچ
    ربطی نداره.
    """
    from .. import health
    await asyncio.sleep(5)
    while True:
        try:
            if (
                config.ASSISTANT_PRESENCE_MODE == "status"
                and assistant_state["auto_detect"]
            ):
                ok = await _poll_profile_status()
                if ok:
                    online = _last_profile_status_online
                    # ⚠️ آنلاینِ جعلی: وقتی منشی خودش پیام می‌فرسته، تلگرام
                    # اکانت را چند ده ثانیه «آنلاین» نشون می‌ده (فعالیتِ
                    # سشنِ خودِ بات). اگر داخلِ grace بعدِ آخرین پاسخِ منشی
                    # باشیم، به «آنلاین» اعتماد نمی‌کنیم — وگرنه منشی با
                    # پیامِ خودش خاموش می‌شد و چرخه‌ی روشن/خاموش می‌افتاد.
                    in_reply_grace = (
                        _last_assistant_reply_at is not None
                        and (datetime.now(timezone.utc) - _last_assistant_reply_at).total_seconds()
                        < config.ASSISTANT_REPLY_STATUS_GRACE
                    )
                    if online and in_reply_grace:
                        health.update_worker_status(
                            "assistant_status_poll", "grace"
                        )
                    else:
                        desired = not online  # آنلاین → خاموش؛ آفلاین → روشن
                        if desired != assistant_state["enabled"]:
                            if desired:
                                assistant_state["replied"] = set()
                            assistant_state["enabled"] = desired
                            logger.info(
                                "منشی %s شد - وضعیتِ پروفایل: %s%s",
                                "روشن" if desired else "خاموش",
                                "آنلاین" if online else "آفلاین",
                                " (داخلِ graceِ پاسخِ خودِ منشی)" if in_reply_grace else "",
                            )
                health.update_worker_status(
                    "assistant_status_poll", "ok" if ok else "degraded"
                )
            else:
                health.update_worker_status("assistant_status_poll", "idle")
        except Exception as exc:
            _record_error()
            logger.exception("خطا در poller وضعیتِ پروفایل - دورِ بعد ادامه می‌دیم")
            try:
                health.update_worker_status(
                    "assistant_status_poll", "error", error=str(exc)
                )
            except Exception:
                pass
        await asyncio.sleep(config.ASSISTANT_STATUS_POLL_INTERVAL)
