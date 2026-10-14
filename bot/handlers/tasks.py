"""🔥 Task Manager شخصی: `.کار` — افزودن/لیست/انجام/حذف/امروز/عقب.

مثال‌ها:
  .کار افزودن خرید کتاب
  .کار افزودن جلسه تیم -- فردا 18:00     (ددلاین با parse طبیعی)
  .کار افزودن ! تماس مهم                 (علامتِ ! = مهم)
  .کارها / .کارهای امروز / .کارهای عقب
  .کار انجام 3 / .کار حذف 3 / .کار بازکردن 3
"""
import datetime as dt

from telethon import events

from .. import assistant_brain
from ..config import PREFIX, TIMEZONE_OFFSET
from ..repositories import tasks_repo
from ..runtime import client
from ..utils import pat


def _fmt_due(due_at: dt.datetime | None, now_utc: dt.datetime | None = None) -> str:
    if due_at is None:
        return ""
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=dt.timezone.utc)
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    local = due_at.replace(tzinfo=None) + dt.timedelta(hours=TIMEZONE_OFFSET)
    label = local.strftime("%m-%d %H:%M")
    diff = due_at - now_utc
    if diff.total_seconds() < 0:
        label = f"⏰{label} (عقب‌افتاده)"
    return f" — 📅 {label}"


def _render(tasks: list[dict], title: str, empty: str) -> str:
    if not tasks:
        return empty
    now = dt.datetime.now(dt.timezone.utc)
    lines = [title, ""]
    for t in tasks:
        mark = "✅" if t["done"] else ("❗" if t["priority"] >= 1 else "▫️")
        due = _fmt_due(t["due_at"], now)
        text = t["text"] if len(t["text"]) <= 60 else t["text"][:60] + "…"
        lines.append(f"{mark} `{t['id']}` {text}{due}")
    return "\n".join(lines)


@client.on(events.NewMessage(outgoing=True, pattern=pat(["کار", "کارها", "کارهای", "task"])))
async def task_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    parts = arg.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub in ("افزودن", "add", "+") and rest:
        priority = 0
        if rest.startswith("!") or rest.startswith("مهم "):
            priority = 1
            rest = rest.lstrip("!").replace("مهم ", "", 1).strip()
        due_at = None
        if "--" in rest:
            rest, time_part = rest.split("--", 1)
            rest = rest.strip()
            parsed = assistant_brain.parse_natural_time(time_part.strip())
            if parsed is not None:
                due_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
        t = await tasks_repo.add_task(rest, due_at=due_at, priority=priority)
        due_note = f"\n📅 ددلاین: **{_fmt_due(due_at).split('— ')[-1].strip()}**" if due_at else ""
        return await event.edit(f"✅ کارِ `{t['id']}` ثبت شد: {rest}{due_note}")

    if sub in ("انجام", "done", "✅"):
        if not rest.isdigit():
            return await event.edit(f"مثال: `{PREFIX}کار انجام 3`")
        if await tasks_repo.set_done(int(rest), True):
            return await event.edit(f"✅ کارِ `{rest}` انجام شد 🎉")
        return await event.edit("همچین کاری پیدا نشد")

    if sub in ("بازکردن", "undone", "reopen"):
        if not rest.isdigit():
            return await event.edit(f"مثال: `{PREFIX}کار بازکردن 3`")
        if await tasks_repo.set_done(int(rest), False):
            return await event.edit(f"↩️ کارِ `{rest}` دوباره باز شد")
        return await event.edit("همچین کاری پیدا نشد")

    if sub in ("حذف", "del", "-"):
        if not rest.isdigit():
            return await event.edit(f"مثال: `{PREFIX}کار حذف 3`")
        if await tasks_repo.delete_task(int(rest)):
            return await event.edit(f"🗑 کارِ `{rest}` حذف شد")
        return await event.edit("همچین کاری پیدا نشد")

    if sub in ("امروز", "today"):
        tasks = await tasks_repo.list_tasks(done=False, limit=100)
        end_of_today_utc = _end_of_local_today()
        today = [t for t in tasks if t["due_at"] and _aware(t["due_at"]) <= end_of_today_utc]
        return await event.edit(_render(today, "📝 **کارهای امروز**", "🎈 برای امروز کارِ سرِرسی نیست"))

    if sub in ("عقب", "عقب‌افتاده", "عقبافتاده", "overdue"):
        tasks = await tasks_repo.list_tasks(done=False, limit=100)
        now = dt.datetime.now(dt.timezone.utc)
        late = [t for t in tasks if t["due_at"] and _aware(t["due_at"]) < now]
        return await event.edit(_render(late, "⏰ **کارهای عقب‌افتاده**", "🎉 هیچ کاری عقب نیفتاده"))

    # بدون sub یا sub ناشناخته → همه‌ی کارهای باز
    tasks = await tasks_repo.list_tasks(done=False)
    n_done = len(await tasks_repo.list_tasks(done=True, limit=200))
    out = _render(tasks, f"📝 **کارهای باز** ({len(tasks)})", "🎉 هیچ کارِ بازی نداری")
    return await event.edit(out + (f"\n\n✅ انجام‌شده: {n_done}" if n_done else ""))


def _aware(d: dt.datetime) -> dt.datetime:
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _end_of_local_today() -> dt.datetime:
    now_local = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=TIMEZONE_OFFSET)
    end_local = now_local.replace(hour=23, minute=59, second=59, microsecond=0)
    return (end_local - dt.timedelta(hours=TIMEZONE_OFFSET)).replace(tzinfo=dt.timezone.utc)
