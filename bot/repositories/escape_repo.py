"""💾 لایه‌ی دیتابیس اتاق فرار (PostgreSQL — طبقِ الگوی repoهای پروژه).

جدول‌ها (migration 0015):
- escape_sessions: state بازیِ در جریان (per user per chat؛ JSON)
- escape_scores: نتایجِ نهایی برای leaderboard
- escape_daily: چالشِ روزانه (تلاشِ روزِ هر کاربر)
"""
from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import func as sa_func, select

from ..db.engine import session_scope
from ..db.models_ext import EscapeDaily, EscapeScore, EscapeSession


# ------------------------------------------------------------- sessions --
async def load_session(chat_id: int, user_id: int) -> dict | None:
    async with session_scope() as session:
        row = (
            await session.execute(
                select(EscapeSession).where(
                    EscapeSession.chat_id == chat_id,
                    EscapeSession.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        return json.loads(row.state) if row else None


async def save_session(chat_id: int, user_id: int, state: dict) -> None:
    """upsert؛ statusهای تمام‌شده حذف می‌شوند (تمیزکاریِ خودکار)."""
    async with session_scope() as session:
        row = (
            await session.execute(
                select(EscapeSession).where(
                    EscapeSession.chat_id == chat_id,
                    EscapeSession.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if state.get("status") != "running":
            if row:
                await session.delete(row)
            return
        if row:
            row.state = json.dumps(state, ensure_ascii=False)
            row.updated_at = dt.datetime.now(dt.timezone.utc)
        else:
            session.add(
                EscapeSession(
                    chat_id=chat_id,
                    user_id=user_id,
                    state=json.dumps(state, ensure_ascii=False),
                )
            )


# --------------------------------------------------------------- scores --
async def add_score(
    chat_id: int,
    user_id: int,
    scenario: str,
    score: int,
    solved_count: int,
    elapsed_seconds: int,
    won: bool,
) -> None:
    async with session_scope() as session:
        session.add(
            EscapeScore(
                chat_id=chat_id,
                user_id=user_id,
                scenario=scenario,
                score=max(0, score),
                solved_count=solved_count,
                elapsed_seconds=elapsed_seconds,
                won=won,
            )
        )


async def leaderboard(limit: int = 10) -> list[dict]:
    """بهترینِ هر کاربر (max score) — فقط برنده‌ها."""
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(
                        EscapeScore.user_id,
                        EscapeScore.chat_id,
                        sa_func.max(EscapeScore.score),
                        sa_func.sum(EscapeScore.solved_count),
                        sa_func.min(EscapeScore.elapsed_seconds),
                    )
                    .where(EscapeScore.won == True)  # noqa: E712
                    .group_by(EscapeScore.user_id, EscapeScore.chat_id)
                    .order_by(sa_func.max(EscapeScore.score).desc())
                    .limit(limit)
                )
            ).all()
        )
        return [
            {"user_id": r[0], "chat_id": r[1], "best": r[2], "solved": r[3] or 0, "fastest": r[4]}
            for r in rows
        ]


async def stats_summary() -> dict:
    async with session_scope() as session:
        fastest = (
            await session.execute(
                select(sa_func.min(EscapeScore.elapsed_seconds)).where(EscapeScore.won == True)  # noqa: E712
            )
        ).scalar()
        most_solved = (
            (await session.execute(select(sa_func.max(EscapeScore.solved_count)))).scalar()
        )
        top_score = (await session.execute(select(sa_func.max(EscapeScore.score)))).scalar()
        return {
            "fastest": fastest,
            "most_solved": most_solved or 0,
            "top_score": top_score or 0,
        }


# ---------------------------------------------------------------- daily --
async def daily_attempt_used(chat_id: int, user_id: int, date_str: str) -> bool:
    async with session_scope() as session:
        row = (
            await session.execute(
                select(EscapeDaily).where(
                    EscapeDaily.chat_id == chat_id,
                    EscapeDaily.user_id == user_id,
                    EscapeDaily.day == date_str,
                )
            )
        ).scalar_one_or_none()
        return bool(row and row.attempts >= 1)


async def register_daily_attempt(chat_id: int, user_id: int, date_str: str, reward_xp: int) -> None:
    async with session_scope() as session:
        row = (
            await session.execute(
                select(EscapeDaily).where(
                    EscapeDaily.chat_id == chat_id,
                    EscapeDaily.user_id == user_id,
                    EscapeDaily.day == date_str,
                )
            )
        ).scalar_one_or_none()
        if row:
            row.attempts += 1
        else:
            session.add(
                EscapeDaily(chat_id=chat_id, user_id=user_id, day=date_str, attempts=1, reward_xp=reward_xp)
            )
