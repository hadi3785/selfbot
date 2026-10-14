"""تستِ منطقیِ همه‌ی دستورها با eventِ mock — ورودی‌های خالی/ناقص/اشتباه.
هیچ دستوری نباید ساکت بماند یا crash کند؛ هر مورد باید پاسخِ متن بدهد."""
import asyncio
import os
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/matrix_check.db")
try:
    os.remove("/tmp/matrix_check.db")
except FileNotFoundError:
    pass

import bot.handlers  # noqa: F401,E402
from bot.runtime import client  # E402

# جدول‌ها را برای sqlite in-memory بساز (روی Railway migration می‌سازد)
from bot.db.engine import engine as _engine  # E402
from bot.db import models as _models  # E402
from bot.db import models_ext as _models_ext  # E402


async def _create_all():
    async with _engine.begin() as conn:
        await conn.run_sync(_models.Base.metadata.create_all)




class FakePattern:
    def __init__(self, text):
        m = re.match(r"^\.(\S+)(?:\s+([\s\S]*))?$", text)
        self._arg = m.group(2) if m else ""
        self._cmd = m.group(1) if m else ""

    def group(self, idx):
        if idx == 1:
            return self._arg
        return self._cmd


class FakeEvent(SimpleNamespace):
    def __init__(self, text, chat_id=100, sender_id=1):
        super().__init__(
            pattern_match=FakePattern(text),
            chat_id=chat_id,
            sender_id=sender_id,
            is_reply=False,
            is_group=False,
            is_private=True,
            is_channel=False,
            edits=[],
            responses=[],
            deletes=0,
            answered=None,
            replies=[],
        )

    async def edit(self, text=None, **kw):
        self.edits.append(text or "")

        async def _edit2(t=None, **_kw):
            self.edits.append(t or "")
            return self

        return SimpleNamespace(id=555, edit=_edit2)

    async def respond(self, text=None, **kw):
        self.responses.append(text or "")
        return SimpleNamespace(id=556)

    async def delete(self):
        self.deletes += 1

    async def answer(self, text=None, **kw):
        self.answered = text

    async def get_reply_message(self):
        return None

    def __getattr__(self, item):
        raise AttributeError(item)


def collect_handlers():
    try:
        built = client._event_builders
    except AttributeError:
        return client.list_event_handlers()[0]
    return list(built)


def get_patterns():
    res = []
    for builder, cb in collect_handlers():
        pat = getattr(builder, "pattern", None)
        inner = getattr(pat, "__self__", None)
        regex_txt = getattr(inner, "pattern", None)
        if regex_txt:
            res.append((regex_txt, cb))
    return res


async def main():
    await _create_all()
    pats = get_patterns()
    print(f"دستورهای pattern-دار: {len(pats)}")
    cases = set()
    for pat, cb in pats:
        m0 = re.search(r"\(\?:([^)]+)\)", pat)
        if not m0:
            continue
        alts = [a for a in m0.group(1).split("|") if a]
        if not alts:
            continue
        base = alts[0]
        for arg in ["", " تست", " xyz"]:
            cases.add((base + arg, cb))
    print(f"caseها: {len(cases)}")

    # مثل dispatch واقعی تلگرام: همه‌ی handlerهای matching باید اجرا شوند؛
    # پاسخِ نهایی کافی است حداقل یکی edit/respond کند.
    by_text = {}
    for text, cb in cases:
        by_text.setdefault(text, []).append(cb)

    no_reply, crashes = [], []
    for text, cbs in sorted(by_text.items()):
        any_reply = False
        errs = []
        for cb in cbs:
            ev = FakeEvent(text)
            try:
                await asyncio.wait_for(cb(ev), timeout=3)
            except asyncio.TimeoutError:
                errs.append("TIMEOUT")
                continue
            except AttributeError:
                continue  # وابسته به رسانه/ریپلای (mock کامل نداریم)
            except Exception as e:
                errs.append(f"{cb.__module__.rsplit('.')[-1]}:{type(e).__name__}: {str(e)[:70]}")
                continue
            if ev.edits or ev.responses or ev.answered:
                any_reply = True
        if errs and not any_reply:
            crashes.append((text, errs[0]))
        elif not any_reply:
            no_reply.append(text)

    print(f"\n=== بدونِ پاسخ ({len(no_reply)}):")
    for t in no_reply:
        print(f"  {t!r}")
    print(f"\n=== کرش/timeout ({len(crashes)}):")
    for t, why in crashes:
        print(f"  {t!r:40} → {why}")


asyncio.run(main())
