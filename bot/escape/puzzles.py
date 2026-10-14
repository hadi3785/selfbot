"""🧩 معماسازِ اتاق فرار: پازل‌های seed-دار با جواب‌های متغیر.

هر پازل یک dict است:
  id, kind, prompt (متنِ نمایشی), answer (رشته‌ی استانداردشده),
  hints: [سه سطح], reward (امتیاز), requires (آیتم‌های لازم برای پاس‌دادن، اختیاری)
پاسخ‌ها همیشه با `_norm` مقایسه می‌شوند (فارسی/انگلیسی/فاصله/ارقام).
seed باعث می‌شود در هر Session جواب‌ها متفاوت باشند ولی قابل‌حل بمانند —
سرنخِ هر پازل داخلِ همان سناریو (متنیِ inspection) جاسازی می‌شود.
"""
from __future__ import annotations

import random

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_fa(num: int) -> str:
    return str(num).translate(PERSIAN_DIGITS)


def _norm(s: str) -> str:
    """نرمال‌سازی پاسخ: ارقام فارسی→انگلیسی، حذفِ فاصله/صفرِ ابتدا، حروف کوچک."""
    s = (s or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    s = " ".join(s.lower().split())
    return s


def check_answer(puzzle: dict, raw: str) -> bool:
    return _norm(raw) == _norm(str(puzzle["answer"]))


# --------------------------------------------------------------- سازنده‌ها --
def make_code_puzzle(rng: random.Random, scenario_id: str) -> dict:
    """رمز عددی سه‌رقمی؛ هر رقم سرنخِ جدا دارد — همه‌ی سرنخ‌ها عینی و داخلِ خودِ متن."""
    a, b, c = (rng.randint(1, 9) for _ in range(3))
    # رقم اول: تعدادِ قفل‌های 🔒 که در همین خط رسم می‌شوند (قابلِ شمارش، عینی)
    a_items = " ".join(["🔒"] * a)
    year = f"1{b}{rng.randint(0, 9)}{rng.randint(0, 9)}"
    prompts = [
        (f"روی در، {a_items} قفلِ کوچک 🔒 چسبیده است. «نخستین رقم، تعدادِ این قفل‌هاست.»",
         a, "قفل‌های روی در را بشمار."),
        (f"روی کاغذی چسبیده: «رقمِ دوم = سالِ ساخته‌شدنِ این مکان، بدونِ قرن» (سال: {year})",
         b, f"سالِ {year[2:]}؟ رقمِ دومِ رمز = دومین رقمِ همین سال است."),
        (f"ساعتِ دیواری روی {to_fa(c)}:00 متوقف مانده. «رقمِ سوم = عقربه‌ی ساعت»",
         c, "ساعت را نگاه کن؛ عقربه‌ی کوچک روی چه عددی ایستاده؟"),
    ]
    rng.shuffle(prompts)
    lines = [p for p, _, _ in prompts]
    hints = [h for _, _, h in prompts]
    return {
        "id": f"code_{scenario_id}",
        "kind": "code",
        "prompt": "🔐 یک قفلِ سه‌رقمی:\n" + "\n".join(lines),
        "answer": f"{a}{b}{c}",
        "hints": hints,
        "reward": 120,
    }


def make_pattern_puzzle(rng: random.Random, scenario_id: str) -> dict:
    """الگوی عددی: دنباله‌ای که رابطه‌اش از سه عضو اول کشف می‌شود."""
    step = rng.randint(2, 6)
    start = rng.randint(1, 9)
    seq = [start + step * i for i in range(4)]
    answer = start + step * 4
    return {
        "id": f"pattern_{scenario_id}",
        "kind": "pattern",
        "prompt": (
            "🧮 روی دیوار با گچ نوشته شده:\n"
            f"{to_fa(seq[0])} → {to_fa(seq[1])} → {to_fa(seq[2])} → {to_fa(seq[3])} → ؟"
        ),
        "answer": str(answer),
        "hints": [
            "اختلافِ ثابتی بینِ اعداد هست.",
            f"هر بار {to_fa(step)} تا اضافه می‌شود.",
            f"جواب: {to_fa(seq[3])} + {to_fa(step)}",
        ],
        "reward": 90,
    }


def make_logic_puzzle(rng: random.Random, scenario_id: str) -> dict:
    """منطقی: سه قفل با شماره؛ هر قفل می‌گوید «قفلِ درست، قفلِ k است».
    دقیقاً یکی از جملات درست است → شماره‌ی درستِ یکتا از خودِ متن استخراج می‌شود."""
    # perm: هر جمله i مدعی است جواب = perm[i]. جوابِ سازگارِ یکتا = مقداری که دقیقاً یک‌بار در perm است
    x, y = 1, 2
    if rng.random() < 0.5:
        x, y = 2, 1
    pattern = rng.choice([[x, x, y], [x, y, y], [y, x, y], [y, y, x], [x, y, x]])
    perm = pattern
    # جواب = مقداری که دقیقاً یک‌بار در ادعاها آمده (تنها تفسیرِ سازگارِ «دقیقاً یکی درست»)
    answer = str(x if perm.count(x) == 1 else y)
    nums = ["۱", "۲", "۳"]
    lines = [
        f"{nums[i]}️⃣ «قفلِ درست، قفلِ {to_fa(perm[i])} است.»" for i in range(3)
    ]
    return {
        "id": f"logic_{scenario_id}",
        "kind": "logic",
        "prompt": (
            "🚪 سه قفلِ شماره‌دار روی در است و هرکدام جمله‌ای حک دارند. "
            "دقیقاً یکی از جملات درست است:\n"
            + "\n".join(lines)
            + "\nکدام قفل باز می‌کند؟ (شماره)"
        ),
        "answer": answer,
        "hints": [
            "دقیقاً یکی از جملات درست است — بقیه دروغ.",
            "فرض کن هر قفل جواب است و جمله‌هایش را بسنج.",
            f"جواب: قفلِ {to_fa(answer)}",
        ],
        "reward": 110,
    }

def make_order_puzzle(rng: random.Random, scenario_id: str) -> dict:
    """ترتیبِ اشیا: دکمه‌ها با چیدمانِ تصادفی؛ جواب = شماره‌های دکمه‌ها به‌ترتیبِ کهنه→نو."""
    objs = [
        ("🥚", "تخم‌مرغِ چینی"),
        ("🕯", "شمعِ نیم‌سوخته"),
        ("🕰", "ساعتِ جیبی"),
        ("📻", "رادیوی قدیمی"),
    ]
    shown = objs[:]
    rng.shuffle(shown)  # چیدمانِ دکمه‌ها تصادفی است
    answer = " ".join(str(shown.index(o) + 1) for o in objs)  # کهنه→نو
    prompt = (
        "🎛 چهار دکمه با علامتِ اشیاست. زیرش نوشته: «از کهنه‌ترین به نوترین فشار بده»\n"
        + " | ".join(f"{i+1}. {e} {n}" for i, (e, n) in enumerate(shown))
        + "\n(ترتیب را با شماره بده: مثل 2 1 4 3)"
    )
    return {
        "id": f"order_{scenario_id}",
        "kind": "order",
        "prompt": prompt,
        "answer": answer,
        "hints": [
            "تخم‌مرغِ چینی هزاران سال قدمت دارد.",
            "شمع قبل از رادیو ساخته شده و ساعتِ جیبی بینِ آن‌هاست.",
            f"جواب: {' '.join(to_fa(d) for d in answer.split())}",
        ],
        "reward": 100,
    }

def make_riddle_puzzle(rng: random.Random, scenario_id: str) -> dict:
    """معمای متنی (چیستان) — جوابِ تک‌کلمه‌ای."""
    riddles = [
        ("هرچه ازش برداری بزرگ‌تر می‌شود. چیست؟", "چاله", ["چیزی که حفر می‌شود.", "با بیل ساخته می‌شود.", "چاله"]),
        ("کلید دارد ولی قفل ندارد؛ فضا دارد ولی خانه ندارد. چیست؟", "پیانو", ["صدا دارد.", "سیاه و سفید است.", "پیانو"]),
        ("هرچه روشن‌تر باشد، سایه‌ها بیشتر دیده می‌شوند. چه چیزی؟", "نور", ["با چشم دیده می‌شود.", "از چراغ می‌آید.", "نور"]),
    ]
    q, a, hints = rng.choice(riddles)
    return {
        "id": f"riddle_{scenario_id}",
        "kind": "riddle",
        "prompt": f"❓ چیستانِ حک‌شده روی در:\n«{q}»",
        "answer": a,
        "hints": hints,
        "reward": 80,
    }


def make_choice_puzzle(rng: random.Random, scenario_id: str) -> dict:
    """انتخابِ درست بین مسیرها؛ یک سرنخِ محیطی راهنمایی می‌کند."""
    right = rng.randint(1, 3)
    cue = {1: "بوی نم از آن‌سو می‌آید", 2: "هوای آن‌سو گرم‌تر است", 3: "صدای قطره از آن‌سو می‌آید"}[right]
    return {
        "id": f"choice_{scenario_id}",
        "kind": "choice",
        "prompt": (
            "🚦 سه راهرو؛ فقط یکی به خروجی می‌رسد:\n"
            "1️⃣ راهرویِ تاریک\n2️⃣ راهرویِ باریک\n3️⃣ راهرویِ سرپوشیده\n"
            f"سرنخ: «{cue}» — کدام؟ (شماره)"
        ),
        "answer": str(right),
        "hints": [
            "سرنخِ محیطی را جدی بگیر.",
            "آب یعنی راهِ خروج به سطحِ زمین.",
            f"پاسخ: {to_fa(right)}",
        ],
        "reward": 90,
    }


PUZZLE_MAKERS = [
    make_code_puzzle,
    make_pattern_puzzle,
    make_logic_puzzle,
    make_order_puzzle,
    make_riddle_puzzle,
    make_choice_puzzle,
]


def build_stage_puzzles(rng: random.Random, scenario_id: str, n_stages: int) -> list[dict]:
    """برای هر مرحله یک پازل؛ بدونِ تکرار تا جایی که ممکن است."""
    makers = PUZZLE_MAKERS[:]
    rng.shuffle(makers)
    puzzles = []
    for i in range(n_stages - 1):  # آخرین مرحله boss است
        maker = makers[i % len(makers)]
        puzzles.append(maker(rng, f"{scenario_id}{i}"))
    return puzzles
