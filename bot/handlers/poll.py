"""
دستورات نظرسنجی تلگرامی + جمع‌بندی خودکار.
"""

import json
from telethon import events

from ..config import PREFIX
from ..runtime import client
from ..storage.stats_store import record_error as _record_error
from ..utils import pat
from ..db.engine import session_scope
from ..db.models_ext import GroupPoll


@client.on(events.NewMessage(outgoing=True, pattern=pat(["نظرسنجی", "poll"])))
async def poll_cmd_handler(event):
    """ایجاد نظرسنجی جدید."""
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.edit(
            f"📊 **نظرسنجی**\n\n"
            f"ایجاد:\n"
            f"`{PREFIX}نظرسنجی <سوال> | گزینه۱ | گزینه۲ | ...`\n\n"
            f"مدیریت:\n"
            f"`{PREFIX}نظرسنجی بستن` — بستن نظرسنجی جاری (با ریپلای)\n"
            f"`{PREFIX}نظرسنجی جمع‌بندی` — جمع‌بندی نتایج نظرسنجی (با ریپلای)\n\n"
            f"⚠️ حداکثر ۱۰ گزینه مجاز است."
        )
    
    # بررسی اگر دستور بستن یا جمع‌بندی باشد
    if raw.startswith("بستن") or raw.startswith("close"):
        if not event.is_reply:
            return await event.edit("❌ روی پیام نظرسنجی ریپلای کن.")
        reply = await event.get_reply_message()
        if not reply.poll:
            return await event.edit("❌ این پیام یک نظرسنجی نیست.")
        try:
            await client.send_message(event.chat_id, f"🔒 نظرسنجی بسته شد.", reply_to=reply.id)
            await event.delete()
        except Exception as e:
            return await event.edit(f"❌ خطا: {e}")
        return
    
    if raw.startswith("جمع‌بندی") or raw.startswith("summary"):
        if not event.is_reply:
            return await event.edit("❌ روی پیام نظرسنجی ریپلای کن.")
        reply = await event.get_reply_message()
        if not reply.poll:
            return await event.edit("❌ این پیام یک نظرسنجی نیست.")
        try:
            # دریافت نتایج
            poll = reply.poll
            results = poll.results
            if not results:
                return await event.edit("❌ هنوز رایی ثبت نشده است.")
            
            total = results.total_voters or 0
            lines = [f"📊 **جمع‌بندی نظرسنجی**", "", f"سوال: {poll.question}", f"تعداد کل رای‌ها: {total}", ""]
            
            for i, opt in enumerate(poll.answers):
                votes = results.results[i] if i < len(results.results) else 0
                pct = (votes / total * 100) if total > 0 else 0
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                lines.append(f"{opt.text}: {votes} رای ({pct:.1f}%) {bar}")
            
            await event.edit("\n".join(lines))
            await event.delete()
        except Exception as e:
            return await event.edit(f"❌ خطا: {e}")
        return
    
    # ایجاد نظرسنجی جدید
    parts = raw.split("|")
    if len(parts) < 3:
        return await event.edit("❌ فرمت: `<سوال> | <گزینه۱> | <گزینه۲> | ...`")
    
    question = parts[0].strip()
    options = [opt.strip() for opt in parts[1:] if opt.strip()]
    if len(options) < 2:
        return await event.edit("❌ حداقل ۲ گزینه لازم است.")
    if len(options) > 10:
        return await event.edit("❌ حداکثر ۱۰ گزینه مجاز است.")
    
    try:
        # ارسال نظرسنجی
        sent = await client.send_message(
            event.chat_id,
            question,
            poll={
                "question": question,
                "options": options,
                "is_anonymous": True,
                "allows_multiple_answers": False,
                "quiz": False,
            }
        )
        await event.delete()
        
        # ذخیره در دیتابیس
        async with session_scope() as session:
            poll_record = GroupPoll(
                chat_id=event.chat_id,
                message_id=sent.id,
                poll_id=str(sent.poll.id) if sent.poll else "",
                question=question,
                options=json.dumps(options, ensure_ascii=False),
            )
            session.add(poll_record)
            await session.flush()
        
    except Exception as e:
        _record_error()
        await event.edit(f"❌ خطا در ایجاد نظرسنجی: {e}")