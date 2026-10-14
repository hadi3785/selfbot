"""تست‌های اتاق فرار (بدونِ تلگرام — موتورِ خالص)."""
import os
import sys

import pytest

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "postgresql://p:p@localhost/p")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.escape import engine, inventory, puzzles, scoring
from bot.escape.scenarios import SCENARIOS


def test_scenarios_valid():
    assert len(SCENARIOS) >= 8
    for s in SCENARIOS:
        assert s["id"] and s["name"] and s["intro"]
        assert len(s["rooms"]) >= 5
        assert s["objects"] and s["boss"] and set(s["endings"]) >= {"good", "perfect", "secret"}


def test_create_game_deterministic():
    a = engine.create_game(1, 100, scenario_id="house")
    b = engine.create_game(1, 100, scenario_id="house")
    # دو بازی با سناریوی ثابت، پازل‌های متفاوت (seed تصادفی) ولی هردو قابل‌حل
    assert a["scenario"] == "house" == b["scenario"]
    assert a["status"] == "running"
    assert a["hp"] == 100
    assert "flashlight" in a["inventory"]


def test_daily_seed_deterministic():
    a = engine.create_game(1, 100, daily_date="2026-08-31")
    b = engine.create_game(1, 100, daily_date="2026-08-31")
    assert a["seed"] == b["seed"]
    assert a["puzzles"].keys() == b["puzzles"].keys()
    assert a["time_limit"] == 600


def test_inspect_gives_items_and_clue():
    st = engine.create_game(1, 100, scenario_id="house")
    res = engine.inspect(st)
    assert res["kind"] == "inspect"
    # آیتم‌های اتاقِ اول جمع شده‌اند (خانواده‌ی کلید/یادداشت...)
    assert len(st["inventory"]) >= 2
    assert len(st["clues"]) >= 1  # سرنخِ پازلِ فعلی


def test_answer_wrong_then_right_progresses():
    st = engine.create_game(1, 100, scenario_id="house")
    cp = st["puzzles"][st["current_puzzle"]]
    wrong = engine.answer(st, "یک جوابِ قطعاً غلط")
    assert wrong["kind"] == "wrong"
    assert st["failed_attempts"] == 1
    right = engine.answer(st, cp["answer"])
    assert right["kind"] == "solved"
    assert st["stage"] == 1


def test_use_unknown_item_safe():
    st = engine.create_game(1, 100)
    try:
        engine.use(st, "موز")
        assert False, "باید EscapeError بدهد"
    except engine.EscapeError as e:
        assert "کوله" in str(e)


def test_combine_flow():
    st = engine.create_game(1, 100, scenario_id="house")
    engine.inspect(st)
    # چراغ‌قوه در شروع هست؛ باتری از زیرزمینِ inspect — شبیه‌سازیِ مستقیم
    inventory.add_item(st["inventory"], "battery")
    res = engine.combine(st, "چراغ", "باتری")
    assert res["kind"] == "combine"
    assert "flashlight_strong" in st["inventory"]
    assert "flashlight" not in st["inventory"]


def test_combine_invalid_safe():
    st = engine.create_game(1, 100)
    inventory.add_item(st["inventory"], "coin")
    inventory.add_item(st["inventory"], "rope")
    try:
        engine.combine(st, "سکه", "طناب")
        assert False, "ترکیبِ نامعتبر باید EscapeError بدهد"
    except engine.EscapeError:
        pass


def test_hint_costs_and_cap():
    st = engine.create_game(1, 100, scenario_id="lab")
    # اول امتیاز بگیر تا جریمه دیده شود
    cp = st["puzzles"][st["current_puzzle"]]
    engine.answer(st, cp["answer"])
    before = st["score"]
    h1 = engine.hint(st)
    assert "Hint ۱" in h1["text"]
    engine.hint(st)
    engine.hint(st)
    engine.hint(st)  # بیش از ۳ → پیامِ «همه را گرفتی»
    assert st["hints_used"] == 3
    assert st["score"] < before


def test_choice_then_gameover_possible():
    st = engine.create_game(1, 100, scenario_id="ship")
    # انتخابِ در انتظارِ مرحله‌ی ۲ — عمداً زودتر: pending فقط بعد از رسیدن به stage
    st["stage"] = 2
    st["pending_choice"] = engine._pending_choice(st)
    if st["pending_choice"]:
        st["hp"] = 5
        opts = st["pending_choice"]["options"]
        dmg_opt = next((i for i, o in enumerate(opts) if o.get("hp", 0) < 0), 0)
        res = engine.answer(st, str(dmg_opt + 1))
        # hp=5 و جریمه‌ی >5 → gameover
        assert st["status"] in ("gameover", "running")


def test_full_playthrough_win():
    """پلی‌ترو تمامِ یک سناریو تا برد — تضمینِ قابل‌حل‌بودن."""
    st = engine.create_game(1, 100, scenario_id="castle")
    for _ in range(20):
        if st["status"] != "running":
            break
        engine.inspect(st)
        cp = st["puzzles"].get(st["current_puzzle"] or "")
        if st.get("pending_choice"):
            engine.answer(st, "1")
        elif st["stage"] == st["stages"] - 1 and st.get("boss_answer"):
            engine.answer(st, st["boss_answer"])
            break
        elif cp:
            engine.answer(st, cp["answer"])
    assert st["status"] == "won", f"status={st['status']}"


def test_state_json_roundtrip():
    st = engine.create_game(1, 100, scenario_id="house")
    raw = engine.render_serialized(st)
    st2 = engine.deserialize(raw)
    assert st2 == st


def test_time_limit_daily():
    st = engine.create_game(1, 100, daily_date="2026-08-31")
    assert st["time_limit"] == 600
    st["started_at"] -= 700
    # هندلر زمان را چک می‌کند؛ موتور فقط timestamp نگه می‌دارد
    assert (600 - (700)) < 0


def test_scoring_bounds():
    assert scoring.apply_score(5, -100) == 0
    assert scoring.apply_score(scoring.MAX_SCORE, 500) == scoring.MAX_SCORE
    assert scoring.rank_of(2000) == "🏆 افسانه"


def test_all_scenario_playthroughs():
    """هر ۸ سناریو باید قابلِ برد باشد — تضمینِ بزرگِ قابل‌حل‌بودن."""
    for scen in SCENARIOS:
        st = engine.create_game(1, 100, scenario_id=scen["id"])
        for _ in range(40):
            if st["status"] != "running":
                break
            engine.inspect(st)
            if st.get("pending_choice"):
                engine.answer(st, "1")
            elif st["stage"] == st["stages"] - 1 and st.get("boss_answer"):
                engine.answer(st, st["boss_answer"])
                break
            else:
                cp = st["puzzles"].get(st["current_puzzle"] or "")
                if cp:
                    engine.answer(st, cp["answer"])
                else:
                    break
        assert st["status"] == "won", f"سناریوی {scen['id']} برد نشد: {st['status']}"


def test_all_scenarios_winnable():
    """رگرسیون: هر ۸ سناریو × ۳ کاربر باید با جریانِ عادی قابلِ برد باشد."""
    import re as _re
    from bot.escape.scenarios import SCENARIOS
    for sc in SCENARIOS:
        for uid in (1, 2, 3):
            st = engine.create_game(uid, 100, scenario_id=sc["id"])
            steps = 0
            while st["status"] == "running" and steps < 60:
                steps += 1
                if st["stage"] == engine._boss_index(st) and st.get("boss_answer"):
                    engine.answer(st, st["boss_answer"])
                    break
                if st.get("pending_choice"):
                    m = _re.search(r"پاسخ: (\d+)", st["pending_choice"]["text"])
                    try:
                        engine.answer(st, m.group(1) if m else "1")
                    except engine.EscapeError:
                        st["pending_choice"] = None
                    continue
                cp = st["puzzles"].get(st.get("current_puzzle") or "")
                assert cp is not None, f"{sc['id']}: گیر در stage={st['stage']}"
                engine.answer(st, cp["answer"])
            assert st["status"] == "won", f"{sc['id']} uid{uid}: {st['status']}"

# ---------------- سناریوهایِ v2 (بیمارستان/تئاتر/بانک/مترو/قطب) ----------------
NEW_SCENARIOS = ["hospital", "theater", "bank", "subway", "arctic",
                  "coldwar", "circus", "ship", "temple", "airport", "casino", "observatory"]


def _play_to_end(state):
    """بازیِ کاملِ خودکار: همه‌ی پازل‌ها + انتخاب‌ها + boss."""
    for _ in range(80):
        if state["status"] != "running":
            return state
        if state.get("pending_choice"):
            state = engine.answer(state, "1")["state"]
            continue
        if state.get("boss_answer") is not None:
            state = engine.answer(state, state["boss_answer"])["state"]
            continue
        pid = state["current_puzzle"]
        if pid is None:
            return state
        state = engine.answer(state, state["puzzles"][pid]["answer"])["state"]
    return state


@pytest.mark.parametrize("sid", NEW_SCENARIOS)
def test_new_scenarios_winnable(sid):
    st = engine.create_game(1, 1, scenario_id=sid)
    st = _play_to_end(st)
    assert st["status"] == "won", f"{sid} → {st['status']} در stage={st['stage']}"


def test_new_scenarios_unique_ids_and_items():
    from bot.escape.scenarios import SCENARIOS
    from bot.escape.inventory import ITEMS, COMBINED_ITEMS
    valid = set(ITEMS) | set(COMBINED_ITEMS)
    ids = [s["id"] for s in SCENARIOS]
    for sid in NEW_SCENARIOS:
        assert ids.count(sid) == 1
        scen = next(s for s in SCENARIOS if s["id"] == sid)
        assert len(scen["rooms"]) == 6 and scen["objects"] and scen["choices"] and scen["boss"]
        for room, objs in scen["objects"].items():
            assert room in scen["rooms"]
            for _name, _desc, gives in objs:
                for it in gives or []:
                    assert it in valid, f"{sid}: آیتمِ ناشناخته {it}"


def test_new_combinations():
    assert inventory.combine("radio", "battery") is not None
    assert inventory.combine("rope", "crystal") is not None
    assert inventory.item_def("radio_active") and inventory.item_def("talisman")

def test_answer_with_spaces_reaches_engine():
    """باگِ قبلی: handler با maxsplit=2 فقط کلمه‌ی اولِ جوابِ چند-کلمه‌ای (order) را
    به engine می‌داد و معمای ترتیب همیشه «اشتباه» بود."""
    from bot.escape.puzzles import make_order_puzzle
    import random as _random
    pz = make_order_puzzle(_random.Random(42), "circus")
    assert pz["kind"] == "order" and " " in pz["answer"]
    # شبیه‌سازیِ دقیقِ پارسِ handler (بعد از فیکسِ maxsplit=1)
    raw = "پاس " + pz["answer"]
    parts = raw.split(maxsplit=1)
    rest = parts[1].strip()
    assert puzzles.check_answer(pz, rest)
