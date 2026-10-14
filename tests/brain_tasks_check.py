"""تستِ دستیار شخصی: Task Manager + مغزِ triage/زمانِ طبیعی."""
import asyncio
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/brain_test.db"
try:
    os.remove("/tmp/brain_test.db")
except FileNotFoundError:
    pass

from bot.db.engine import engine
from bot.db import models, models_ext  # noqa: F401
from bot import assistant_brain as ab
from bot.repositories import tasks_repo

NOW = dt.datetime(2026, 9, 2, 10, 0, tzinfo=dt.timezone.utc)  # 13:30 محلی


def t_parse():
    r = ab.parse_natural_time("فردا ساعت ۵ جلسه داریم", NOW)
    assert r is not None and (r.replace(tzinfo=None) + dt.timedelta(hours=3.5)).hour == 5, r
    r2 = ab.parse_natural_time("۲ ساعت دیگه چک کن", NOW)
    assert r2 == NOW + dt.timedelta(hours=2), r2
    r3 = ab.parse_natural_time("فردا 17:00 تماس", NOW)
    assert (r3.replace(tzinfo=None) + dt.timedelta(hours=3.5)).strftime("%H:%M") == "17:00"
    assert ab.parse_natural_time("سلام خوبی؟", NOW) is None
    print("✓ parse_natural_time")


def t_strip():
    assert ab.strip_time_phrase("فردا ساعت ۸ جلسه با تیم برو") == "جلسه با تیم برو"
    assert ab.strip_time_phrase("۲ ساعت دیگه پروژه رو چک کن") == "پروژه رو چک کن"
    assert ab.strip_time_phrase("فردا ساعت ۵") == "فردا ساعت ۵"
    print("✓ strip_time_phrase")


def t_fallback():
    r = ab._triage_fallback("فردا ساعت ۵ جلسه داریم یادت نره")
    assert r["importance"] == 2 and r["event"], r
    r2 = ab._triage_fallback("سلام رفتم بازار")
    assert r2["importance"] == 0 and not r2["event"]
    print("✓ triage fallback")


async def t_tasks():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    t1 = await tasks_repo.add_task("خرید کتاب", priority=1)
    due = ab.parse_natural_time("فردا 18:00", NOW)
    t2 = await tasks_repo.add_task("جلسه تیم", due_at=due)
    open_tasks = await tasks_repo.list_tasks(done=False)
    assert len(open_tasks) == 2
    assert await tasks_repo.set_done(t1["id"], True)
    assert len(await tasks_repo.list_tasks(done=False)) == 1
    assert await tasks_repo.set_done(t1["id"], False)
    assert await tasks_repo.delete_task(t2["id"])
    assert not await tasks_repo.delete_task(999)
    print("✓ tasks repo")


t_parse()
t_strip()
t_fallback()
asyncio.run(t_tasks())
print("\nALL BRAIN/TASKS CHECKS PASSED")
