"""
Repository لایه‌ی هشدارِ قیمت (`.هشدارقیمت`).
"""

from typing import List

from sqlalchemy import select

from ..db.engine import session_scope
from ..db.models_ext import PriceAlert


async def add_alert(
    chat_id: int, item_key: str, item_label: str, direction: str, target_price: float
) -> PriceAlert:
    """افزودنِ یه هشدارِ قیمتِ جدید."""
    async with session_scope() as session:
        obj = PriceAlert(
            chat_id=chat_id,
            item_key=item_key,
            item_label=item_label,
            direction=direction,
            target_price=target_price,
        )
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj


async def remove_alert(chat_id: int, alert_id: int) -> bool:
    """حذفِ یه هشدار با آیدیش (فقط اگه متعلق به همون چت باشه)."""
    async with session_scope() as session:
        obj = await session.get(PriceAlert, alert_id)
        if obj is None or obj.chat_id != chat_id:
            return False
        await session.delete(obj)
        return True


async def list_alerts(chat_id: int) -> List[PriceAlert]:
    """لیستِ همه‌ی هشدارهای فعالِ (تریگرنشده‌یِ) یه چت."""
    async with session_scope() as session:
        stmt = select(PriceAlert).where(
            PriceAlert.chat_id == chat_id, PriceAlert.triggered == False  # noqa: E712
        ).order_by(PriceAlert.created_at.asc())
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def clear_alerts(chat_id: int) -> int:
    """پاک‌کردنِ همه‌ی هشدارهای (فعال) یه چت. تعدادِ حذف‌شده رو برمی‌گردونه."""
    async with session_scope() as session:
        stmt = select(PriceAlert).where(PriceAlert.chat_id == chat_id)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        for row in rows:
            await session.delete(row)
        return len(rows)


async def list_all_untriggered() -> List[PriceAlert]:
    """همه‌ی هشدارهای هنوز-تریگرنشده‌ی همه‌ی چت‌ها - برای چکِ دوره‌ایِ ورکر."""
    async with session_scope() as session:
        stmt = select(PriceAlert).where(PriceAlert.triggered == False)  # noqa: E712
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def mark_triggered(alert_id: int) -> None:
    async with session_scope() as session:
        obj = await session.get(PriceAlert, alert_id)
        if obj is not None:
            obj.triggered = True
            await session.flush()
