"""
دستوراتِ تکرارشونده: `.یادآوری تکراری` و `.تکرار`

برخلافِ `.یادآوری`/`.زمان‌بند` (که یک‌بار اجرا می‌شن و پاک می‌شن)، اینجا یه
برنامه‌ی دائمی توی جدولِ recurring_jobs ثبت می‌شه:

  • `.تکرار هر 30دقیقه متن` / `.تکرار هر 2h متن`  → فاصله‌ای
  • `.تکرار روزانه 08:00 متن`  → هر روز سرِ ساعتِ محلی
  • `.یادآوری تکراری ...` همون `.تکرار`ه (مقصدش همیشه Saved Messages)
  • `.تکرار لیست` / `.تکرار توقف <id>` / `.تکرار ادامه <id>` / `.تکرار حذف <id>`

ورکرِ پس‌زمینه هر ۳۰ ثانیه چک می‌کنه و کارهای سررسیده رو می‌فرسته و
next_run_at رو برای دورِ بعد جلو می‌بره.
"""
import asyncio
import datetime as dt
import logging
import re

from telethon import errors, events

from .. import runtime
from ..config import PREFIX, TIMEZONE_OFFSET
from ..repositories import recurring_repo
from ..runtime import client
from ..storage.stats_store import record_error as _record_error
from ..utils import pat
from .scheduler import _local_now, _to_utc_aware

logger = logging.getLogger("selfbot.handlers.recurring")

MIN_INTERVAL_SECONDS = 60  # زیرِ یه دقیقه مجاز نیست (ریسکِ فلاد/محدودیت)


# -------------------------------------------------------------- پارسِ زمان ---
_INTERVAL_RE = re.compile(
    r"^(\d+)\s*(" + "|".join(
        re.escape(u) for u in ("s", "sec", "ثانیه", "m", "min", "دقیقه", "h", "hour", "ساعت", "d", "day", "روز")
    ) + r")$"
)
_UNIT_SECONDS = {
    "s": 1, "sec": 1, "ثانیه": 1,
    "m": 60, "min": 60, "دقیقه": 60,
    "h": 3600, "hour": 3600, "ساعت": 3600,
    "d": 86400, "day": 86400, "روز": 86400,
}
_CLOCK_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def parse_recurring(arg: str):
    """
    آرگومانِ بعد از «تکراری»/«هر»/«روزانه» رو parse می‌کنه.
    خروجی: (interval_seconds | None, daily_hour, daily_minute) یا None.
    """
    m = _INTERVAL_RE.match(arg.strip())
    if m:
        seconds = int(m.group(1)) * _UNIT_SECONDS[m.group(2)]
        if seconds < MIN_INTERVAL_SECONDS:
            return None
        return seconds, None, None
    m = _CLOCK_RE.match(arg.strip())
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return "daily", hh, mm
    return None


def _next_daily_run(hh: int, mm: int) -> tuple[dt.datetime, str]:
    """اولین زمانِ آینده‌ی HH:MM به‌وقتِ محلی؛ خروجی: (utc_aware, نمایشِ محلی)."""
    now_local = _local_now()
    target_local = now_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target_local <= now_local:
        target_local += dt.timedelta(days=1)
    return _to_utc_aware(target_local), target_local.strftime("%Y-%m-%d %H:%M")


def _advance(now_utc: dt.datetime, job) -> dt.datetime:
    """محاسبه‌ی runِ بعدی بعد از یه اجرا (بر پایه‌ی now تا عقب‌ماندگی جبران شه)."""
    if job.interval_seconds:
        return now_utc + dt.timedelta(seconds=job.interval_seconds)
    if job.daily_hour is not None:
        next_local = _local_now().replace(
            hour=job.daily_hour, minute=job.daily_minute or 0, second=0, microsecond=0
        )
        if next_local <= _local_now():
            next_local += dt.timedelta(days=1)
        return _to_utc_aware(next_local)
    return now_utc + dt.timedelta(days=1)  # نباید رخ بده؛ محضِ احتیاط


def _describe(job) -> str:
    if job.interval_seconds:
        s = job.interval_seconds
        if s % 86400 == 0:
            return f"هر {s // 86400} روز"
        if s % 3600 == 0:
            return f"هر {s // 3600} ساعت"
        if s % 60 == 0:
            return f"هر {s // 60} دقیقه"
        return f"هر {s} ثانیه"
    if job.daily_hour is not None:
        return f"هر روز {job.daily_hour:02d}:{job.daily_minute or 0:02d}"
    return "؟"


def _format_list(jobs, empty_msg: str, title: str) -> str:
    if not jobs:
        return empty_msg
    lines = [title, ""]
    for j in jobs:
        run_at = j.next_run_at if j.next_run_at.tzinfo else j.next_run_at.replace(tzinfo=dt.timezone.utc)
        local_dt = run_at.astimezone(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(hours=TIMEZONE_OFFSET)
        preview = j.text if len(j.text) <= 40 else j.text[:40] + "…"
        status = "▶️" if j.active else "⏸"
        lines.append(
            f"{status} `{j.id}` — {_describe(j)} — بعدی: {local_dt.strftime('%Y-%m-%d %H:%M')} — {preview}"
        )
    return "\n".join(lines)


# ------------------------------------------------------------- دستورات ---
async def _add_recurring(event, kind: str, dest_chat_id: int, arg: str, label: str):
    parts = (arg or "").strip().split(maxsplit=2)
    if len(parts) < 2:
        return await event.edit(
            f"مثال‌ها:\n`{PREFIX}{label} هر 30دقیقه متن پیام`\n`{PREFIX}{label} هر 2ساعت متن پیام`\n`{PREFIX}{label} روزانه 08:00 متن پیام`"
        )
    mode_raw, text = parts[0], parts[2] if len(parts) > 2 else ""
    if not text and event.is_reply:
        reply = await event.get_reply_message()
        text = reply.raw_text or ""
    if not text:
        return await event.edit("متنِ پیام لازمه (یا ریپلای کن)")

    parsed = parse_recurring(mode_raw)
    if parsed is None:
        return await event.edit(
            "❌ فاصله/ساعتِ نامعتبر (حداقل ۱ دقیقه).\n"
            f"مثال: `{PREFIX}{label} هر 30دقیقه متن` یا `{PREFIX}{label} روزانه 08:00 متن`"
        )

    if parsed[0] == "daily":
        _, hh, mm = parsed
        next_run, local_display = _next_daily_run(hh, mm)
        job = await recurring_repo.create(
            dest_chat_id, text, kind, next_run, daily_hour=hh, daily_minute=mm
        )
        schedule_desc = f"هر روز {hh:02d}:{mm:02d} — اولین اجرا: {local_display}"
    else:
        seconds = parsed[0]
        next_run = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)
        job = await recurring_repo.create(
            dest_chat_id, text, kind, next_run, interval_seconds=seconds
        )
        schedule_desc = _describe(job) + f" — اولین اجرا: {dt.timedelta(seconds=seconds)} دیگه"

    await event.edit(f"✅ تکرار ثبت شد (#{job.id}):\n🔁 {schedule_desc}\n📝 {text}")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["تکرار", "recur", "repeat"])))
async def recurring_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    parts = arg.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if sub in ("لیست", "list", ""):
        jobs = await recurring_repo.list_all(event.chat_id)
        return await event.edit(
            _format_list(jobs, "توی این چت هیچ تکراری ثبت نشده", "🔁 **برنامه‌های تکراری (این چت)**")
        )

    if sub in ("توقف", "pause", "خاموش"):
        if not rest.strip().isdigit():
            return await event.edit(f"مثال: `{PREFIX}تکرار توقف 3`")
        ok = await recurring_repo.set_active(int(rest.strip()), False)
        return await event.edit(f"⏸ تکرارِ #{rest.strip()} متوقف شد" if ok else "پیدا نشد")

    if sub in ("ادامه", "resume", "روشن"):
        if not rest.strip().isdigit():
            return await event.edit(f"مثال: `{PREFIX}تکرار ادامه 3`")
        ok = await recurring_repo.set_active(int(rest.strip()), True)
        return await event.edit(f"▶️ تکرارِ #{rest.strip()} دوباره فعال شد" if ok else "پیدا نشد")

    if sub in ("حذف", "delete", "remove", "لغو"):
        if not rest.strip().isdigit():
            return await event.edit(f"مثال: `{PREFIX}تکرار حذف 3`")
        ok = await recurring_repo.delete(int(rest.strip()))
        return await event.edit(f"🗑 تکرارِ #{rest.strip()} حذف شد" if ok else "پیدا نشد")

    # «هر ...» یا «روزانه ...» → ثبتِ جدید در همین چت؛ «به من» → مقصدِ Saved Messages
    if arg.startswith("به‌من ") or arg.startswith("به من "):
        self_id = runtime.SELF_ID or event.chat_id
        return await _add_recurring(event, "reminder", self_id, arg.split(maxsplit=1)[1], "تکرار")
    await _add_recurring(event, "schedule", event.chat_id, arg, "تکرار")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["یادآوری‌تکراری", "یادآوری تکراری", "recurringreminder"])))
async def recurring_reminder_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    self_id = runtime.SELF_ID or event.chat_id
    if not arg or arg.split()[0].lower() in ("لیست", "list"):
        jobs = await recurring_repo.list_all(self_id)
        return await event.edit(
            _format_list(jobs, "هیچ یادآوریِ تکراری‌ای ثبت نشده", "🔁 **یادآوری‌های تکراری**")
        )
    await _add_recurring(event, "reminder", self_id, arg, "یادآوری‌تکراری")


# ------------------------------------------------------ ورکرِ پس‌زمینه ---
async def recurring_worker():
    """هر ۳۰ ثانیه: کارهای سررسیده رو بفرست و next_run رو جلو ببر."""
    from .. import health
    while True:
        await asyncio.sleep(30)
        health.update_worker_status("recurring", "ok")
        now_utc = dt.datetime.now(dt.timezone.utc)
        try:
            due = await recurring_repo.list_due(now_utc)
        except Exception:
            logger.exception("خطا در خوندنِ تکرارهای سررسیده")
            _record_error()
            health.update_worker_status("recurring", "error")
            continue
        for job in due:
            text = job.text if job.kind == "schedule" else f"🔁 **یادآوریِ تکراری**\n\n{job.text}"
            try:
                await client.send_message(job.chat_id, text)
            except errors.FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 300))
                break  # بقیه رو برای دورِ بعد بذار
            except Exception:
                logger.exception("خطا در ارسالِ تکرار #%s", job.id)
                _record_error()
            try:
                await recurring_repo.reschedule(job.id, _advance(now_utc, job))
            except Exception:
                logger.exception("خطا در جلوبردنِ next_run تکرار #%s", job.id)
                _record_error()
