"""تستِ حافظه‌ی هوشمند v2: save/search/relevant/delete_by_id/stats."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/mem_v2_test.db"
try:
    os.remove("/tmp/mem_v2_test.db")
except FileNotFoundError:
    pass

from bot.db.engine import engine
from bot.db import models, models_ext  # noqa: F401
from bot.repositories import ai_memory_repo as repo


async def t():
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    await repo.save_memory("Preference", "coffee", "قهوه‌ی تلخ دوست دارد، شیرینی نه")
    await repo.save_memory("Project", "selfbot", "سلف‌بات تلگرام فارسی روی Railway")
    await repo.save_memory("Link", "repo", "github.com/hadi/selfbot")
    await repo.save_memory("کاربران", "هادی", "owner")
    await repo.save_memory("Task", "buy_milk", "خریدِ شیر یادت نره")

    rel = await repo.relevant_memories("قهوه چی بنوشم؟")
    cats = [(m.category, m.key) for m in rel]
    assert ("Preference", "coffee") in cats, cats
    assert ("Task", "buy_milk") not in cats, "نامرتبط نباید بیاید"
    print("✓ relevant: Preference همیشه + مرتبط‌ها:", cats[:3])

    stats = await repo.get_stats()
    assert stats["Preference"] == 1 and stats["کاربران"] == 1
    print("✓ stats:", {k: v for k, v in stats.items() if v})

    ok = await repo.delete_by_id(2)
    assert ok
    assert not await repo.delete_by_id(999)
    print("✓ delete_by_id")

    recent = await repo.get_recent(3)
    assert len(recent) == 3
    print("✓ get_recent:", [(m.category, m.key) for m in recent])

    with_ids = await repo.list_all_ids("Preference")
    assert len(with_ids) == 1 and with_ids[0].id
    print("✓ list_all_ids")


asyncio.run(t())
print("\nALL MEMORY-V2 CHECKS PASSED")
