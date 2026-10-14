"""
قابلیت‌های جدیدِ نسخه‌ی ارتقا:

  • `.تقویم`  → تقویمِ ماهِ جاری به شمسی و میلادی
  • `.تبدیل‌تاریخ 1403/05/01` یا `.تبدیل‌تاریخ 2025-08-22` → تشخیصِ خودکار و
    تبدیلِ دوطرفه‌ی شمسی↔میلادی (الگوریتمِ exactِ jalaali، بدونِ وابستگی)
  • `.بینایی <سوال اختیاری>` → ریپلای روی عکس + پرسش از AI Vision
  • `.نشست‌ها` → لیستِ دستگاه‌های لاگین‌شده به اکانت + امکانِ خروجِ اجباری
  • `.اطلاعات‌گروه` → آمار و اطلاعاتِ کاملِ گروه فعلی
  • `.اسپویل <متن>` → ارسالِ متن به‌صورتِ اسپویلِ تلگرام
  • `.دیکشنری <کلمه>` → معنیِ انگلیسی↔فارسیِ سریع (سرویسِ رایگانِ MyMemory)

تبدیلِ تاریخِ شمسی (jalaali) با الگوریتمِ دقیقِ معروف (same as jalaali-js)
این‌جا پیاده شده تا هیچ وابستگیِ جدیدی به requirements اضافه نشه.
"""
import asyncio
import datetime as dt
import logging

import aiohttp
from telethon import events, functions
from telethon.tl.types import MessageEntitySpoiler

from .. import ai, config
from ..config import PREFIX, TIMEZONE_OFFSET
from ..runtime import client, get_http_session
from ..storage.stats_store import record_error as _record_error
from ..utils import pat

logger = logging.getLogger("selfbot.handlers.extras")


# ============================================================= تقویم شمسی ===
def _div(a: int, b: int) -> int:
    return a // b


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """الگوریتمِ استانداردِ jdf.scr.ir - دقیق و بدونِ خطا."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """الگوریتمِ استانداردِ jdf.scr.ir - دقیق و بدونِ خطا."""
    jy += 1595
    days = (
        -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
        + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30 + 186))
    )
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)
    sal_a = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    for i in range(1, 13):
        if gd <= sal_a[i]:
            gm = i
            break
        gd -= sal_a[i]
    return gy, gm, gd


_FA_MONTHS = ["", "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
_EN_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
_FA_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"]


def _local_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=TIMEZONE_OFFSET)


def _to_fa_digits(s: str) -> str:
    return s.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


@client.on(events.NewMessage(outgoing=True, pattern=pat(["تقویم", "calendar"], arg=False)))
async def calendar_handler(event):
    now = _local_now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    gy, gm, gd = now.year, now.month, now.day
    weekday = _FA_WEEKDAYS[now.weekday()]
    text = (
        f"📅 **امروز:**\n"
        f"🗓 شمسی: **{_to_fa_digits(f'{jd:02d}')} {_FA_MONTHS[jm]} {_to_fa_digits(str(jy))}** ({weekday})\n"
        f"🌍 میلادی: **{gd} { _EN_MONTHS[gm]} {gy}**\n"
        f"⏰ ساعت: **{now.strftime('%H:%M')}**"
    )
    await event.edit(text)


@client.on(events.NewMessage(outgoing=True, pattern=pat(["تبدیل‌تاریخ", "dateconv"])))
async def date_convert_handler(event):
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.edit(
            f"مثال: `{PREFIX}تبدیل‌تاریخ 1403/05/01` یا `{PREFIX}تبدیل‌تاریخ 2025-08-22`\n"
            "فرمتِ شمسی و میلادی هر دو خودکار تشخیص داده می‌شن."
        )
    sep = [c for c in raw if c in "/-."]
    if not sep:
        return await event.edit("فرمت: `1403/05/01` یا `2025-08-22`")
    try:
        parts = [int(p) for p in raw.replace("-", "/").replace(".", "/").split("/")]
        if len(parts) != 3:
            raise ValueError
    except ValueError:
        return await event.edit("فرمت: `1403/05/01` یا `2025-08-22` (سه بخشِ عددی)")
    a, b, c = parts
    if a > 1700:  # میلادی → شمسی
        jy, jm, jd = gregorian_to_jalali(a, b, c)
        gy, gm, gd = a, b, c
    elif a > 1200:  # شمسی → میلادی
        jy, jm, jd = a, b, c
        gy, gm, gd = jalali_to_gregorian(a, b, c)
    else:
        return await event.edit("سال رو دقیق‌تر بنویس (مثل 1403 یا 2025)")
    try:
        dt.date(gy, gm, gd)
    except ValueError:
        return await event.edit("تاریخِ نامعتبره")
    weekday = _FA_WEEKDAYS[dt.date(gy, gm, gd).weekday()]
    await event.edit(
        f"📅 تبدیلِ تاریخ:\n"
        f"🗓 شمسی: **{_to_fa_digits(f'{jd:02d}')} {_FA_MONTHS[jm]} {_to_fa_digits(str(jy))}** ({weekday})\n"
        f"🌍 میلادی: **{gd} {_EN_MONTHS[gm]} {gy}**"
    )


# ============================================================== بینایی AI ===
@client.on(events.NewMessage(outgoing=True, pattern=pat(["بینایی", "vision"])))
async def vision_handler(event):
    question = (event.pattern_match.group(1) or "").strip() or "این تصویر رو با جزئیات توصیف کن."
    if not event.is_reply:
        return await event.edit(f"روی یه عکس ریپلای کن: `{PREFIX}بینایی چی توی این عکسه؟`")
    reply = await event.get_reply_message()
    if not reply.media or type(reply.media).__name__ != "MessageMediaPhoto":
        return await event.edit("❌ پیامِ ریپلای‌شده عکس نیست.")
    await event.edit("👁 در حال تحلیلِ تصویر...")
    try:
        data = await reply.download_media(bytes)
    except Exception as e:
        _record_error()
        return await event.edit(f"❌ خطا در دانلودِ عکس: {e}")
    import base64

    b64 = base64.b64encode(data).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }
    ]
    try:
        answer = await ai.ask_ai(messages, max_tokens=config.AI_MAX_TOKENS)
    except ai.AIDisabledError:
        return await event.edit("⚠️ برای `.بینایی` باید `AI_API_KEY` با مدلِ Vision تنظیم شده باشه.")
    except ai.AIRequestError as e:
        _record_error()
        return await event.edit(f"❌ خطا در تحلیلِ تصویر: {e}")
    tagged, entities = ai.tag_ai_text(f"👁 {answer}")
    await event.edit(tagged, formatting_entities=entities)


# ============================================================== نشست‌ها ====
@client.on(events.NewMessage(outgoing=True, pattern=pat(["نشست‌ها", "sessions"])))
async def sessions_handler(event):
    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split()
    sub = parts[0].lower() if parts else ""

    if sub in ("خروج", "terminate", "logout") and len(parts) > 1:
        hash_str = parts[1]
        if not hash_str.lstrip("-").isdigit():
            return await event.edit(f"مثال: `{PREFIX}نشست‌ها خروج 1234567890` (hash از لیستِ بالا)")
        try:
            await client(functions.account.ResetAuthorizationRequest(hash_=int(hash_str)))
            return await event.edit(f"✅ نشستِ `{hash_str}` از اکانت خارج شد")
        except Exception as e:
            _record_error()
            return await event.edit(f"❌ خطا در خروجِ اجباری: {e}")

    await event.edit("⏳ در حال دریافتِ نشست‌های فعال...")
    try:
        result = await client(functions.account.GetAuthorizationsRequest())
    except Exception as e:
        _record_error()
        return await event.edit(f"❌ خطا: {e}")
    lines = []
    for auth in result.authorizations:
        current = " ✅ **همین دستگاه**" if auth.current else ""
        model = auth.device_model or "نامشخص"
        emoji = "📱" if any(k in model for k in ("Android", "iOS", "iPhone", "iPad")) else "💻"
        lines.append(
            f"{emoji} **{model}** — {auth.platform or '؟'}{current}\n"
            f"   📍 {auth.country or '؟'} — {auth.date_created:%Y-%m-%d} — hash: `{auth.hash}`"
        )
    text = f"🔐 **نشست‌های فعال اکانت شما** ({len(result.authorizations)}):\n\n" + "\n".join(lines)
    text += f"\n\nبرای خروجِ اجباری: `{PREFIX}نشست‌ها خروج <hash>` (با احتیاط!)"
    await event.edit(text)


# ======================================================== اطلاعات‌گروه ====
@client.on(events.NewMessage(outgoing=True, pattern=pat(["اطلاعات‌گروه", "groupinfo"], arg=False)))
async def group_info_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")
    await event.edit("⏳ در حال دریافتِ اطلاعات...")
    try:
        full = await client.get_entity(event.chat_id)
        participants_count = (await client(functions.channels.GetFullChannelRequest(event.chat_id))).full_chat.participants_count if event.is_channel else None
    except Exception as e:
        _record_error()
        return await event.edit(f"❌ خطا: {e}")
    text = (
        f"👥 **اطلاعات گروه**\n"
        f"🏷 نام: **{full.title}**\n"
        f"🆔 آیدی: `{event.chat_id}`\n"
    )
    if full.username:
        text += f"🔗 یوزرنیم: @{full.username}\n"
    if participants_count:
        text += f"👤 تعدادِ اعضا: **{participants_count:,}**\n"
    text += f"🛡 دسترسی‌های شما: {'ادمین ✅' if (await client.get_permissions(event.chat_id, 'me')).is_admin else 'عضو عادی'}"
    await event.edit(text)


# ============================================================== اسپویل ====
@client.on(events.NewMessage(outgoing=True, pattern=pat(["اسپویل", "spoiler"])))
async def spoiler_handler(event):
    text = (event.pattern_match.group(1) or "").strip()
    if not text and event.is_reply:
        reply = await event.get_reply_message()
        text = reply.raw_text or ""
    if not text:
        return await event.edit(f"مثال: `{PREFIX}اسپویل این متن محرفه!`")
    entities = [MessageEntitySpoiler(offset=0, length=len(text))]
    await event.delete()
    await client.send_message(event.chat_id, text, formatting_entities=entities)


# ============================================================ دیکشنری ====
@client.on(events.NewMessage(outgoing=True, pattern=pat(["دیکشنری", "dict", "معنی"])))
async def dict_handler(event):
    word = (event.pattern_match.group(1) or "").strip()
    if not word:
        return await event.edit(f"مثال: `{PREFIX}دیکشنری book` یا `{PREFIX}دیکشنری سلام`")
    await event.edit("📖 در حال جستجو...")
    session = await get_http_session()
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with session.get(
            "https://api.mymemory.translated.net/get",
            params={"q": word, "langpair": "en|fa"},
            timeout=timeout,
        ) as r:
            data = await r.json(content_type=None)
    except Exception:
        _record_error()
        return await event.edit("❌ خطا در دسترسی به سرویسِ دیکشنری")
    translation = (data.get("responseData") or {}).get("translatedText", "")
    if not translation or "MYMEMORY WARNING" in translation:
        return await event.edit(f"معنیِ «{word}» پیدا نشد")
    await event.edit(f"📖 **{word}** = {translation}")

# ====================================================== تحلیل هوشمند (Vision) ===
_VISION_PRESETS = {
    "خطا": "این اسکرین‌شاتِ یک خطاست. به فارسی تحلیل کن: ❌ خطای اصلی، 🔧 علتِ احتمالی، ✅ راه‌حلِ گام‌به‌گام. کوتاه و دقیق.",
    "error": "این اسکرین‌شاتِ یک خطاست. به فارسی تحلیل کن: ❌ خطای اصلی، 🔧 علتِ احتمالی، ✅ راه‌حلِ گام‌به‌گام. کوتاه و دقیق.",
    "کد": "کدِ داخلِ این تصویر را کامل استخراج کن (بلوکِ کد)، بعد در یک جمله بگو چه می‌کند و اگر باگ دارد ذکر کن.",
    "code": "کدِ داخلِ این تصویر را کامل استخراج کن (بلوکِ کد)، بعد در یک جمله بگو چه می‌کند و اگر باگ دارد ذکر کن.",
    "جدول": "جدولِ این تصویر را استخراج و به‌صورتِ لیستِ ساختاریافته (ردیف به ردیف) بازنویسی کن.",
    "table": "جدولِ این تصویر را استخراج و به‌صورتِ لیستِ ساختاریافته (ردیف به ردیف) بازنویسی کن.",
    "نمودار": "این نمودار را تحلیل کن: نوع، محورها، مقادیرِ کلیدی، و نتیجه‌گیریِ اصلی در دو خط.",
    "chart": "این نمودار را تحلیل کن: نوع، محورها، مقادیرِ کلیدی، و نتیجه‌گیریِ اصلی در دو خط.",
}


@client.on(events.NewMessage(outgoing=True, pattern=pat(["تحلیل", "analyze"])))
async def smart_vision_handler(event):
    """`.تحلیل خطا/کد/جدول/نمودار` روی عکسِ ریپلای‌شده (یا توصیفِ عمومی)."""
    arg = (event.pattern_match.group(1) or "").strip()
    parts = arg.split(maxsplit=1)
    sub = parts[0] if parts else ""
    extra = parts[1].strip() if len(parts) > 1 else ""

    if not event.is_reply:
        return await event.edit(
            "🖼 **تحلیلِ هوشمندِ تصویر**\n\n"
            f"روی یه عکس ریپلای کن:\n"
            f"`{PREFIX}تحلیل خطا` — اسکرین‌شاتِ خطا → علت + راه‌حل\n"
            f"`{PREFIX}تحلیل کد` — استخراجِ کد از تصویر\n"
            f"`{PREFIX}تحلیل جدول` — بازنویسیِ جدول\n"
            f"`{PREFIX}تحلیل نمودار` — تفسیرِ نمودار\n"
            f"`{PREFIX}تحلیل <سوال>` — سوالِ آزاد"
        )

    preset = _VISION_PRESETS.get(sub)
    question = (preset + ("\nسوالِ اضافه: " + extra if extra else "")) if preset else (arg or "این تصویر رو با جزئیات توصیف کن.")
    reply = await event.get_reply_message()
    if not reply.media or type(reply.media).__name__ != "MessageMediaPhoto":
        return await event.edit("❌ پیامِ ریپلای‌شده عکس نیست.")
    await event.edit("👁 در حال تحلیلِ تصویر...")
    try:
        data = await reply.download_media(bytes)
    except Exception as e:
        _record_error()
        return await event.edit(f"❌ خطا در دانلودِ عکس: {e}")
    import base64

    b64 = base64.b64encode(data).decode()
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }
    ]
    try:
        answer = await ai.ask_ai(messages, max_tokens=config.AI_MAX_TOKENS)
    except ai.AIDisabledError:
        return await event.edit("⚠️ برای `.تحلیل` باید `AI_API_KEY` با مدلِ Vision تنظیم شده باشه.")
    except ai.AIRequestError as e:
        _record_error()
        return await event.edit(f"❌ خطا در تحلیلِ تصویر: {e}")
    tagged, entities = ai.tag_ai_text(f"🖼 {answer}")
    await event.edit(tagged, formatting_entities=entities)
