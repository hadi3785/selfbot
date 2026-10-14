"""
ردیابِ ویرایش/حذفِ پیام (`.ردیاب`).

با events.MessageEdited/events.MessageDeleted تلتون: هر پیامِ ورودی (نه
خروجی - توضیح پایین) که می‌بینیم رو موقتاً کش می‌کنیم؛ اگه بعداً طرفِ مقابل
(توی پیوی یا هر گروه/کانالی) اون پیام رو ویرایش یا حذف کنه، نسخه‌ی قبلی‌ش
رو به کانال(های) مقصدِ تنظیم‌شده می‌فرستیم:
  • پیوی: فقط متن/رسانه + نامِ فرستنده.
  • گروه/کانال: متن/رسانه + نامِ فرستنده + نامِ گروه/کانال.

چرا فقط پیام‌های ورودی کش می‌شن (نه event.out):
  تقریباً همه‌ی دستورهای این پروژه با event.edit() روی پیامِ خروجیِ خودشون
  کار می‌کنن - یعنی هر بار یه دستور می‌زنی، خودش از دیدِ تلگرام یه
  «ویرایشِ پیامِ خروجی»‌ه. اگه خروجی‌ها رو هم ردیابی می‌کردیم، هر اجرای
  دستوری توی کل ربات یه false positive می‌شد.

چرا دو کشِ جداگانه لازمه، نه یه دیکشنریِ ساده‌ی (chat_id, message_id):
  تلگرام برای رویدادِ حذف دو نوع آپدیتِ متفاوت می‌فرسته:
    • UpdateDeleteMessages (پیوی/گروهِ‌ساده): فقط message_id - بدونِ
      chat_id! چون فضای شناسه‌ی پیام برای این دو نوع چت، از دیدِ خودِ
      اکانتِ ما، یکتاست (طبقِ مستنداتِ Telethon: «message identifier alone
      is enough to uniquely identify a message only if it's not from a
      megagroup or channel») - یعنی می‌تونیم فقط با message_id (بدونِ
      دونستنِ چت) پیام رو توی کشِ خودمون پیدا کنیم.
    • UpdateDeleteChannelMessages (کانال/سوپرگروه): message_id + channel_id
      - چون فضای شناسه‌ی پیام مخصوصِ خودِ همون کانالِه (بینِ کانال‌های
      مختلف می‌تونه تکرار بشه)، این‌جا chat_id لازم و همیشه موجوده.
  به همین خاطر: _pv_cache فقط با message_id ایندکس می‌شه (پیوی+گروهِ‌ساده)،
  _channel_cache با (chat_id, message_id) (کانال/سوپرگروه) - دقیقاً همون
  تفکیکی که event.is_channel توی assistant.py هم برای همین منظور استفاده
  می‌کنه.

کش فقط توی حافظه‌ست (نه دیتابیس) - دقیقاً هم‌رفتار با حافظه‌ی مکالمه‌ی AI
منشی (ASSISTANT_HISTORY_LIMIT توی config.py): با ری‌استارتِ پروسه پاک می‌شه؛
سقفِ تعداد + پاکسازیِ دوره‌ای بر اساسِ سن جلوی رشدِ بی‌حدوحصرش رو می‌گیره.
فقط لیستِ کانال‌های مقصد (نه خودِ کشِ پیام‌ها) توی PostgreSQL دائمیه
(bot/storage/message_tracker_store.py).

هماهنگی با `.حذف`/`.پاکسازی`: اون دو دستور می‌تونن با ریپلای، پیامِ کسِ
دیگه‌ای رو هم حذف کنن (مثلاً پاک‌سازیِ یه گروه) - این حذفِ عمدیِ خودِ owner
است، نه تصمیمِ فرستنده‌ی اصلی، پس نباید گزارش بشه. bot/self_delete_registry.py
دقیقاً همین تفکیک رو انجام می‌ده (نگاه کن به bot/handlers/messages.py).
"""
import asyncio
import logging
import time
from collections import OrderedDict

from telethon import errors, events

from ..config import PREFIX
from ..runtime import client
from ..self_delete_registry import consume as _consume_self_deleted
from ..storage.message_tracker_store import (
    add_tracker_channel,
    clear_tracker_channels,
    message_tracker_state,
    remove_tracker_channel,
)
from ..storage.settings_toggles import set_toggle, toggles
from ..storage.stats_store import record_error as _record_error
from ..utils import pat

logger = logging.getLogger("selfbot.handlers.message_tracker")

_MAX_ENTRIES = 3000  # سقفِ هر کش (پیوی/گروهِ‌ساده و کانال/سوپرگروه جداجدا)
_MAX_AGE_SECONDS = 12 * 3600  # پیام‌های کش‌شده‌ی قدیمی‌تر از این دورریخته می‌شن
_CLEANUP_INTERVAL_SECONDS = 30 * 60

_pv_cache: "OrderedDict[int, dict]" = OrderedDict()
_channel_cache: "OrderedDict[tuple, dict]" = OrderedDict()


# ------------------------------------------------------------- کش‌کردن ---
def _media_kind(msg):
    """یه برچسبِ کوتاهِ فارسی برای نوعِ رسانه، یا None اگه پیام رسانه نداره."""
    if not msg.media:
        return None
    if msg.photo:
        return "🖼 عکس"
    if msg.video:
        return "🎞 ویدیو"
    if msg.voice:
        return "🎙 پیامِ صوتی"
    if msg.audio:
        return "🎵 صوت"
    if msg.gif:
        return "🎞 گیف"
    if msg.sticker:
        return "🎭 استیکر"
    if msg.document:
        return "📎 فایل"
    return "📎 رسانه"


def _evict_if_needed(cache) -> None:
    while len(cache) > _MAX_ENTRIES:
        cache.popitem(last=False)


def _purge_expired(cache) -> None:
    cutoff = time.time() - _MAX_AGE_SECONDS
    stale_keys = [k for k, v in cache.items() if v["cached_at"] < cutoff]
    for k in stale_keys:
        del cache[k]


async def _sender_display_name(event) -> str:
    try:
        sender = await event.get_sender()
    except Exception:
        sender = None
    if sender is None:
        return str(event.sender_id) if event.sender_id else "ناشناس"
    name = f"{getattr(sender, 'first_name', '') or ''} {getattr(sender, 'last_name', '') or ''}".strip()
    return name or (getattr(sender, "username", None) or getattr(sender, "title", None) or str(event.sender_id))


async def _cache_incoming(event) -> None:
    """روی هر پیامِ ورودی (تازه یا تازه‌ویرایش‌شده) صدا زده می‌شه تا نسخه‌ی فعلی‌ش کش بشه."""
    msg = event.message
    try:
        chat = await event.get_chat()
    except Exception:
        chat = None

    is_private = bool(event.is_private)
    is_channel_scoped = bool(event.is_channel)  # کانال یا سوپرگروه - فضای شناسه‌ی جدا

    chat_title = None
    if not is_private:
        chat_title = getattr(chat, "title", None) or str(event.chat_id)

    info = {
        "chat_id": event.chat_id,
        "is_private": is_private,
        "chat_title": chat_title,
        "sender_id": event.sender_id,
        "sender_name": await _sender_display_name(event),
        "text": msg.raw_text or "",
        "media_kind": _media_kind(msg),
        "message": msg,  # برای تلاشِ فورواردِ رسانه بعدِ حذف
        "cached_at": time.time(),
    }

    if is_channel_scoped:
        key = (event.chat_id, event.id)
        _channel_cache[key] = info
        _channel_cache.move_to_end(key)
        _evict_if_needed(_channel_cache)
    else:
        _pv_cache[event.id] = info
        _pv_cache.move_to_end(event.id)
        _evict_if_needed(_pv_cache)


@client.on(events.NewMessage(incoming=True))
async def _tracker_cache_hook(event):
    if not toggles["message_tracker_enabled"]:
        return
    try:
        await _cache_incoming(event)
    except Exception:
        logger.exception("خطا در کش‌کردنِ پیام برای ردیابِ ویرایش/حذف")


# ------------------------------------------------------- ارسالِ گزارش ---
def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _format_header(info: dict, title_line: str) -> list:
    lines = [title_line, "", f"👤 فرستنده: {info['sender_name']}"]
    if not info["is_private"]:
        lines.append(f"💬 چت: {info['chat_title']}")
    lines.append("")
    return lines


async def _dispatch(text: str, media_message=None) -> None:
    for chat_id_str in list(message_tracker_state["channels"].keys()):
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            continue
        sent = False
        if media_message is not None:
            try:
                await client.send_file(chat_id, media_message, caption=_truncate(text, 1000))
                sent = True
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception:
                logger.exception("خطا در ارسالِ رسانه‌ی کش‌شده به کانالِ ردیاب؛ فقط متن فرستاده می‌شه")
        if not sent:
            try:
                await client.send_message(chat_id, text)
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception:
                _record_error()
                logger.exception("خطا در ارسالِ گزارشِ ردیاب به چتِ %s", chat_id_str)


async def _send_delete_alert(info: dict) -> None:
    lines = _format_header(info, "🗑 **پیامِ حذف‌شده**")
    if info["media_kind"]:
        lines.append(f"({info['media_kind']})")
    body = info["text"] or ("" if info["media_kind"] else "(بدون متن)")
    if body:
        lines.append(body)
    await _dispatch("\n".join(lines).strip(), media_message=info.get("message"))


async def _send_edit_alert(info: dict, new_text: str) -> None:
    lines = _format_header(info, "✏️ **پیامِ ویرایش‌شده**")
    lines.append("متنِ قبلی:")
    lines.append(info["text"] or "(بدون متن)")
    lines.append("")
    lines.append("متنِ جدید:")
    lines.append(new_text or "(بدون متن)")
    await _dispatch("\n".join(lines).strip())


# --------------------------------------------------------- ویرایش ---
@client.on(events.MessageEdited(incoming=True))
async def _tracker_edited_hook(event):
    if not toggles["message_tracker_enabled"]:
        return
    if not message_tracker_state["channels"]:
        return
    try:
        await _handle_edit(event)
    except Exception:
        _record_error()
        logger.exception("خطا در ردیابیِ ویرایشِ پیام")


async def _handle_edit(event) -> None:
    is_channel_scoped = bool(event.is_channel)
    cache = _channel_cache if is_channel_scoped else _pv_cache
    key = (event.chat_id, event.id) if is_channel_scoped else event.id
    old = cache.get(key)

    new_text = event.message.raw_text or ""

    if old is None:
        # پیامی که قبلاً ندیده بودیم (مثلاً قبل از روشن‌شدنِ ربات فرستاده شده) -
        # چیزی برای مقایسه نیست؛ فقط نسخه‌ی جدید کش بشه تا ویرایشِ *بعدی*‌ش قابل‌تشخیص باشه.
        await _cache_incoming(event)
        return

    old_text = old["text"]
    await _cache_incoming(event)  # آپدیتِ کش با نسخه‌ی تازه، برای ویرایش‌های بعدی

    if old_text == new_text:
        return  # فقط چیزِ دیگه‌ای عوض شده (پین/واکنش/...)، نه خودِ متن

    await _send_edit_alert(old, new_text)


# ----------------------------------------------------------- حذف ---
@client.on(events.MessageDeleted())
async def _tracker_deleted_hook(event):
    if not toggles["message_tracker_enabled"]:
        return
    if not message_tracker_state["channels"]:
        return
    try:
        await _handle_deleted(event)
    except Exception:
        _record_error()
        logger.exception("خطا در ردیابیِ حذفِ پیام")


async def _handle_deleted(event) -> None:
    chat_id = event.chat_id  # فقط برای کانال/سوپرگروه ست می‌شه؛ پیوی/گروهِ‌ساده = None
    for msg_id in event.deleted_ids:
        info = _channel_cache.pop((chat_id, msg_id), None) if chat_id is not None else _pv_cache.pop(msg_id, None)
        if info is None:
            continue  # کش نشده بود

        if _consume_self_deleted(info["chat_id"], msg_id):
            continue  # این حذف عمداً با .حذف/.پاکسازیِ خودمون بوده، نه تصمیمِ فرستنده

        await _send_delete_alert(info)


# ------------------------------------------------------- پاکسازیِ دوره‌ای ---
async def message_tracker_cleanup_worker():
    """هر _CLEANUP_INTERVAL_SECONDS یک‌بار، پیام‌های خیلی قدیمیِ کش رو دور می‌ریزه."""
    from .. import health

    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
        health.update_worker_status("message_tracker_cleanup", "ok")
        try:
            _purge_expired(_pv_cache)
            _purge_expired(_channel_cache)
        except Exception:
            logger.exception("خطا در پاکسازیِ دوره‌ایِ کشِ ردیاب")


# ------------------------------------------------------------- دستور ---
def _tracker_status_text() -> str:
    status = "روشن ✅" if toggles["message_tracker_enabled"] else "خاموش ❌"
    channels = message_tracker_state["channels"]
    if channels:
        lines = "\n".join(f"   – {title} (`{cid}`)" for cid, title in channels.items())
        dest_line = f"{len(channels)} کانال/چت\n{lines}"
    else:
        dest_line = f"هیچ‌کدام (اول با `{PREFIX}ردیاب افزودن` اضافه کن)"
    return (
        "🕵️ **ردیابِ ویرایش/حذفِ پیام**\n\n"
        f"• وضعیت: {status}\n"
        f"• کانال(های) مقصد: {dest_line}\n\n"
        "وقتی طرفِ مقابل (توی پیوی یا هر گروه/کانالی) پیامی که قبلاً دیده بودیم رو "
        "ویرایش یا حذف کنه، نسخه‌ی قبلی‌ش به همین کانال(ها) فرستاده می‌شه.\n\n"
        f"راهنما:\n"
        f"`{PREFIX}ردیاب روشن/خاموش`\n"
        f"`{PREFIX}ردیاب تنظیم <chat_id>` (لیست رو پاک می‌کنه و فقط همین یکی رو می‌ذاره)\n"
        f"`{PREFIX}ردیاب افزودن <chat_id>` (به لیست اضافه می‌کنه)\n"
        f"`{PREFIX}ردیاب حذف <chat_id>`\n"
        f"`{PREFIX}ردیاب پاک` (کل لیست)\n\n"
        "نکته: دستور رو داخلِ خودِ کانال/گروهِ مقصد بفرست (بدونِ آرگومان) تا همون‌جا اضافه/تنظیم بشه؛ "
        "یا آیدیِ عددیِ چت رو مستقیم بده."
    )


def _resolve_target_chat_id(event, rest: str) -> int:
    rest = rest.strip()
    return int(rest) if rest.lstrip("-").isdigit() else event.chat_id


@client.on(events.NewMessage(outgoing=True, pattern=pat(["ردیاب", "tracker"])))
async def message_tracker_handler(event):
    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if not sub:
        return await event.edit(_tracker_status_text())

    if sub in ("روشن", "on"):
        await set_toggle("message_tracker_enabled", True)
        return await event.edit(_tracker_status_text())

    if sub in ("خاموش", "off"):
        await set_toggle("message_tracker_enabled", False)
        return await event.edit(_tracker_status_text())

    if sub in ("تنظیم", "set"):
        chat_id = _resolve_target_chat_id(event, rest)
        try:
            chat = await client.get_entity(chat_id)
        except Exception as e:
            _record_error()
            return await event.edit(f"❌ خطا در پیداکردنِ چت: {e}")
        title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(chat_id)
        await clear_tracker_channels()
        await add_tracker_channel(chat_id, title)
        return await event.edit(f"✅ کانالِ ردیاب روی «{title}» تنظیم شد (کانال‌های قبلی پاک شدن)")

    if sub in ("افزودن", "add"):
        chat_id = _resolve_target_chat_id(event, rest)
        try:
            chat = await client.get_entity(chat_id)
        except Exception as e:
            _record_error()
            return await event.edit(f"❌ خطا در پیداکردنِ چت: {e}")
        title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(chat_id)
        await add_tracker_channel(chat_id, title)
        return await event.edit(f"✅ «{title}» به لیستِ مقصدهای ردیاب اضافه شد")

    if sub in ("حذف", "remove"):
        chat_id = _resolve_target_chat_id(event, rest)
        removed = await remove_tracker_channel(chat_id)
        if removed:
            return await event.edit(f"🗑 «{removed}» از لیستِ مقصدهای ردیاب حذف شد")
        return await event.edit("این چت توی لیستِ مقصدهای ردیاب نبود")

    if sub in ("پاک", "clear"):
        await clear_tracker_channels()
        return await event.edit("🗑 همه‌ی کانال‌های مقصدِ ردیاب پاک شدن")

    await event.edit(f"دستور نامعتبره. برای وضعیتِ کامل: `{PREFIX}ردیاب`")
