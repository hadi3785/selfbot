"""
🤖 اتوپایلوت — حالتِ AI Auto-Pilot

وقتی روشن باشد، پیام‌های خصوصیِ دریافتی را با مغزِ دستیار (assistant_brain)
تحلیل می‌کند و بسته به نتیجه:
  • پیامِ مهم → آیتمِ اینباکس با priority=2 + هشدارِ فوری
  • قرار/جلسه/ددلاین → یادآوریِ خودکار (جدول scheduled_jobs)
  • نیازمند پاسخ → آیتمِ اینباکس با priority=1
  • بقیه → نادیده (بدونِ اسپم)

محدودیت‌ها (برای پرهیز از اسپمِ API):
  • فقط پیام‌های خصوصیِ غیرخودی
  • حداکثر یک triage هم‌زمان + rate-gap بینِ فراخوانی‌های AI
  • toggle سراسری از settings_toggles (مثل بقیه‌ی سوییچ‌های پروژه)

دستورها:
  .اتوپایل روشن / خاموش / وضعیت
"""
import asyncio
import datetime as dt
import logging

from telethon import events

from .. import assistant_brain, config, runtime
from ..config import PREFIX, TIMEZONE_OFFSET
from ..repositories import inbox_repo
from ..storage.scheduler_store import create_job
from ..storage.settings_toggles import set_toggle, toggles
from ..runtime import client
from ..utils import pat

logger = logging.getLogger("selfbot.handlers.autopilot")

_MIN_GAP_SECONDS = 20  # حداقل فاصله‌ی بین triageها (کنترلِ هزینه/نرخ)
_triage_lock = asyncio.Lock()
_last_triage_at = 0.0

IGNORE_KEY = "autopilot_ignored_chats"


async def _ignored_chats() -> set:
    """چت‌های مستثنی (`.اتوپایل مستثنی`) — پایدار در settings."""
    from ..repositories import settings_repo

    val = await settings_repo.get_setting(IGNORE_KEY)
    if not val:
        return set()
    out = set()
    for part in val.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            out.add(int(part))
    return out


async def _toggle_ignore(chat_id: int) -> bool:
    """toggleِ چتِ جاری؛ خروجی = حالتِ جدید (True یعنی مستثنی شد)."""
    from ..repositories import settings_repo

    chats = await _ignored_chats()
    if chat_id in chats:
        chats.discard(chat_id)
        state = False
    else:
        chats.add(chat_id)
        state = True
    await settings_repo.set_setting(IGNORE_KEY, ",".join(str(c) for c in sorted(chats)))
    return state


def _local_display(run_at_utc: dt.datetime) -> str:
    naive = run_at_utc.replace(tzinfo=None) if run_at_utc.tzinfo else run_at_utc
    return (naive + dt.timedelta(hours=TIMEZONE_OFFSET)).strftime("%Y-%m-%d %H:%M")


async def _maybe_create_reminder(event, text: str, due_iso: str, title: str) -> str | None:
    try:
        due = dt.datetime.fromisoformat(due_iso)
    except (TypeError, ValueError):
        return None
    if due.tzinfo is None:
        due = due.replace(tzinfo=dt.timezone.utc)
    if due <= dt.datetime.now(dt.timezone.utc):
        return None
    dest = runtime.SELF_ID or event.chat_id
    job = await create_job(dest, title or text, due, "reminder")
    return f"🔔 یادآوریِ خودکار #{job.id} — سرِ **{_local_display(due)}**"


async def _handle_private(event):
    """پردازشِ پیامِ خصوصیِ دریافتی در حالتِ اتوپایلوت."""
    global _last_triage_at
    import time as _time

    if not toggles.get("autopilot_enabled", False):
        return
    sender = await event.get_sender()
    if sender and getattr(sender, "is_self", False):
        return
    # پیام‌های بات‌ها (مثل پیام‌های هوش مصنوعی/پنل) را تحلیل نکن — وگرنه هر
    # اعلانِ خودکارِ ما (پر از کلمه‌های «مهم/یادآوری/جلسه») خودش ترییژ می‌شود.
    if sender and getattr(sender, "bot", False):
        return
    if event.chat_id in await _ignored_chats():
        return
    text = (event.raw_text or "").strip()
    if not text:
        return
    if config.AI_API_KEY and not (await _rate_gate()):
        # با AI فعال: کنترلِ نرخِ فراخوانی (صف نکن؛ رد شود)
        return

    try:
        result = await assistant_brain.triage_message(text)
    except Exception:
        logger.exception("triage failed")
        return

    lines = []
    importance = int(result.get("importance") or 0)
    needs_reply = bool(result.get("needs_reply"))
    event_ = result.get("event") or {}

    priority = 2 if importance == 2 else (1 if needs_reply else 0)
    if priority or event_:
        sender_name = getattr(sender, "first_name", None) or "ناشناس"
        await inbox_repo.save_item(
            chat_id=event.chat_id,
            message_id=event.id,
            text=text[:4000],
            sender_id=event.sender_id,
            sender_name=sender_name,
            importance=2 if importance == 2 else (1 if needs_reply else 0),
            tags="autopilot",
            note=result.get("reason", ""),
        )
        preview = text if len(text) <= 120 else text[:120] + "…"
        if priority == 2:
            lines.append(f"🔴 پیامِ مهم — به اینباکس (مهم) اضافه شد\n> {preview}")
        elif needs_reply:
            lines.append(f"🟡 نیازمندِ پاسخ — به اینباکس اضافه شد\n> {preview}")

    due_iso = (event_ or {}).get("due_at")
    if due_iso:
        title = (event_ or {}).get("title") or text
        note = await _maybe_create_reminder(event, text, due_iso, title)
        if note:
            lines.append(note)

    if lines:
        lines.insert(0, f"🤖 **اتوپایلوت** — از {getattr(sender, 'first_name', '؟')}")
        lines.append(f"_{result.get('reason', '')}_")
        try:
            await event.reply("\n".join(lines))
        except Exception:
            logger.exception("autopilot notice failed")


async def _rate_gate() -> bool:
    global _last_triage_at
    async with _triage_lock:
        import time as _time

        now = _time.monotonic()
        if now - _last_triage_at < _MIN_GAP_SECONDS:
            return False
        _last_triage_at = now
        return True


# فقط یک listener همیشه‌فعال؛ خودش toggle را چک می‌کند (روشن/خاموشِ ارزان)
client.add_event_handler(_handle_private, events.NewMessage(incoming=True, func=lambda e: e.is_private))


@client.on(events.NewMessage(outgoing=True, pattern=pat(["اتوپایل", "autopilot"])))
async def autopilot_cmd(event):
    arg = (event.pattern_match.group(1) or "").strip()
    parts = arg.split(maxsplit=1)
    sub = parts[0].strip().lower() if parts else ""

    if sub in ("روشن", "on", "1"):
        await set_toggle("autopilot_enabled", True)
        return await event.edit("🤖 اتوپایلوت **روشن** شد\nپیام‌های خصوصی تحلیل می‌شوند (مهم/نیاز به پاسخ/یادآوریِ خودکار)")
    if sub in ("خاموش", "off", "0"):
        await set_toggle("autopilot_enabled", False)
        return await event.edit("🤖 اتوپایلوت **خاموش** شد")
    if sub in ("مستثنی", "ignore"):
        state = await _toggle_ignore(event.chat_id)
        return await event.edit(
            "🚫 این چت از تحلیلِ اتوپایلوت **مستثنی** شد" if state
            else "✅ این چت دوباره واردِ تحلیلِ اتوپایلوت شد"
        )
    state = "🟢 روشن" if toggles.get("autopilot_enabled", False) else "🔴 خاموش"
    await event.edit(
        f"🤖 **اتوپایلوت**\nوضعیت: {state}\n\n"
        f"`{PREFIX}اتوپایل روشن` / `{PREFIX}اتوپایل خاموش`\n"
        f"`{PREFIX}اتوپایل مستثنی` — بی‌خیالِ این چت (toggle)\n\n"
        "وقتی روشن است، پیام‌های خصوصی تحلیل می‌شوند:\n"
        "🔴 مهم → اینباکس (مهم)\n🟡 نیازمند پاسخ → اینباکس\n"
        "🔔 قرار/جلسه → یادآوریِ خودکار"
    )
