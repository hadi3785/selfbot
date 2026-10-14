"""تستِ مقاومت در برابرِ state قدیمیِ ناسازگار (boss فعال نشده)."""
import os
import sys

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "postgresql://p:p@localhost/p")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.escape import engine

st = engine.create_game(1, 100, scenario_id="house")
st["stage"] = st["stages"] - 1
for pid in st["puzzles"]:
    st["solved"].append(pid)
st["current_puzzle"] = None
st["boss_answer"] = None
res = engine.answer(st, "999999")  # باید boss را فعال کند و جوابِ غلط بدهد
assert st.get("boss_answer"), "boss must auto-activate on old state"
assert res["kind"] in ("wrong", "boss", "won")
print("✓ state قدیمی: boss خودکار فعال شد؛ «پاس» جواب می‌دهد")

# حالتِ بدونِ پازل و بدونِ boss و stage وسط: باید پیامِ واضح بدهد نه crash
st2 = engine.create_game(2, 100, scenario_id="lab")
st2["current_puzzle"] = None
try:
    res2 = engine.answer(st2, "هرچی")
    print("✓ state وسطی:", res2["kind"], "— پیام:", res2["text"][:40])
except engine.EscapeError as e:
    print("✓ پیامِ واضح:", e)
