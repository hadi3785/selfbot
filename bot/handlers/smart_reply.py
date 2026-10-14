"""
دستور .جواب - پیشنهاد پاسخ هوشمند
"""
import logging
import time
from typing import List, Tuple

from telethon import events
from telethon.tl.types import Message

from .. import ai
from ..config import PREFIX
from ..runtime import client
from ..utils import pat

logger = logging.getLogger("selfbot.handlers.smart_reply")

# حالت‌های پاسخ
MODES = {
    "رسمی": "پاسخ رسمی و محترمانه، با ادبیات کامل",
    "دوستانه": "پاسخ دوستانه و گرم، مثل یک رفیق صمیمی",
    "طنز": "پاسخ طنزآمیز و شوخ، با کمی شوخی",
    "کوتاه": "پاسخ بسیار کوتاه و مستقیم، حداکثر ۲ جمله",
    "حرفه‌ای": "پاسخ حرفه‌ایِ کاری: شفاف، مودبانه، با تمرکز بر نتیجه و گامِ بعدی",
}

DEFAULT_STYLE_KEY = "smart_reply_style"


async def _get_default_style() -> str:
    from ..repositories import settings_repo

    val = await settings_repo.get_setting(DEFAULT_STYLE_KEY)
    return val or "دوستانه"


@client.on(events.NewMessage(outgoing=True, pattern=pat(["جواب", "reply"])))
async def smart_reply_handler(event):
    """پیشنهاد پاسخ هوشمند برای یک پیام."""
    args = (event.pattern_match.group(1) or "").strip().split()
    mode = args[0] if args else await _get_default_style()

    # بررسی حالت ارسال
    if mode in ("ارسال", "send"):
        return await _send_reply(event, args[1:] if len(args) > 1 else [])

    if not event.is_reply:
        return await event.edit(
            f"❌ باید به یک پیام ریپلای کنید.\n"
            f"مثال: `{PREFIX}جواب دوستانه`\n"
            f"حالت‌ها: {', '.join(MODES.keys())}\n"
            f"برای ارسال: `{PREFIX}جواب ارسال`"
        )

    if mode not in MODES and mode != "ارسال":
        return await event.edit(
            f"❌ حالت نامعتبر. حالت‌های موجود: {', '.join(MODES.keys())}\n"
            f"مثال: `{PREFIX}جواب رسمی`"
        )

    reply: Message = await event.get_reply_message()
    if not reply:
        return await event.edit("❌ پیام مورد نظر یافت نشد.")

    await event.edit("🤔 در حال تولید پاسخ هوشمند...")

    # بررسیِ در دسترس‌بودنِ هوش مصنوعی (این دستور مستقل از سوییچِ ai_modeِ منشیه)
    from .. import config
    if not config.AI_API_KEY:
        return await event.edit(
            "⚠️ **قابلیت هوش مصنوعی غیرفعال است**\n"
            "برای فعال‌سازی، متغیر `AI_API_KEY` را تنظیم کنید."
        )

    # ساخت پرامپت — با کانتکستِ چند پیامِ آخرِ چت + حافظه‌ی مرتبط
    mode_desc = MODES.get(mode, MODES["دوستانه"])
    text = reply.text or "[پیام بدون متن]"
    sender = reply.sender_id or "کاربر ناشناس"

    context_bits: list[str] = []
    try:
        history = await event.client.get_messages(
            event.chat_id, limit=6, max_id=reply.id, min_id=max(reply.id - 60, 0)
        )
        prev_lines = []
        for m in reversed(list(history)):
            t = (m.raw_text or "").strip()
            if t:
                who = "من" if m.out else "طرف"
                prev_lines.append(f"- {who}: {t[:160]}")
        if prev_lines:
            context_bits.append("پیام‌های قبلیِ گفتگو:\n" + "\n".join(prev_lines[-6:]))
    except Exception:
        pass

    try:
        from .. import assistant_brain

        mem = await ai.build_memory_context(text)
        if mem:
            context_bits.append("خاطراتِ مرتبط:\n" + mem)
    except Exception:
        pass

    system_prompt = (
        "تو یک دستیار هوشمند هستی که به پیام‌ها پاسخ می‌دهی.\n"
        f"سبک پاسخ: {mode_desc}\n"
        f"پیام اصلی از طرف کاربر {sender} آمده است.\n"
        "پاسخ باید فارسی باشد و دقیقاً به محتوای پیام بپردازد.\n"
        + ("\n".join(context_bits) + "\n" if context_bits else "")
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"پیام: {text}\n\nلطفاً پاسخ بده."},
    ]

    try:
        response = await ai.ask_ai(messages, max_tokens=300)
    except ai.AIDisabledError:
        return await event.edit(
            "⚠️ **قابلیت هوش مصنوعی غیرفعال است**\n"
            "برای فعال‌سازی، متغیر `AI_API_KEY` را تنظیم کنید."
        )
    except ai.AIRequestError as e:
        return await event.edit(f"❌ خطا در ارتباط با سرویس AI: {e}")

    if not response:
        return await event.edit("❌ پاسخ تولید نشد. دوباره امتحان کنید.")

    # ذخیره پیشنهاد در حافظه موقت برای ارسال
    # پاک‌سازیِ entryهای منقضی (TTL فقط در لحظه‌ی ارسال چک نمی‌شود تا چت‌های
    # رهاشده بی‌نهایت در dict نمانند) + سقفِ کل برای اطمینانِ دوگانه
    now = time.time()
    for cid in [cid for cid, pr in _pending_replies.items() if now - pr["created_at"] > _PENDING_TTL]:
        _pending_replies.pop(cid, None)
    while len(_pending_replies) >= _PENDING_MAX_CHATS:
        _pending_replies.pop(next(iter(_pending_replies)))
    _pending_replies[event.chat_id] = {
        "text": response,
        "reply_to": reply.id,
        "created_at": time.time(),
    }

    await event.edit(
        f"💡 **پاسخ پیشنهادی** ({mode}):\n\n{response}\n\n"
        f"• ارسال: `{PREFIX}جواب ارسال`\n"
        f"• حالت‌های دیگر: `{PREFIX}جواب رسمی`، `{PREFIX}جواب طنز`، ..."
    )


# حافظه موقت برای پاسخ‌های در انتظار
_pending_replies = {}
_PENDING_TTL = 120  # ثانیه
_PENDING_MAX_CHATS = 200  # سقفِ چت‌های درانتظار (ضدِ نشتِ حافظه)


async def _send_reply(event, args):
    """ارسال پاسخ پیشنهادی."""
    chat_id = event.chat_id
    pending = _pending_replies.get(chat_id)

    if not pending:
        return await event.edit(
            f"❌ هیچ پاسخ در انتظاری نیست. اول `{PREFIX}جواب` را اجرا کنید."
        )

    if time.time() - pending["created_at"] > _PENDING_TTL:
        _pending_replies.pop(chat_id, None)
        return await event.edit("⏳ پیشنهاد منقضی شد. دوباره امتحان کنید.")

    try:
        tagged_text, entities = ai.tag_ai_text(pending["text"])
        await event.client.send_message(
            chat_id,
            tagged_text,
            reply_to=pending["reply_to"],
            formatting_entities=entities,
        )
        _pending_replies.pop(chat_id, None)
        await event.edit("✅ پاسخ ارسال شد.")
    except Exception as e:
        await event.edit(f"❌ خطا در ارسال پاسخ: {e}")

@client.on(events.NewMessage(outgoing=True, pattern=pat(["سبک", "style"])))
async def style_handler(event):
    """`.سبک` — سبکِ فعلی؛ `.سبک <نام>` — ذخیره‌ی سبکِ پیش‌فرض برای `.جواب`."""
    from ..repositories import settings_repo

    arg = (event.pattern_match.group(1) or "").strip()
    if not arg:
        current = await _get_default_style()
        return await event.edit(
            "🎨 **سبکِ پاسخ**\n\n"
            f"سبکِ فعلی: **{current}**\n"
            f"حالت‌ها: {', '.join(MODES.keys())}\n"
            f"ذخیره: `{PREFIX}سبک رسمی` (یا هر سبکِ دیگه)"
        )
    if arg not in MODES:
        return await event.edit(f"❌ حالت نامعتبر. حالت‌ها: {', '.join(MODES.keys())}")
    await settings_repo.set_setting(DEFAULT_STYLE_KEY, arg)
    await event.edit(f"✅ سبکِ پیش‌فرضِ `.جواب` روی **{arg}** ذخیره شد")
