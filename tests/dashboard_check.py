"""تستِ داشبوردِ جدید: دینامیکِ greeting/attention/insight + fail-safe."""
import asyncio, datetime as dt, os, sys
sys.path.insert(0, "/data/workspace/selfbot/selfbot-main")
os.environ["API_ID"] = "12345"; os.environ["API_HASH"] = "x"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/dash_new.db"
try: os.remove("/tmp/dash_new.db")
except FileNotFoundError: pass

import bot.handlers  # noqa
from bot.db.engine import engine
from bot.db import models
from bot.handlers import dashboard as db
from bot.repositories import tasks_repo, inbox_repo
from bot.storage.scheduler_store import create_job


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    # داده‌ی واقعی: کارِ عقب‌افتاده + کارِ امروز + پیامِ مهم + یادآوریِ نزدیک
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    soon = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
    today_late = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    await tasks_repo.add_task("کارِ عقب‌افتاده‌ی تستی", due_at=past)
    t2 = await tasks_repo.add_task("کارِ مهمِ امروز", priority=1, due_at=today_late)
    await inbox_repo.save_item(chat_id=1, message_id=1, text="پیامِ مهمِ تستی", sender_name="علی", importance=1)
    await create_job(1, "یادآوریِ تست", soon, "reminder")

    text = await db.build_dashboard()
    print(text)
    print("=" * 50)
    # دینامیک: باید greetingِ هشدار بدهد
    assert "نیاز به توجه" in text or "عقب‌افتاده" in text, "greeting dynamic failed"
    assert "NEEDS ATTENTION" in text or "نیاز به توجه" in text
    assert "AI INSIGHT" in text
    assert "QUICK ACTIONS" in text
    # یادآوریِ ۱۰ دقیقه‌ای باید دیده شود
    d = await db._gather()
    assert d["next_rem_in_min"] is not None and d["next_rem_in_min"] <= 15, d["next_rem_in_min"]
    assert len(d["overdue"]) == 1 and d and True
    assert d["important"] == 1
    print("\nDASHBOARD CHECKS PASSED")

asyncio.run(main())
