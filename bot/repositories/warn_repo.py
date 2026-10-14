"""
Repository لایه‌ی سیستم هشدار تدریجی (warn).
"""

from sqlalchemy import select, delete, func
from typing import Optional, List
import datetime as dt

from ..db.engine import session_scope
from ..db.models_ext import GroupUserWarning, GroupWarnSettings


async def _get_or_create_warning(session, chat_id: int, user_id: int) -> GroupUserWarning:
    """دریافت یا ایجاد رکورد هشدار برای کاربر در گروه (با سشنِ خودِ caller - بدونِ باز کردنِ سشنِ جدید)."""
    stmt = select(GroupUserWarning).where(
        GroupUserWarning.chat_id == chat_id,
        GroupUserWarning.user_id == user_id
    )
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj is None:
        obj = GroupUserWarning(chat_id=chat_id, user_id=user_id)
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
    return obj


async def add_warn(chat_id: int, user_id: int) -> GroupUserWarning:
    """افزودن یک هشدار به کاربر."""
    async with session_scope() as session:
        obj = await _get_or_create_warning(session, chat_id, user_id)
        obj.warn_count += 1
        obj.last_warn_time = dt.datetime.now(dt.timezone.utc)
        await session.flush()
        await session.refresh(obj)
        return obj


async def remove_warn(chat_id: int, user_id: int) -> bool:
    """کاهش یک هشدار از کاربر (اگر >0 باشد)."""
    async with session_scope() as session:
        stmt = select(GroupUserWarning).where(
            GroupUserWarning.chat_id == chat_id,
            GroupUserWarning.user_id == user_id
        )
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj and obj.warn_count > 0:
            obj.warn_count -= 1
            await session.flush()
            return True
        return False


async def clear_warnings(chat_id: int, user_id: int) -> bool:
    """پاک کردن همه هشدارهای کاربر."""
    async with session_scope() as session:
        stmt = select(GroupUserWarning).where(
            GroupUserWarning.chat_id == chat_id,
            GroupUserWarning.user_id == user_id
        )
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj:
            obj.warn_count = 0
            obj.muted_until = None
            obj.kicked = False
            obj.banned = False
            await session.flush()
            return True
        return False


async def get_user_warnings(chat_id: int, user_id: int) -> Optional[GroupUserWarning]:
    """دریافت وضعیت هشدارهای یک کاربر."""
    async with session_scope() as session:
        stmt = select(GroupUserWarning).where(
            GroupUserWarning.chat_id == chat_id,
            GroupUserWarning.user_id == user_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def list_warnings(chat_id: int) -> List[GroupUserWarning]:
    """لیست همه هشدارهای یک گروه."""
    async with session_scope() as session:
        stmt = select(GroupUserWarning).where(
            GroupUserWarning.chat_id == chat_id
        ).order_by(GroupUserWarning.warn_count.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def _get_or_create_settings(session, chat_id: int) -> GroupWarnSettings:
    """دریافت یا ایجادِ تنظیماتِ هشدارِ گروه (با سشنِ خودِ caller)."""
    obj = await session.get(GroupWarnSettings, chat_id)
    if obj is None:
        obj = GroupWarnSettings(chat_id=chat_id)
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
    return obj


async def get_warn_settings(chat_id: int) -> GroupWarnSettings:
    """دریافت تنظیمات هشدار گروه (ایجاد در صورت نبود)."""
    async with session_scope() as session:
        return await _get_or_create_settings(session, chat_id)


async def update_warn_settings(
    chat_id: int,
    enabled: Optional[bool] = None,
    warn_limit: Optional[int] = None,
    action_on_limit: Optional[str] = None,
    mute_duration_minutes: Optional[int] = None,
    auto_reset_days: Optional[int] = None,
) -> GroupWarnSettings:
    """به‌روزرسانی تنظیمات هشدار گروه."""
    async with session_scope() as session:
        obj = await _get_or_create_settings(session, chat_id)
        if enabled is not None:
            obj.enabled = enabled
        if warn_limit is not None:
            obj.warn_limit = warn_limit
        if action_on_limit is not None:
            obj.action_on_limit = action_on_limit
        if mute_duration_minutes is not None:
            obj.mute_duration_minutes = mute_duration_minutes
        if auto_reset_days is not None:
            obj.auto_reset_days = auto_reset_days
        await session.flush()
        await session.refresh(obj)
        return obj


async def list_all_settings() -> List[GroupWarnSettings]:
    """تنظیماتِ اخطارِ همه‌ی چت‌ها با هم - فقط برای بکاپِ کاملِ تنظیمات (نه شمارشِ زنده‌ی کاربرها)."""
    async with session_scope() as session:
        result = await session.execute(select(GroupWarnSettings))
        return list(result.scalars().all())