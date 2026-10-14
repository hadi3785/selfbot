"""📚 Knowledge Base شخصی: `.دانش` — افزودن/لیست/جستجو/حذف + AI در agent."""
import re

from telethon import events

from .. import knowledge_base as kb
from ..config import PREFIX
from ..runtime import client
from ..storage.stats_store import record_error as _record_error
from ..utils import pat


@client.on(events.NewMessage(outgoing=True, pattern=pat(["دانش", "knowledge"])))
async def knowledge_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    parts = arg.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""

    if not sub:
        titles = await kb.kb_list()
        if not titles:
            return await event.edit(
                "📚 **دانشِ شخصی (Knowledge Base)**\n\n"
                f"`{PREFIX}دانش افزودن <عنوان>` — با ریپلای روی متن (یا در پیامِ بعدی)\n"
                f"`{PREFIX}دانش افزودن <عنوان> | <متن>` — مستقیم\n"
                f"`{PREFIX}دانش لیست` — پرونده‌ها\n"
                f"`{PREFIX}دانش جستجو <عبارت>` — بینِ پرونده‌ها\n"
                f"`{PREFIX}دانش حذف <عنوان>`\n\n"
                "🧠 AI در `.پرسش`/عامل، خودش از دانش‌ها استفاده می‌کند."
            )

    if sub in ("افزودن", "add", "+"):
        rest = parts[1] if len(parts) > 1 else ""
        if "|" in rest:
            title, body = rest.split("|", 1)
            title, body = title.strip(), body.strip()
            if not title or not body:
                return await event.edit("❌ عنوان یا متن خالی است.")
            n = await kb.kb_add(title, body)
            return await event.edit(f"📚 پرونده‌ی «{title}» ذخیره شد ({n} قطعه).")
        if not rest:
            return await event.edit(f"مثال: `{PREFIX}دانش افزودن پروژه‌ی ربات | متنِ توضیح...`")
        title = rest
        if event.is_reply:
            reply = await event.get_reply_message()
            body = reply.raw_text or ""
            if not body:
                return await event.edit("❌ پیامِ ریپلای‌شده متن ندارد.")
            n = await kb.kb_add(title, body)
            return await event.edit(f"📚 پرونده‌ی «{title}» ذخیره شد ({n} قطعه).")
        return await event.edit(
            "⏳ عنوان ثبت شد؛ حالا متنش را بفرست (پیامِ بعدی) یا:\n"
            f"`{PREFIX}دانش افزودن {title} | <متن>`"
        )

    if sub in ("لیست", "list"):
        titles = await kb.kb_list()
        if not titles:
            return await event.edit("📚 دانش خالی است.")
        lines = ["📚 **پرونده‌های دانش**", ""]
        lines += [f"• {t}" for t in titles[:30]]
        return await event.edit("\n".join(lines))

    if sub in ("جستجو", "search"):
        q = parts[1].strip() if len(parts) > 1 else ""
        if not q:
            return await event.edit(f"مثال: `{PREFIX}دانش جستجو ریلوی`")
        hits = await kb.kb_search(q)
        if not hits:
            return await event.edit("🔎 نتیجه‌ای در دانش پیدا نشد.")
        lines = [f"🔎 **{len(hits)} نتیجه در دانش:**", ""]
        for h in hits:
            lines.append(f"📄 **{h['key']}**")
            lines.append(f"{h['value'][:250]}\n")
        return await event.edit("\n".join(lines))

    if sub in ("حذف", "del", "-"):
        title = parts[1].strip() if len(parts) > 1 else ""
        if not title:
            return await event.edit(f"مثال: `{PREFIX}دانش حذف پروژه‌ی ربات`")
        n = await kb.kb_delete(title)
        return await event.edit(f"🗑 {n} قطعه از «{title}» حذف شد." if n else "چنین پرونده‌ای نیست.")

    return await event.edit("sub نامعتبر؛ `.دانش` را بدونِ آرگومان بزن برای راهنما.")
