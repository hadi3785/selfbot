"""Repository لایه‌ی یادآوری/ارسالِ تکرارشونده (`.یادآوری تکراری` / `.تکرار`)."""
import datetime as dt

from sqlalchemy import select

from ..db.engine import session_scope
from ..db.models import RecurringJob


def _detached_copy(obj: RecurringJob) -> RecurringJob:
    return RecurringJob(
        id=obj.id,
        chat_id=obj.chat_id,
        text=obj.text,
        kind=obj.kind,
        interval_seconds=obj.interval_seconds,
        daily_hour=obj.daily_hour,
        daily_minute=obj.daily_minute,
        next_run_at=obj.next_run_at,
        active=obj.active,
        created_at=obj.created_at,
    )


async def create(
    chat_id: int,
    text: str,
    kind: str,
    next_run_at: dt.datetime,
    *,
    interval_seconds: int | None = None,
    daily_hour: int | None = None,
    daily_minute: int | None = None,
) -> RecurringJob:
    async with session_scope() as session:
        obj = RecurringJob(
            chat_id=chat_id,
            text=text,
            kind=kind,
            next_run_at=next_run_at,
            interval_seconds=interval_seconds,
            daily_hour=daily_hour,
            daily_minute=daily_minute,
        )
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return _detached_copy(obj)


async def list_due(now: dt.datetime) -> list[RecurringJob]:
    async with session_scope() as session:
        rows = (
            (
                await session.execute(
                    select(RecurringJob).where(
                        RecurringJob.active == True,  # noqa: E712
                        RecurringJob.next_run_at <= now,
                    )
                )
            )
            .scalars()
            .all()
        )
        return [_detached_copy(r) for r in rows]


async def list_all(chat_id: int | None = None) -> list[RecurringJob]:
    async with session_scope() as session:
        stmt = select(RecurringJob).order_by(RecurringJob.next_run_at.asc())
        if chat_id is not None:
            stmt = stmt.where(RecurringJob.chat_id == chat_id)
        rows = (await session.execute(stmt)).scalars().all()
        return [_detached_copy(r) for r in rows]


async def get(job_id: int) -> RecurringJob | None:
    async with session_scope() as session:
        obj = await session.get(RecurringJob, job_id)
        return _detached_copy(obj) if obj else None


async def reschedule(job_id: int, next_run_at: dt.datetime) -> None:
    """فقط وقتیِ اجرای بعدی رو جلو ببره (بعد از هر اجرای موفق)."""
    async with session_scope() as session:
        obj = await session.get(RecurringJob, job_id)
        if obj is not None:
            obj.next_run_at = next_run_at


async def set_active(job_id: int, active: bool) -> bool:
    async with session_scope() as session:
        obj = await session.get(RecurringJob, job_id)
        if obj is None:
            return False
        obj.active = active
        return True


async def delete(job_id: int) -> bool:
    async with session_scope() as session:
        obj = await session.get(RecurringJob, job_id)
        if obj is None:
            return False
        await session.delete(obj)
        return True
