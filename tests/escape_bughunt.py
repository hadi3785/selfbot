"""باگ‌هانتِ شدیدِ اتاق فرار — سناریوهای مرزی و حملاتِ ورودی."""
import os
import random
import re
import sys

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "postgresql://p:p@localhost/p")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.escape import engine, inventory
from bot.escape.engine import EscapeError
from bot.escape.scenarios import SCENARIOS

issues = []


def check(name, fn):
    try:
        fn()
        print("✓", name)
    except Exception as e:
        issues.append((name, repr(e)))
        print("✗", name, "→", repr(e))


# --------------------------------------------------------------- مرزی‌ها --
def t_inspect_empty_room():
    """اتاقی که کلیدِ objects ندارد (مراحلِ آخر معمولاً) نباید crash کند."""
    st = engine.create_game(1, 100, scenario_id="house")
    # به مرحله‌ای برو که room بی‌شیء است (انبار/اتاقِ خواب...)
    st["stage"] = min(5, st["stages"] - 1)
    res = engine.inspect(st)  # نباید IndexError بدهد
    assert "text" in res
check("inspect روی اتاقِ بی‌شیء", t_inspect_empty_room)


def t_hp_floor_and_gameover():
    st = engine.create_game(1, 100, scenario_id="house")
    st["hp"] = 3
    st["pending_choice"] = {"stage": 0, "text": "X", "options": [
        {"label": "1️⃣", "hp": -20, "score": 0, "flag": "x", "msg": "ضربه"}]}
    res = engine.answer(st, "1")
    assert st["hp"] == 0 and st["status"] == "gameover", (st["hp"], st["status"])
check("HP floor + gameover در انتخاب", t_hp_floor_and_gameover)


def t_score_never_negative():
    st = engine.create_game(1, 100)
    st["hp"] = 10_000  # تا gameover نشود؛ فقط floorِ امتیاز را می‌سنجیم
    for _ in range(30):
        engine.answer(st, "قطعاً غلط")
        assert st["score"] >= 0, st["score"]
    assert st["score"] == 0
check("امتیازِ هرگز منفی نمی‌شود", t_score_never_negative)


def t_puzzle_pool_exhaustion():
    """پازل‌های کمتر از مراحل؟ stages=7 و ۶ سازنده → باید با تکرار پر شود."""
    st = engine.create_game(1, 100, scenario_id="house")
    assert len(st["puzzles"]) >= st["stages"] - 1, (len(st["puzzles"]), st["stages"])
check("پازل برای هر مرحله‌ی غیرِ boss وجود دارد", t_puzzle_pool_exhaustion)


def t_answer_after_won():
    st = engine.create_game(1, 100)
    st["status"] = "won"
    try:
        engine.answer(st, "x")
        assert False
    except EscapeError:
        pass
check("اکشن بعد از پایان بازی ممنوع", t_answer_after_won)


def t_choice_wrong_number():
    st = engine.create_game(1, 100)
    st["pending_choice"] = {"stage": 0, "text": "X", "options": [
        {"label": "1️⃣", "hp": 0, "score": 0, "flag": "a", "msg": "y"},
        {"label": "2️⃣", "hp": 0, "score": 0, "flag": "b", "msg": "z"}]}
    for bad in ["0", "5", "abc", "۱.۵", "-1", ""]:
        try:
            engine.answer(st, bad)
            ok = False
        except EscapeError:
            ok = True
        except Exception as e:
            ok = False
            raise
        assert ok, bad
check("انتخاب با ورودی‌های عجیب امن", t_choice_wrong_number)


def t_use_with_partial_names():
    """استفاده با بخشی از اسم یا کاراکترهای خاص نباید crash کند."""
    st = engine.create_game(1, 100, scenario_id="house")
    engine.inspect(st)
    for probe in ["چراغ", "💡", "﷼", "a" * 300, "       ", "🔒"]:
        try:
            engine.use(st, probe)
        except EscapeError:
            pass
check("use با اسم‌های جزئی/خاص", t_use_with_partial_names)


def t_combine_same_item():
    st = engine.create_game(1, 100)
    inventory.add_item(st["inventory"], "rope", 2)
    try:
        engine.combine(st, "طناب", "طناب")
        assert False
    except EscapeError:
        pass
check("ترکیبِ آیتم با خودش ممنوع", t_combine_same_item)


def t_boss_answer_format():
    """boss_answer همیشه ۶ رقم؟"""
    for _ in range(30):
        st = engine.create_game(1, 100, scenario_id="house")
        st["stage"] = st["stages"] - 1
        engine.boss_skip_guard(st)
        ba = st.get("boss_answer")
        if ba is not None:
            assert len(ba) == 6 and ba.isdigit(), ba
check("فرمتِ رمزِ Boss (۶ رقم)", t_boss_answer_format)


def t_boss_skip_guard_idempotent():
    st = engine.create_game(1, 100, scenario_id="lab")
    st["stage"] = st["stages"] - 1
    for pid in st["puzzles"]:
        st["solved"].append(pid)
    engine.boss_skip_guard(st)
    a1 = st["boss_answer"]
    engine.boss_skip_guard(st)
    assert st["boss_answer"] == a1, "نباید رمز عوض شود!"
check("boss_skip_guard idempotent", t_boss_skip_guard_idempotent)


def t_daily_seed_stable_and_distinct():
    a = engine.create_game(1, 100, daily_date="2026-09-01")
    b = engine.create_game(1, 100, daily_date="2026-09-01")
    c = engine.create_game(1, 100, daily_date="2026-09-02")
    assert a["seed"] == b["seed"] != c["seed"]
    # دو کاربرِ همان روز: seed باید یکسان باشد (طبق پرامت: «برای همه‌ی بازیکنان همان روز»)
    d = engine.create_game(2, 100, daily_date="2026-09-01")
    assert d["seed"] == a["seed"], "daily باید بینِ کاربرانِ یک روز مشترک باشد"
check("seed روزانه: ثابت در روز، متفاوت بینِ روزها", t_daily_seed_stable_and_distinct)


def t_puzzle_hints_complete():
    """هر پازل باید دقیقاً ۳ hint و جوابِ غیرخالی داشته باشد."""
    for scen in SCENARIOS:
        for i in range(20):
            rng = random.Random(i)
            for maker in (
                __import__("bot.escape.puzzles", fromlist=["make_code_puzzle"]).make_code_puzzle,
                __import__("bot.escape.puzzles", fromlist=["make_pattern_puzzle"]).make_pattern_puzzle,
                __import__("bot.escape.puzzles", fromlist=["make_logic_puzzle"]).make_logic_puzzle,
                __import__("bot.escape.puzzles", fromlist=["make_order_puzzle"]).make_order_puzzle,
                __import__("bot.escape.puzzles", fromlist=["make_riddle_puzzle"]).make_riddle_puzzle,
                __import__("bot.escape.puzzles", fromlist=["make_choice_puzzle"]).make_choice_puzzle,
            ):
                p = maker(rng, scen["id"])
                assert len(p["hints"]) == 3 and p["answer"] and p["prompt"], (maker, p)
check("ساختارِ همه‌ی پازل‌ها (۳ hint، جواب، prompt)", t_puzzle_hints_complete)


def t_logic_puzzle_consistency():
    """منطقی جدید: «دقیقاً یکی درست» → جواب باید مقدارِ یکتایِ ادعاها باشد (۵۰۰ نمونه)."""
    import bot.escape.puzzles as pz
    def fa2en(s):
        return s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    for i in range(500):
        rng = random.Random(i)
        p = pz.make_logic_puzzle(rng, "x")
        claims = [int(fa2en(m.group(1))) for m in re.finditer(r"قفلِ درست، قفلِ ([۰-۹]+) است", p["prompt"])]
        assert len(claims) == 3, p["prompt"]
        ans = int(p["answer"])
        assert sum(c == ans for c in claims) == 1, (i, claims, ans)
check("سازگاریِ معمای منطقی (۵۰۰ نمونه)", t_logic_puzzle_consistency)


def t_order_puzzle_answer_matches_prompt():
    """ترتیب: جواب باید از promptِ نمایشی قابل‌استخراج باشد (کهنه→نو) — ۲۰۰ نمونه."""
    import bot.escape.puzzles as pz
    for i in range(200):
        rng = random.Random(i)
        p = pz.make_order_puzzle(rng, "x")
        shown = [e for _, e in re.findall(r"(\d)\. (\S+)", p["prompt"])]
        derived = " ".join(str(shown.index(e) + 1) for e in ["🥚", "🕯", "🕰", "📻"])
        assert derived == p["answer"], (i, shown, p["answer"], derived)
check("جوابِ معمای ترتیب با prompt سازگار (۲۰۰ نمونه)", t_order_puzzle_answer_matches_prompt)


def t_time_limit_zero_elapsed():
    st = engine.create_game(1, 100, daily_date="2026-09-01")
    st["started_at"] -= st["time_limit"] + 5
    # هندلر این را چک می‌کند؛ state باید دست‌نخورده بماند
    assert st["status"] == "running"  # موتور خودش زمان چک نمی‌کند (طرحِ صحیح)
check("زمانِ تمام‌شده (مسئولیتِ هندلر)", t_time_limit_zero_elapsed)


def t_serialization_after_boss():
    st = engine.create_game(1, 100, scenario_id="house")
    st["stage"] = st["stages"] - 1
    engine.boss_skip_guard(st)
    raw = engine.render_serialized(st)
    st2 = engine.deserialize(raw)
    assert st2["boss_answer"] == st["boss_answer"]
check("serialize بعد از Boss", t_serialization_after_boss)


def t_random_events_no_dupes_streak():
    """۵۰۰ بازی: بعد از هر اکشن، دو رویدادِ متوالیِ یکسان ممنوع."""
    for seed in range(500):
        st = engine.create_game(1, 100)
        for act in range(30):
            st["failed_attempts"] = act
            engine._maybe_event(st)
            keys = st["events_seen"]
            assert not (len(keys) >= 2 and keys[-1] == keys[-2]), keys[-2:]
check("رویدادها: بدونِ تکرارِ پشتِ‌سرِهم (۵۰۰ بازی)", t_random_events_no_dupes_streak)


def t_inventory_render_unknown():
    r = inventory.render_inventory({"__unknown__": 2})
    assert "ناشناخته" in r and "__unknown__" not in r, r
check("render آیتمِ ناشناخته امن", t_inventory_render_unknown)


def t_combine_consumes_correctly():
    st = engine.create_game(1, 100)
    inventory.add_item(st["inventory"], "note")
    inventory.add_item(st["inventory"], "codecard")
    engine.combine(st, "یادداشت", "کارت")
    assert "decoded_note" in st["inventory"]
    assert "note" not in st["inventory"] and "codecard" not in st["inventory"]
check("ترکیب: مصرفِ درستِ مواد", t_combine_consumes_correctly)


def t_win_bonus_applied_once():
    """جریانِ کامل: حلِ همه‌ی پازل‌ها → boss → برد؛ بعدش اکشن ممنوع."""
    st = engine.create_game(1, 100, scenario_id="house")
    import re as _re
    steps = 0
    while st["status"] == "running" and steps < 40:
        steps += 1
        if st["stage"] == engine._boss_index(st) and st.get("boss_answer"):
            r = engine.answer(st, st["boss_answer"]); break
        if st.get("pending_choice"):
            m = _re.search(r"پاسخ: (\d+)", st["pending_choice"]["text"])
            engine.answer(st, m.group(1) if m else "1"); continue
        cp = st["puzzles"].get(st.get("current_puzzle") or "")
        assert cp is not None, f"گیر در stage={st['stage']} — هیچ پازل/boss فعال نیست!"
        engine.answer(st, cp["answer"])
    assert st["status"] == "won"
    s1 = st["score"]
    try:
        engine.answer(st, st["boss_answer"])
        assert False
    except EscapeError:
        pass
    assert st["score"] == s1
check("برد: بونوسِ یک‌بار + قفلِ اکشن بعد از برد", t_win_bonus_applied_once)


print()
if issues:
    print(f"⚠️ {len(issues)} مشکل:")
    for n, e in issues:
        print(" -", n, e)
    sys.exit(1)
print("🎉 بدونِ crash در همه‌ی مرزی‌ها")
