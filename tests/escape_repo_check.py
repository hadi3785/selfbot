"""تستِ runtime واقعی: repoهای escape روی SQLite درون‌حافظه‌ای (async)."""
import asyncio
import os
import sys

os.environ["API_ID"] = "12345"
os.environ["API_HASH"] = "x"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["BOT_TOKEN"] = "1:fake"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot.db.engine as db_engine
import bot.db.models_ext  # noqa: F401 — ثبتِ مدل‌ها روی Base قبل از create_all
from bot.db.models import Base
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from bot.escape import engine


async def main() -> None:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db_engine.SessionLocal = async_sessionmaker(eng, expire_on_commit=False)

    from bot.repositories import escape_repo

    # ۱) save/load دورِ کامل
    st = engine.create_game(111, 222, scenario_id="house")
    await escape_repo.save_session(111, 222, st)
    loaded = await escape_repo.load_session(111, 222)
    assert loaded is not None and loaded["scenario"] == "house"
    assert loaded["current_puzzle"] == st["current_puzzle"]
    print("✓ save/load round-trip")

    # ۲) upsert دوباره (بازنویسی)
    engine.answer(st, st["puzzles"][st["current_puzzle"]]["answer"])
    await escape_repo.save_session(111, 222, st)
    loaded2 = await escape_repo.load_session(111, 222)
    assert loaded2["stage"] == st["stage"], (loaded2["stage"], st["stage"])
    print("✓ upsert بازنویسی")

    # ۳) پایان بازی → رکورد حذف + امتیاز ثبت
    st["status"] = "won"
    await escape_repo.save_session(111, 222, st)
    assert (await escape_repo.load_session(111, 222)) is None
    await escape_repo.add_score(111, 222, "house", 500, 5, 300, won=True)
    rows = await escape_repo.leaderboard(10)
    assert rows and rows[0]["user_id"] == 222, rows
    print("✓ پایان بازی: حذفِ session + ثبتِ score + leaderboard")

    # ۴) daily: ثبتِ یک‌باره و چکِ attempts
    used = await escape_repo.daily_attempt_used(111, 222, "2026-08-31")
    assert used is False
    await escape_repo.register_daily_attempt(111, 222, "2026-08-31", 500)
    assert await escape_repo.daily_attempt_used(111, 222, "2026-08-31")
    print("✓ daily attempt")

    # ۵) stats_summary
    summ = await escape_repo.stats_summary()
    assert summ["most_solved"] >= 1 and summ["top_score"] >= 500
    print("✓ stats_summary:", summ)

    await eng.dispose()
    print("\nALL DB CHECKS PASSED")


asyncio.run(main())
