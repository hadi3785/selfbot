"""Repository کارهای شخصی (Task Manager)."""
import datetime as dt

from sqlalchemy import select

from ..db.engine import session_scope
from ..db.models_ext import TaskItem


async def add_task(text: str, due_at: dt.datetime | None = None, priority: int = 0) -> dict:
    async with session_scope() as session:
        obj = TaskItem(text=text, due_at=due_at, priority=priority)
        session.add(obj)
        await session.flush()
        return {"id": obj.id, "text": obj.text, "due_at": due_at, "priority": priority, "done": False}


async def list_tasks(done: bool = False, limit: int = 50) -> list[dict]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(TaskItem)
                .where(TaskItem.done == done)
                .order_by(TaskItem.due_at.is_(None), TaskItem.due_at, TaskItem.id.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {"id": r.id, "text": r.text, "due_at": r.due_at, "priority": r.priority, "done": r.done}
            for r in rows
        ]


async def get_task(task_id: int) -> dict | None:
    async with session_scope() as session:
        r = (await session.execute(select(TaskItem).where(TaskItem.id == task_id))).scalar_one_or_none()
        if not r:
            return None
        return {"id": r.id, "text": r.text, "due_at": r.due_at, "priority": r.priority, "done": r.done}


async def set_done(task_id: int, done: bool = True) -> bool:
    async with session_scope() as session:
        r = (await session.execute(select(TaskItem).where(TaskItem.id == task_id))).scalar_one_or_none()
        if not r:
            return False
        r.done = done
        await session.flush()
        return True


async def delete_task(task_id: int) -> bool:
    async with session_scope() as session:
        r = (await session.execute(select(TaskItem).where(TaskItem.id == task_id))).scalar_one_or_none()
        if not r:
            return False
        await session.delete(r)
        return True


async def overdue_count(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(TaskItem).where(TaskItem.done == False, TaskItem.due_at.is_not(None))  # noqa: E712
            )
        ).scalars().all()
        return sum(1 for r in rows if r.due_at and r.due_at < now)
