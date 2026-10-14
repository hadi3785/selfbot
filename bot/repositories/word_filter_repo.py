"""
Repository لایه‌ی فیلترِ کلماتِ ممنوعه‌ی سفارشیِ گروه (word filter).
"""

import re
from typing import List, Optional

from sqlalchemy import select, delete

from ..db.engine import session_scope
from ..db.models_ext import GroupWordFilter


async def add_word_filter(
    chat_id: int,
    word: str,
    action: str = "delete",
    case_sensitive: bool = False,
    is_regex: bool = False,
) -> GroupWordFilter:
    """افزودنِ یک کلمه/الگو به فیلترِ کلماتِ گروه. اگه قبلاً وجود داشته باشه، ValueError می‌ده."""
    async with session_scope() as session:
        stmt = select(GroupWordFilter).where(
            GroupWordFilter.chat_id == chat_id,
            GroupWordFilter.word == word,
        )
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise ValueError(f"کلمه‌ی «{word}» از قبل توی لیست هست.")

        obj = GroupWordFilter(
            chat_id=chat_id,
            word=word,
            action=action,
            case_sensitive=case_sensitive,
            is_regex=is_regex,
        )
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj


async def remove_word_filter(chat_id: int, word: str) -> bool:
    """حذفِ یک کلمه از فیلترِ کلماتِ گروه."""
    async with session_scope() as session:
        stmt = select(GroupWordFilter).where(
            GroupWordFilter.chat_id == chat_id,
            GroupWordFilter.word == word,
        )
        result = await session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            return False
        await session.delete(obj)
        return True


async def get_word_filters(chat_id: int) -> List[GroupWordFilter]:
    """لیستِ همه‌ی کلماتِ ممنوعه‌ی یه گروه."""
    async with session_scope() as session:
        stmt = select(GroupWordFilter).where(
            GroupWordFilter.chat_id == chat_id
        ).order_by(GroupWordFilter.created_at.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def clear_word_filters(chat_id: int) -> int:
    """پاک‌کردنِ همه‌ی کلماتِ ممنوعه‌ی یه گروه. تعدادِ ردیف‌های حذف‌شده رو برمی‌گردونه."""
    async with session_scope() as session:
        stmt = select(GroupWordFilter).where(GroupWordFilter.chat_id == chat_id)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        count = len(rows)
        if count:
            await session.execute(
                delete(GroupWordFilter).where(GroupWordFilter.chat_id == chat_id)
            )
        return count


def _matches(filt: GroupWordFilter, text: str) -> bool:
    if filt.is_regex:
        try:
            flags = 0 if filt.case_sensitive else re.IGNORECASE
            return re.search(filt.word, text, flags) is not None
        except re.error:
            return False
    if filt.case_sensitive:
        return filt.word in text
    return filt.word.lower() in text.lower()


async def search_word_in_filters(chat_id: int, text: str) -> List[GroupWordFilter]:
    """پیداکردنِ همه‌ی فیلترهایی که با متنِ داده‌شده مطابقت دارن."""
    filters = await get_word_filters(chat_id)
    if not text:
        return []
    return [f for f in filters if _matches(f, text)]


async def list_all() -> List[GroupWordFilter]:
    """همه‌ی فیلترهای کلمه‌ی همه‌ی چت‌ها با هم - فقط برای بکاپِ کاملِ تنظیمات."""
    async with session_scope() as session:
        result = await session.execute(select(GroupWordFilter))
        return list(result.scalars().all())
