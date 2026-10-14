"""
Repository لایه‌ی گزارش فعالیت روزانه گروه.
"""

from sqlalchemy import select, func
from typing import Optional, List
import datetime as dt

from ..db.engine import session_scope
from ..db.models_ext import GroupActivityLog


async def _get_or_create_log(session, chat_id: int, date: Optional[str] = None) -> GroupActivityLog:
    """دریافت یا ایجاد لاگ برای یک روز خاص (با سشنِ خودِ caller - بدونِ باز کردنِ سشنِ جدید)."""
    if date is None:
        date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    stmt = select(GroupActivityLog).where(
        GroupActivityLog.chat_id == chat_id,
        GroupActivityLog.log_date == date
    )
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is None:
        obj = GroupActivityLog(chat_id=chat_id, log_date=date)
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
    return obj


async def increment_messages(chat_id: int, count: int = 1, date: Optional[str] = None) -> None:
    """افزایش شمارش پیام‌های ارسال شده."""
    async with session_scope() as session:
        obj = await _get_or_create_log(session, chat_id, date)
        obj.messages_sent += count
        await session.flush()


async def increment_warnings(chat_id: int, count: int = 1) -> None:
    """افزایش شمارش هشدارها."""
    async with session_scope() as session:
        obj = await _get_or_create_log(session, chat_id)
        obj.warnings_given += count
        await session.flush()


async def increment_deleted(chat_id: int, count: int = 1) -> None:
    """افزایش شمارش پیام‌های حذف شده."""
    async with session_scope() as session:
        obj = await _get_or_create_log(session, chat_id)
        obj.messages_deleted += count
        await session.flush()


async def increment_joined(chat_id: int, count: int = 1) -> None:
    """افزایش شمارش اعضای جدید."""
    async with session_scope() as session:
        obj = await _get_or_create_log(session, chat_id)
        obj.members_joined += count
        await session.flush()


async def increment_left(chat_id: int, count: int = 1) -> None:
    """افزایش شمارش اعضای خارج شده."""
    async with session_scope() as session:
        obj = await _get_or_create_log(session, chat_id)
        obj.members_left += count
        await session.flush()


async def get_logs(chat_id: int, days: int = 7) -> List[GroupActivityLog]:
    """دریافت لاگ‌های چند روز اخیر."""
    async with session_scope() as session:
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
        stmt = select(GroupActivityLog).where(
            GroupActivityLog.chat_id == chat_id,
            GroupActivityLog.log_date >= cutoff
        ).order_by(GroupActivityLog.log_date.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def get_summary(chat_id: int, days: int = 7) -> dict:
    """دریافت خلاصه آماری چند روز اخیر."""
    logs = await get_logs(chat_id, days)
    summary = {
        "total_messages": 0,
        "total_warnings": 0,
        "total_deleted": 0,
        "total_joined": 0,
        "total_left": 0,
        "days": len(logs)
    }
    for log in logs:
        summary["total_messages"] += log.messages_sent
        summary["total_warnings"] += log.warnings_given
        summary["total_deleted"] += log.messages_deleted
        summary["total_joined"] += log.members_joined
        summary["total_left"] += log.members_left
    return summary