"""Repository کارهای «کپی کانال» (`.کپی‌کانال`)."""
import datetime as dt

from sqlalchemy import delete, select, update

from ..db.engine import session_scope
from ..db.models_ext import ChannelCopyJob


def _to_dict(r: ChannelCopyJob) -> dict:
    return {
        "id": r.id,
        "source_id": r.source_id,
        "source_title": r.source_title,
        "source_ref": r.source_ref,
        "dest_id": r.dest_id,
        "dest_title": r.dest_title,
        "dest_ref": r.dest_ref,
        "last_id": r.last_id,
        "copied": r.copied,
        "skipped": r.skipped,
        "total_hint": r.total_hint,
        "status": r.status,
        "drop_author": r.drop_author,
        "window_start": r.window_start,
        "window_count": r.window_count,
        "last_error": r.last_error,
    }


async def create_job(
    *,
    source_id: int,
    source_title: str,
    source_ref: str,
    dest_id: int,
    dest_title: str,
    dest_ref: str,
    last_id: int = 0,
    total_hint: int = 0,
    drop_author: bool = True,
) -> dict:
    async with session_scope() as session:
        obj = ChannelCopyJob(
            source_id=source_id,
            source_title=source_title,
            source_ref=source_ref,
            dest_id=dest_id,
            dest_title=dest_title,
            dest_ref=dest_ref,
            last_id=last_id,
            total_hint=total_hint,
            drop_author=drop_author,
            status="running",
        )
        session.add(obj)
        await session.flush()
        return _to_dict(obj)


async def get_job(job_id: int) -> dict | None:
    async with session_scope() as session:
        r = await session.get(ChannelCopyJob, job_id)
        return _to_dict(r) if r else None


async def get_latest_job() -> dict | None:
    async with session_scope() as session:
        r = (
            await session.execute(select(ChannelCopyJob).order_by(ChannelCopyJob.id.desc()).limit(1))
        ).scalar_one_or_none()
        return _to_dict(r) if r else None


async def list_jobs(limit: int = 10) -> list[dict]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(ChannelCopyJob).order_by(ChannelCopyJob.id.desc()).limit(limit)
            )
        ).scalars().all()
        return [_to_dict(r) for r in rows]


async def update_progress(
    job_id: int,
    *,
    last_id: int,
    copied: int,
    skipped: int,
    window_start: dt.datetime | None,
    window_count: int,
) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ChannelCopyJob)
            .where(ChannelCopyJob.id == job_id)
            .values(
                last_id=last_id,
                copied=copied,
                skipped=skipped,
                window_start=window_start,
                window_count=window_count,
            )
        )


async def set_status(job_id: int, status: str, error: str = "") -> None:
    async with session_scope() as session:
        await session.execute(
            update(ChannelCopyJob)
            .where(ChannelCopyJob.id == job_id)
            .values(status=status, last_error=error[:1000])
        )


async def set_total_hint(job_id: int, total: int) -> None:
    async with session_scope() as session:
        await session.execute(
            update(ChannelCopyJob).where(ChannelCopyJob.id == job_id).values(total_hint=total)
        )


async def mark_running_as_paused() -> int:
    """بعد از ری‌استارتِ پروسه: کارهای «running» دیگه تسکِ زنده ندارن؛ به paused می‌رن."""
    async with session_scope() as session:
        res = await session.execute(
            update(ChannelCopyJob)
            .where(ChannelCopyJob.status == "running")
            .values(status="paused", last_error="پروسه ری‌استارت شد؛ با «ادامه» دنبال کن")
        )
        return res.rowcount or 0


async def delete_job(job_id: int) -> bool:
    async with session_scope() as session:
        res = await session.execute(delete(ChannelCopyJob).where(ChannelCopyJob.id == job_id))
        return bool(res.rowcount)
