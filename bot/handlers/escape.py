"""🔐 اتاق فرار متنی (`.فرار`) — هندلرِ تلگرامی.

منطقِ بازی در bot/escape/* است (خالص و تست‌پذیر)؛ این فایل فقط
ورودی/خروجیِ تلگرام + persistence (bot/repositories/escape_repo.py).

هر (chat_id, user_id) یک نشستِ مستقل دارد → جداسازیِ کاملِ کاربرها.
State در PostgreSQL ذخیره می‌شود → با restart/redeploy نمی‌میرد.
"""
from __future__ import annotations

import logging
import time

from telethon import events

from .. import runtime
from ..config import PREFIX, TIMEZONE_OFFSET
from ..repositories import escape_repo
from ..runtime import client
from ..storage.stats_store import record_error as _record_error
from ..utils import pat
from ..escape import engine
from ..escape.engine import EscapeError

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "🔐 **اتاق فرار متنی**\n\n"
    f"`{PREFIX}فرار شروع` — شروعِ بازی (سناریوی تصادفی از ۲۰ داستان)\n"
    f"`{PREFIX}فرار بررسی` — زیر و رو کردنِ محیطِ فعلی\n"
    f"`{PREFIX}فرار استفاده <آیتم>` — استفاده از آیتمِ کوله\n"
    f"`{PREFIX}فرار ترکیب <آیتم۱> <آیتم۲>` — ساختنِ ابزارِ جدید\n"
    f"`{PREFIX}فرار انتخاب <شماره>` — انتخابِ داستانی\n"
    f"`{PREFIX}فرار کوله` — نشان‌دادنِ آیتم‌ها\n"
    f"`{PREFIX}فرار نقشه` — نقشه‌ی سناریو\n"
    f"`{PREFIX}فرار راهنما` — Hint سه‌سطحی (جریمه‌ی امتیاز دارد)\n"
    f"`{PREFIX}فرار وضعیت` — وضعیتِ کاملِ بازی\n"
    f"`{PREFIX}فرار روزانه` — چالشِ روزانه (۱ تلاش در روز)\n"
    f"`{PREFIX}فرار رکورد` — جدولِ امتیازها\n"
    f"`{PREFIX}فرار لغو` — رهاکردنِ بازیِ جاری\n"
)


async def _load(chat_id: int, user_id: int) -> dict | None:
    try:
        raw = await escape_repo.load_session(chat_id, user_id)
        # load_session خودش dict برمی‌گرداند (json.loads در repo)؛ در صورتِ str هم deserialize
        if raw is None:
            return None
        return engine.deserialize(raw) if isinstance(raw, str) else raw
    except Exception:
        _record_error()
        logger.exception("خطا در خواندنِ نشستِ اتاق فرار")
        return None


async def _save(chat_id: int, user_id: int, state: dict) -> None:
    try:
        await escape_repo.save_session(chat_id, user_id, state)
    except Exception:
        _record_error()
        logger.exception("خطا در ذخیره‌ی نشستِ اتاق فرار")


async def _finalize_and_reply(event, res: dict, chat_id: int, user_id: int) -> None:
    """ذخیره‌ی state + در پایانِ بازی، ثبتِ امتیاز و تلاشِ روزانه."""
    state = res["state"]
    await _save(chat_id, user_id, state)
    if state["status"] in ("won", "lost", "gameover"):
        elapsed = int(time.time() - state["started_at"])
        try:
            await escape_repo.add_score(
                chat_id,
                user_id,
                state["scenario"],
                state["score"],
                len(state["solved"]),
                elapsed,
                won=(state["status"] == "won"),
            )
            if state.get("daily_date"):
                await escape_repo.register_daily_attempt(
                    chat_id, user_id, state["daily_date"], state.get("xp", 0)
                )
        except Exception:
            _record_error()
            logger.exception("ثبتِ امتیازِ اتاق فرار شکست خورد")
    await event.edit(res["text"])


@client.on(events.NewMessage(outgoing=True, pattern=pat(["فرار", "escape"])))
async def escape_handler(event):
    raw = (event.pattern_match.group(1) or "").strip()
    # ⚠️ maxsplit=1: جوابِ چند-کلمه‌ای (مثل «ترتیب: 4 2 1 3» یا چیستانِ دوکلمه‌ای) باید
    # کامل داخلِ rest بماند — با maxsplit=2 فقط کلمه‌ی اول به engine می‌رسید و
    # معمایِ order همیشه «اشتباه» می‌شد!
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""
    chat_id, user_id = event.chat_id, runtime.SELF_ID

    # --- دستورهای مستقل از نشست ---
    if sub in ("راهنما", "help", ""):
        return await event.edit(HELP_TEXT)

    if sub == "رکورد":
        try:
            rows = await escape_repo.leaderboard(10)
            summary = await escape_repo.stats_summary()
        except Exception:
            _record_error()
            logger.exception("خواندنِ رکوردها شکست خورد")
            return await event.edit("❌ خطا در خواندنِ رکوردها از دیتابیس.")
        if not rows:
            return await event.edit("🏆 هنوز رکوردی ثبت نشده — اولین نفر باش! `.فرار شروع`")
        medals = ["🥇", "🥈", "🥉"]
        lines = ["🏆 **ESCAPE LEADERBOARD**", ""]
        for i, r in enumerate(rows):
            medal = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{medal} کاربر `{r['user_id']}` — ⭐ {engine.pz.to_fa(r['best'])}")
        lines += ["", "─── رکوردهای ویژه ───"]
        if summary.get("fastest"):
            f_min, f_sec = divmod(summary["fastest"], 60)
            lines.append(f"⚡ سریع‌ترین فرار: {engine.pz.to_fa(f_min)}:{engine.pz.to_fa(f_sec):02d}")
        lines.append(f"🧠 بیشترین معمای حل‌شده: {engine.pz.to_fa(summary['most_solved'])}")
        lines.append(f"⭐ بالاترین امتیاز: {engine.pz.to_fa(summary['top_score'])}")
        return await event.edit("\n".join(lines))

    if sub == "روزانه":
        # روزِ چالش به وقتِ محلیِ کاربر (TIMEZONE_OFFSET؛ پیش‌فرض تهران) — هم‌ترازِ بقیه‌ی پروژه
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        local_now = _dt.now(_tz.utc) + _td(hours=TIMEZONE_OFFSET)
        today = local_now.strftime("%Y-%m-%d")
        used = await escape_repo.daily_attempt_used(chat_id, user_id, today)
        if used:
            return await event.edit(
                "🌑 تلاشِ امروز را استفاده کردی!\nفردا یه چالشِ تازه می‌آید. (تلاشِ امروز: ۱/۱)"
            )
        state = engine.create_game(chat_id, user_id, daily_date=today)
        scen = engine._scenario(state)
        first = state["puzzles"].get(state["current_puzzle"] or "")
        res = {
            "state": state,
            "text": (
                "🌑 **DAILY ESCAPE**\n━━━━━━━━━━━━━━\n"
                f"{scen['emoji']} {scen['name']}\n"
                "⌛ فقط ۱۰ دقیقه تا پایانِ مهلت!\n"
                "🏆 جایزه: +۵۰۰ XP\n\n"
                + scen["intro"]
                + ("\n\n" + first["prompt"] if first else "")
                + "\n\n🔎 با `.فرار بررسی` شروع کن!"
            ),
        }
        return await _finalize_and_reply(event, res, chat_id, user_id)

    if sub == "شروع":
        existing = await _load(chat_id, user_id)
        if existing and existing.get("status") == "running":
            return await event.edit(
                "⚠️ یه بازیِ ناتمام داری! با `.فرار وضعیت` ببین کجایی، یا `.فرار لغو` کن."
            )
        state = engine.create_game(chat_id, user_id, scenario_id=rest or None)
        scen = engine._scenario(state)
        first = state["puzzles"].get(state["current_puzzle"] or "")
        text = (
            f"{scen['emoji']} **{scen['name']}**\n\n"
            + scen["intro"]
            + "\n\n📍 شروع: " + scen["rooms"][0]
        )
        if first:
            text += "\n\n" + first["prompt"]
        text += "\n\n🔎 با `.فرار بررسی` اطراف را بگرد!"
        res = {"state": state, "text": text}
        return await _finalize_and_reply(event, res, chat_id, user_id)

    if sub == "ادامه":
        state = await _load(chat_id, user_id)
        if not state or state["status"] != "running":
            return await event.edit("❌ بازیِ فعالی نداری. با `.فرار شروع` یکی بساز.")
        return await event.edit(engine.status_line(state))

    # --- از اینجا به بعد، بازیِ فعال لازم است ---
    state = await _load(chat_id, user_id)
    if not state or state.get("status") != "running":
        return await event.edit("❌ بازیِ فعالی نداری. با `.فرار شروع` یکی بساز.")

    # زمانِ سقفِ چالشِ روزانه
    if state.get("time_limit") and (time.time() - state["started_at"]) > state["time_limit"]:
        state["status"] = "lost"
        return await _finalize_and_reply(
            event,
            {"state": state, "text": "⌛ وقت تمام شد! چالشِ روزانه ناتمام ماند. 💀"},
            chat_id, user_id,
        )

    # برای stateهایِ ناسازگار (مثل بازیِ شروع‌شده با نسخه‌ی قبلی): boss را در صورتِ نیاز فعال کن
    try:
        engine.boss_skip_guard(state)
    except Exception:
        logger.debug("boss_skip_guard روی state قدیمی شکست خورد", exc_info=True)

    try:
        if sub == "بررسی":
            res = engine.inspect(state)
        elif sub in ("بردار", "بگیر"):
            res = engine.take(state, rest)
        elif sub in ("استفاده", "استعمال"):
            if not rest:
                return await event.edit(f"مثال: `{PREFIX}فرار استفاده چراغ‌قوه`")
            res = engine.use(state, rest)
        elif sub == "ترکیب":
            words = rest.split()
            if len(words) < 2:
                return await event.edit(f"مثال: `{PREFIX}فرار ترکیب چراغ‌قوه باتری`")
            res = engine.combine(state, " ".join(words[:-1]), words[-1])
        elif sub in ("انتخاب", "پاس", "جواب", "رمز"):
            if not rest:
                return await event.edit(f"مثال: `{PREFIX}فرار انتخاب 1` یا `{PREFIX}فرار پاس 123`")
            res = engine.answer(state, rest)
        elif sub == "راهنما":
            res = engine.hint(state)
        elif sub == "کوله":
            inv_txt = engine.inv_mod.render_inventory(state["inventory"])
            return await event.edit("🎒 **کوله‌پشت:**\n" + inv_txt)
        elif sub == "نقشه":
            return await event.edit(engine.map_text(state))
        elif sub == "وضعیت":
            engine.boss_skip_guard(state)
            return await event.edit(engine.status_line(state))
        elif sub in ("لغو", "پایان"):
            state["status"] = "lost"
            return await _finalize_and_reply(
                event, {"state": state, "text": "🚪 بازیِ اتاق فرار رها شد. هر وقت خواستی: `.فرار شروع`"},
                chat_id, user_id,
            )
        else:
            return await event.edit(
                f"❓ زیرفرمانِ نامعلوم. راهنما: `{PREFIX}فرار راهنما`"
            )
    except EscapeError as e:
        return await event.edit(str(e))
    except Exception:
        _record_error()
        logger.exception("خطای غیرمنتظره در اتاق فرار")
        # state را ذخیره کن تا پیشرفتِ بازیکن از دست نرود
        try:
            await _save(chat_id, user_id, state)
        except Exception:
            logger.exception("ذخیره‌ی اضطراریِ state هم شکست خورد")
        return await event.edit("❌ خطای غیرمنتظره! بازیِ تو ذخیره شد؛ دوباره امتحان کن.")

    # اگر boss باید فعال شود و نشده
    if engine.boss_skip_guard(state):
        scen = engine._scenario(state)
        res["text"] += "\n\n" + scen["boss"]["intro"] + "\n" + scen["boss"]["desc"]

    await _finalize_and_reply(event, res, chat_id, user_id)
