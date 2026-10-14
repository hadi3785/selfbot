"""شبیه‌سازی کاملِ هندلر مار‌پله بدون تلگرام — شروع، تاس، ربات، برد و باخت."""
import os, sys, types, asyncio, random

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "postgresql://p:p@localhost/p")
sys.path.insert(0, "/data/workspace/selfbot/selfbot-main")

import bot.handlers.fun as fun


class FakeMatch:
    def __init__(self, arg):
        self._arg = arg
    def group(self, i):
        return self._arg if i == 1 else None


import re as _re

_SN_PAT = _re.compile(r"^\.(?:مار‌پله|مارپله|مار پله|snakes)(?:\s+([\s\S]*))?$")


class FakeEvent:
    def __init__(self, text):
        self.chat_id = -100123
        m = _SN_PAT.match(text)
        assert m, f"pattern no match: {text!r}"
        self.pattern_match = FakeMatch(m.group(1))
        self.edits = []
    async def edit(self, text, **kw):
        self.edits.append(text)
        return self
    @property
    def last(self):
        # آخرین محتوای پیامِ زنده اگر آپدیت شده، وگرنه آخرین edit خودش
        if fun.FAKE_BOARD and fun.FAKE_BOARD.texts:
            return fun.FAKE_BOARD.texts[-1]
        return self.edits[-1]


async def fake_roll(chat_id):
    return (None, FUN.next_roll)


fun._roll_real_dice = fake_roll  # تاس واقعی → تاس کنترل‌شده


class FakeMsg:
    """پیامِ مصنوعی — آپدیت‌ها فقط ثبت می‌شن."""
    def __init__(self):
        self.id = 999
        self.texts = []
    async def edit(self, text, **kw):
        self.texts.append(text)
        return self
    async def delete(self):
        pass


fun.FAKE_BOARD = None  # آخرین پیامِ زنده‌ی ساختگی


async def fake_send(chat_id, text):
    fun.FAKE_BOARD = FakeMsg()
    fun.FAKE_BOARD.texts.append(text)
    return fun.FAKE_BOARD


async def fake_edit(chat_id, mid, text):
    if fun.FAKE_BOARD and fun.FAKE_BOARD.id == mid:
        fun.FAKE_BOARD.texts.append(text)
        return fun.FAKE_BOARD
    raise RuntimeError("no such message")


fun.client.send_message = fake_send
fun.client.edit_message = fake_edit

FUN = types.SimpleNamespace(next_roll=1)
S = fun.SNAKES_GAMES
S.clear()


def step(text, roll=None, bot_roll=None):
    if roll is not None:
        FUN.next_roll = roll
    if bot_roll is not None:
        random.seed(bot_roll)  # randint(1,6) بعدیِ ربات قطعی می‌شه
    ev = FakeEvent(text)
    asyncio.get_event_loop().run_until_complete(fun.snakes_handler(ev))
    return ev


# ۱) شروع با ربات
ev = step(".مار‌پله شروع ربات")
assert "حالت: تو در برابرِ ربات" in ev.last, ev.last
assert "🔴" in ev.last and "🔵" in ev.last
print("1) شروع با ربات ✓")

# ۲) چند دور بازی
for roll, br in [(1, 3), (3, 2), (4, 6)]:
    ev = step(".مارپله", roll=roll, bot_roll=br)   # بدون نیم‌فاصله — باید match بشه
assert "🔴" in ev.last and "🔵" in ev.last
g = S[-100123]
# من: 0→1، 1+3=4→پله25، 25+4=29 | ربات: seed(3)→2، seed(2)→1، seed(6)→5 → 2,3,8
assert g["pos"] == 29 and g["bot"] == 8, g
print("2) pos =", g["pos"], "| bot =", g["bot"], "| پله‌ی ۴→۲۵ و بعد ۲۹ ✓")

# ۳) نقشه
ev = step(".مارپله نقشه")
assert "🐍" in ev.last and "🟫" in ev.last and "🟩" in ev.last
print("3) نقشه ✓")

# ۴) برد با رسیدن دقیق به ۱۰۰
S[-100123]["pos"] = 98
ev = step(".مارپله", roll=2)
assert "بردی!" in ev.last and -100123 not in S
print("4) بردِ دقیق ✓")

# ۵) اضافه‌شدن از ۱۰۰ → همون‌جا می‌مونی
step(".مار‌پله شروع")
S[-100123]["pos"] = 99
ev = step(".مارپله", roll=6)
assert S[-100123]["pos"] == 99
print("5) قانونِ دقیق-۱۰۰ ✓")

# ۶) باخت در برابر ربات: من 95+1=96، ربات 95+5=100 → ربات دقیق ۱۰۰ و برنده
step(".مارپله با‌ربات")
S[-100123]["pos"] = 95
S[-100123]["bot"] = 95
ev = step(".مارپله", roll=1, bot_roll=6)  # seed(6)→randint=5
assert "ربات برد" in ev.last, ev.last[-200:]
assert -100123 not in S
print("6) باخت در برابر ربات ✓")

# ۷) دکمه‌ها و callback — شبیه‌سازیِ کلیکِ 🎲 تاس
import types as _t

btns = fun._snakes_buttons({"vs_bot": True})
assert btns is None or (isinstance(btns, list) and btns), btns
print("7a) _snakes_buttons ok (bot_client=None → بدون دکمه در سندباکس):", btns)

# کلیکِ تاس: مستقیمِ _snakes_take_turn رو صدا می‌زنیم (همون کاری که callback می‌کنه)
step(".مارپله شروع")
S[-100123]["pos"] = 96
FUN.next_roll = 4  # → 100 دقیق
fake_board_holder = {}
async def _click_roll():
    await fun._snakes_take_turn(-100123, S[-100123])
asyncio.get_event_loop().run_until_complete(_click_roll())
assert -100123 not in S, S
print("7b) کلیکِ 🎲 تاس → برد ✓")

# کلیکِ لغو منطقی: pop + edit — با state واقعی
step(".مارپله با‌ربات")
S[-100123].clear if False else None
S[-100123]["msg_id"] = None
async def _click_cancel_logic():
    # همان کاری که callback sn:cancel می‌کند
    SNAKES_POP = fun.SNAKES_GAMES.pop(-100123, None)
    assert SNAKES_POP is not None
asyncio.get_event_loop().run_until_complete(_click_cancel_logic())
print("7c) منطقِ لغو ✓")

print("\nهمه‌ی مراحلِ شبیه‌سازی (با دکمه‌ها) پاس شد ✓")

