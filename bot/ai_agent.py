"""
🧠 AI CORE — Context Engine + Router + Intent + Tool Calling (Agent).

لایه‌های این ماژول (طبق معماری «AI CORE»):
  1. detect_intent(text)       → QUESTION/REMINDER/TASK/... (قاعده‌مند، بدونِ AI)
  2. build_context(...)        → Context Engine: memory مرتبط + کارها/یادآوری‌ها + یادداشت‌ها
  3. route_model(intent/len)   → Router: انتخابِ مدل از env (FAST/CODING/REASONING/پیش‌فرض)
  4. TOOLS + run_agent(...)    → Agent Mode: حلقه‌ی tool-calling با سقفِ گام

همه‌ی این‌ها خالص‌اند (بدون Telethon) و در خطای AI، fallback دارند.
"""
from __future__ import annotations

import aiohttp
import json
import logging
import re
from typing import Any, Awaitable, Callable

from . import ai
from .repositories import ai_memory_repo, tasks_repo

logger = logging.getLogger("selfbot.ai_agent")


# ============================================================ 1) Intent
_INTENT_RULES: list[tuple[str, re.Pattern]] = [
    ("REMINDER", re.compile(r"(یادم\s?بنداز|یادآوری|یادت نره|بهم یادآوری کن)", re.I)),
    ("TASK", re.compile(r"(کار\s?جدید|به کارها اضافه|یادداشت کار|تسک)", re.I)),
    ("SEARCH", re.compile(r"(دنبال|پیدا کن|جستجو|کجا بود|کدام پیام)", re.I)),
    ("SUMMARY", re.compile(r"(خلاصه|جمع‌بندی)", re.I)),
    ("TRANSLATION", re.compile(r"(ترجمه|به انگلیسی|به فارسی|translate)", re.I)),
    ("CODING", re.compile(r"(کد|باگ|ارور|خطا|دبیگ|پیاده‌سازی|فانکشن|پایتون|بگ)", re.I)),
]


def detect_intent(text: str) -> str:
    """تشخیصِ قاعده‌مندِ نیت؛ CASUAL_CHAT به‌عنوان پیش‌فرض."""
    t = text or ""
    for intent, rx in _INTENT_RULES:
        if rx.search(t):
            return intent
    if t.strip().endswith(("؟", "?")):
        return "QUESTION"
    return "CASUAL_CHAT"


# ============================================================ 2) Context Engine
async def build_context(
    query: str,
    *,
    chat_id: int | None = None,
    recent_messages: list[dict] | None = None,
    max_chars: int = 1800,
) -> str:
    """زمینه‌ی کامل برای مدل: حافظه‌ی مرتبط + کارها/یادآوری‌های باز + یادداشت‌های مرتبط."""
    parts: list[str] = []

    mem = await ai.build_memory_context(query, max_chars=700)
    if mem:
        parts.append("🧠 خاطراتِ مرتبط:\n" + mem)

    try:
        opens = await tasks_repo.list_tasks(done=False, limit=8)
        if opens:
            lines = []
            for t in opens:
                due = ""
                if t.get("due_at"):
                    due = f" (ددلاین: {t['due_at']:%m-%d %H:%M})"
                mark = "❗" if t.get("priority") else "▫️"
                lines.append(f"{mark} #{t['id']} {t['text'][:60]}{due}")
            parts.append("📝 کارهای باز:\n" + "\n".join(lines))
    except Exception:
        pass

    try:
        from .knowledge_base import kb_search as _kb_search

        kb_hits = await _kb_search(query or "")
        if kb_hits:
            parts.append("📚 دانشِ شخصی:\n" + "\n".join(
                f"• {h['key']}: {h['value'][:150]}" for h in kb_hits[:3]
            ))
    except Exception:
        pass

    try:
        from .storage.notes_store import load_notes

        notes = await load_notes()
        if notes and query:
            q = query.lower()
            hits = [
                f"• {k}: {v[:120]}" for k, v in list(notes.items())[:30]
                if any(w and w in (k + " " + v).lower() for w in q.split() if len(w) > 2)
            ]
            if hits:
                parts.append("📒 یادداشت‌های مرتبط:\n" + "\n".join(hits[:4]))
    except Exception:
        pass

    if recent_messages:
        rl = []
        for m in recent_messages[-6:]:
            role = "من" if m.get("out") else "طرف"
            txt = (m.get("text") or "")[:140]
            if txt:
                rl.append(f"- {role}: {txt}")
        if rl:
            parts.append("💬 گفتگوی اخیر:\n" + "\n".join(rl))

    out = "\n\n".join(parts)
    if len(out) <= max_chars:
        return out

    # 💬 فشرده‌سازی با AI (Conversation Summarizer) — بدونِ AI: برشِ هوشمند
    try:
        summary = await ai.ask_ai(
            [
                {
                    "role": "system",
                    "content": (
                        "زمینه‌های پراکنده‌ی دستیار را می‌بینی. به فارسی، حداکثر ۸ خط، "
                        "فقطِ اطلاعاتِ مهم و مرتبط با سوالِ کاربر را فشرده کن "
                        "(تصمیم‌ها، کارهای باز، حقایقِ کلیدی). بدونِ مقدمه."
                    ),
                },
                {"role": "user", "content": f"سوالِ کاربر: {query}\n\nزمینه:\n{out[:5000]}"},
            ],
            max_tokens=250,
        )
        if summary and len(summary.strip()) > 20:
            return summary.strip()[:max_chars]
    except Exception:
        pass
    return out[:max_chars]


# ============================================================ 3) Personality
_PERSONALITY_KEY = "ai_personality"

PERSONALITY_PRESETS = {
    "پیش‌فرض": "کوتاه، دقیق و کاربردی جواب بده؛ فارسیِ روان؛ بدونِ مقدمه‌چینی.",
    "حرفه‌ای": "لحنِ رسمی و حرفه‌ای؛ ساختارمند؛ نتیجه‌محور؛ بدونِ شوخی.",
    "دوستانه": "دوستانه و صمیمی جواب بده؛ انگار یه رفقیه؛ ولی دقیق.",
    "کوتاه": "حداکثر ۲-۳ جمله؛ بدونِ توضیحِ اضافه؛ مستقیمِ سرِ اصل مطلب.",
    "برنامه‌نویس": "دستیارِ برنامه‌نویسی باش: کوتاه، فنی و دقیق؛ کد را بلوک‌بده؛ فرض‌ها را ذکر کن.",
    "طنز": "با کمی شوخی و طنزِ ملایم جواب بده؛ ولی جوابِ درست را نده زیرِ شوخی.",
}


async def get_personality() -> str:
    """متنِ شخصیتِ فعال (پیش‌فرض یا سفارشیِ کاربر)."""
    from .repositories.settings_repo import get_setting

    val = await get_setting(_PERSONALITY_KEY)
    if not val:
        return PERSONALITY_PRESETS["پیش‌فرض"]
    return val


async def set_personality(value: str) -> None:
    from .repositories.settings_repo import set_setting

    await set_setting(_PERSONALITY_KEY, value[:500])


def personality_system_block(pers: str) -> str:
    return f"🎤 سبکِ پاسخ: {pers}"


# ============================================================ 3) Router
def route_model(intent: str, text_len: int = 0) -> str | None:
    """انتخابِ مدل بر اساسِ نیت/حجم — از env؛ اگر ست نباشد همان AI_MODEL (None=پیش‌فرض)."""
    from .config import (
        AI_MODEL_CODING,
        AI_MODEL_FAST,
        AI_MODEL_REASONING,
    )

    if intent in ("CODING",) and AI_MODEL_CODING:
        return AI_MODEL_CODING
    if intent in ("SUMMARY", "TRANSLATION", "CASUAL_CHAT") and text_len < 400 and AI_MODEL_FAST:
        return AI_MODEL_FAST
    if intent in ("QUESTION",) and text_len > 1200 and AI_MODEL_REASONING:
        return AI_MODEL_REASONING
    return None  # AI_MODEL پیش‌فرض


async def ask_ai_routed(messages: list[dict], *, intent: str = "CASUAL_CHAT", **kw):
    """ask_ai با انتخابِ مدلِ مناسب."""
    user_text = next((m.get("content") for m in reversed(messages) if m.get("role") == "user"), "")
    model = route_model(intent, len(user_text or ""))
    kw = dict(kw)
    if model:
        kw["model"] = model
    return await ai.ask_ai(messages, **kw)


# ============================================================ 4) Tool Calling
# هر ابزار: (نام، توضیحِ کوتاه برای مدل، coroutine(args_json) -> str)
async def _tool_create_task(args: dict) -> str:
    from . import assistant_brain

    text = str(args.get("text") or "").strip()
    if not text:
        return "خطا: text لازم است"
    due = assistant_brain.parse_natural_time(text)
    t = await tasks_repo.add_task(text, due_at=due, priority=1 if "!" in text else 0)
    return f"کارِ #{t['id']} ثبت شد: {text[:60]}"


async def _tool_search_memory(args: dict) -> str:
    q = str(args.get("query") or "").strip()
    if not q:
        return "خطا: query لازم است"
    hits = await ai_memory_repo.search_memories(q)
    out = []
    for cat, items in list(hits.items())[:3]:
        for it in items[:2]:
            out.append(f"[{cat}] {it.key}: {it.value[:120]}")
    return "\n".join(out) or "چیزی در حافظه پیدا نشد"


async def _tool_list_tasks(args: dict) -> str:
    opens = await tasks_repo.list_tasks(done=False, limit=10)
    if not opens:
        return "کارِ بازی نیست"
    return "\n".join(f"#{t['id']} {t['text'][:60]}" for t in opens)


async def _tool_search_knowledge(args: dict) -> str:
    q = str(args.get("query") or "").strip()
    if not q:
        return "خطا: query لازم است"
    from .knowledge_base import kb_search

    hits = await kb_search(q)
    if not hits:
        return "در دانشِ شخصی چیزی نبود"
    return "\n".join(f"📄 {h['key']}: {h['value'][:200]}" for h in hits)


async def _tool_web_search(args: dict) -> str:
    """جستجوی وب با Bing RSS (بدونِ کلید) — عنوان + لینکِ نتایج."""
    q = str(args.get("query") or "").strip()
    if not q:
        return "خطا: query لازم است"
    from urllib.parse import quote

    from .runtime import get_http_session

    session = await get_http_session()
    try:
        async with session.get(
            "https://www.bing.com/search",
            params={"q": q, "format": "rss", "setlang": "en", "cc": "US"},
            timeout=aiohttp.ClientTimeout(total=12),
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120"},
        ) as r:
            xml = await r.text()
    except Exception as e:
        return f"خطای جستجوی وب: {e}"
    import re as _re

    items = _re.findall(
        r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<description>(.*?)</description>",
        xml, _re.S,
    )
    if not items:
        return "نتیجه‌ای پیدا نشد"
    out = []
    for title, link, desc in items[:5]:
        title = _re.sub(r"<[^>]+>", "", title).strip()
        desc = _re.sub(r"<[^>]+>", "", desc).strip()[:180]
        out.append(f"• {title}\n  {desc}\n  {link}")
    return "\n".join(out)


async def _tool_complete_task(args: dict) -> str:
    tid = str(args.get("id") or "").strip()
    if not tid.isdigit():
        return "خطا: id عددی لازم است"
    ok = await tasks_repo.set_done(int(tid), True)
    return f"کارِ #{tid} انجام شد" if ok else "چنین کاری نیست"


TOOLS: dict[str, tuple[str, Callable[[dict], Awaitable[str]]]] = {
    "create_task": ("ثبتِ کارِ جدید. args: {\"text\": \"...\"}", _tool_create_task),
    "search_memory": ("جستجو در حافظه‌ی بلندمدت. args: {\"query\": \"...\"}", _tool_search_memory),
    "list_tasks": ("لیستِ کارهای باز. args: {}", _tool_list_tasks),
    "complete_task": ("انجام‌شده‌کردنِ کار. args: {\"id\": \"1\"}", _tool_complete_task),
    "web_search": ("جستجوی وب برای اطلاعاتِ جدید. args: {\"query\": \"...\"}", _tool_web_search),
    "search_knowledge": ("جستجو در دانشِ شخصیِ کاربر. args: {\"query\": \"...\"}", _tool_search_knowledge),
}


async def _tool_search_knowledge(args: dict) -> str:
    q = str(args.get("query") or "").strip()
    if not q:
        return "خطا: query لازم است"
    from .knowledge_base import kb_search

    hits = await kb_search(q)
    if not hits:
        return "در دانشِ شخصی چیزی نبود"
    return "\n".join(f"📄 {h['key']}: {h['value'][:200]}" for h in hits)

_TOOL_SYS = (
    "تو عاملِ (Agent) دستیارِ شخصی هستی. ابزارها را فقط وقتی لازم است صدا بزن.\n"
    "برای صدا زدنِ ابزار فقط و فقط یک خطِ JSON بده: {\"tool\": \"نام\", \"args\": {...}}\n"
    "وقتی جوابِ نهایی آماده است، بدونِ JSON فارسی جواب بده."
)

_MAX_STEPS = 3


async def run_agent(user_text: str, *, context: str = "", max_steps: int = _MAX_STEPS) -> str:
    """حلقه‌ی Agent: مدل → (اختیاری) tool call → نتیجه → پاسخِ نهایی."""
    from .config import AI_MODEL

    pers = await get_personality()
    messages: list[dict] = [
        {"role": "system", "content": _TOOL_SYS + "\n" + personality_system_block(pers)}
    ]
    if context:
        messages.append({"role": "system", "content": f"زمینه:\n{context}"})
    messages.append({"role": "user", "content": user_text})

    for _ in range(max_steps):
        user_text_len = len(user_text)
        intent = detect_intent(user_text)
        model = route_model(intent, user_text_len) or AI_MODEL
        try:
            out = await ai.ask_ai(messages, model_override=model, max_tokens=500)
        except ai.AIDisabledError:
            raise
        except Exception as e:
            return f"❌ خطای AI: {e}"

        # آیا مدل tool خواست؟
        m = re.search(r'\{"tool"\s*:\s*"(\w+)"\s*,\s*"args"\s*:\s*(\{.*\})\}', out or "", re.S)
        if not m:
            return await _self_check((out or "").strip(), user_text)
        name, args_json = m.group(1), m.group(2)
        tool = TOOLS.get(name)
        if not tool:
            messages.append({"role": "assistant", "content": out})
            messages.append({"role": "user", "content": f"ابزارِ «{name}» وجود ندارد. ابزارها: {', '.join(TOOLS)}"})
            continue
        try:
            args = json.loads(args_json)
        except Exception:
            args = {}
        desc, fn = tool
        try:
            result = await fn(args if isinstance(args, dict) else {})
        except Exception as e:
            result = f"خطای ابزار: {e}"
        messages.append({"role": "assistant", "content": out})
        messages.append({"role": "user", "content": f"نتیجه‌ی ابزارِ {name}:\n{result}\nحالا جوابِ نهایی را بده."})

    return "⏳ عامل به سقفِ گام رسید؛ ساده‌تر بپرس."


async def _self_check(answer: str, user_text: str) -> str:
    """🧪 Self-Evaluation: برای پاسخ‌های بلند/کدینگ، یک‌بار بازبینی + اصلاح."""
    intent = detect_intent(user_text)
    if intent != "CODING" and len(answer) < 600:
        return answer  # کوتاه/چت: نیازی به چک نیست (صرفه‌جویی)
    try:
        fixed = await ai.ask_ai(
            [
                {
                    "role": "system",
                    "content": (
                        "یک بازبینِ سخت‌گیر هستی. پاسخِ دستیار را برای یک سوالِ فنی می‌بینی. "
                        "اگر خطای فنی/منطقی یا کدِ خراب دارد، نسخه‌ی اصلاح‌شده را به فارسی بده "
                        "(فقطِ نسخه‌ی اصلاح‌شده). اگر سالم است، دقیقاً همان متن را برگردان."
                    ),
                },
                {"role": "user", "content": f"سوال: {user_text[:500]}\n\nپاسخ:\n{answer[:2500]}"},
            ],
            max_tokens=700,
        )
        return (fixed or answer).strip() or answer
    except Exception:
        return answer
