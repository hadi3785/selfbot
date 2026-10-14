"""
📚 Knowledge Base شخصی: `.دانش` — با category="دانش" روی همان AIMemory.

یک پرونده‌ی دانش (متن/فایل/نکته) با «کلید» و «متنِ بلند» ذخیره می‌شود و در
Context Engine (build_context) و ابزارِ search_knowledge در دسترسِ AI است.
"""
import re

KB_CATEGORY = "دانش"


def _split_chunks(text: str, size: int = 3500) -> list[str]:
    """متنِ بلند را به پاراگراف‌های زیرِ size می‌شکند (برای جای‌دادن در value)."""
    text = text.strip()
    if len(text) <= size:
        return [text]
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if len(cur) + len(para) + 2 <= size:
            cur = f"{cur}\n{para}".strip()
        else:
            if cur:
                chunks.append(cur)
            while len(para) > size:
                chunks.append(para[:size])
                para = para[size:]
            cur = para
    if cur:
        chunks.append(cur)
    return chunks


async def kb_add(title: str, body: str) -> int:
    """افزودنِ پرونده‌ی دانش؛ متنِ بلند چندتکه ذخیره می‌شود. خروجی: تعدادِ قطعه."""
    from .repositories.ai_memory_repo import save_memory

    title = title.strip()[:120]
    chunks = _split_chunks(body)
    n = len(chunks)
    for i, ch in enumerate(chunks, 1):
        key = title if n == 1 else f"{title} — بخش {i}/{n}"
        await save_memory(KB_CATEGORY, key, ch)
    return n


async def kb_search(query: str, limit: int = 6) -> list[dict]:
    """جستجوی وردی در دانش؛ امتیازدهیِ ساده (تعدادِ توکنِ منطبق)."""
    from .repositories.ai_memory_repo import get_memories_by_category

    items = await get_memories_by_category(KB_CATEGORY)
    q_tokens = [w for w in re.split(r"\s+", query.lower()) if len(w) > 2]
    scored = []
    for it in items:
        hay = f"{it.key} {it.value}".lower()
        score = sum(hay.count(w) for w in q_tokens)
        if score:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return [
        {"key": it.key, "value": it.value[:400]} for _, it in scored[:limit]
    ]


async def kb_list(limit: int = 30) -> list[str]:
    from .repositories.ai_memory_repo import get_memories_by_category

    items = await get_memories_by_category(KB_CATEGORY)
    return [it.key for it in items[:limit]]


async def kb_delete(title: str) -> int:
    """حذفِ همه‌ی قطعاتِ یک عنوان (پیشوندی). خروجی: تعدادِ حذف‌شده."""
    from .repositories.ai_memory_repo import delete_memory, get_memories_by_category

    items = await get_memories_by_category(KB_CATEGORY)
    title = title.strip().lower()
    deleted = 0
    for it in items:
        if it.key.lower().startswith(title):
            if await delete_memory(KB_CATEGORY, it.key):
                deleted += 1
    return deleted
