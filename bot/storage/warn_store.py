"""
ذخیره‌سازی سیستم هشدار تدریجی - از طریق Repository Layer.
"""

from ..repositories import warn_repo
from ..db.models_ext import GroupUserWarning, GroupWarnSettings
from typing import Optional, List


async def add_warn(chat_id: int, user_id: int) -> GroupUserWarning:
    return await warn_repo.add_warn(chat_id, user_id)


async def remove_warn(chat_id: int, user_id: int) -> bool:
    return await warn_repo.remove_warn(chat_id, user_id)


async def clear_warnings(chat_id: int, user_id: int) -> bool:
    return await warn_repo.clear_warnings(chat_id, user_id)


async def get_user_warnings(chat_id: int, user_id: int) -> Optional[GroupUserWarning]:
    return await warn_repo.get_user_warnings(chat_id, user_id)


async def list_warnings(chat_id: int) -> List[GroupUserWarning]:
    return await warn_repo.list_warnings(chat_id)


async def get_warn_settings(chat_id: int) -> GroupWarnSettings:
    return await warn_repo.get_warn_settings(chat_id)


async def update_warn_settings(
    chat_id: int,
    enabled: Optional[bool] = None,
    warn_limit: Optional[int] = None,
    action_on_limit: Optional[str] = None,
    mute_duration_minutes: Optional[int] = None,
    auto_reset_days: Optional[int] = None,
) -> GroupWarnSettings:
    return await warn_repo.update_warn_settings(
        chat_id, enabled, warn_limit, action_on_limit,
        mute_duration_minutes, auto_reset_days
    )