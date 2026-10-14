"""Repository لایه‌ی ردیابِ ویرایش/حذفِ پیام (فقط لیستِ کانال‌های مقصد؛ خودِ
کشِ پیام‌ها درون‌حافظه‌ست و اینجا ذخیره نمی‌شه - نگاه کن به
bot/handlers/message_tracker.py)."""
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db.engine import session_scope
from ..db.models_ext import MessageTrackerChannel


async def list_channels() -> dict:
    """chat_id (رشته) -> title"""
    async with session_scope() as session:
        rows = (await session.execute(select(MessageTrackerChannel))).scalars().all()
        return {str(row.chat_id): row.title for row in rows}


async def upsert_channel(chat_id: int, title: str) -> None:
    async with session_scope() as session:
        stmt = pg_insert(MessageTrackerChannel).values(chat_id=chat_id, title=title)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MessageTrackerChannel.chat_id], set_={"title": title}
        )
        await session.execute(stmt)


async def remove_channel(chat_id: int) -> None:
    async with session_scope() as session:
        await session.execute(
            delete(MessageTrackerChannel).where(MessageTrackerChannel.chat_id == chat_id)
        )


async def clear_channels() -> None:
    async with session_scope() as session:
        await session.execute(delete(MessageTrackerChannel))
