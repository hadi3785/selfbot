"""
Repository برای حافظه‌ی هوش مصنوعی (AI Memory).
"""

from sqlalchemy import select, delete, func
from typing import List, Optional, Dict

from ..db.engine import session_scope
from ..db.models_ext import AIMemory


CATEGORIES = ["کاربران", "گفتگوها", "پروژه‌ها", "یادداشت‌ها", "تنظیمات"]

# انواعِ ساختاریافته‌ی «حافظه‌ی هوشمند» (با حافظه‌ی کلاسیک هم‌زیست دارند):
# 👤 Preference | 📌 Project | 📝 Task | 💡 Idea | 🔗 Link
SMART_CATEGORIES = ["Preference", "Project", "Task", "Idea", "Link"]
SMART_ICONS = {
    "Preference": "👤",
    "Project": "📌",
    "Task": "📝",
    "Idea": "💡",
    "Link": "🔗",
}
KB_CATEGORY = "دانش"  # Knowledge Base شخصی (.دانش)

ALL_CATEGORIES = CATEGORIES + SMART_CATEGORIES + [KB_CATEGORY]


async def save_memory(category: str, key: str, value: str) -> AIMemory:
    """ذخیره یا بروزرسانی یک حافظه."""
    if category not in ALL_CATEGORIES:
        raise ValueError(f"دسته‌بندی نامعتبر: {category}")

    async with session_scope() as session:
        stmt = select(AIMemory).where(AIMemory.category == category, AIMemory.key == key)
        result = await session.execute(stmt)
        memory = result.scalar_one_or_none()
        if memory:
            memory.value = value
            await session.commit()
            await session.refresh(memory)
            return memory
        memory = AIMemory(category=category, key=key, value=value)
        session.add(memory)
        await session.commit()
        await session.refresh(memory)
        return memory


async def get_memory(category: str, key: str) -> Optional[AIMemory]:
    """دریافت یک حافظه."""
    async with session_scope() as session:
        stmt = select(AIMemory).where(AIMemory.category == category, AIMemory.key == key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_memories_by_category(category: str) -> List[AIMemory]:
    """دریافت همه‌ی حافظه‌های یک دسته."""
    async with session_scope() as session:
        stmt = select(AIMemory).where(AIMemory.category == category).order_by(AIMemory.key)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def search_memories(query: str) -> Dict[str, List[AIMemory]]:
    """جستجو در حافظه‌ها (بر اساس کلید یا مقدار)."""
    escaped = query.replace("%", "\\%").replace("_", "\\_")
    async with session_scope() as session:
        stmt = select(AIMemory).where(
            (AIMemory.key.ilike(f"%{escaped}%")) |
            (AIMemory.value.ilike(f"%{escaped}%"))
        )
        result = await session.execute(stmt)
        items = list(result.scalars().all())
        # گروه‌بندی بر اساس دسته
        grouped = {}
        for item in items:
            grouped.setdefault(item.category, []).append(item)
        return grouped


async def delete_memory(category: str, key: str) -> bool:
    """حذف یک حافظه."""
    async with session_scope() as session:
        stmt = delete(AIMemory).where(AIMemory.category == category, AIMemory.key == key)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0


async def delete_category(category: str) -> int:
    """حذف همه‌ی حافظه‌های یک دسته."""
    async with session_scope() as session:
        stmt = delete(AIMemory).where(AIMemory.category == category)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount


async def get_stats() -> Dict[str, int]:
    """آمار حافظه‌ها به تفکیک دسته (کلاسیک + هوشمند)."""
    async with session_scope() as session:
        stats = {}
        for cat in ALL_CATEGORIES:
            stmt = select(func.count(AIMemory.id)).where(AIMemory.category == cat)
            count = await session.scalar(stmt) or 0
            stats[cat] = count
        return stats


# -------------------------------------------------- حافظه‌ی هوشمند (v2) ---
async def delete_by_id(memory_id: int) -> bool:
    """حذف با id (ساده‌تر از دسته+کلید برای کاربر)."""
    async with session_scope() as session:
        stmt = delete(AIMemory).where(AIMemory.id == memory_id)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0


async def get_recent(limit: int = 30) -> List[AIMemory]:
    """آخرین حافظه‌های ذخیره‌شده (هر دسته)."""
    async with session_scope() as session:
        stmt = select(AIMemory).order_by(AIMemory.updated_at.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def list_all_ids(category: Optional[str] = None, limit: int = 50) -> List[AIMemory]:
    """آیتم‌ها با id برای حذف/مرور."""
    async with session_scope() as session:
        stmt = select(AIMemory).order_by(AIMemory.category, AIMemory.updated_at.desc())
        if category:
            stmt = stmt.where(AIMemory.category == category)
        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


def _tokenize(text: str) -> set:
    """توکن‌های جستجو: کلماتِ ۲+ حرفی، کوچک‌شده."""
    import re as _re
    words = _re.findall(r"[\w\u0600-\u06FF]{2,}", (text or "").lower())
    return {w for w in words if w}


async def relevant_memories(query: str, limit: int = 12) -> List[AIMemory]:
    """
    خاطراتِ مرتبط برای تزریق به پرامپتِ مدل:
      • همه‌ی Preference ها (کوچک و پرارزش — همیشه قابلِ استفاده)
      + آیتم‌هایی که بیشترین تطبیقِ کلمه‌ای با query دارند (key/value/دسته)
    مرتب‌شده بر اساس امتیاز؛ خالی اگر هیچ‌چیز نیامده.
    """
    tokens = _tokenize(query)
    prefs: List[AIMemory] = []
    scored: List[tuple] = []

    async with session_scope() as session:
        stmt = select(AIMemory)
        result = await session.execute(stmt)
        items = list(result.scalars().all())

    for m in items:
        hay = " ".join(filter(None, [m.category, m.key, m.value])).lower()
        if m.category in SMART_CATEGORIES:
            hay += " " + m.category.lower()
        score = 0
        for t in tokens:
            if t in m.key.lower():
                score += 3
            if t in m.value.lower():
                score += 2
            if t in hay:
                score += 1
        if m.category == "Preference":
            prefs.append(m)
        elif score > 0:
            scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    out = prefs + [m for _, m in scored]
    return out[:limit]
