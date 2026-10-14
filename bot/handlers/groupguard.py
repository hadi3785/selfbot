"""
۱۵) مدیریت گروه پیشرفته: فیلترلینک / خوش‌آمدگویی / برچسب‌همه / فیلترِ پورن / فیلترِ اسپم

  - `.فیلترلینک روشن/خاموش/وضعیت`  → حذف خودکار پیام‌های حاویِ لینک از
    اعضای غیرادمینِ همین گروه (چک ادمین‌بودن با client.get_permissions، پس
    خودِ ادمین‌ها و owner همیشه مستثنی‌ان).
  - `.خوش‌آمد روشن/خاموش/وضعیت/متن <متن>`  → پیامِ خوش‌آمدگویی خودکار برای
    عضو جدیدِ همین گروه. توی متن می‌شه از `{نام}` (اسمِ کاربر) یا `{منشن}`
    (تگِ واقعیِ کاربر) استفاده کرد.
  - `.برچسب‌همه <متن اختیاری>`  → با یه دستور همه‌ی اعضای گروه رو تگ می‌زنه؛
    برای کاهشِ ریسکِ اسپم/فلاد، در batchهای چندتایی با فاصله ارسال می‌شه و
    سقفِ تعداد عضو داره - این ویژگی رو با احتیاط و کم استفاده کن.
  - `.فیلترپورن روشن/خاموش/وضعیت/تست`  → هر عکسِ معمولیِ ارسالی از طرفِ اعضای
    غیرادمین با AI (نیازمندِ AI_API_KEY + مدلِ Vision-دار مثلِ gpt-4o-mini)
    بررسی و در صورتِ تشخیصِ محتوای نامناسب حذف می‌شه. اگه AI در دسترس نباشه
    یا خطا بده، fail-open می‌کنه (کاری با عکس نداره؛ ترجیح بر ریسک‌نکردنِ
    حذفِ اشتباهیِ عکسِ سالمه) - و این خطا رو با warning ثبت می‌کنه. فعلاً فقط
    عکسِ فشرده رو پوشش می‌ده، نه ویدیو/GIF/استیکر/فایل. زیردستورِ `تست` (با
    ریپلای روی یه عکس) پاسخِ خامِ AI یا خطای دقیق رو مستقیم توی چت نشون می‌ده -
    برای عیب‌یابیِ سریع، بدونِ نیاز به لاگ‌های Railway.
  - `.فیلتراسپم روشن/خاموش/وضعیت`  → کاملاً محلی (بدونِ نیاز به AI): اگه یه
    عضوِ غیرادمین توی یه بازه‌ی زمانیِ کوتاه بیش از حد پیام بفرسته (فلاد) یا
    عینِ یه متن رو چندبار پشتِ‌سرِهم تکرار کنه، اون پیام‌ها خودکار حذف می‌شن
    و یه هشدارِ کوتاه (با فاصله‌ی زمانی، برای جلوگیری از اسپم‌شدنِ خودِ هشدار)
    توی گروه فرستاده می‌شه.

هر پنج تنظیم (فیلترلینک/خوش‌آمد/فیلترپورن/فیلتراسپم) به‌ازای هر گروه (chat_id)
در PostgreSQL ذخیره می‌شن، پس با ری‌استارت/ری‌دیپلوی از دست نمی‌رن.
"""
import asyncio
import base64
import datetime as dt
import logging
import re
import time
from collections import deque

from telethon import events

from .. import ai, config, runtime
from ..config import PREFIX
from ..runtime import client
from ..storage.group_guard_store import (
    get_welcome_text,
    group_guard_state,
    is_link_filter_enabled,
    is_porn_filter_enabled,
    is_profanity_filter_enabled,
    is_spam_filter_enabled,
    is_welcome_enabled,
    set_link_filter,
    set_porn_filter,
    set_profanity_filter,
    set_spam_filter,
    set_welcome_enabled,
    set_welcome_text,
    MEDIA_LOCK_TYPES,
    get_media_locks,
    is_media_locked,
    set_all_media_locks,
    set_media_lock,
)
from ..storage.word_filter_store import (
    add_word_filter,
    remove_word_filter,
    get_word_filters,
    clear_word_filters,
    search_word_in_filters,
)
from ..storage.warn_store import (
    add_warn,
    remove_warn,
    clear_warnings,
    get_user_warnings,
    list_warnings,
    get_warn_settings,
    update_warn_settings,
)
from ..storage.activity_store import (
    increment_warnings,
    increment_deleted,
    increment_joined,
    increment_left,
    record_message_activity,
    get_summary,
)
from ..storage.stats_store import record_error as _record_error
from ..utils import pat

logger = logging.getLogger("selfbot.handlers.groupguard")

# لینک/دعوتِ تلگرام یا هر URL دیگه (http/https/www./t.me/telegram.me) - عمداً
# @username رو چک نمی‌کنیم چون ریپلای/منشنِ عادیِ اعضا هم همین الگو رو داره
# و false-positive زیاد می‌شد.
_LINK_RE = re.compile(
    r"(https?://|www\.[a-z0-9-]+\.[a-z]{2,}|t(?:elegram)?\.me/)", re.IGNORECASE
)

_TAG_BATCH_SIZE = 5
_TAG_BATCH_DELAY = 3  # ثانیه بین هر batch - برای کاهش ریسک اسپم/فلاد
_TAG_MAX_MEMBERS = 200  # سقف امن؛ گروه‌های بزرگ‌تر ریسک محدودیت اکانت رو بالا می‌برن

# کشِ کوتاه‌مدتِ نتیجه‌ی ادمین‌بودن - چون فیلترِ اسپم رویِ *هر* پیامِ گروه چک
# می‌کنه، بدونِ این کش هر پیام یه درخواستِ شبکه‌ایِ جدید به تلگرام می‌زد.
_ADMIN_CACHE_TTL = 300  # ثانیه
_admin_cache: dict[tuple[int, int], tuple[bool, float]] = {}


async def _is_admin_or_creator(event) -> bool:
    """
    نکته (تاریخچه): قبلاً وقتی get_permissions fail می‌شد، تابع False ("ادمین
    نیست") برمی‌گردوند - که یعنی پیام حذف می‌شد؛ درحالی‌که کامنتِ خودِ کد
    می‌گفت هدف اینه که با عدمِ اطمینان، پیام حذف *نشه*. اون‌موقع درستش کردیم:
    روی خطا True ("برای احتیاط، ادمین فرض کن") برمی‌گردوند.

    باگِ واقعی (پیدا شده بعد از گزارشِ کاربر - عکسِ NSFWِ یه عضوِ غیرادمین حذف
    نمی‌شد با این‌که `.فیلترپورن تست` رویِ همون عکس درست NSFW تشخیص می‌داد):
    قبلاً اینجا `client.get_permissions(chat_id, user_id)` با یه آی‌دیِ خام
    صدا زده می‌شد. تلتون برای resolveِ یه آی‌دیِ خام باید اون یوزر رو از کشِ
    داخلیِ session پیدا کنه؛ اگه فرستنده کسی باشه که اکانتِ خودمون قبلاً
    مستقیماً باهاش تعامل نداشته (خیلی معموله توی گروه‌های بزرگ)، همین خط با
    `ValueError: Could not find the input entity...` fail می‌شد - که می‌افتاد
    توی fail-openِ بالا و اون کاربرِ کاملاً غیرادمین رو ۵ دقیقه (به‌خاطرِ کش)
    «ادمین» فرض می‌کرد؛ یعنی نه فقط فیلترِ پورن، فیلترِ لینک/اسپم/فحش/کلمه هم
    برای همون کاربر توی همون بازه بی‌صدا غیرفعال می‌شدن. بدونِ هیچ لاگِ خطایی،
    چون قبلاً قورت می‌شد.

    فیکس: به‌جای resolveِ یه آی‌دیِ خام، از خودِ event.get_permissions()
    استفاده می‌کنیم - چون پیامِ ورودی خودش از قبل حاویِ Peerِ کاملِ فرستنده‌ست
    و برخلافِ client.get_permissions(chat_id, user_id) نیازی به کشِ سشن
    نداره، پس این خطای خاص اصلاً پیش نمی‌آد.
    """
    chat_id = event.chat_id
    user_id = event.sender_id
    key = (chat_id, user_id)
    now = time.monotonic()
    cached = _admin_cache.get(key)
    if cached is not None and now - cached[1] < _ADMIN_CACHE_TTL:
        return cached[0]
    try:
        # ⚠️ NewMessage.Event متدِ get_permissions ندارد (فقط ChatAction دارد) —
        # نسخه‌ی قبلی AttributeError می‌داد و همیشه به fail-open می‌افتاد (یعنی
        # فیلترها برای همه غیرفعال!). درست: client.get_permissions با entityِ
        # چت از خودِ event (چتِ فرستنده در session کش است؛ resolve می‌شود).
        perms = await client.get_permissions(await event.get_input_chat(), user_id)
        is_admin = bool(getattr(perms, "is_admin", False) or getattr(perms, "is_creator", False))
    except Exception:
        # fallback دوم: GetParticipantRequest خام (بدون نیاز به resolveِ سشنِ تک‌کاربر)
        # چون event خودش Peerِ فرستنده رو داره؛ خیلی از خطاهای get_permissions اینجا پیش نمی‌آن.
        is_admin = None
        try:
            from telethon.tl.functions.channels import GetParticipantRequest
            from telethon.tl.types import (
                ChannelParticipantAdmin,
                ChannelParticipantCreator,
            )
            participant = await client(
                GetParticipantRequest(await event.get_input_chat(), await event.get_input_sender())
            )
            p = participant.participant
            is_admin = isinstance(p, (ChannelParticipantAdmin, ChannelParticipantCreator))
        except Exception:
            pass
        if is_admin is None:
            # اگه واقعاً نتونستیم چک کنیم، برای احتیاط پیام رو حذف نمی‌کنیم (fail-open)
            is_admin = True
            logger.warning(
                "چک ادمین‌بودن برای (chat_id=%s, user_id=%s) هر دو روش fail شد - fail-open (ادمین فرض شد)",
                chat_id, user_id, exc_info=True,
            )
    _admin_cache[key] = (is_admin, now)
    return is_admin


# ---------------------------------------------------------------- فیلترلینک ---
@client.on(events.NewMessage(outgoing=True, pattern=pat(["فیلترلینک", "linkfilter"])))
async def linkfilter_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    sub = (event.pattern_match.group(1) or "").strip().lower()

    if sub in ("روشن", "on"):
        await set_link_filter(event.chat_id, True)
        return await event.edit(
            "✅ فیلترلینک روشن شد.\n"
            "از این به بعد پیام‌های حاویِ لینک از طرفِ اعضای غیرادمینِ این گروه خودکار حذف می‌شن."
        )

    if sub in ("خاموش", "off"):
        await set_link_filter(event.chat_id, False)
        return await event.edit("❌ فیلترلینک این گروه خاموش شد")

    status = "روشن ✅" if is_link_filter_enabled(event.chat_id) else "خاموش ❌"
    await event.edit(
        "🔗 **فیلترلینک**\n"
        f"وضعیتِ این گروه: {status}\n\n"
        f"`{PREFIX}فیلترلینک روشن` / `{PREFIX}فیلترلینک خاموش`\n"
        "⚠️ فقط پیام‌های اعضای غیرادمین حذف می‌شن؛ خودتون و بقیه‌ی ادمین‌ها مستثنی‌اید."
    )


@client.on(events.NewMessage(incoming=True))
async def linkfilter_watcher(event):
    if not event.is_group:
        return
    if not is_link_filter_enabled(event.chat_id):
        return
    sender_id = event.sender_id
    if sender_id is None or sender_id == runtime.SELF_ID:
        return
    text = event.raw_text or ""
    if not _LINK_RE.search(text):
        return
    if await _is_admin_or_creator(event):
        return
    try:
        await event.delete()
    except Exception:
        _record_error()
        logger.exception("خطا در حذف پیامِ لینک‌دار")


# ---------------------------------------------------------------- فیلترِ پورن ---
_PORN_FILTER_SYSTEM = (
    "شما یه فیلترِ محتوای بزرگسالان هستید. فقط بر اساسِ تصویرِ داده‌شده، دقیقاً "
    "با یکی از این دو کلمه جواب بده و هیچ چیزِ دیگه‌ای ننویس: "
    "NSFW اگه تصویر شاملِ نمایشِ صریحِ برهنگی/محتوای جنسی/پورنوگرافی باشه، "
    "یا SAFE در غیرِ این صورت."
)


async def _classify_image(raw: bytes, *, return_raw: bool = False):
    """
    تصویر رو با همون سرویسِ AI که `.پرسش`/`.منشی` هم ازش استفاده می‌کنن تحلیل
    می‌کنه (پس AI_MODEL باید Vision داشته باشه) و پاسخِ مدل رو برمی‌گردونه.
    خطا رو قورت نمی‌ده - AIDisabledError/AIRequestError مستقیم بالا می‌ره؛
    fail-openِ فیلترِ خودکار توی _is_nsfw_image مدیریت می‌شه، نه اینجا.

    return_raw=True یعنی به‌جای فقط متنِ content (str)، کلِ دیکشنریِ JSONِ
    پاسخ برگردونده بشه - فقط دستورِ تستیِ `.فیلترپورن تست` از این استفاده
    می‌کنه تا finish_reason رو هم نشون بده (برای فهمیدنِ این‌که پاسخِ خالی
    یعنی چی: قطع‌شده به‌خاطرِ توکن؟ فیلترِ محتوای خودِ سرویس؟ یا یه stopِ عادی؟).
    """
    b64 = base64.b64encode(raw).decode("ascii")
    messages = [
        {"role": "system", "content": _PORN_FILTER_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "این عکس رو بررسی کن."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        },
    ]
    # max_tokens: ۵ -> ۲۰ فایده نکرد (هم عکسِ پورن هم عکسِ غذا پاسخِ خالی
    # دادن) - یعنی این احتمالاً «کمبودِ توکن برای مدلِ reasoning» نیست (اگه
    # بود، محدودیت باید به مدلِ عکسِ ساده کمتر برمی‌خورد)، ولی برای رد/تأییدِ
    # قطعیِ همین فرضیه، به‌طورِ آزمایشی خیلی بالاتر بردیمش. اگه بازم خالی
    # موند، مشکل ربطی به max_tokens نداره - probably خودِ سرویس/مدل ورودیِ
    # تصویر رو اصلاً پردازش نمی‌کنه.
    return await ai.ask_ai(messages, max_tokens=300, return_raw=return_raw)


async def _is_nsfw_image(raw: bytes) -> bool:
    """
    خطاهای سرویس (AI غیرفعاله، کلید/endpoint اشتباهه، تایم‌اوت، ...) fail-open
    می‌شن: False برمی‌گردونه - چون این‌ها ربطی به محتوای عکس ندارن (نمی‌خوایم
    یه قطعیِ موقتِ سرویس باعثِ پاک‌شدنِ عکسِ سالمِ یه کاربر بشه).

    حالتِ «بدونِ خطای HTTP، پاسخ نه NSFW بود نه SAFE» (content خالی/مبهم) هم
    از قبل fail-close بود (یعنی NSFW در نظر گرفته می‌شد) - اون‌موقع مبتنی بر
    این فرض بود که خودِ AI_MODEL اصلاً قادر به تشخیصِ NSFW نبوده، پس سکوت رو
    نشونه‌ی صریح‌بودنِ تصویر می‌گرفتیم. حالا که با AI_MODELِ فعلی مدل درست هم
    NSFW هم SAFE رو صریح تشخیص می‌ده، این فرض دیگه درست نیست: یه پاسخِ خالی/
    مبهم دیگه لزوماً یعنی تصویر صریحه، بلکه معمولاً یعنی یه گلیچِ موقتِ سرویسه
    (مثلِ قطع‌شدنِ اتصال وسطِ استریم، یا هر خطای دیگه‌ای که تبدیل به یه پاسخِ
    ناقص شده نه یه خطای HTTPِ تمیز) - برای همین اینجا هم fail-open شده: به‌جای
    پاک‌کردنِ اشتباهیِ عکسِ سالمِ یه کاربر، عکس رو دست‌نخورده رد می‌کنیم و فقط
    warning لاگ می‌کنیم (قابلِ دیدن مستقیم توی چت هم با `.فیلترپورن تست`).
    """
    last_answer, last_finish = "", None
    for attempt in range(config.GROUP_PORN_FILTER_RETRIES):
        try:
            raw_response = await _classify_image(raw, return_raw=True)
        except (ai.AIDisabledError, ai.AIRequestError) as e:
            logger.warning("فیلترِ پورن: سرویسِ AI خطا داد - fail-open. جزئیات: %s", e)
            return False
        choice = {}
        if isinstance(raw_response, dict):
            choices = raw_response.get("choices") or [{}]
            choice = choices[0] if choices else {}
        answer = ((choice.get("message") or {}).get("content") or "").strip()
        normalized = answer.upper()
        last_answer, last_finish = answer, choice.get("finish_reason")

        if "NSFW" in normalized:
            return True   # تشخیصِ صریح - حذف
        if "SAFE" in normalized:
            return False  # تشخیصِ صریح - سالم

        # پاسخِ خالی/مبهم: مدلِ بعضی‌وقت‌ها (گلیچِ موقتِ سرویس) خالی جواب می‌ده
        # و تلاشِ بعدی درست تشخیص می‌ده - قبل از fail-open، دوباره امتحان می‌کنیم.
        logger.warning(
            "فیلترِ پورن: تلاشِ %s/%s - پاسخِ مدل نه NSFW بود نه SAFE (احتمالاً خالی). "
            "پاسخِ خام: %r finish_reason: %r",
            attempt + 1, config.GROUP_PORN_FILTER_RETRIES, answer, choice.get("finish_reason"),
        )
        if attempt + 1 < config.GROUP_PORN_FILTER_RETRIES:
            await asyncio.sleep(1.0)  # یه مکثِ کوتاه بینِ تلاش‌ها

    # همه‌ی تلاش‌ها پاسخِ مبهم داد - fail-open: کاری با عکس نداریم (ریسکِ
    # حذفِ اشتباهیِ عکسِ سالم از حذف‌نشدنِ احتمالیِ یه عکسِ صریح مهم‌تره)
    logger.warning(
        "فیلترِ پورن: بعد از %s تلاش پاسخِ قابلِ استفاده نبود - fail-open. "
        "آخرین پاسخ: %r finish_reason: %r",
        config.GROUP_PORN_FILTER_RETRIES, last_answer, last_finish,
    )
    return False


@client.on(events.NewMessage(outgoing=True, pattern=pat(["فیلترپورن", "pornfilter"])))
async def pornfilter_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    sub = (event.pattern_match.group(1) or "").strip().lower()

    if sub in ("روشن", "on"):
        if not config.AI_API_KEY:
            return await event.edit(
                "⚠️ فیلترِ پورن به AI_API_KEY نیاز داره (با یه مدلِ Vision-دار "
                "مثلِ gpt-4o یا gpt-4o-mini) - این متغیر رو تنظیم کن و دوباره امتحان کن. "
                "بدونِ این، این فیلتر عملاً هیچ عکسی رو چک نمی‌کنه."
            )
        await set_porn_filter(event.chat_id, True)
        return await event.edit(
            "✅ فیلترِ پورن روشن شد.\n"
            "از این به بعد عکسِ ارسالی از طرفِ اعضای غیرادمینِ این گروه با AI بررسی "
            "و در صورتِ تشخیصِ محتوای نامناسب حذف می‌شه.\n"
            "⚠️ فعلاً فقط عکسِ معمولی پوشش داده می‌شه؛ ویدیو/GIF/استیکر/فایل نه."
        )

    if sub in ("خاموش", "off"):
        await set_porn_filter(event.chat_id, False)
        return await event.edit("❌ فیلترِ پورنِ این گروه خاموش شد")

    if sub in ("تست", "test"):
        if not event.is_reply:
            return await event.edit(
                f"روی یه عکس ریپلای کن و بنویس `{PREFIX}فیلترپورن تست` - "
                "پاسخِ خامِ AI یا (در صورتِ بروز) متنِ دقیقِ خطا مستقیم توی چت نشون داده می‌شه. "
                "برای دیدنِ دلیلِ واقعیِ این‌که چرا فیلتر روی یه عکسِ خاص کاری نمی‌کنه، از همین استفاده کن."
            )
        reply = await event.get_reply_message()
        if not reply or not reply.photo:
            return await event.edit("پیامِ ریپلای‌شده باید یه عکسِ معمولی باشه (نه ویدیو/GIF/استیکر/فایل)")
        file_size = getattr(reply.file, "size", None) or 0
        if file_size and file_size > config.GROUP_PORN_FILTER_MAX_BYTES:
            return await event.edit(
                f"⚠️ حجمِ این عکس ({file_size / (1024 * 1024):.1f} مگابایت) از سقفِ "
                f"`GROUP_PORN_FILTER_MAX_BYTES` (`{config.GROUP_PORN_FILTER_MAX_BYTES / (1024 * 1024):.0f}` "
                "مگابایت) بیشتره.\n\n"
                "فیلترِ خودکار چنین عکسی رو اصلاً به AI نمی‌فرسته و بدونِ هیچ چکی رد می‌کنه - "
                "برای همینه که همین دستورِ تست هم اینجا متوقف شد (تا دقیقاً هماهنگ با رفتارِ واقعیِ "
                "فیلتر باشه). اگه عکسِ فرستاده‌شده (بدون فوروارد/ریپلای) با کیفیتِ بالاتری از سمتِ "
                "تلگرام فشرده شده باشه، ممکنه دقیقاً همین باشه: نسخه‌ی فورواردی/اصلی کوچیک‌تر از سقف "
                "بوده، نسخه‌ی تازه‌فرستاده‌شده بزرگ‌تر."
            )
        if not config.AI_API_KEY:
            return await event.edit(
                "⚠️ AI_API_KEY تنظیم نشده - اول این متغیر رو ست کن و دوباره امتحان کن."
            )
        await event.edit("⏳ در حالِ تحلیلِ عکس با AI...")
        try:
            raw = await client.download_media(reply, bytes)
        except Exception as e:
            return await event.edit(f"❌ خطا در دانلودِ عکس: {e}")
        if not raw:
            return await event.edit("❌ دانلودِ عکس چیزی برنگردوند")
        try:
            raw_response = await _classify_image(raw, return_raw=True)
        except ai.AIDisabledError:
            return await event.edit("⚠️ AI_API_KEY تنظیم نشده")
        except ai.AIRequestError as e:
            return await event.edit(
                "❌ **خطای واقعی که فیلترِ خودکار باهاش fail-open می‌کنه:**\n"
                f"`{e}`\n\n"
                "یعنی الان (وقتی فیلتر روشنه)، این عکس دقیقاً به‌خاطرِ همین خطا بدونِ حذف رد می‌شه - "
                "نه این‌که خودِ فیلتر خاموش یا خراب باشه. معمولاً یعنی: AI_API_BASE با آدرسِ واقعیِ "
                "سرویسِ متصل‌شده هم‌خونی نداره، مدلِ ست‌شده (AI_MODEL) از ورودیِ تصویر (Vision) "
                "پشتیبانی نمی‌کنه، یا کلید/سرویس اصلاً به این نوعِ درخواست جواب نمی‌ده."
            )
        choice = {}
        if isinstance(raw_response, dict):
            choices = raw_response.get("choices") or [{}]
            choice = choices[0] if choices else {}
        answer = ((choice.get("message") or {}).get("content") or "").strip()
        finish_reason = choice.get("finish_reason")

        if "NSFW" not in answer.upper() and "SAFE" not in answer.upper():
            reason_note = {
                "length": (
                    "توکن‌ها تموم شده (`length`) - یعنی حتی با ۳۰۰ توکن هم مدل قبلِ نوشتنِ "
                    "جوابِ نهایی توکن‌هاش تموم شده؛ معمولاً یعنی یه مدلِ reasoningِ خیلی پرمصرفه "
                    "که برای این کار مناسب نیست."
                ),
                "content_filter": (
                    "خودِ سرویس/مدل این درخواست رو با فیلترِ محتوای داخلیِ خودش مسدود کرده "
                    "(`content_filter`) - این محدودیتِ سمتِ سرویسه، نه چیزی که با تنظیماتِ این "
                    "پروژه قابلِ دورزدن باشه."
                ),
                "stop": (
                    "مدل خودش با `stop` تموم کرده ولی محتوایی ننوشته - نه کمبودِ توکن بوده نه "
                    "فیلترِ اعلام‌شده. معمولاً یعنی مدل/سرویس اصلاً فرمتِ چندرسانه‌ای (تصویر) رو "
                    "درست تفسیر نکرده."
                ),
            }.get(
                finish_reason,
                f"سرویس این `finish_reason` رو اعلام کرده: `{finish_reason}`"
                if finish_reason
                else "سرویس اصلاً finish_reason برنگردوند - پاسخِ خامِ کامل رو باید دستی چک کرد.",
            )
            return await event.edit(
                "⚠️ **درخواست بدونِ خطای HTTP موفق بود، ولی مدل نه NSFW نوشت نه SAFE** "
                f"(پاسخِ خام: `{answer or '(خالی)'}`)\n"
                f"**دلیل:** {reason_note}\n\n"
                "فیلترِ خودکار همچین پاسخی رو **fail-open** می‌کنه (یعنی کاری با این عکس نداره، "
                "حذف نمی‌شه) - با AI_MODELِ فعلی که درست NSFW/SAFE تشخیص می‌ده، یه پاسخِ مبهم/خالی "
                "معمولاً یعنی یه گلیچِ موقتِ سرویس، نه لزوماً محتوای صریح؛ پس ترجیح بر ریسک‌نکردنِ "
                "حذفِ اشتباهیِ عکسِ سالمه."
            )
        return await event.edit(f"✅ پاسخِ خامِ مدل برای این عکس: `{answer}` (finish_reason: `{finish_reason}`)")

    status = "روشن ✅" if is_porn_filter_enabled(event.chat_id) else "خاموش ❌"
    ai_status = "آماده ✅" if config.AI_API_KEY else "AI_API_KEY تنظیم نشده ⚠️"
    await event.edit(
        "🔞 **فیلترِ پورن**\n"
        f"وضعیتِ این گروه: {status}\n"
        f"سرویسِ AI: {ai_status}\n"
        f"AI_API_BASE: `{config.AI_API_BASE}`\n"
        f"AI_MODEL: `{config.AI_MODEL}`\n\n"
        f"`{PREFIX}فیلترپورن روشن` / `{PREFIX}فیلترپورن خاموش`\n"
        f"`{PREFIX}فیلترپورن تست` (با ریپلای روی یه عکس) — تشخیصِ دقیقِ مشکل، بدونِ نیاز به لاگ\n\n"
        "⚠️ فقط عکس‌های معمولی چک می‌شن (نه ویدیو/GIF/استیکر/فایل)؛ فقط پیام‌های اعضای غیرادمین حذف می‌شن.\n"
        "هر عکس یعنی یک درخواستِ AI - توی گروه‌های خیلی شلوغ ممکنه هزینه/تعدادِ درخواست بالا بره."
    )


@client.on(events.NewMessage(incoming=True))
async def pornfilter_watcher(event):
    if not event.is_group:
        return
    if not is_porn_filter_enabled(event.chat_id):
        return
    sender_id = event.sender_id
    if sender_id is None or sender_id == runtime.SELF_ID:
        return
    if not event.photo:
        return  # فعلاً فقط عکسِ فشرده‌شده چک می‌شه (نه ویدیو/GIF/استیکر/فایل)
    if await _is_admin_or_creator(event):
        return

    file_size = getattr(event.message.file, "size", None) or 0
    if file_size and file_size > config.GROUP_PORN_FILTER_MAX_BYTES:
        return  # عکسِ خیلی بزرگ - برای جلوگیری از دانلودِ سنگین/کند رد می‌شیم

    try:
        raw = await client.download_media(event.message, bytes)
    except Exception:
        _record_error()
        logger.exception("خطا در دانلودِ عکس برای فیلترِ پورن")
        return
    if not raw:
        return

    if not await _is_nsfw_image(raw):
        return

    # حذف با دو روش: اول event.delete؛ اگه شکست خورد client.delete_messages
    deleted = False
    try:
        await event.delete()
        deleted = True
    except Exception:
        _record_error()
        logger.warning("event.delete برای عکسِ NSFW شکست خورد - تلاش با delete_messages", exc_info=True)
    if not deleted:
        try:
            await client.delete_messages(event.chat_id, event.message.id)
            deleted = True
        except Exception:
            _record_error()
            logger.exception("حذفِ عکسِ فیلترشده (هر دو روش) شکست خورد (chat_id=%s)", event.chat_id)
    if deleted:
        try:
            await increment_deleted(event.chat_id, 1)
        except Exception:
            logger.debug("شمارشِ پیامِ حذف‌شده ثبت نشد", exc_info=True)
        return

    # حذف شکست خورد (معمولاً: سلف ادمین این گروه نیست یا محدودیتِ تلگرام) -
    # بی‌صدا نگذاریم: گزارش به Saved Messages تا کاربر بدونه چرا پاک نشد
    try:
        sender = await event.get_sender()
        name = getattr(sender, "first_name", "") or getattr(sender, "title", "") or "?"
        await client.send_message(
            "me",
            "🔞 فیلترِ پورن: عکسِ NSFW پیدا شد ولی حذف نشد!\n"
            f"گروه: {event.chat_title or event.chat_id}\n"
            f"فرستنده: {name} ({sender_id})\n"
            "احتمالاً این اکانت در این گروه ادمین نیست (حذفِ پیامِ دیگران نیاز به ادمین داره).",
        )
    except Exception:
        _record_error()
        logger.exception("خطا در گزارشِ عدمِ حذفِ عکسِ NSFW")


# ----------------------------------------------------------- قفل رسانه ---
_MEDIA_TYPE_LABEL = {
    "sticker": "استیکر", "video": "ویدیو", "audio": "صدا/آهنگ", "voice": "وویس",
    "gif": "گیف", "photo": "عکس", "game": "بازی", "poll": "نظرسنجی",
}


def _message_media_type(message) -> str | None:
    """نوعِ رسانه‌ایِ پیام رو به کلیدِ داخلیِ قفل‌ها برمی‌گردونه (یا None برای متن)."""
    media = message.media
    if media is None:
        return None
    name = type(media).__name__
    if name == "MessageMediaDocument":
        doc = getattr(media, "document", None)
        attrs = getattr(doc, "attributes", []) if doc else []
        attr_names = {type(a).__name__ for a in attrs}
        if "DocumentAttributeSticker" in attr_names:
            return "sticker"
        if "DocumentAttributeAnimated" in attr_names:
            return "gif"
        if "DocumentAttributeVideo" in attr_names:
            # وویس/round هم VideoNote نیستن؛ voice attribute دارن
            if "DocumentAttributeAudio" in attr_names:
                return "voice" if getattr(next(a for a in attrs if type(a).__name__ == "DocumentAttributeAudio"), "voice", False) else "audio"
            return "video"
        if "DocumentAttributeAudio" in attr_names:
            audio_attr = next(a for a in attrs if type(a).__name__ == "DocumentAttributeAudio")
            return "voice" if getattr(audio_attr, "voice", False) else "audio"
        return None
    if name == "MessageMediaPhoto":
        return "photo"
    if name == "MessageMediaGame":
        return "game"
    if name == "MessageMediaPoll":
        return "poll"
    if name == "MessageMediaDice":
        return "game"
    return None


@client.on(events.NewMessage(outgoing=True, pattern=pat(["قفل‌رسانه", "medialock"])))
async def media_lock_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")
    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split()
    chat_id = event.chat_id

    if not parts:
        locked = get_media_locks(chat_id)
        if not locked:
            text = "🔓 هیچ رسانه‌ای در این گروه قفل نیست."
        else:
            text = "🔒 **رسانه‌های قفل‌شده‌ی این گروه:**\n" + "\n".join(
                f"• {_MEDIA_TYPE_LABEL.get(t, t)}" for t in sorted(locked)
            )
        return await event.edit(
            text
            + f"\n\n`{PREFIX}قفل‌رسانه <استیکر/ویدیو/صدا/وویس/گیف/عکس/بازی/نظرسنجی> روشن/خاموش`"
            + f"\n`{PREFIX}قفل‌رسانه همه روشن/خاموش` — قفل/بازکردنِ همه"
        )

    sub = parts[0].lower()
    state_word = parts[1].lower() if len(parts) > 1 else ""

    if state_word in ("روشن", "on", "lock", "قفل"):
        enabled = True
    elif state_word in ("خاموش", "off", "unlock", "باز"):
        enabled = False
    else:
        return await event.edit(
            f"مثال: `{PREFIX}قفل‌رسانه استیکر روشن` یا `{PREFIX}قفل‌رسانه همه خاموش`\n"
            "انواع: استیکر، ویدیو، صدا، وویس، گیف، عکس، بازی، نظرسنجی"
        )

    if sub in ("همه", "all", "*"):
        await set_all_media_locks(chat_id, enabled)
        return await event.edit(
            "🔒 همه‌ی رسانه‌ها برای اعضای غیرادمین قفل شد" if enabled
            else "🔓 همه‌ی قفل‌های رسانه‌ای این گروه برداشته شد"
        )

    media_type = MEDIA_LOCK_TYPES.get(sub) or MEDIA_LOCK_TYPES.get(parts[0])
    if media_type is None:
        return await event.edit(
            f"❌ نوعِ نامعتبر: «{parts[0]}»\n"
            "انواع: استیکر، ویدیو، صدا، وویس، گیف، عکس، بازی، نظرسنجی"
        )
    await set_media_lock(chat_id, media_type, enabled)
    await event.edit(
        f"🔒 {_MEDIA_TYPE_LABEL[media_type]} برای اعضای غیرادمین قفل شد" if enabled
        else f"🔓 {_MEDIA_TYPE_LABEL[media_type]} برای اعضا آزاد شد"
    )


@client.on(events.NewMessage(incoming=True))
async def media_lock_watcher(event):
    """حذفِ خودکارِ رسانه‌های قفل‌شده از اعضای غیرادمین (هم‌الگوی فیلترلینک)."""
    if not event.is_group:
        return
    chat_id = event.chat_id
    if not get_media_locks(chat_id):
        return  # هیچ قفلی فعال نیست - سریع‌ترین مسیر خروج
    media_type = _message_media_type(event.message)
    if media_type is None or not is_media_locked(chat_id, media_type):
        return
    if await _is_admin_or_creator(event):
        return
    try:
        await event.delete()
        await increment_deleted(chat_id, 1)
    except Exception:
        _record_error()
        logger.exception("خطا در حذفِ رسانه‌ی قفل‌شده (chat_id=%s)", chat_id)


# --------------------------------------------------------------- خوش‌آمد ---
@client.on(events.NewMessage(outgoing=True, pattern=pat(["خوش‌آمد", "welcome"])))
async def welcome_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if sub in ("روشن", "on"):
        await set_welcome_enabled(event.chat_id, True)
        return await event.edit("✅ خوش‌آمدگویی خودکار برای عضو جدیدِ این گروه روشن شد")

    if sub in ("خاموش", "off"):
        await set_welcome_enabled(event.chat_id, False)
        return await event.edit("❌ خوش‌آمدگویی خودکار این گروه خاموش شد")

    if sub in ("متن", "text"):
        text = rest
        if not text and event.is_reply:
            reply = await event.get_reply_message()
            text = reply.raw_text or ""
        if not text:
            return await event.edit(
                f"مثال: `{PREFIX}خوش‌آمد متن سلام {{نام}} خوش اومدی به گروه!`\n"
                "می‌تونی از `{نام}` (اسمِ کاربر) یا `{منشن}` (تگِ واقعی) داخلِ متن استفاده کنی."
            )
        await set_welcome_text(event.chat_id, text)
        return await event.edit("✅ متنِ خوش‌آمدگویی ذخیره شد")

    status = "روشن ✅" if is_welcome_enabled(event.chat_id) else "خاموش ❌"
    await event.edit(
        "👋 **خوش‌آمدگویی**\n"
        f"وضعیتِ این گروه: {status}\n"
        f"متنِ فعلی: {get_welcome_text(event.chat_id)}\n\n"
        f"`{PREFIX}خوش‌آمد روشن` / `{PREFIX}خوش‌آمد خاموش`\n"
        f"`{PREFIX}خوش‌آمد متن <متن>` — جای‌گذاری‌های مجاز: `{{نام}}`, `{{منشن}}`"
    )


@client.on(events.ChatAction)
async def welcome_watcher(event):
    chat_id = event.chat_id
    if chat_id is None or not event.is_group:
        return

    if event.user_joined or event.user_added:
        try:
            users = await event.get_users()
        except Exception:
            users = []
        real_users = [u for u in users if not getattr(u, "bot", False) and u.id != runtime.SELF_ID]
        if real_users:
            await increment_joined(chat_id, len(real_users))
        if is_welcome_enabled(chat_id) and real_users:
            template = get_welcome_text(chat_id)
            for user in real_users:
                name = f"{user.first_name or ''} {user.last_name or ''}".strip() or (
                    user.username or str(user.id)
                )
                mention = f"[{name}](tg://user?id={user.id})"
                text = template.replace("{نام}", name).replace("{name}", name)
                text = text.replace("{منشن}", mention).replace("{mention}", mention)
                try:
                    await client.send_message(chat_id, text, parse_mode="markdown")
                except Exception:
                    _record_error()
                    logger.exception("خطا در ارسالِ پیامِ خوش‌آمدگویی")
        return

    if event.user_left or event.user_kicked:
        try:
            users = await event.get_users()
        except Exception:
            users = []
        real_users = [u for u in users if not getattr(u, "bot", False) and u.id != runtime.SELF_ID]
        if real_users:
            await increment_left(chat_id, len(real_users))
        return


# ---------------------------------------------------------- شمارشِ پیام‌ها ---
@client.on(events.NewMessage(incoming=True))
async def activity_message_counter(event):
    if not event.is_group:
        return
    # سینک و بدونِ I/O - فقط بافرِ درون‌حافظه‌ای رو افزایش می‌ده؛ ذخیره‌ی واقعی
    # توسطِ همون ورکرِ دوره‌ایِ stats_saver انجام می‌شه (نگاه کن به
    # bot/storage/activity_store.py برای توضیح کامل)
    record_message_activity(event.chat_id)


# ------------------------------------------------------------ برچسب‌همه ---
@client.on(events.NewMessage(outgoing=True, pattern=pat(["برچسب‌همه", "tagall"])))
async def tagall_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    custom_text = (event.pattern_match.group(1) or "").strip()

    try:
        participants = await client.get_participants(event.chat_id)
    except Exception as e:
        _record_error()
        logger.exception("خطا در گرفتنِ لیستِ اعضا")
        return await event.edit(f"❌ خطا در گرفتنِ لیستِ اعضا: {e}")

    members = [
        p
        for p in participants
        if not getattr(p, "bot", False) and not getattr(p, "deleted", False) and p.id != runtime.SELF_ID
    ]
    if not members:
        return await event.edit("عضوی برای تگ‌کردن پیدا نشد")

    if len(members) > _TAG_MAX_MEMBERS:
        return await event.edit(
            f"⚠️ این گروه {len(members)} عضو داره - برای کاهشِ ریسکِ اسپم/محدودیتِ اکانت "
            f"سقفِ این دستور {_TAG_MAX_MEMBERS} نفره. لطفاً توی گروه‌های کوچیک‌تر استفاده‌ش کن."
        )

    await event.edit(
        f"📣 در حالِ تگ‌کردنِ {len(members)} عضو، طیِ چند پیام با فاصله (برای جلوگیری از اسپم)..."
    )

    batches = [members[i : i + _TAG_BATCH_SIZE] for i in range(0, len(members), _TAG_BATCH_SIZE)]
    for batch in batches:
        mentions = " ".join(
            f"[{(m.first_name or m.username or str(m.id))}](tg://user?id={m.id})" for m in batch
        )
        body = f"{custom_text}\n{mentions}" if custom_text else mentions
        try:
            await client.send_message(event.chat_id, body, parse_mode="markdown")
        except Exception:
            _record_error()
            logger.exception("خطا در ارسالِ برچسب‌همه")
        await asyncio.sleep(_TAG_BATCH_DELAY)


# ---------------------------------------------------------------- فیلترِ اسپم ---
def _normalize_for_spam(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


# (chat_id, sender_id) -> deque[(monotonic_ts, message_id, normalized_text)] -
# فقط درون‌حافظه‌ست (نیازی به ماندگاریِ بینِ ری‌استارت نداره، چون فقط برای
# تشخیصِ فلادِ *لحظه‌ای* استفاده می‌شه، نه تاریخچه‌ی بلندمدت).
_spam_tracker: dict[tuple[int, int], deque] = {}
# برای این‌که خودِ پیامِ هشدار سرِ هر فلاد اسپم نشه، بینِ دو هشدارِ پیاپی برای
# همون (گروه، فرستنده) این‌قدر صبر می‌کنیم.
_spam_last_warned: dict[tuple[int, int], float] = {}


@client.on(events.NewMessage(outgoing=True, pattern=pat(["فیلتراسپم", "spamfilter"])))
async def spamfilter_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    sub = (event.pattern_match.group(1) or "").strip().lower()

    if sub in ("روشن", "on"):
        await set_spam_filter(event.chat_id, True)
        return await event.edit(
            "✅ فیلترِ اسپم روشن شد.\n"
            f"از این به بعد اگه یه عضوِ غیرادمین توی {config.GROUP_SPAM_WINDOW_SECONDS} ثانیه "
            f"بیشتر از {config.GROUP_SPAM_MAX_MESSAGES} پیام بفرسته (فلاد)، یا عینِ یه متن رو "
            f"{config.GROUP_SPAM_DUPLICATE_THRESHOLD} بار پشتِ‌سرِهم تکرار کنه، اون پیام‌ها "
            "خودکار حذف می‌شن."
        )

    if sub in ("خاموش", "off"):
        await set_spam_filter(event.chat_id, False)
        return await event.edit("❌ فیلترِ اسپمِ این گروه خاموش شد")

    status = "روشن ✅" if is_spam_filter_enabled(event.chat_id) else "خاموش ❌"
    await event.edit(
        "🚯 **فیلترِ اسپم**\n"
        f"وضعیتِ این گروه: {status}\n\n"
        f"`{PREFIX}فیلتراسپم روشن` / `{PREFIX}فیلتراسپم خاموش`\n"
        f"معیار: بیش از {config.GROUP_SPAM_MAX_MESSAGES} پیام در {config.GROUP_SPAM_WINDOW_SECONDS} ثانیه "
        f"(فلاد)، یا تکرارِ عینِ یه متن {config.GROUP_SPAM_DUPLICATE_THRESHOLD} بار پشتِ‌سرِهم.\n"
        "⚠️ فقط پیام‌های اعضای غیرادمین چک می‌شن؛ بدونِ نیاز به AI کار می‌کنه."
    )


@client.on(events.NewMessage(incoming=True))
async def spamfilter_watcher(event):
    if not event.is_group:
        return
    if not is_spam_filter_enabled(event.chat_id):
        return
    sender_id = event.sender_id
    if sender_id is None or sender_id == runtime.SELF_ID:
        return
    if await _is_admin_or_creator(event):
        return

    key = (event.chat_id, sender_id)
    now = time.monotonic()
    dq = _spam_tracker.setdefault(key, deque(maxlen=50))

    # پاک‌کردنِ رکوردهای قدیمی‌تر از بازه‌ی زمانیِ موردنظر
    while dq and now - dq[0][0] > config.GROUP_SPAM_WINDOW_SECONDS:
        dq.popleft()

    text = _normalize_for_spam(event.raw_text)
    dq.append((now, event.id, text))

    flood = len(dq) > config.GROUP_SPAM_MAX_MESSAGES
    duplicate = bool(text) and sum(1 for _, _, t in dq if t == text) >= config.GROUP_SPAM_DUPLICATE_THRESHOLD
    if not (flood or duplicate):
        return

    if flood:
        # فلاده - کلِ بازه‌ی اخیرِ همین فرستنده مشکوکه، همه رو پاک می‌کنیم.
        ids_to_delete = [mid for _, mid, _ in dq]
        dq.clear()
    else:
        # فقط تکرارِ همون متنِ خاص رو پاک می‌کنیم؛ پیام‌های دیگه‌ی همین فرستنده
        # که توی بازه بودن ولی متنِ متفاوتی داشتن دست‌نخورده می‌مونن.
        ids_to_delete = [mid for _, mid, t in dq if t == text]
        remaining = [entry for entry in dq if entry[1] not in ids_to_delete]
        dq.clear()
        dq.extend(remaining)

    try:
        await client.delete_messages(event.chat_id, ids_to_delete)
    except Exception:
        _record_error()
        logger.exception("خطا در حذفِ پیام‌های اسپم")

    last_warned = _spam_last_warned.get(key, 0.0)
    if now - last_warned >= config.GROUP_SPAM_WARN_COOLDOWN_SECONDS:
        _spam_last_warned[key] = now
        reason = "فلادِ پیام" if flood else "تکرارِ پیام"
        try:
            await client.send_message(
                event.chat_id,
                f"🚯 اسپم ({reason}) از طرفِ [یه عضو](tg://user?id={sender_id}) شناسایی و پاک شد.",
                parse_mode="markdown",
            )
        except Exception:
            _record_error()
            logger.exception("خطا در ارسالِ هشدارِ اسپم")


# ---------------------------------------------------------------- فیلترِ فحش ---
# لیستِ پایه‌ی کلماتِ رکیک/توهین‌آمیزِ رایج (فارسی + چندتا معادلِ انگلیسی) - برای
# تشخیصِ خودکار، بدونِ نیاز به AI و بدونِ نیاز به این‌که خودِ ادمین دستی کلمه‌به‌کلمه
# اضافه کنه (بر خلافِ `.فیلترکلمه` که کاملاً سفارشیه). این یه لیستِ پایه‌ست، نه
# جامع؛ در صورتِ نیاز به کلماتِ بیشتر/خاص‌ترِ یه گروه، همون `.فیلترکلمه` مکمّلشه.
PROFANITY_WORDS = frozenset({
    "کیر", "کص", "کوص", "کون", "جنده", "کسکش", "کسخل", "گاییدم", "گاییده",
    "گائیدم", "زنیکه", "حرومزاده", "حروم‌زاده", "مادرجنده", "ننه‌جنده",
    "کونی", "لاشی", "عوضی", "آشغال", "کثافت", "بیناموس", "بی‌ناموس",
    "fuck", "fucking", "bitch", "asshole", "motherfucker", "slut", "whore",
})


def _normalize_for_profanity(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("\u200c", "")  # نیم‌فاصله (ZWNJ) - رایج‌ترین ترفندِ دورزدنِ فیلتر
    text = re.sub(r"[\s\-_.،,!؟?]+", " ", text)
    return text


def _contains_profanity(text: str) -> str | None:
    normalized = _normalize_for_profanity(text)
    if not normalized:
        return None
    tokens = normalized.split()
    joined = normalized.replace(" ", "")
    for word in PROFANITY_WORDS:
        if word in tokens or word in joined:
            return word
    return None


@client.on(events.NewMessage(outgoing=True, pattern=pat(["فیلترفحش", "profanityfilter"])))
async def profanityfilter_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    sub = (event.pattern_match.group(1) or "").strip().lower()

    if sub in ("روشن", "on"):
        await set_profanity_filter(event.chat_id, True)
        return await event.edit(
            "✅ فیلترِ فحش روشن شد.\n"
            "از این به بعد پیامِ حاویِ کلماتِ رکیک از طرفِ اعضای غیرادمین این گروه خودکار حذف می‌شه."
        )

    if sub in ("خاموش", "off"):
        await set_profanity_filter(event.chat_id, False)
        return await event.edit("❌ فیلترِ فحشِ این گروه خاموش شد")

    status = "روشن ✅" if is_profanity_filter_enabled(event.chat_id) else "خاموش ❌"
    await event.edit(
        "🤬 **فیلترِ فحش**\n"
        f"وضعیتِ این گروه: {status}\n\n"
        f"`{PREFIX}فیلترفحش روشن` / `{PREFIX}فیلترفحش خاموش`\n\n"
        "بر پایه‌ی یه لیستِ داخلیِ کلماتِ رکیکِ رایج کار می‌کنه (بدونِ نیاز به AI)؛ "
        f"برای کلماتِ سفارشیِ خودتون از `{PREFIX}فیلترکلمه` استفاده کنید.\n"
        "⚠️ فقط پیام‌های اعضای غیرادمین چک می‌شن."
    )


@client.on(events.NewMessage(incoming=True))
async def profanityfilter_watcher(event):
    if not event.is_group:
        return
    if not is_profanity_filter_enabled(event.chat_id):
        return
    sender_id = event.sender_id
    if sender_id is None or sender_id == runtime.SELF_ID:
        return
    if await _is_admin_or_creator(event):
        return

    text = event.raw_text or ""
    if not text or not _contains_profanity(text):
        return

    try:
        await event.delete()
        await increment_deleted(event.chat_id)
    except Exception:
        _record_error()
        logger.exception("خطا در حذفِ پیامِ حاویِ فحش")


# ------------------------------------------------------------ فیلتر کلمات ممنوعه سفارشی ---
@client.on(events.NewMessage(outgoing=True, pattern=pat(["فیلترکلمه", "wordfilter"])))
async def wordfilter_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    chat_id = event.chat_id

    if not sub:
        filters = await get_word_filters(chat_id)
        if not filters:
            return await event.edit(
                f"📋 **فیلتر کلمات ممنوعه**\n\n"
                f"هیچ کلمه‌ای تعریف نشده.\n\n"
                f"دستورات:\n"
                f"`{PREFIX}فیلترکلمه افزودن <کلمه> [حذف/اخطار/بن]`\n"
                f"`{PREFIX}فیلترکلمه حذف <کلمه>`\n"
                f"`{PREFIX}فیلترکلمه لیست`\n"
                f"`{PREFIX}فیلترکلمه پاک`"
            )
        lines = ["📋 **لیست کلمات ممنوعه**\n"]
        for f in filters:
            action_label = {"delete": "حذف", "warn": "اخطار", "ban": "بن"}.get(f.action, f.action)
            lines.append(f"• `{f.word}` → {action_label}")
        await event.edit("\n".join(lines))
        return

    if sub in ("افزودن", "add"):
        args = rest.split(maxsplit=1)
        if not args:
            return await event.edit(f"مثال: `{PREFIX}فیلترکلمه افزودن کلمه‌ممنوع حذف`")
        word = args[0]
        action = args[1].lower() if len(args) > 1 else "delete"
        if action not in ("delete", "warn", "ban"):
            return await event.edit("اقدام باید یکی از: delete, warn, ban باشد.")
        try:
            await add_word_filter(chat_id, word, action)
            await event.edit(f"✅ کلمه `{word}` با اقدام `{action}` اضافه شد.")
        except ValueError as e:
            await event.edit(f"❌ {e}")
        return

    if sub in ("حذف", "remove"):
        if not rest:
            return await event.edit(f"مثال: `{PREFIX}فیلترکلمه حذف کلمه‌ممنوع`")
        word = rest.strip()
        success = await remove_word_filter(chat_id, word)
        if success:
            await event.edit(f"✅ کلمه `{word}` حذف شد.")
        else:
            await event.edit(f"❌ کلمه `{word}` در لیست وجود ندارد.")
        return

    if sub in ("لیست", "list"):
        filters = await get_word_filters(chat_id)
        if not filters:
            return await event.edit("لیست کلمات ممنوعه خالی است.")
        lines = ["📋 **لیست کلمات ممنوعه**\n"]
        for f in filters:
            action_label = {"delete": "حذف", "warn": "اخطار", "ban": "بن"}.get(f.action, f.action)
            lines.append(f"• `{f.word}` → {action_label}")
        await event.edit("\n".join(lines))
        return

    if sub in ("پاک", "clear"):
        count = await clear_word_filters(chat_id)
        await event.edit(f"🗑 {count} کلمه ممنوعه پاک شد.")
        return

    await event.edit(f"دستور نامعتبر. برای راهنما: `{PREFIX}فیلترکلمه`")


@client.on(events.NewMessage(incoming=True))
async def wordfilter_watcher(event):
    if not event.is_group:
        return
    chat_id = event.chat_id
    sender_id = event.sender_id
    if sender_id is None or sender_id == runtime.SELF_ID:
        return
    if await _is_admin_or_creator(event):
        return
    text = event.raw_text or ""
    if not text:
        return
    matched = await search_word_in_filters(chat_id, text)
    if not matched:
        return
    action = matched[0].action
    try:
        if action == "delete":
            await event.delete()
        elif action == "warn":
            await client.send_message(
                chat_id,
                f"⚠️ {sender_id} لطفاً از کلمات ممنوعه استفاده نکنید.",
                reply_to=event.id
            )
        elif action == "ban":
            await client.ban_participant(chat_id, sender_id)
            await client.send_message(chat_id, f"🚫 کاربر {sender_id} به دلیل استفاده از کلمه ممنوعه بن شد.")
    except Exception as e:
        _record_error()
        logger.exception("خطا در اعمال فیلتر کلمه: %s", e)


# ------------------------------------------------------------ سیستم هشدار تدریجی ---
async def _resolve_warn_target(event, target: str):
    """
    پیداکردنِ کاربرِ مقصد برای دستورهای اخطار: یا با ریپلای‌کردن روی پیامِ خودِ
    کاربر (بدونِ نیاز به دونستنِ یوزرنیم/آیدی)، یا با دادنِ @یوزرنیم/آیدیِ عددی.
    """
    if not target and event.is_reply:
        reply = await event.get_reply_message()
        if reply and reply.sender_id:
            try:
                return await client.get_entity(reply.sender_id)
            except Exception:
                return None
        return None
    if target and (target.startswith("@") or target.lstrip("-").isdigit()):
        try:
            return await client.get_entity(target)
        except Exception:
            return None
    return None


@client.on(events.NewMessage(outgoing=True, pattern=pat(["اخطار", "warn"])))
async def warn_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    chat_id = event.chat_id

    if not sub:
        settings = await get_warn_settings(chat_id)
        status = "روشن ✅" if settings.enabled else "خاموش ❌"
        return await event.edit(
            f"⚖️ **سیستم هشدار تدریجی**\n"
            f"وضعیت: {status}\n"
            f"حد هشدار: {settings.warn_limit}\n"
            f"اقدام در حد: {settings.action_on_limit}\n"
            f"مدت سکوت: {settings.mute_duration_minutes} دقیقه\n"
            f"بازنشانی خودکار: {settings.auto_reset_days} روز\n\n"
            f"دستورات:\n"
            f"`{PREFIX}اخطار افزودن <آیدی/یوزر> [دلیل]`\n"
            f"`{PREFIX}اخطار حذف <آیدی/یوزر>`\n"
            f"`{PREFIX}اخطار پاک <آیدی/یوزر>`\n"
            f"`{PREFIX}اخطار لیست`\n"
            f"`{PREFIX}اخطار تنظیمات <کلید> <مقدار>`"
        )

    if sub in ("افزودن", "add"):
        args = rest.split(maxsplit=1)
        target = args[0] if args and (args[0].startswith("@") or args[0].lstrip("-").isdigit()) else ""
        if target:
            reason = args[1] if len(args) > 1 else "بدون دلیل"
        else:
            reason = rest.strip() or "بدون دلیل"
        user = await _resolve_warn_target(event, target)
        if user is None:
            return await event.edit(
                f"کاربر پیدا نشد. یا با ریپلای روی پیامِ کاربر بزنید `{PREFIX}اخطار افزودن [دلیل]`، "
                f"یا آیدیِ عددی/یوزرنیم بدید: `{PREFIX}اخطار افزودن @username دلیل`"
            )
        user_id = user.id
        # افزودن هشدار
        warn_obj = await add_warn(chat_id, user_id)
        await increment_warnings(chat_id)
        settings = await get_warn_settings(chat_id)
        msg = f"⚠️ به کاربر {user.first_name or user_id} یک هشدار اضافه شد. (تعداد: {warn_obj.warn_count}) — دلیل: {reason}"
        if settings.enabled and warn_obj.warn_count >= settings.warn_limit:
            # اجرای اقدام خودکار
            action = settings.action_on_limit
            try:
                if action == "mute":
                    duration = settings.mute_duration_minutes
                    await client.edit_permissions(chat_id, user_id, until_date=dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=duration), send_messages=False)
                    msg += f" 🚫 کاربر به مدت {duration} دقیقه بی‌صدا شد."
                elif action == "kick":
                    await client.kick_participant(chat_id, user_id)
                    msg += " 🚫 کاربر از گروه اخراج شد."
                elif action == "ban":
                    await client.ban_participant(chat_id, user_id)
                    msg += " 🚫 کاربر از گروه بن شد."
            except Exception as e:
                _record_error()
                logger.exception("خطا در اعمال اقدام خودکار: %s", e)
                msg += " ❌ خطا در اعمال اقدام خودکار."
        await event.edit(msg)
        return

    if sub in ("حذف", "remove"):
        user = await _resolve_warn_target(event, rest.strip())
        if user is None:
            return await event.edit(
                f"کاربر پیدا نشد. یا با ریپلای روی پیامِ کاربر بزنید `{PREFIX}اخطار حذف`، "
                f"یا آیدیِ عددی/یوزرنیم بدید: `{PREFIX}اخطار حذف @username`"
            )
        success = await remove_warn(chat_id, user.id)
        if success:
            await event.edit(f"✅ یک هشدار از کاربر {user.first_name or user.id} کم شد.")
        else:
            await event.edit(f"⚠️ کاربر هیچ هشداری نداشت.")
        return

    if sub in ("پاک", "clear"):
        user = await _resolve_warn_target(event, rest.strip())
        if user is None:
            return await event.edit(
                f"کاربر پیدا نشد. یا با ریپلای روی پیامِ کاربر بزنید `{PREFIX}اخطار پاک`، "
                f"یا آیدیِ عددی/یوزرنیم بدید: `{PREFIX}اخطار پاک @username`"
            )
        success = await clear_warnings(chat_id, user.id)
        if success:
            await event.edit(f"✅ همه هشدارهای کاربر {user.first_name or user.id} پاک شد.")
        else:
            await event.edit(f"⚠️ کاربر هیچ هشداری نداشت.")
        return

    if sub in ("لیست", "list"):
        warnings = await list_warnings(chat_id)
        if not warnings:
            return await event.edit("هیچ هشداری در این گروه ثبت نشده.")
        lines = ["📋 **لیست هشدارها**\n"]
        for w in warnings[:20]:
            try:
                user = await client.get_entity(w.user_id)
                name = user.first_name or str(w.user_id)
            except Exception:
                name = str(w.user_id)
            lines.append(f"• {name}: {w.warn_count} هشدار")
        if len(warnings) > 20:
            lines.append(f"\n... و {len(warnings) - 20} مورد دیگر.")
        await event.edit("\n".join(lines))
        return

    if sub in ("تنظیمات", "settings"):
        args = rest.split(maxsplit=1)
        if len(args) < 2:
            return await event.edit(
                f"مثال: `{PREFIX}اخطار تنظیمات warn_limit 3`\n"
                f"کلیدهای قابل تنظیم: enabled, warn_limit, action_on_limit (mute/kick/ban), mute_duration_minutes, auto_reset_days"
            )
        key = args[0].lower()
        value = args[1]
        # تبدیل مقدار
        if key == "enabled":
            val = value.lower() in ("true", "on", "1", "روشن")
            await update_warn_settings(chat_id, enabled=val)
            await event.edit(f"✅ وضعیت سیستم هشدار: {'روشن' if val else 'خاموش'}")
        elif key == "warn_limit":
            try:
                val = int(value)
                await update_warn_settings(chat_id, warn_limit=val)
                await event.edit(f"✅ حد هشدار به {val} تغییر کرد.")
            except ValueError:
                await event.edit("❌ مقدار باید عدد باشد.")
        elif key == "action_on_limit":
            if value not in ("mute", "kick", "ban"):
                return await event.edit("❌ اقدام باید یکی از mute, kick, ban باشد.")
            await update_warn_settings(chat_id, action_on_limit=value)
            await event.edit(f"✅ اقدام در حد هشدار به {value} تغییر کرد.")
        elif key == "mute_duration_minutes":
            try:
                val = int(value)
                await update_warn_settings(chat_id, mute_duration_minutes=val)
                await event.edit(f"✅ مدت سکوت به {val} دقیقه تغییر کرد.")
            except ValueError:
                await event.edit("❌ مقدار باید عدد باشد.")
        elif key == "auto_reset_days":
            try:
                val = int(value)
                await update_warn_settings(chat_id, auto_reset_days=val)
                await event.edit(f"✅ بازنشانی خودکار به {val} روز تغییر کرد.")
            except ValueError:
                await event.edit("❌ مقدار باید عدد باشد.")
        else:
            await event.edit(f"❌ کلید نامعتبر. کلیدهای مجاز: enabled, warn_limit, action_on_limit, mute_duration_minutes, auto_reset_days")
        return

    await event.edit(f"دستور نامعتبر. برای راهنما: `{PREFIX}اخطار`")


# ------------------------------------------------------------ گزارش روزانه فعالیت گروه ---
@client.on(events.NewMessage(outgoing=True, pattern=pat(["گزارش", "report"])))
async def report_cmd_handler(event):
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")

    raw = (event.pattern_match.group(1) or "").strip()
    sub = raw.lower() if raw else ""
    chat_id = event.chat_id

    if sub in ("امروز", "today"):
        summary = await get_summary(chat_id, days=1)
        days = 1
        label = "امروز"
    elif sub in ("هفته", "week"):
        summary = await get_summary(chat_id, days=7)
        days = 7
        label = "۷ روز اخیر"
    elif sub.isdigit():
        days = int(sub)
        if days < 1:
            return await event.edit("تعداد روز باید حداقل ۱ باشد.")
        if days > 30:
            return await event.edit("حداکثر ۳۰ روز قابل گزارش است.")
        summary = await get_summary(chat_id, days=days)
        label = f"{days} روز اخیر"
    else:
        # نمایش راهنما
        summary = await get_summary(chat_id, days=1)
        return await event.edit(
            f"📊 **گزارش فعالیت گروه**\n\n"
            f"برای دریافت گزارش، از زیردستورهای زیر استفاده کن:\n"
            f"`{PREFIX}گزارش امروز` — گزارش امروز\n"
            f"`{PREFIX}گزارش هفته` — گزارش ۷ روز اخیر\n"
            f"`{PREFIX}گزارش <تعداد روز>` — گزارش تعداد روز دلخواه (حداکثر ۳۰)\n\n"
            f"**آمار امروز:**\n"
            f"• پیام‌ها: {summary['total_messages']}\n"
            f"• هشدارها: {summary['total_warnings']}\n"
            f"• پیام‌های حذف‌شده: {summary['total_deleted']}\n"
            f"• اعضای جدید: {summary['total_joined']}\n"
            f"• اعضای خارج‌شده: {summary['total_left']}"
        )

    # نمایش گزارش
    lines = [
        f"📊 **گزارش فعالیت گروه** ({label})",
        "",
        f"📨 پیام‌های ارسال‌شده: **{summary['total_messages']}**",
        f"⚠️ هشدارها: **{summary['total_warnings']}**",
        f"🗑 پیام‌های حذف‌شده: **{summary['total_deleted']}**",
        f"➕ اعضای جدید: **{summary['total_joined']}**",
        f"➖ اعضای خارج‌شده: **{summary['total_left']}**",
        "",
        f"📆 تعداد روزهای گزارش‌شده: {summary['days']}"
    ]
    await event.edit("\n".join(lines))
