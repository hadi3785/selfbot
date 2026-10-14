"""
دستورات حافظه هوش مصنوعی: .حافظه
"""
import logging
from typing import Dict, List

from telethon import events

from ..config import PREFIX
from ..runtime import client
from ..utils import pat
from ..repositories import ai_memory_repo

logger = logging.getLogger("selfbot.handlers.ai_memory")

CATEGORY_ICONS = {
    "کاربران": "👤",
    "گفتگوها": "💬",
    "پروژه‌ها": "📌",
    "یادداشت‌ها": "📝",
    "تنظیمات": "⚙️",
}


@client.on(events.NewMessage(outgoing=True, pattern=pat(["حافظه", "memory"])))
async def memory_handler(event):
    """مدیریت حافظه هوش مصنوعی."""
    args = (event.pattern_match.group(1) or "").strip().split()
    sub = args[0].lower() if args else ""

    # تفکیک از بازیِ حافظه‌ی اعداد (fun.py همین pattern را دارد):
    # «شروع/لغو/عدد» مالِ بازی است — اینجا کاری با آن نداریم.
    if sub in ("شروع", "start", "لغو", "cancel", "stop") or (sub.lstrip("-").isdigit() and sub):
        return None

    # subهای v2 را handlerِ memory_v2_handler (پایینِ همین فایل) مدیریت می‌کند
    if sub in ("وضعیت", "status", "یادبگیر", "learn", "ازپیام", "از_پیام", "learnfrom"):
        return None
    # «حذف <id>» سبکِ v2
    if sub == "حذف" and len(args) > 1 and args[1].lstrip("-").isdigit():
        return None

    if not sub:
        return await _show_memory_stats(event)

    if sub in ("افزودن", "add"):
        return await _add_memory(event, args[1:] if len(args) > 1 else [])
    if sub in ("جستجو", "search"):
        return await _search_memory(event, args[1:] if len(args) > 1 else [])
    if sub in ("حذف", "delete", "remove"):
        return await _delete_memory(event, args[1:] if len(args) > 1 else [])
    if sub in ("لیست", "list"):
        return await _list_memory(event, args[1:] if len(args) > 1 else [])
    if sub in ("پاک", "clear"):
        return await _clear_category(event, args[1:] if len(args) > 1 else [])

    return await _show_memory_stats(event)


async def _show_memory_stats(event):
    """نمایش آمار حافظه."""
    stats = await ai_memory_repo.get_stats()
    total = sum(stats.values())

    if total == 0:
        return await event.edit(
            f"🧠 **حافظه هوش مصنوعی**\n\n"
            f"🕳️ هنوز هیچ حافظه‌ای ذخیره نشده.\n\n"
            f"• افزودن: `{PREFIX}حافظه افزودن <دسته> <کلید> <مقدار>`\n"
            f"• مثال: `{PREFIX}حافظه افزودن کاربران هادی کاربر VIP`"
        )

    lines = ["🧠 **حافظه هوش مصنوعی**", ""]
    for cat in ai_memory_repo.CATEGORIES:
        icon = CATEGORY_ICONS.get(cat, "📁")
        count = stats.get(cat, 0)
        lines.append(f"{icon} {cat}: {count} آیتم")

    lines.append("")
    lines.append(f"📊 مجموع: {total} آیتم")
    lines.append("")
    lines.append(f"• جستجو: `{PREFIX}حافظه جستجو <عبارت>`")
    lines.append(f"• لیست: `{PREFIX}حافظه لیست <دسته>`")
    lines.append(f"• حذف: `{PREFIX}حافظه حذف <دسته> <کلید>`")
    lines.append(f"• پاک کردن دسته: `{PREFIX}حافظه پاک <دسته>`")

    await event.edit("\n".join(lines))


async def _add_memory(event, args):
    """افزودن حافظه جدید."""
    if len(args) < 3:
        return await event.edit(
            f"❌ استفاده: `{PREFIX}حافظه افزودن <دسته> <کلید> <مقدار>`\n"
            f"دسته‌ها: {', '.join(ai_memory_repo.CATEGORIES)}"
        )

    category = args[0]
    if category not in ai_memory_repo.CATEGORIES:
        return await event.edit(
            f"❌ دسته نامعتبر. دسته‌ها: {', '.join(ai_memory_repo.CATEGORIES)}"
        )

    key = args[1]
    value = " ".join(args[2:])

    try:
        memory = await ai_memory_repo.save_memory(category, key, value)
        value_preview = memory.value[:100] + ("..." if len(memory.value) > 100 else "")
        await event.edit(
            f"✅ حافظه ذخیره شد.\n"
            f"📁 دسته: {memory.category}\n"
            f"🔑 کلید: {memory.key}\n"
            f"📝 مقدار: {value_preview}"
        )
    except Exception as e:
        await event.edit(f"❌ خطا: {e}")


async def _search_memory(event, args):
    """جستجو در حافظه."""
    if not args:
        return await event.edit(f"❌ استفاده: `{PREFIX}حافظه جستجو <عبارت>`")

    query = " ".join(args)
    results = await ai_memory_repo.search_memories(query)

    if not results:
        return await event.edit(f"🔍 نتیجه‌ای برای `{query}` یافت نشد.")

    lines = [f"🔍 **نتایج جستجو: `{query}`**", ""]
    for category, items in results.items():
        icon = CATEGORY_ICONS.get(category, "📁")
        lines.append(f"{icon} **{category}** ({len(items)})")
        for item in items[:5]:
            value_preview = item.value[:60] + ("..." if len(item.value) > 60 else "")
            lines.append(f"  `{item.key}`: {value_preview}")
        if len(items) > 5:
            lines.append(f"  ... و {len(items) - 5} مورد دیگر")
        lines.append("")

    await event.edit("\n".join(lines))


async def _delete_memory(event, args):
    """حذف یک حافظه."""
    if len(args) < 2:
        return await event.edit(f"❌ استفاده: `{PREFIX}حافظه حذف <دسته> <کلید>`")

    category = args[0]
    key = args[1]

    if category not in ai_memory_repo.CATEGORIES:
        return await event.edit(f"❌ دسته نامعتبر. دسته‌ها: {', '.join(ai_memory_repo.CATEGORIES)}")

    success = await ai_memory_repo.delete_memory(category, key)
    if success:
        await event.edit(f"✅ حافظه `{key}` از دسته `{category}` حذف شد.")
    else:
        await event.edit(f"❌ حافظه `{key}` در دسته `{category}` یافت نشد.")


async def _list_memory(event, args):
    """لیست حافظه‌های یک دسته."""
    if not args:
        return await event.edit(f"❌ استفاده: `{PREFIX}حافظه لیست <دسته>`")

    category = args[0]
    if category not in ai_memory_repo.CATEGORIES:
        return await event.edit(f"❌ دسته نامعتبر. دسته‌ها: {', '.join(ai_memory_repo.CATEGORIES)}")

    items = await ai_memory_repo.get_memories_by_category(category)

    if not items:
        return await event.edit(f"🕳️ دسته `{category}` خالی است.")

    icon = CATEGORY_ICONS.get(category, "📁")
    lines = [f"{icon} **{category}** ({len(items)})", ""]

    for item in items[:20]:
        value_preview = item.value[:60] + ("..." if len(item.value) > 60 else "")
        lines.append(f"`{item.key}`: {value_preview}")

    if len(items) > 20:
        lines.append(f"... و {len(items) - 20} مورد دیگر")

    await event.edit("\n".join(lines))


async def _clear_category(event, args):
    """پاک کردن همه حافظه‌های یک دسته."""
    if not args:
        return await event.edit(f"❌ استفاده: `{PREFIX}حافظه پاک <دسته>`")

    category = args[0]
    if category not in ai_memory_repo.CATEGORIES:
        return await event.edit(f"❌ دسته نامعتبر. دسته‌ها: {', '.join(ai_memory_repo.CATEGORIES)}")

    count = await ai_memory_repo.delete_category(category)
    await event.edit(f"✅ {count} آیتم از دسته `{category}` پاک شد.")

# -------------------------------------------------- حافظه‌ی هوشمند (v2) ---
_SMART_ICONS = ai_memory_repo.SMART_ICONS
_SMART_CATEGORIES = ai_memory_repo.SMART_CATEGORIES


@client.on(events.NewMessage(outgoing=True, pattern=pat(["حافظه", "memory"])))
async def memory_v2_handler(event):
    """زیر‌دستورهای v2: وضعیت/یادبگیر/ازپیام/id حذف — قبل از handlerِ قدیمی dispatch می‌شود."""
    raw = (event.pattern_match.group(1) or "").strip()
    args = raw.split()
    sub = args[0].lower() if args else ""

    # تفکیک از بازیِ حافظه (fun.py)
    if sub in ("شروع", "start", "لغو", "cancel", "stop") or (sub.lstrip("-").isdigit() and sub):
        return None

    if sub in ("وضعیت", "status"):
        return await _smart_status(event)

    if sub in ("یادبگیر", "learn"):
        text = raw[len(args[0]):].strip()
        if not text:
            return await event.edit(
                "🧠 چه چیزی را یاد بگیرم؟\n"
                f"مثال: `{PREFIX}حافظه یادبگیر هادی به قهوه‌ی تلخ علاقه داره و شیرینی دوست نداره`"
            )
        return await _smart_learn(event, text)

    if sub in ("ازپیام", "از_پیام", "learnfrom"):
        if not event.is_reply:
            return await event.edit(
                f"روی پیامی ریپلای کن تا محتوایش را ساختاریافته یاد بگیرم.\n"
                f"یا مستقیم: `{PREFIX}حافظه یادبگیر <متن>`"
            )
        reply = await event.get_reply_message()
        text = (reply.raw_text or "").strip() if reply else ""
        if not text:
            return await event.edit("❌ پیامِ ریپلای‌شده متنی نیست.")
        return await _smart_learn(event, text)

    if sub == "حذف" and args[1:] and args[1].lstrip("-").isdigit():
        # «حذف <id>» → حذفِ مستقیم با id (سبکِ v2)
        ok = await ai_memory_repo.delete_by_id(int(args[1]))
        if ok:
            return await event.edit(f"🗑 حافظه‌ی #{args[1]} حذف شد.")
        return await event.edit(f"❌ حافظه‌ای با id {args[1]} پیدا نشد. (`{PREFIX}حافظه وضعیت` برای idها)")

    if not sub:
        # آمار را handlerِ قدیمی می‌دهد؛ اینجا pass
        return None

    # بقیه‌ی subها را handlerِ قدیمیِ پایینِ فایل مدیریت می‌کند (هر دو روی همین pattern ثبت‌اند؛
    # این handler فقط مواردِ v2 را می‌گیرد و بقیه را پاس می‌دهد)
    return None


async def _smart_status(event):
    """وضعیتِ حافظه‌ی هوشمند + آخرین idها."""
    stats = await ai_memory_repo.get_stats()
    smart_total = sum(stats.get(cat, 0) for cat in _SMART_CATEGORIES)
    lines = ["🧠 **حافظه‌ی هوشمند**", ""]
    if smart_total == 0:
        lines += [
            "🕳️ هنوز چیزی ذخیره نشده.",
            "",
            "• یادگیری از متن: `{PREFIX}حافظه یادبگیر <متن>`",
            "• یادگیری از پیام: روی پیام ریپلای کن + `.حافظه ازپیام`",
            "",
            "انواعِ ذخیره: 👤 Preference | 📌 Project | 📝 Task | 💡 Idea | 🔗 Link",
        ]
        return await event.edit("\n".join(lines).replace("{PREFIX}", PREFIX))

    for cat in _SMART_CATEGORIES:
        n = stats.get(cat, 0)
        if n:
            lines.append(f"{_SMART_ICONS[cat]} {cat}: {n}")
    lines.append(f"\n📊 مجموعِ هوشمند: {smart_total} | کل: {sum(stats.values())}")

    # آخرین ۱۰ آیتم با id
    recent = await ai_memory_repo.list_all_ids(limit=10)
    if recent:
        lines.append("")
        lines.append("🕒 **آخرین‌ها** (حذف: `.حافظه حذف <id>`)")
        for m in recent:
            icon = _SMART_ICONS.get(m.category, "📁")
            v = m.value[:40] + ("…" if len(m.value) > 40 else "")
            lines.append(f"  #{m.id} {icon} {m.key}: {v}")

    await event.edit("\n".join(lines))


_LEARN_SYSTEM = (
    "تو استخراج‌کننده‌ی حافظه هستی. متنِ کاربر را به آیتم‌های حافظه تبدیل کن. "
    "فقط JSON برگردان، بدون هیچ متنِ اضافه، با این شکل:\n"
    '[{"type": "Preference|Project|Task|Idea|Link", "key": "کلیدِ کوتاهِ یکتا", "value": "مقدارِ کامل"}]\n'
    "قواعد: type دقیقاً یکی از پنج مقدار بالا. هر fact مهم یک آیتم. key کوتاه و انگلیسی/فارسیِ معنادار. "
    "اگر هیچ fact مستقل‌ی نیست، یک آیتمِ کلی با key=\"general\" بساز. حداکثر ۶ آیتم."
)


async def _smart_learn(event, text: str):
    """تبدیلِ متن به آیتم‌های ساختاریافته با مدل و ذخیره."""
    from .. import ai as ai_core

    try:
        raw = await ai_core.ask_ai(
            [
                {"role": "system", "content": _LEARN_SYSTEM},
                {"role": "user", "content": text},
            ],
            max_tokens=500,
        )
    except ai_core.AIDisabledError:
        return await event.edit(
            "❌ برایِ یادگیریِ هوشمند به `AI_API_KEY` نیاز است.\n"
            "(ذخیره‌ی دستی همیشه کار می‌کند: `.حافظه افزودن <دسته> <کلید> <مقدار>`)"
        )
    except ai_core.AIRequestError as e:
        return await event.edit(f"❌ خطای AI: {e}")

    # parse: ممکن است مدل ```json wrapper بگذارد
    import json as _json
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
    try:
        items = _json.loads(txt)
        if isinstance(items, dict):
            items = [items]
        assert isinstance(items, list) and items
    except Exception:
        # fallback: کلِ متن به‌عنوان یک Idea ذخیره شود تا چیزی گم نشود
        items = [{"type": "Idea", "key": text[:40], "value": text}]

    saved = []
    for it in items[:6]:
        cat = str(it.get("type", "Idea")).strip()
        if cat not in _SMART_CATEGORIES:
            cat = "Idea"
        key = str(it.get("key", "")).strip()[:120] or "general"
        value = str(it.get("value", "")).strip()
        if not value:
            continue
        m = await ai_memory_repo.save_memory(cat, key, value)
        saved.append(m)

    if not saved:
        return await event.edit("❌ چیزی قابلِ ذخیره پیدا نشد.")

    lines = [f"🧠 **{len(saved)} حافظه ذخیره شد**", ""]
    for m in saved:
        icon = _SMART_ICONS.get(m.category, "📁")
        lines.append(f"{icon} [{m.category}] **{m.key}**")
        v = m.value[:80] + ("…" if len(m.value) > 80 else "")
        lines.append(f"   {v}")
    lines += [
        "",
        f"• مشاهده/حذف: `{PREFIX}حافظه وضعیت` — حذف: `{PREFIX}حافظه حذف <id>`",
        "• این خاطرات حالا در پاسخ‌های `.پرسش` و منشیِ هوش‌مصنوعی لحاظ می‌شوند.",
    ]
    await event.edit("\n".join(lines))
