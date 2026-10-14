"""⚙️ موتورِ اتاق فرار: state machineِ خالص (بدونِ Telethon).

طراحی:
- کل وضعیتِ بازی یک dict قابلِ JSON-شدن است تا در PostgreSQL (ستونِ state)
  ذخیره شود → persistence و session isolation خودکار.
- هیچ loop/تسکی نمی‌سازد؛ زمان فقط با timestamp چک می‌شود.
- seed تضمین می‌کند بازی قابل‌حل باشد: آیتم‌هایِ ضروری همیشه در اشیای
  پیش‌فرض اتاق‌ها هستند؛ فقط ترتیب/مواردِ اضافی/رویدادها تصادفی‌اند.
- هر اکشن یک dict نتیجه برمی‌گرداند: {text, state, done, kind}
"""
from __future__ import annotations

import json
import random
import time

from . import inventory as inv_mod
from . import puzzles as pz
from . import scoring
from .scenarios import SCENARIOS, scenario_by_id

MAX_STAGES_DEFAULT = 7
# boss همیشه «آخرین مرحله» است (stages-1) — در توابعِ زیر از state خوانده می‌شود.
TIME_LIMIT_DEFAULT = None  # ثانیه؛ None = بی‌حد. حالتِ daily مقدار می‌دهد.

# رویدادهای عمومی (بین سناریوها) — روی وضعیت اثر دارند
RANDOM_EVENTS = [
    {"text": "🚨 آژیر کوتاهی صدا زد! قلب‌ات تندتر زد ولی چیز مهمی نشد.", "hp": 0, "score": 0},
    {"text": "💡 برق قطع شد! لحظه‌ای همه‌چیز تاریک شد و برگشت.", "hp": 0, "score": -10},
    {"text": "👣 صدایی از پشت در شنیدی… گذشت. نفس کشیدی.", "hp": 0, "score": 0},
    {"text": "🎁 یک محفظه‌ی مخفی باز شد! 🪙 سکه‌ای داخلش بود.", "hp": 0, "score": 30, "item": "coin"},
    {"text": "🕳 زمین کمی نشست! به زانو خوردی.", "hp": -10, "score": 0},
    {"text": "💨 خاک از سقف ریخت و چشمت را اذیت کرد.", "hp": -5, "score": 0},
    {"text": "🗝 صدای کلیکِ قفلِ کوچکی از گوشه‌ی اتاق! امتیازِ شانس.", "hp": 0, "score": 20},
]


class EscapeError(Exception):
    """خطایِ به‌دستِ کاربر (ورودیِ بد) — برای نمایشِ پیام، نه crash."""


def new_seed() -> int:
    return random.SystemRandom().randint(1, 999_999_999)


def _daily_seed_for(date_str: str, chat_id: int) -> int:
    """seedِ قطعیِ روزانه: همه‌ی بازیکنانِ یک روز، همان چالش (بر اساسِ تاریخ)."""
    return int(f"{int(date_str.replace('-', '')) % 99_999}{chat_id % 997:03d}")


def create_game(
    chat_id: int,
    user_id: int,
    *,
    daily_date: str | None = None,
    scenario_id: str | None = None,
) -> dict:
    """state اولیه؛ اگر daily_date داده شود چالشِ روزانه با seedِ قطعی ساخته می‌شود."""
    rng_seed = _daily_seed_for(daily_date, user_id) if daily_date else new_seed()
    rng = random.Random(rng_seed)
    scen = (
        scenario_by_id(scenario_id)
        if scenario_id and scenario_by_id(scenario_id)
        else rng.choice(SCENARIOS)
    )
    n_rooms = len(scen["rooms"])
    stages = min(MAX_STAGES_DEFAULT, max(5, n_rooms))
    puzzles = pz.build_stage_puzzles(rng, scen["id"], stages)

    state = {
        "seed": rng_seed,
        "scenario": scen["id"],
        "stage": 0,               # 0-based
        "stages": stages,
        "hp": 100,
        "score": 0,
        "xp": 0,
        "clues": [],
        "flags": [],
        "solved": [],
        "failed_attempts": 0,
        "hints_used": 0,
        "inventory": {},
        "current_puzzle": puzzles[0]["id"] if puzzles else None,
        "puzzles": {p["id"]: p for p in puzzles},
        "events_seen": [],
        "status": "running",      # running/won/lost/gameover
        "started_at": time.time(),
        "daily_date": daily_date,
        "time_limit": 600 if daily_date else None,
        "boss_answer": None,
        "pending_choice": None,
    }
    # آیتم‌های شروع: یک چراغ‌قوه (کلاسیک اتاق فرار)
    inv_mod.add_item(state["inventory"], "flashlight")
    return state


# --------------------------------------------------------------- helpers --
def _scenario(state: dict) -> dict:
    return scenario_by_id(state["scenario"]) or SCENARIOS[0]


def _room_of(state: dict) -> str:
    scen = _scenario(state)
    idx = min(state["stage"], len(scen["rooms"]) - 1)
    return scen["rooms"][idx]


def _rng(state: dict) -> random.Random:
    """rngِ اکشن‌ها: seed + stage + تلاش‌ها تا قطعی‌ِ قابلِ تکرار ولی متغیر."""
    return random.Random(state["seed"] * 31 + state["stage"] * 7 + state["failed_attempts"])


def status_line(state: dict) -> str:
    scen = _scenario(state)
    mm, ss = divmod(int(time.time() - state["started_at"]), 60)
    hh, mm = divmod(mm, 60)
    time_s = f"{hh:02d}:{mm:02d}" if hh else f"{mm:02d}:{ss:02d}"
    inv_txt = inv_mod.render_inventory(state["inventory"])
    lines = [
        "🔐 اتاق فرار",
        "━━━━━━━━━━━━━━",
        f"{scen['emoji']} سناریو: {scen['name']}",
        f"📍 مرحله: {pz.to_fa(state['stage'] + 1)}/{pz.to_fa(state['stages'])} — {_room_of(state)}",
        "",
        f"❤️ HP: {pz.to_fa(state['hp'])}/۱۰۰",
        f"⭐ امتیاز: {pz.to_fa(state['score'])}",
        f"🧠 سرنخ: {pz.to_fa(len(state['clues']))}",
        "",
        "🎒 کوله:\n" + inv_txt,
        "",
        f"⏱ زمان: {time_s}",
    ]
    if state["time_limit"]:
        remain = max(0, state["time_limit"] - int(time.time() - state["started_at"]))
        lines.append(f"⌛ باقی‌مانده: {pz.to_fa(remain // 60)}:{pz.to_fa(remain % 60):02d}")
    return "\n".join(lines)


def _maybe_event(state: dict) -> str | None:
    """۳۵٪ شانس رویداد تصادفی در هر اکشن؛ جلوی تکرارِ فوریِ همان رویداد."""
    rng = _rng(state)
    if rng.random() > 0.35:
        return None
    ev = rng.choice(RANDOM_EVENTS)
    key = ev["text"][:24]
    if key in state["events_seen"][-3:]:
        return None
    state["events_seen"].append(key)
    if len(state["events_seen"]) > 20:  # سقفِ حافظه؛ فقط چندتایِ آخر لازم است
        del state["events_seen"][:-20]
    if ev.get("hp"):
        state["hp"] = max(0, state["hp"] + ev["hp"])
    if ev.get("score"):
        state["score"] = scoring.apply_score(state["score"], ev["score"])
    if ev.get("item"):
        inv_mod.add_item(state["inventory"], ev["item"])
    return ev["text"]


def _boss_index(state: dict) -> int:
    """مرحله‌ی boss = آخرین مرحله (0-based)."""
    return state["stages"] - 1


def _activate_boss(state: dict) -> None:
    """ساختِ رمزِ نهایی boss (قطعی با seed؛ متفاوت در هر بازی)."""
    boss_rng = random.Random(state["seed"] + 999)
    parts = [boss_rng.randint(10, 99) for _ in range(3)]
    state["boss_answer"] = f"{parts[0]}{parts[1]}{parts[2]}"
    state["current_puzzle"] = None


def _advance(state: dict) -> None:
    state["stage"] += 1
    if state["stage"] >= state["stages"]:
        state["stage"] = state["stages"] - 1
    remaining = [pid for pid in state["puzzles"] if pid not in state["solved"]]
    if state["stage"] == _boss_index(state) and not remaining:
        _activate_boss(state)   # همه‌ی پازل‌ها حل شدند → boss
    else:
        state["current_puzzle"] = remaining[0] if remaining else None
    state["pending_choice"] = _pending_choice(state)


def _pending_choice(state: dict) -> dict | None:
    scen = _scenario(state)
    for ch in scen.get("choices", []):
        if ch["stage"] == state["stage"] and ch.get("text") not in state["flags"]:
            return ch
    return None


# ---------------------------------------------------------------- actions --
def inspect(state: dict) -> dict:
    """بررسیِ محیط: اشیای اتاقِ فعلی + شانسِ سرنخ/آیتمِ مخفی."""
    if state["status"] != "running":
        raise EscapeError("بازیِ فعالی نیست — با `.فرار شروع` یکی بساز.")
    scen = _scenario(state)
    room = _room_of(state)
    objs = scen["objects"].get(room, [])
    rng = _rng(state)
    shown = objs[:]
    rng.shuffle(shown)  # ترتیبِ نمایش تصادفی (محتوایِ لازم دست‌نخورده)

    lines = [f"👁️ «{room}» را زیر و رو کردی:"]
    took_auto = []
    for name, desc, gives in shown:
        lines.append(f"▫️ {name}: {desc}")
        for it in gives or []:
            if it not in state["inventory"]:
                inv_mod.add_item(state["inventory"], it)
                took_auto.append(it)

    # سرنخِ پازلِ فعلی (همیشه در دسترس — تضمینِ قابل‌حل‌بودن)
    cp = state["puzzles"].get(state["current_puzzle"] or "")
    clue_line = None
    if cp and cp["id"] not in state["solved"]:
        clue = f"🔎 سرنخ برای معمای «{cp['kind']}»: {cp['hints'][0]}"
        if cp["id"] not in state["clues"]:
            state["clues"].append(cp["id"])
            state["score"] = scoring.apply_score(state["score"], scoring.SCORE_CLUE)
            clue_line = clue

    # آیتمِ مخفی‌ی شانسی
    hidden = None
    if rng.random() < 0.25:
        pick = rng.choice(["coin", "battery", "tape", "note"])
        if pick not in state["inventory"]:
            inv_mod.add_item(state["inventory"], pick)
            state["score"] = scoring.apply_score(state["score"], scoring.SCORE_HIDDEN_ITEM)
            spot = shown[0][0] if shown else "گوشه‌ای از اتاق"
            hidden = f"✨ پشتِ {spot}، {pick} مخفی بود! (+{pz.to_fa(scoring.SCORE_HIDDEN_ITEM)} امتیاز)"

    ev = _maybe_event(state)
    blocks = ["\n".join(lines)]
    if took_auto:
        from .inventory import item_def
        names = "، ".join(f"{item_def(i)['emoji']} {item_def(i)['name']}" for i in took_auto)
        blocks.append(f"🎒 برداشتی: {names}")
    if clue_line:
        blocks.append(clue_line)
    if hidden:
        blocks.append(hidden)
    if ev:
        blocks.append(f"⚡ {ev}")
    return {"text": "\n\n".join(blocks), "state": state, "kind": "inspect"}


def take(state: dict, obj_name: str) -> dict:
    """برداشتنِ آیتم — در این طراحی برداشتنِ خودکار در inspect رخ می‌دهد؛
    take فقط برای اطمینان/لیست‌کردنِ برداشت‌هاست."""
    if state["status"] != "running":
        raise EscapeError("بازیِ فعالی نیست.")
    inv_txt = inv_mod.render_inventory(state["inventory"])
    return {
        "text": f"🎒 کوله‌پشتی (هرچه در inspect دیدی برداشته شد):\n{inv_txt}",
        "state": state,
        "kind": "take",
    }


def use(state: dict, item_name: str) -> dict:
    if state["status"] != "running":
        raise EscapeError("بازیِ فعالی نیست.")
    item_name = (item_name or "").strip()
    target = None
    for iid in state["inventory"]:
        d = inv_mod.item_def(iid)
        if d and (item_name in d["name"] or d["name"] in item_name):
            target = iid
            break
    if not target:
        raise EscapeError("❌ چنین آیتمی در کوله‌پشتی وجود ندارد.")
    d = inv_mod.item_def(target)
    if not d["usable"]:
        return {"text": f"🤷 {d['emoji']} {d['name']} الان قابلِ استفاده نیست.", "state": state, "kind": "use"}
    # استفاده: اثرِ ساده بر اساسِ نوع
    if target == "flashlight" or target == "flashlight_strong":
        msg = "🔆 نورافکنی کردی؛ گوشه‌های اتاق بی‌رحم واضح شدند. چیزِ تازه‌ای؟ با «بررسی» دقیق‌تر نگاه کن."
    elif target == "note" or target == "decoded_note":
        cp = state["puzzles"].get(state["current_puzzle"] or "")
        msg = "📜 یادداشت را خواندی: " + (cp["prompt"].split("\n", 1)[1][:120] if cp and "\n" in cp["prompt"] else "چیزی خاص نبود.")
    elif target == "coin":
        state["score"] = scoring.apply_score(state["score"], 20)
        msg = f"🪙 سکه را وارسی کردی؛ پشتش نقشِ رخِ پادشاه با عددِ کوچکی. (+{pz.to_fa(20)})"
    else:
        msg = f"👌 {d['emoji']} {d['name']} را استفاده کردی — ولی شاید ترکیبش با چیزی دیگر کارسازتر باشد…"
    ev = _maybe_event(state)
    text = msg + (f"\n\n⚡ {ev}" if ev else "")
    return {"text": text, "state": state, "kind": "use"}


def combine(state: dict, a_name: str, b_name: str) -> dict:
    if state["status"] != "running":
        raise EscapeError("بازیِ فعالی نیست.")
    def find(name: str) -> str | None:
        for iid in state["inventory"]:
            d = inv_mod.item_def(iid)
            if d and (name in d["name"] or d["name"] in name):
                return iid
        return None
    a, b = find(a_name), find(b_name)
    if not a or not b:
        raise EscapeError("❌ یکی از آیتم‌ها در کوله‌پشتی نیست. با `.فرار کوله` چک کن.")
    if a == b:
        raise EscapeError("❌ دو آیتمِ متفاوت لازم است.")
    rule = inv_mod.combine(a, b)
    if not rule:
        raise EscapeError("❌ این دو با هم ترکیب نمی‌شوند. چیزِ دیگری امتحان کن.")
    out_id, msg = rule
    inv_mod.remove_item(state["inventory"], a)
    inv_mod.remove_item(state["inventory"], b)
    inv_mod.add_item(state["inventory"], out_id)
    state["score"] = scoring.apply_score(state["score"], 35)
    state["clues"].append(f"combined:{out_id}")
    return {"text": f"{msg}\n⭐ +{pz.to_fa(35)} امتیاز", "state": state, "kind": "combine"}


def answer(state: dict, raw: str) -> dict:
    """پاسخ به پازل/انتخاب/boss — ورودیِ اصلیِ «حل»."""
    if state["status"] != "running":
        raise EscapeError("بازیِ فعالی نیست.")
    raw = (raw or "").strip()

    # ۱) انتخابِ داستانیِ در انتظار
    if state.get("pending_choice"):
        ch = state["pending_choice"]
        try:
            idx = int(raw.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))) - 1
        except ValueError:
            raise EscapeError("❌ شماره‌ی گزینه را بده (مثلاً `فرار انتخاب 1`).")
        opts = ch["options"]
        if not (0 <= idx < len(opts)):
            raise EscapeError(f"❌ گزینه باید بین ۱ و {pz.to_fa(len(opts))} باشد.")
        opt = opts[idx]
        state["hp"] = max(0, state["hp"] + opt.get("hp", 0))
        state["score"] = scoring.apply_score(state["score"], opt.get("score", 0))
        state["flags"].append(ch["text"])
        state["pending_choice"] = None
        if state["hp"] <= 0:
            state["status"] = "gameover"
            return {"text": opt["msg"] + "\n\n💀 HP صفر شد — Game Over!", "state": state, "kind": "gameover"}
        ev = _maybe_event(state)
        return {"text": opt["msg"] + (f"\n\n⚡ {ev}" if ev else ""), "state": state, "kind": "choice"}

    # ۲) boss (اگر هنوز فعال نشده ولی باید، همین‌جا فعالش کن — مقاوم به stateهای قدیمی)
    if state["stage"] == _boss_index(state):
        boss_skip_guard(state)
    if state["stage"] == _boss_index(state) and state.get("boss_answer") is not None:
        if pz.check_answer({"answer": state["boss_answer"]}, raw):
            return _win(state, perfect=not state["failed_attempts"] and len(state["clues"]) >= state["stages"])
        state["failed_attempts"] += 1
        state["hp"] = max(0, state["hp"] - 15)
        state["score"] = scoring.apply_score(state["score"], -scoring.SCORE_WRONG_ANSWER)
        if state["hp"] <= 0:
            state["status"] = "gameover"
            return {"text": "💀 رمزِ نهایی غلط بود و انرژی‌ات تمام شد — Game Over!", "state": state, "kind": "gameover"}
        return {"text": f"❌ رمزِ نهایی درست نیست. (HP: {pz.to_fa(state['hp'])}) دوباره فکر کن!", "state": state, "kind": "wrong"}

    # ۳) پازلِ معمولی
    cp = state["puzzles"].get(state["current_puzzle"] or "")
    if not cp:
        raise EscapeError("الان معمایی برای حل‌کردن نیست — «بررسی» کن.")
    if pz.check_answer(cp, raw):
        state["solved"].append(cp["id"])
        state["score"] = scoring.apply_score(state["score"], cp["reward"])
        state["xp"] += scoring.xp_of(cp["reward"])
        # رفتن به مرحله‌ی بعد (اگر پازلِ قبلِ boss بود، _advance خودش boss را می‌سازد)
        if state["stage"] == _boss_index(state) - 1 and len(state["solved"]) >= state["stages"] - 1:
            state["stage"] = _boss_index(state)
            _activate_boss(state)
            scen = _scenario(state)
            return {
                "text": (
                    f"✅ درست بود! (+{pz.to_fa(cp['reward'])} امتیاز)\n\n"
                    f"{scen['boss']['intro']}\n{scen['boss']['desc']}\n\n"
                    f"🔓 رمزِ نهایی: سه عدد — سرنخ‌هایت را با «بررسی» جمع کن. (کدِ ۶ رقمی)"
                ),
                "state": state,
                "kind": "boss",
            }
        _advance(state)
        ev = _maybe_event(state)
        nxt = state["puzzles"].get(state["current_puzzle"] or "")
        text = f"✅ درست بود! (+{pz.to_fa(cp['reward'])} امتیاز)\n\n📍 مرحله‌ی بعد: {_room_of(state)}"
        if nxt:
            text += "\n\n" + nxt["prompt"]
        if ev:
            text += f"\n\n⚡ {ev}"
        if state.get("pending_choice"):
            ch = state["pending_choice"]
            text += "\n\n" + ch["text"] + "\n" + "\n".join(o["label"] for o in ch["options"])
        return {"text": text, "state": state, "kind": "solved"}

    state["failed_attempts"] += 1
    state["score"] = scoring.apply_score(state["score"], -scoring.SCORE_WRONG_ANSWER)
    state["hp"] = max(0, state["hp"] - 5)
    if state["hp"] <= 0:
        state["status"] = "gameover"
        return {"text": "💀 HP صفر شد — Game Over! با `.فرار شروع` دوباره تلاش کن.", "state": state, "kind": "gameover"}
    return {"text": f"❌ اشتباه بود. (HP: {pz.to_fa(state['hp'])}، امتیاز: {pz.to_fa(state['score'])})", "state": state, "kind": "wrong"}


def hint(state: dict, level: int | None = None) -> dict:
    if state["status"] != "running":
        raise EscapeError("بازیِ فعالی نیست.")
    # boss همیشه راهنمایِ کلی دارد؛ پازلِ فعلی hintهایِ سه‌سطحی
    if state["stage"] == _boss_index(state) and state.get("boss_answer") is not None:
        state["score"] = scoring.apply_score(state["score"], -scoring.HINT_COSTS[1])
        return {"text": f"💡 سرنخ‌هایی که «بررسی» کردی را کنارِ هم بگذار؛ سه عدد، پشتِ هم. (−{pz.to_fa(scoring.HINT_COSTS[1])} امتیاز)", "state": state, "kind": "hint"}
    cp = state["puzzles"].get(state["current_puzzle"] or "")
    if not cp:
        raise EscapeError("معمایی در جریان نیست.")
    # سطح: بر اساسِ تعدادِ hintهایِ استفاده‌شده برای همین پازل (پیش‌فرض بعدی)
    per_puzzle_key = f"hint_count:{cp['id']}"
    used = state.get(per_puzzle_key, 0)
    level = (used + 1) if level is None else max(1, min(3, level))
    if level <= used:
        level = used + 1
    if level > 3:
        return {"text": "💡 همه‌ی سه سطحِ راهنما را گرفتی — دیگر جای گیری نیست!", "state": state, "kind": "hint"}
    cost = scoring.HINT_COSTS[level - 1]
    if state.get("hints_used", 0) >= scoring.HINT_CAP:
        cost = cost // 2  # ضدِ اسپم: بعد از سقف، نصف
    state[per_puzzle_key] = level
    state["hints_used"] = state.get("hints_used", 0) + 1
    state["score"] = scoring.apply_score(state["score"], -cost)
    return {"text": f"💡 Hint {pz.to_fa(level)}: {cp['hints'][level - 1]}\n(−{pz.to_fa(cost)} امتیاز)", "state": state, "kind": "hint"}


def _win(state: dict, *, perfect: bool) -> dict:
    elapsed = int(time.time() - state["started_at"])
    bonus = scoring.time_bonus(elapsed, state.get("time_limit"))
    state["score"] = scoring.apply_score(state["score"], scoring.SCORE_END_BONUS + bonus)
    state["xp"] += scoring.xp_of(scoring.SCORE_END_BONUS + bonus)
    state["status"] = "won"
    scen = _scenario(state)
    ending = scen["endings"]["perfect" if perfect else "good"]
    if "secret" in state["flags"]:
        ending = scen["endings"]["secret"]
    mm, ss = divmod(elapsed, 60)
    hh, mm = divmod(mm, 60)
    return {
        "text": (
            f"{ending}\n\n"
            f"⏱ زمان: {hh:02d}:{mm:02d}\n"
            f"⭐ امتیاز نهایی: {pz.to_fa(state['score'])} ({scoring.rank_of(state['score'])})\n"
            f"🧠 معماها: {pz.to_fa(len(state['solved']))} | 💡 راهنما: {pz.to_fa(state.get('hints_used', 0))}"
        ),
        "state": state,
        "kind": "won",
    }


def boss_skip_guard(state: dict) -> bool:
    """در مرحله‌ی boss: اگر همه‌ی پازل‌ها حل شده و boss خاموش است فعالش کن؛
    اگر هنوز پازل مانده، پازلِ معوق را به جریان برگردان (self-heal — هرگز گیر/سوختنِ بی‌دلیل)."""
    if state["stage"] != _boss_index(state):
        return False
    remaining = [pid for pid in state["puzzles"] if pid not in state["solved"]]
    if not remaining:
        if state.get("boss_answer") is None:
            _activate_boss(state)
            return True
        return False
    # پازل‌های معوق: جریانِ پازل را ترمیم کن
    if state.get("current_puzzle") not in state["puzzles"] or state["current_puzzle"] in state["solved"]:
        state["current_puzzle"] = remaining[0]
        return True
    return False


def status(state: dict) -> str:
    return status_line(state)


def map_text(state: dict) -> str:
    scen = _scenario(state)
    lines = ["🗺 نقشه‌ی سناریو:", ""]
    for i, room in enumerate(scen["rooms"]):
        mark = "🔹" if i < state["stage"] else ("📍" if i == state["stage"] else "▫️")
        lines.append(f"{mark} {room}")
    return "\n".join(lines)


def render_serialized(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True)


def deserialize(raw: str) -> dict:
    return json.loads(raw)


# alias برای هندلر (دسترسیِ راحت به زیرماژول‌ها)
class _PZAlias:
    """دسترسیِ به توابعِ نمایشیِ puzzles از طریقِ engine."""
    to_fa = staticmethod(pz.to_fa)


pz = pz  # noqa: PLW0127 — صریح برای خواناییِ import در هندلر
inv_mod = inv_mod  # noqa: PLW0127
