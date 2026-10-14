"""🎒 Inventory اتاق فرار: آیتم‌ها + ترکیب‌ها.

هر آیتم یک dict با کلیدهای: id/name/emoji/desc/type/usable/combinable/qty.
ترکیب‌ها جدولِ ثابتی است (هر جفتِ معتبر یک خروجی + پیام) — ترکیبِ نامعتبر
پیامِ راهنما می‌دهد نه خطا.
"""
from __future__ import annotations

# ---------- آیتم‌های پایه (بین سناریوها مشترک) ----------
ITEMS: dict[str, dict] = {
    "flashlight": {"name": "چراغ‌قوه", "emoji": "🔦", "desc": "نورِ کم ولی قابل‌اعتماد", "type": "tool", "usable": True, "combinable": True},
    "note": {"name": "یادداشت", "emoji": "📜", "desc": "خط‌هایی ناخوانا روی کاغذِ پاره", "type": "clue", "usable": True, "combinable": True},
    "key": {"name": "کلید کوچک", "emoji": "🔑", "desc": "زنگ‌زده ولی سالم", "type": "key", "usable": True, "combinable": True},
    "puzzle_piece": {"name": "قطعه پازل", "emoji": "🧩", "desc": "قطعه‌ای از تصویری نامعلوم", "type": "part", "usable": False, "combinable": True},
    "coin": {"name": "سکه", "emoji": "🪙", "desc": "قدیمی؛ پشتش عددی حک شده", "type": "tool", "usable": True, "combinable": True},
    "liquid": {"name": "ماده‌ی ناشناخته", "emoji": "🧪", "desc": "مایعی سبز که می‌درخشد", "type": "material", "usable": True, "combinable": True},
    "battery": {"name": "باتری", "emoji": "🔋", "desc": "هنوز کمی شارژ دارد", "type": "part", "usable": False, "combinable": True},
    "rope": {"name": "طناب", "emoji": "🪢", "desc": "محنّر و بلند", "type": "tool", "usable": True, "combinable": True},
    "magnet": {"name": "آهن‌ربا", "emoji": "🧲", "desc": "قوی؛ فلزها را می‌کشد", "type": "tool", "usable": True, "combinable": True},
    "wire": {"name": "سیم", "emoji": "🧵", "desc": "دو سرش لخت شده", "type": "part", "usable": False, "combinable": True},
    "crowbar": {"name": "جراق", "emoji": "🪓", "desc": "برای بازکردنِ چیزی که نمی‌خواهد باز شود", "type": "tool", "usable": True, "combinable": False},
    "codecard": {"name": "کارتِ رمز", "emoji": "💳", "desc": "جدولی از اعداد روی پلاستیک", "type": "clue", "usable": True, "combinable": True},
    "vial": {"name": "ویال خالی", "emoji": "🧫", "desc": "شیشه‌ی کوچکِ دردار", "type": "tool", "usable": False, "combinable": True},
    "tape": {"name": "چسب‌برق", "emoji": "🩹", "desc": "همه‌چیز را با هم نگه می‌دارد", "type": "tool", "usable": False, "combinable": True},
    "handle": {"name": "دسته‌ی فلزی", "emoji": "🪝", "desc": "جدا شده از چیزی", "type": "part", "usable": False, "combinable": True},
    "crystal": {"name": "بلور", "emoji": "💎", "desc": "وقتی نور می‌خورد رنگ عوض می‌کند", "type": "material", "usable": True, "combinable": True},
    "chip": {"name": "تراشه", "emoji": "💾", "desc": "پردازنده‌ای با حروفِ محوشده", "type": "part", "usable": True, "combinable": True},
    "keycard": {"name": "کارتِ دسترسی", "emoji": "🪪", "desc": "کارتی که ردیابِ قرمز دارد", "type": "key", "usable": True, "combinable": True},
    "radio": {"name": "رادیوی مخابراتی", "emoji": "📻", "desc": "بی‌باتری؛ کلیدِ فرکانسش گم است", "type": "tool", "usable": True, "combinable": True},
    "mask": {"name": "ماسکِ فیلتردار", "emoji": "😷", "desc": "فیلترش هنوز تازه است", "type": "tool", "usable": True, "combinable": True},
}

# ---------- ترکیب‌ها: (a, b) → (خروجی، پیام) ----------
COMBINE_RULES: dict[tuple[str, str], tuple[str, str]] = {
    ("flashlight", "battery"): ("flashlight_strong", "🔋 چراغ‌قوه روشن و قوی شد! حالا تاریکی‌ها معنای دیگری دارند."),
    ("magnet", "wire"): ("electromagnet", "🧲 یک آهن‌ربای الکتریکی دست‌ساز! فلزهای پشتِ درها لرزیدند."),
    ("rope", "handle"): ("hook_rope", "🪢 قلابِ طناب‌دار ساختی — می‌توانی چیزی را از بالا بکشی."),
    ("liquid", "vial"): ("vial_full", "🧫 ماده‌ی سبز را داخلِ ویال ریختی — حالا قابلِ حمل است."),
    ("note", "codecard"): ("decoded_note", "📜 کارتِ رمز را روی یادداشت گرفتی؛ حروفِ ناخوانا اعداد شدند!"),
    ("puzzle_piece", "tape"): ("puzzle_fixed", "🧩 قطعه‌ی پازل با چسب سرِ جایش نشست — تصویر نیمه‌کاره کامل‌تر شد."),
    ("chip", "battery"): ("chip_active", "💾 تراشه روشن شد و یه ردیفِ عدد رویش چشمک زد."),
    ("key", "handle"): ("key_tool", "🔑 کلید را روی دسته سوار کردی — یک ابزارِ خلاقانه!"),
    ("radio", "battery"): ("radio_active", "📻 رادیو روشن شد؛ صدای ضبطِ قدیمی‌ای از فرکانسِ ۹۸.۲ می‌آید…"),
    ("rope", "crystal"): ("talisman", "💎 بلور را به طناب بستی — طلسمی که در تاریکی می‌درخشد و راه را نشان می‌دهد."),
}

COMBINED_ITEMS: dict[str, dict] = {
    "flashlight_strong": {"name": "چراغ‌قوه‌ی قوی", "emoji": "🔆", "desc": "هر تاریکی را شکاف می‌دهد", "type": "tool", "usable": True, "combinable": False},
    "electromagnet": {"name": "آهن‌ربای الکتریکی", "emoji": "🧲", "desc": "فلزها را از آن‌سوی مانع می‌کشد", "type": "tool", "usable": True, "combinable": False},
    "hook_rope": {"name": "قلابِ طناب‌دار", "emoji": "🪢", "desc": "برای کشیدنِ چیزهای دور", "type": "tool", "usable": True, "combinable": False},
    "vial_full": {"name": "ویالِ ماده", "emoji": "🧫", "desc": "ماده‌ی درخشانِ قابل‌حمل", "type": "material", "usable": True, "combinable": False},
    "decoded_note": {"name": "یادداشتِ رمزگشایی‌شده", "emoji": "📃", "desc": "اعدادی که بالاخره خوانا شدند", "type": "clue", "usable": True, "combinable": False},
    "puzzle_fixed": {"name": "پازلِ کامل‌شده", "emoji": "🖼", "desc": "تصویری که یک عدد رویش است", "type": "clue", "usable": True, "combinable": False},
    "chip_active": {"name": "تراشه‌ی فعال", "emoji": "🖥", "desc": "اعدادِ چشمک‌زن رویِ تراشه", "type": "clue", "usable": True, "combinable": False},
    "key_tool": {"name": "ابزارِ کلید", "emoji": "🛠", "desc": "کلید با دسته‌ای محکم", "type": "tool", "usable": True, "combinable": False},
    "radio_active": {"name": "رادیوی روشن", "emoji": "🔊", "desc": "فرکانسِ ۹۸.۲: صدایی که راهنمایت است", "type": "clue", "usable": True, "combinable": False},
    "talisman": {"name": "طلسمِ بلورین", "emoji": "🔮", "desc": "در تاریکیِ کامل نورِ آبی می‌پراکند", "type": "tool", "usable": True, "combinable": False},
}


def item_def(item_id: str) -> dict | None:
    """تعریفِ آیتم (پایه یا ترکیبی) یا None."""
    return COMBINED_ITEMS.get(item_id) or ITEMS.get(item_id)


def combine(a: str, b: str) -> tuple[str, str] | None:
    """نتیجه‌ی ترکیب دو آیتم؛ ترتیب مهم نیست. None = نامعتبر."""
    rule = COMBINE_RULES.get((a, b)) or COMBINE_RULES.get((b, a))
    return rule


def add_item(inv: dict[str, int], item_id: str, qty: int = 1) -> None:
    if item_def(item_id) is None:
        raise ValueError(f"آیتمِ ناشناخته: {item_id}")
    inv[item_id] = inv.get(item_id, 0) + qty


def remove_item(inv: dict[str, int], item_id: str, qty: int = 1) -> bool:
    if inv.get(item_id, 0) < qty:
        return False
    inv[item_id] -= qty
    if inv[item_id] <= 0:
        del inv[item_id]
    return True


def has_items(inv: dict[str, int], *item_ids: str) -> bool:
    return all(inv.get(i, 0) > 0 for i in item_ids)


def render_inventory(inv: dict[str, int]) -> str:
    """نمایشِ کوله؛ خالی نبودنِ این متن را هندلر چک می‌کند."""
    lines = []
    for item_id, qty in inv.items():
        d = item_def(item_id) or {"emoji": "❔", "name": item_id if not item_id.startswith("__") else "آیتم ناشناخته"}
        qty_s = f" ×{qty}" if qty > 1 else ""
        lines.append(f"{d['emoji']} {d['name']}{qty_s}")
    return "\n".join(lines) or "(خالی)"
