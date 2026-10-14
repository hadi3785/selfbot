"""۵) سرگرمی: write / type / reverse / mock / dice / coin / random / choose / rps
/ guess / slot / 8ball / love / wyr / quiz / fal"""
import asyncio
import hashlib
import logging
import random
import re
import urllib.parse

import aiohttp
from telethon import errors, events, functions, types
from telethon.tl.custom import Button
from telethon.tl.types import InputMediaDice

from ..config import PREFIX
from ..runtime import client, bot_client, get_http_session
from .. import runtime
from ..repositories import hafez_repo
from ..storage.stats_store import record_error as _record_error
from ..utils import pat
from .. import ai

logger = logging.getLogger(__name__)

@client.on(events.NewMessage(outgoing=True, pattern=pat(["تایپ‌زنده", "write"])))
async def write_handler(event):
    text = event.pattern_match.group(1)
    if not text:
        return await event.edit(f"مثال: `{PREFIX}تایپ‌زنده سلام دنیا`")
    current = ""
    msg = await event.edit("▌")
    for ch in text:
        current += ch
        try:
            await msg.edit(current + "▌")
            await asyncio.sleep(0.05)
        except errors.FloodWaitError as e:
            await asyncio.sleep(e.seconds)
    await msg.edit(current)


@client.on(events.NewMessage(outgoing=True, pattern=pat(["پیش‌تایپ", "type"])))
async def type_handler(event):
    text = event.pattern_match.group(1)
    if not text:
        return await event.edit(f"مثال: `{PREFIX}پیش‌تایپ سلام`")
    await event.delete()
    async with client.action(event.chat_id, "typing"):
        await asyncio.sleep(min(len(text) * 0.05, 5))
    await client.send_message(event.chat_id, text)


@client.on(events.NewMessage(outgoing=True, pattern=pat(["معکوس", "reverse"])))
async def reverse_handler(event):
    text = event.pattern_match.group(1)
    if not text and event.is_reply:
        reply = await event.get_reply_message()
        text = reply.raw_text
    if not text:
        return await event.edit(f"مثال: `{PREFIX}معکوس سلام`")
    await event.edit(text[::-1])


@client.on(events.NewMessage(outgoing=True, pattern=pat(["طنز", "mock"])))
async def mock_handler(event):
    text = event.pattern_match.group(1)
    if not text and event.is_reply:
        reply = await event.get_reply_message()
        text = reply.raw_text
    if not text:
        return await event.edit(f"مثال: `{PREFIX}طنز متن شما`")
    mocked = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(text))
    await event.edit(mocked)


DICE_MAX_ATTEMPTS = 60  # سقف تلاش - میانگین لازم ۶ باره، این حاشیه‌ی امن کافیه


async def _roll_real_dice(chat_id):
    """
    یه تاس واقعی می‌فرسته. برای اطمینان از خوندن درستِ عدد نتیجه، به‌جای اتکا
    به آبجکتی که مستقیم از send_file برمی‌گرده (که بعضی‌وقت‌ها media توش کامل
    پر نشده)، پیام رو یک‌بار دیگه از خودِ سرور تلگرام می‌خونیم.
    """
    sent = await client.send_file(chat_id, InputMediaDice("🎲"))
    fresh = await client.get_messages(chat_id, ids=sent.id)
    value = getattr(getattr(fresh, "media", None), "value", None)
    return fresh, value


@client.on(events.NewMessage(outgoing=True, pattern=pat(["تاس", "dice"])))
async def dice_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    if not arg.isdigit() or not (1 <= int(arg) <= 6):
        return await event.edit(f"مثال: `{PREFIX}تاس 4` (عدد باید بین ۱ تا ۶ باشه)")
    target = int(arg)
    chat_id = event.chat_id
    await event.delete()

    last_value = None
    for _ in range(DICE_MAX_ATTEMPTS):
        try:
            msg, value = await _roll_real_dice(chat_id)
        except errors.FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            continue
        except Exception as e:
            _record_error()
            return await client.send_message(chat_id, f"❌ خطا در ارسال تاس: {e}")

        last_value = value
        if value == target:
            return  # تاس با عدد درست موند، تمام

        try:
            await msg.delete()
        except Exception:
            pass
        await asyncio.sleep(0.5)

    await client.send_message(
        chat_id,
        f"❌ بعد از {DICE_MAX_ATTEMPTS} تلاش نتونستم عدد {target} رو بیارم "
        f"(آخرین عددی که اومد: {last_value})",
    )


@client.on(events.NewMessage(outgoing=True, pattern=pat(["شیرخط", "coin"], arg=False)))
async def coin_handler(event):
    result = random.choice(["🦁 شیر", "✍️ خط"])
    await event.edit(f"🪙 {result}")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["تصادفی", "random"])))
async def random_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    nums = arg.split()
    if len(nums) != 2 or not all(n.lstrip("-").isdigit() for n in nums):
        return await event.edit(f"مثال: `{PREFIX}تصادفی 1 100`")
    lo, hi = int(nums[0]), int(nums[1])
    if lo > hi:
        lo, hi = hi, lo
    await event.edit(f"🎯 عدد تصادفی: **{random.randint(lo, hi)}**")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["انتخاب", "choose"])))
async def choose_handler(event):
    arg = event.pattern_match.group(1)
    if not arg:
        return await event.edit(f"مثال: `{PREFIX}انتخاب پیتزا, برگر, سوشی`")
    options = [o.strip() for o in re.split(r",|\|", arg) if o.strip()]
    if len(options) < 2:
        options = [o.strip() for o in arg.split() if o.strip()]
    if len(options) < 2:
        return await event.edit("حداقل ۲ گزینه لازمه (با کاما یا فاصله جداشون کن)")
    await event.edit(f"🎲 انتخاب شد: **{random.choice(options)}**")


_RPS_CHOICES = {
    "سنگ": "🪨", "rock": "🪨",
    "کاغذ": "📄", "paper": "📄",
    "قیچی": "✂️", "scissors": "✂️",
}
_RPS_CANONICAL = {"سنگ": "سنگ", "rock": "سنگ", "کاغذ": "کاغذ", "paper": "کاغذ", "قیچی": "قیچی", "scissors": "قیچی"}
_RPS_BEATS = {"سنگ": "قیچی", "قیچی": "کاغذ", "کاغذ": "سنگ"}


@client.on(events.NewMessage(outgoing=True, pattern=pat(["سنگ‌کاغذقیچی", "rps"])))
async def rps_handler(event):
    arg = (event.pattern_match.group(1) or "").strip().lower()
    if arg not in _RPS_CANONICAL:
        return await event.edit(f"مثال: `{PREFIX}سنگ‌کاغذقیچی سنگ` (یا کاغذ/قیچی)")
    user_choice = _RPS_CANONICAL[arg]
    bot_choice = random.choice(["سنگ", "کاغذ", "قیچی"])
    if user_choice == bot_choice:
        result = "🤝 مساوی شد!"
    elif _RPS_BEATS[user_choice] == bot_choice:
        result = "🎉 بردی!"
    else:
        result = "😅 باختی!"
    await event.edit(
        f"شما: {_RPS_CHOICES[user_choice]} {user_choice}\n"
        f"من: {_RPS_CHOICES[bot_choice]} {bot_choice}\n\n"
        f"{result}"
    )


GUESS_GAMES = {}  # chat_id -> {"target": int, "max": int, "attempts": int} - بازیِ فعالِ هر چت
_MAX_GAMES = 100  # حداکثر تعداد بازی‌های هم‌زمان (جلوگیری از memory leak)


@client.on(events.NewMessage(outgoing=True, pattern=pat(["حدس", "guess"])))
async def guess_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    chat_id = event.chat_id
    parts = arg.split()
    sub = parts[0].lower() if parts else ""

    if not arg or sub in ("شروع", "start"):
        max_n = 100
        if len(parts) > 1 and parts[1].isdigit():
            max_n = max(10, min(int(parts[1]), 1_000_000))
        # جلوگیری از memory leak: اغه تعداد بازی‌ها از حداکثر رد شد، قدیمی‌ها رو پاک کن
        if len(GUESS_GAMES) >= _MAX_GAMES:
            oldest_keys = list(GUESS_GAMES.keys())[:_MAX_GAMES // 2]
            for k in oldest_keys:
                GUESS_GAMES.pop(k, None)
        GUESS_GAMES[chat_id] = {"target": random.randint(1, max_n), "max": max_n, "attempts": 0}
        return await event.edit(
            f"🎯 یه عدد بین ۱ تا {max_n} توی ذهنم انتخاب کردم.\n"
            f"حدس بزن: `{PREFIX}حدس <عدد>` — برای لغو: `{PREFIX}حدس لغو`"
        )

    if sub in ("لغو", "cancel", "stop"):
        if GUESS_GAMES.pop(chat_id, None) is not None:
            return await event.edit("🚫 بازی لغو شد")
        return await event.edit("بازی‌ای در حال اجرا نیست")

    if not arg.lstrip("-").isdigit():
        return await event.edit(f"مثال: اول `{PREFIX}حدس شروع` بعد `{PREFIX}حدس 50`")

    game = GUESS_GAMES.get(chat_id)
    if not game:
        return await event.edit(f"بازی‌ای شروع نشده. اول بزن: `{PREFIX}حدس شروع`")

    guess = int(arg)
    game["attempts"] += 1
    if guess == game["target"]:
        attempts = game["attempts"]
        del GUESS_GAMES[chat_id]
        return await event.edit(f"🎉 درست حدس زدی! عدد **{guess}** بود (با {attempts} تلاش)")
    if not (1 <= guess <= game["max"]):
        game["attempts"] -= 1  # حدسِ خارج از بازه، به‌عنوان تلاش واقعی حساب نشه
        return await event.edit(f"عدد باید بین ۱ تا {game['max']} باشه")
    hint = "بالاتر برو 🔼" if guess < game["target"] else "پایین‌تر بیا 🔽"
    await event.edit(f"❌ نه. {hint} (تلاش شماره {game['attempts']})")


_SLOT_EMOJIS = ["🍒", "🍋", "🍇", "🍉", "⭐", "7️⃣", "🔔"]


@client.on(events.NewMessage(outgoing=True, pattern=pat(["اسلات", "slot"], arg=False)))
async def slot_handler(event):
    reels = [random.choice(_SLOT_EMOJIS) for _ in range(3)]
    result = " | ".join(reels)
    if reels[0] == reels[1] == reels[2]:
        msg = "🎉 جکپات! هر سه یکی شدن!"
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        msg = "✨ دوتاش یکی شدن، یه‌کم شانس آوردی!"
    else:
        msg = "😅 این دفعه نه، شانس بعدی!"
    await event.edit(f"🎰 [ {result} ]\n{msg}")


_MAGIC8BALL_ANSWERS = [
    "بله، مطمئنم ✅", "به احتمال زیاد آره", "علائم می‌گن بله",
    "آره، ولی شک نکن که باید تلاش هم بکنی", "قطعاً همینطوره",
    "بعیده", "من که بهش شک دارم", "نه، فکر نکنم", "قطعاً نه ❌",
    "الان نمی‌تونم بگم، دوباره بپرس 🌀", "روی این حساب نکن",
    "آینده مبهمه، بعداً بپرس", "تمرکز کن و دوباره بپرس",
]


@client.on(events.NewMessage(outgoing=True, pattern=pat(["جادوگر", "8ball"])))
async def magic8ball_handler(event):
    q = event.pattern_match.group(1)
    if not q and event.is_reply:
        reply = await event.get_reply_message()
        q = reply.raw_text
    if not q:
        return await event.edit(f"مثال: `{PREFIX}جادوگر فردا هوا خوبه؟`")
    answer = random.choice(_MAGIC8BALL_ANSWERS)
    await event.edit(f"🔮 سوال: {q}\nپاسخ جادوگر: **{answer}**")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["عشق‌سنج", "love"])))
async def love_calc_handler(event):
    arg = event.pattern_match.group(1)
    if not arg:
        return await event.edit(f"مثال: `{PREFIX}عشق‌سنج علی و سارا`")
    names = re.split(r"\s+و\s+|\s*[+&]\s*", arg, maxsplit=1)
    if len(names) != 2 or not all(n.strip() for n in names):
        words = arg.split()
        if len(words) < 2:
            return await event.edit(f"مثال: `{PREFIX}عشق‌سنج علی و سارا`")
        names = [words[0], " ".join(words[1:])]
    a, b = names[0].strip(), names[1].strip()
    # نتیجه بر اساس هش دو اسم محاسبه می‌شه، پس برای یه جفتِ ثابت همیشه یکسانه
    key = "|".join(sorted([a.lower(), b.lower()]))
    percent = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % 101
    if percent >= 80:
        note = "عالیه! 💞"
    elif percent >= 50:
        note = "بدک نیست 🙂"
    elif percent >= 20:
        note = "یه‌کم ضعیفه 😅"
    else:
        note = "شاید دوستیِ ساده بهتر باشه 😬"
    filled = percent // 10
    bar = "❤️" * filled + "🤍" * (10 - filled)
    await event.edit(f"💘 {a} + {b}\n{bar}\n**{percent}%** — {note}")


_WYR_PROMPTS = [
    # اصلی
    ("همیشه یک ساعت زودتر همه‌جا برسی", "همیشه یک ساعت دیرتر همه‌جا برسی"),
    ("بتونی پرواز کنی", "بتونی نامرئی بشی"),
    ("همیشه گرمت باشه", "همیشه سردت باشه"),
    ("پول زیاد ولی وقت کم داشته باشی", "وقت زیاد ولی پول کم داشته باشی"),
    ("هر روز پیتزا بخوری", "هر روز سوشی بخوری"),
    ("بتونی گذشته رو ببینی", "بتونی آینده رو ببینی"),
    ("توی جنگل زندگی کنی", "توی وسط شهر شلوغ زندگی کنی"),
    ("همیشه حقیقت رو بشنوی، حتی تلخ", "همیشه چیزی که دوست داری رو بشنوی"),
    ("بتونی ذهن بقیه رو بخونی", "بتونی هر زبونی رو بلد باشی"),
    ("هیچ‌وقت خسته نشی", "هیچ‌وقت گرسنه نشی"),
    # قدرت‌ها و ابرقهرمانی
    ("بتونی زمان رو متوقف کنی", "بتونی زمان رو برگردونی"),
    ("قدرت فوق‌العاده داشته باشی ولی تنها باشی", "قدرت معمولی داشته باشی ولی دوستان زیاد"),
    ("بتونی هر شبی که بخوای رویای دلخواهت رو ببینی", "هیچ‌وقت خواب نبینی و همیشه خواب راحت داشته باشی"),
    ("قدرت پرواز با سرعت کم", "قدرت دویدن با سرعت نور"),
    ("بتونی به حیوونا حرف بزنی", "بتونی به هر زبون انسانی حرف بزنی"),
    ("نامرئی بشی فقط شب‌ها", "پرواز کنی فقط روزها"),
    ("بتونی هر چیزی رو با فکر جابه‌جا کنی", "بتونی هر چیزی رو با لمس آتیش بزنی"),
    ("قدرت شفای خودت رو داشته باشی", "قدرت شفای دیگران رو داشته باشی"),
    ("بتونی سایز خودتو کوچیک کنی", "بتونی سایز خودتو بزرگ کنی"),
    ("قدرت کنترل آب داشته باشی", "قدرت کنترل باد داشته باشی"),
    # غذا و خوراکی
    ("تا آخر عمر فقط کباب بخوری", "تا آخر عمر فقط پیتزا بخوری"),
    ("هیچ‌وقت نتونی شیرینی بخوری", "هیچ‌وقت نتونی غذای شور بخوری"),
    ("غذاهای خیلی تند بخوری", "غذاهای کاملاً بی‌مزه بخوری"),
    ("همه‌ی غذات سرد باشه", "همه‌ی غذات خیلی داغ باشه"),
    ("فقط صبحونه بخوری تا آخر عمر", "فقط شام بخوری تا آخر عمر"),
    ("چای همیشه در دسترست باشه ولی بدون قند", "قهوه همیشه در دسترست باشه ولی تلخ"),
    ("هیچ‌وقت گشنه نشی ولی طعم غذا حس نکنی", "همیشه گشنه باشی ولی هر غذایی خوشمزه‌ترین چیز دنیا باشه"),
    ("فقط با دست غذا بخوری", "فقط با نی غذا بخوری"),
    ("آب‌میوه‌ی طبیعی رایگان تا آخر عمر", "قهوه‌ی مجانی تا آخر عمر"),
    ("هر روز آش رشته بخوری", "هر روز قورمه‌سبزی بخوری"),
    # زندگی روزمره و سبک زندگی
    ("صبح‌ها زود بیدار بشی ولی سرحال باشی", "دیر بیدار بشی ولی همیشه خسته باشی"),
    ("خونه‌ی بزرگ دور از شهر", "آپارتمان کوچیک وسط شهر"),
    ("همیشه پیاده بری سرکار", "همیشه با ترافیک سنگین بری سرکار"),
    ("هر روز باران ببارید", "هیچ‌وقت باران نباره"),
    ("توی گرمای شدید زندگی کنی", "توی سرمای شدید زندگی کنی"),
    ("همیشه تنها زندگی کنی", "همیشه با هم‌خونه زندگی کنی"),
    ("هیچ‌وقت نیاز به خواب نداشته باشی", "هیچ‌وقت نیاز به غذا نداشته باشی"),
    ("همیشه توی صف بمونی", "همیشه دیر برسی و صف رو از دست بدی"),
    ("هر روز صبح دویدن کنی", "هر شب یک ساعت پیاده‌روی کنی"),
    ("خونه‌ای با استخر داشته باشی", "خونه‌ای با باغ بزرگ داشته باشی"),
    # تکنولوژی
    ("گوشیت همیشه شارژ کم داشته باشه", "گوشیت همیشه اینترنت کند داشته باشه"),
    ("هیچ‌وقت نتونی پیام صوتی بفرستی", "هیچ‌وقت نتونی استیکر بفرستی"),
    ("یک هفته بدون اینترنت", "یک هفته بدون تلویزیون"),
    ("همیشه گوشیت رینگ صدا کنه", "همیشه گوشیت روی حالت بی‌صدا گیر کنه"),
    ("رمز عبورهات رو یادت بره", "همیشه با کپچا گیر کنی"),
    ("لپ‌تاپ خیلی قوی ولی بدون اینترنت", "اینترنت خیلی سریع ولی لپ‌تاپ ضعیف"),
    ("هر اپلیکیشنی که نصب کنی پر از تبلیغ باشه", "هر اپلیکیشنی که نصب کنی حجم خیلی زیادی بگیره"),
    ("بتونی هر فیلمی رو رایگان ببینی ولی با کیفیت پایین", "فقط یک فیلم با کیفیت عالی ببینی ولی پولی"),
    ("هوش مصنوعیِ شخصیت داشته باشه ولی گاهی اشتباه کنه", "هوش مصنوعیِ خیلی دقیق باشه ولی خشک و بی‌روح"),
    ("همیشه باتری پاوربانکت پر باشه", "همیشه سیم شارژرت همراهت باشه"),
    # حیوانات
    ("سگ نگه داری", "گربه نگه داری"),
    ("پرنده‌ی خونگی داشته باشی", "ماهی تزئینی داشته باشی"),
    ("بتونی مثل عقاب ببینی", "بتونی مثل سگ بو بکشی"),
    ("با یه شیر دوست بشی", "با یه پلنگ دوست بشی"),
    ("بتونی زیر آب مثل ماهی نفس بکشی", "بتونی روی زمین مثل پرنده پرواز کنی"),
    # سفر و ماجراجویی
    ("سفر به کوهستان", "سفر به ساحل"),
    ("سفر به گذشته‌ی تاریخی", "سفر به آینده‌ی دور"),
    ("دور دنیا با قطار", "دور دنیا با کشتی"),
    ("چادر زدن توی طبیعت", "اقامت توی هتل پنج‌ستاره"),
    ("سفر تنها", "سفر گروهی"),
    ("زندگی توی یه جزیره‌ی دورافتاده", "زندگی توی یه کلان‌شهر شلوغ"),
    ("سفر بدون برنامه‌ریزی", "سفر با برنامه‌ی دقیق از قبل"),
    ("رفتن به فضا", "رفتن به اعماق اقیانوس"),
    # پول و کار
    ("حقوق بالا با کار سخت", "حقوق متوسط با کار راحت"),
    ("رئیس خودت باشی با درآمد نامشخص", "کارمند باشی با درآمد ثابت"),
    ("پول زیاد یک‌باره ولی بعدش هیچی", "پول کم ولی هر ماه ثابت تا آخر عمر"),
    ("شغلی که دوستش داری با حقوق کم", "شغلی که ازش خوشت نمیاد با حقوق زیاد"),
    ("همیشه دورکار باشی", "همیشه توی دفتر کار کنی"),
    ("رئیس سخت‌گیر با تیم خوب", "رئیس خوب با تیم بد"),
    # روابط و اجتماعی
    ("یک دوست خیلی صمیمی داشته باشی", "چند تا دوست معمولی داشته باشی"),
    ("همیشه راستشو بگی حتی اگه بد باشه", "گاهی دروغ مصلحتی بگی"),
    ("مهمونیِ بزرگ و شلوغ", "دورهمیِ کوچیک و صمیمی"),
    ("همیشه توی جمع باشی", "بیشتر وقتت رو تنها باشی"),
    ("دوستی که همیشه دیر میاد", "دوستی که همیشه لغو می‌کنه"),
    ("همه چیزتو با یه نفر در میون بذاری", "چیزی رو با هیچکس در میون نذاری"),
    # سرگرمی و فرهنگ
    ("فیلم دیدن", "کتاب خوندن"),
    ("موسیقی گوش دادن", "پادکست گوش دادن"),
    ("بازی کامپیوتری", "بازی فکری روی میز"),
    ("کنسرت زنده", "سینمای خانگی"),
    ("فیلم ترسناک", "فیلم کمدی"),
    ("رمان عاشقانه", "رمان علمی‌تخیلی"),
    ("نقاشی کردن", "آواز خوندن"),
    ("رقصیدن جلوی جمع", "آواز خوندن جلوی جمع"),
    # فرضی و خنده‌دار
    ("همیشه با صدای بلند حرف بزنی", "همیشه خیلی آروم حرف بزنی"),
    ("هیچ‌وقت نخندی", "همیشه بی‌موقع بخندی"),
    ("هر دفعه عطسه کنی رعد و برق بزنه", "هر دفعه خمیازه بکشی چراغ‌ها خاموش بشن"),
    ("بتونی فقط دروغ بگی", "بتونی فقط راست بگی"),
    ("موهات همیشه رنگ عوض کنه", "چشمات همیشه رنگ عوض کنه"),
    ("هر روز لباس یکسان بپوشی", "هر روز مجبور باشی لباس عجیب بپوشی"),
    ("صدات مثل کارتون بشه", "قدت نصف بشه"),
    ("همیشه بوی نون تازه بدی", "همیشه بوی قهوه بدی"),
    ("بتونی فقط با آواز حرف بزنی", "بتونی فقط با رقص حرف بزنی"),
    ("سایه‌ت زندگی مستقل داشته باشه", "انعکاست توی آینه حرف بزنه"),
    # ورزش
    ("فوتبال بازی کنی", "بسکتبال بازی کنی"),
    ("شنا کردن", "دوچرخه‌سواری"),
    ("ورزش انفرادی", "ورزش تیمی"),
    ("کوهنوردی", "دویدن ماراتن"),
    ("یوگا", "بدنسازی"),
    # آب‌وهوا و فصل
    ("زندگی توی تابستون همیشگی", "زندگی توی زمستون همیشگی"),
    ("بهار همیشگی", "پاییز همیشگی"),
    ("برف‌بازی", "شنا توی دریا"),
    ("هوای مه‌آلود", "هوای آفتابیِ خیلی داغ"),
    # تصمیم‌های بزرگ زندگی
    ("زودتر ازدواج کنی", "دیرتر ازدواج کنی"),
    ("توی شهر زادگاهت بمونی", "به یه کشور دیگه مهاجرت کنی"),
    ("دنبال علاقه‌ت بری با ریسک بالا", "شغل امن انتخاب کنی با ریسک کم"),
    ("خانواده‌ی بزرگ داشته باشی", "خانواده‌ی کوچیک داشته باشی"),
    ("همیشه توی یه شهر زندگی کنی", "هر چند سال یه‌بار جابه‌جا بشی"),
]


@client.on(events.NewMessage(outgoing=True, pattern=pat(["این‌یا‌اون", "wyr"], arg=False)))
async def wyr_handler(event):
    a, b = random.choice(_WYR_PROMPTS)
    await event.edit(f"🤔 **این یا اون؟**\n\n1️⃣ {a}\n\nیا\n\n2️⃣ {b}")


# ---------------------------------------------------------------------------
# کوییز عمومی — با Open Trivia Database (opentdb.com، رایگان و بدون کلید)
# ---------------------------------------------------------------------------

QUIZ_GAMES = {}   # chat_id -> {"correct": int (۱ تا ۴), "answer_text": str}
QUIZ_SCORES = {}  # chat_id -> {"correct": int, "total": int} - فقط توی حافظه (ری‌استارت پاک می‌شه)
_MAX_QUIZ_GAMES = 50
_MAX_QUIZ_SCORES = 200

_QUIZ_TRANSLATE_SYSTEM_PROMPT = (
    "شما مترجمی هستید که سوالِ کوییزهای انگلیسی رو به فارسیِ روان و طبیعی "
    "ترجمه می‌کنه. اسم‌های خاص (افراد، مکان‌ها، فیلم‌ها، بازی‌ها و...) رو "
    "همون‌طور نگه دار یا فقط تلفظِ فارسیش رو بنویس. خروجی رو دقیقاً و فقط "
    "در همون قالبی که خواسته شده بده، بدون هیچ توضیحِ اضافه."
)


async def _translate_quiz(category: str, question: str, options: list[str]):
    """
    دسته/سوال/گزینه‌های کوییز رو (که از OpenTDB انگلیسی میان) با هسته‌ی
    هوش‌مصنوعیِ داخلیِ ربات (همون bot/ai.py که `.پرسش` ازش استفاده می‌کنه)
    به فارسی ترجمه می‌کنه. اگه AI غیرفعال باشه، خطا بده، یا خروجی قابلِ
    پارس‌کردن نباشه، None برمی‌گردونه (یعنی نسخه‌ی انگلیسیِ اصلی نمایش داده بشه)
    - هیچ‌وقت کوییز رو به‌خاطرِ خطای ترجمه از کار نمی‌ندازه.
    """
    prompt = (
        f"دسته: {category}\n"
        f"سوال: {question}\n"
        "گزینه‌ها:\n"
        + "\n".join(f"{i}) {opt}" for i, opt in enumerate(options, start=1))
        + "\n\n"
        "همه‌ی این‌ها رو به فارسیِ روان ترجمه کن. خروجی رو دقیقاً به همین "
        "قالب بده (فقط ترجمه، خط به خط، بدونِ هیچ توضیحِ اضافه):\n"
        "دسته: <ترجمه>\n"
        "سوال: <ترجمه>\n"
        + "\n".join(f"{i}) <ترجمه>" for i in range(1, len(options) + 1))
    )
    try:
        answer = await ai.ask_ai(
            [
                {"role": "system", "content": _QUIZ_TRANSLATE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
    except (ai.AIDisabledError, ai.AIRequestError):
        return None
    if not answer:
        return None

    t_category = None
    t_question = None
    t_options = {}
    for line in answer.splitlines():
        line = line.strip()
        m_cat = re.match(r"^دسته\s*[:：]\s*(.+)$", line)
        m_q = re.match(r"^سوال\s*[:：]\s*(.+)$", line)
        m_opt = re.match(r"^(\d+)\s*[)\.]\s*(.+)$", line)
        if m_cat:
            t_category = m_cat.group(1).strip()
        elif m_q:
            t_question = m_q.group(1).strip()
        elif m_opt:
            idx = int(m_opt.group(1))
            t_options[idx] = m_opt.group(2).strip()

    if not t_question or len(t_options) != len(options):
        return None
    try:
        ordered_options = [t_options[i] for i in range(1, len(options) + 1)]
    except KeyError:
        return None
    return (t_category or category), t_question, ordered_options


@client.on(events.NewMessage(outgoing=True, pattern=pat(["کوییز", "quiz"])))
async def quiz_handler(event):
    """
    `.کوییز` یه سوالِ چهارگزینه‌ایِ تصادفی از Open Trivia Database می‌گیره،
    `.کوییز <۱ تا ۴>` به سوالِ فعالِ همون چت جواب می‌ده.
    """
    arg = (event.pattern_match.group(1) or "").strip()
    chat_id = event.chat_id

    if arg.isdigit() and 1 <= int(arg) <= 4:
        game = QUIZ_GAMES.get(chat_id)
        if not game:
            return await event.edit(
                f"سوالِ فعالی نیست. بزن `{PREFIX}کوییز` تا یه سوالِ جدید بیاد."
            )
        chosen = int(arg)
        del QUIZ_GAMES[chat_id]
        if chat_id not in QUIZ_SCORES and len(QUIZ_SCORES) >= _MAX_QUIZ_SCORES:
            oldest_keys = list(QUIZ_SCORES.keys())[:_MAX_QUIZ_SCORES // 2]
            for k in oldest_keys:
                QUIZ_SCORES.pop(k, None)
        score = QUIZ_SCORES.setdefault(chat_id, {"correct": 0, "total": 0})
        score["total"] += 1
        if chosen == game["correct"]:
            score["correct"] += 1
            return await event.edit(
                f"✅ درسته! جواب «{game['answer_text']}» بود.\n"
                f"📊 امتیازِ این چت: {score['correct']}/{score['total']}"
            )
        return await event.edit(
            f"❌ نه. جوابِ درست، گزینه‌ی {game['correct']} («{game['answer_text']}») بود.\n"
            f"📊 امتیازِ این چت: {score['correct']}/{score['total']}"
        )

    await event.edit("🎲 در حالِ گرفتنِ سوال...")
    try:
        session = await get_http_session()
        async with session.get(
            "https://opentdb.com/api.php",
            params={"amount": 1, "type": "multiple", "encode": "url3986"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            data = await r.json(content_type=None)
    except errors.FloodWaitError:
        raise
    except Exception:
        _record_error()
        return await event.edit("❌ خطا در ارتباط با سرویسِ کوییز (opentdb.com)")

    if data.get("response_code") != 0 or not data.get("results"):
        return await event.edit("⚠️ سوالی پیدا نشد، دوباره امتحان کن")

    q = data["results"][0]
    unquote = urllib.parse.unquote
    category = unquote(q.get("category", ""))
    question = unquote(q.get("question", ""))
    correct = unquote(q.get("correct_answer", ""))
    options = [unquote(a) for a in q.get("incorrect_answers", [])] + [correct]
    random.shuffle(options)
    correct_index = options.index(correct) + 1

    # نمایشِ سوال/گزینه‌ها به فارسی (اگه AI فعال باشه و ترجمه جواب بده)؛
    # correct_index از رویِ متنِ اصلیِ انگلیسی حساب شده و دست‌نخورده می‌مونه،
    # چون فقط متنِ نمایشی عوض می‌شه نه ترتیبِ گزینه‌ها.
    await event.edit("🌐 در حالِ ترجمه...")
    translated = await _translate_quiz(category, question, options)
    if translated:
        display_category, display_question, display_options = translated
    else:
        display_category, display_question, display_options = category, question, options

    # جلوگیری از memory leak: دقیقاً هم‌الگو با GUESS_GAMES - اگه تعداد بازی‌های
    # هم‌زمان از حداکثر رد شد، نیمی از قدیمی‌ترین‌ها رو پاک کن
    if len(QUIZ_GAMES) >= _MAX_QUIZ_GAMES:
        oldest_keys = list(QUIZ_GAMES.keys())[:_MAX_QUIZ_GAMES // 2]
        for k in oldest_keys:
            QUIZ_GAMES.pop(k, None)
    QUIZ_GAMES[chat_id] = {"correct": correct_index, "answer_text": display_options[correct_index - 1]}

    lines = [f"❓ **کوییز** — _{display_category}_", "", display_question, ""]
    for i, opt in enumerate(display_options, start=1):
        lines.append(f"{i}) {opt}")
    lines.append("")
    lines.append(f"جواب رو با `{PREFIX}کوییز <عدد>` بده")
    await event.edit("\n".join(lines))


# ---------------------------------------------------------------------------
# فال حافظ — از PostgreSQL (جدولِ hafez_poems)، نه import در لحظه
# ---------------------------------------------------------------------------
# دیتا با `scripts/seed_hafez.py` (یک‌بار، خارج از خودِ ربات) پر می‌شه؛ اینجا
# فقط یه ردیفِ رندوم می‌خونیم - نه importِ زمانِ‌اجرا، نه pip، نه شبکه.

@client.on(events.NewMessage(outgoing=True, pattern=pat(["فال", "hafez"], arg=False)))
async def hafez_fal_handler(event):
    """یه فالِ حافظِ تصادفی از جدولِ hafez_poems (PostgreSQL) می‌گیره."""
    try:
        row = await hafez_repo.random_poem()
    except Exception:
        _record_error()
        logger.exception("خطا در خوندنِ فال از دیتابیس")
        return await event.edit("❌ خطا در ارتباط با دیتابیس")

    if row is None:
        return await event.edit(
            "⚠️ جدولِ فال هنوز خالیه. یه‌بار (فقط یه‌بار، نه هر دفعه) از روی "
            "سرور این رو اجرا کن:\n"
            "`pip install hafez && python scripts/seed_hafez.py`\n\n"
            "بعدش `.فال` همیشه مستقیم از دیتابیسِ خودمون جواب می‌ده، بدون "
            "هیچ نصب/شبکه‌ای."
        )

    body = f"🔮 **فالِ حافظ**\n\n{row.poem}"
    if row.interpretation:
        body += f"\n\n💬 **تفسیر:**\n{row.interpretation}"
    await event.edit(body)



# ---------------------------------------------------------------------------
# بازی‌های جدید: کلمه‌ساز (زنجیره)، حدسِ کلمه، مار‌پله، حافظه‌ی اعداد
# ---------------------------------------------------------------------------

# ----------------------------------------------------- ۱) کلمه‌ساز (زنجیره) ---
WORDCHAIN_GAMES = {}  # chat_id -> {"last_word": str, "used": set[str], "count": int}
_MAX_WORDCHAIN_GAMES = 50

# اسم‌های متداولِ فارسی برای شروعِ راحتِ بازی (همه با حروفِ جدا)
_WORDCHAIN_STARTERS = [
    "تبریز", "کاشان", "نیشابور", "همدان", "سوادکوه", "رشت", "گرگان", "اراک",
    "لیمو", "هویج", "انار", "سیب", "خرما", "زردآلو", "گلابی", "آلبالو",
    "کتاب", "تاق", "کوهنورد", "دریا", "آسمان", "باران", "گلدان", "مدرسه",
]

_PERSIAN_LETTERS = "آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی"


@client.on(events.NewMessage(outgoing=True, pattern=pat(["کلمه‌ساز", "کلمه ساز", "کلمهساز", "wordchain", "زنجیره"])))
async def wordchain_handler(event):
    """
    زنجیره‌کلمات فارسی: با یه کلمه شروع می‌کنیم؛ هر کلمه‌ی جدید باید با
    حرفِ آخرِ کلمه‌ی قبلی شروع بشه. این بازی خودِ کاربر با بات (یا دو نفره
    توی گروه) بازی می‌کنه.
    """
    arg = (event.pattern_match.group(1) or "").strip()
    chat_id = event.chat_id

    if not arg or arg.lower() in ("شروع", "start"):
        if len(WORDCHAIN_GAMES) >= _MAX_WORDCHAIN_GAMES:
            oldest = list(WORDCHAIN_GAMES.keys())[:_MAX_WORDCHAIN_GAMES // 2]
            for k in oldest:
                WORDCHAIN_GAMES.pop(k, None)
        starter = random.choice(_WORDCHAIN_STARTERS)
        WORDCHAIN_GAMES[chat_id] = {"last_word": starter, "used": {starter}, "count": 1}
        return await event.edit(
            f"🔗 **کلمه‌ساز شروع شد!**\n"
            f"کلمه‌ی اول: **{starter}**\n\n"
            f"حالا یه کلمه بگو که با «{starter[-1]}» شروع بشه:\n"
            f"`{PREFIX}کلمه‌ساز <کلمه>` — لغو: `{PREFIX}کلمه‌ساز لغو`"
        )

    if arg.lower() in ("لغو", "cancel", "stop"):
        if WORDCHAIN_GAMES.pop(chat_id, None) is not None:
            return await event.edit("🚫 کلمه‌ساز لغو شد")
        return await event.edit("بازی‌ای در حال اجرا نیست")

    game = WORDCHAIN_GAMES.get(chat_id)
    if not game:
        return await event.edit(f"اول بازی رو شروع کن: `{PREFIX}کلمه‌ساز شروع`")

    word = arg.strip().strip("‌")  # نیم‌فاصله‌های ابتدا/انتها رو هم بگیره
    if not word:
        return await event.edit("کلمه رو بنویس")
    if word in game["used"]:
        return await event.edit(f"♻️ «{word}» قبلاً گفته شده! یه کلمه‌ی جدید بگو")
    if word[0] != game["last_word"][-1]:
        return await event.edit(
            f"❌ «{word}» باید با «{game['last_word'][-1]}» شروع بشه (حرفِ آخرِ «{game['last_word']}»)"
        )
    game["used"].add(word)
    game["count"] += 1
    last_letter = word[-1]
    # نوبتِ بات: یه حرف تصادفی برای ادامه نمی‌تونیم «بلد باشیم»؛ پس بازی‌کننده
    # ادامه می‌ده و بات فقط داوره - شمارنده رو نشون بده
    game["last_word"] = word
    await event.edit(
        f"✅ «{word}» قبوله! (تعداد: {game['count']})\n"
        f"حالا با «{last_letter}» ادامه بده"
    )


# ------------------------------------------------------ ۲) حدسِ کلمه (واژه) ---
WORDGUESS_GAMES = {}  # chat_id -> {"word": str, "hint": str, "revealed": list[str], "wrong": int}
_MAX_WORDGUESS_GAMES = 50

_WORDGUESS_WORDS = [
    ("کتابخونه", "جایی که کتاب توش زیاده"),
    ("دوچرخه", "وسیله‌ی دوردَوَزه با دو تا چرخ"),
    ("آفتاب‌گردون", "گلی که همیشه رو به خورشیده"),
    ("زمستان", "سردترین فصل سال"),
    ("تلویزیون", "جعبه‌ای که فیلم توش پخش می‌شه"),
    ("قهوه", "نوشیدنیِ تلخِ بیدارکننده"),
    ("ماشین‌لباسشویی", "لباس‌ها رو خودکار می‌شوره"),
    ("فوتبال", "ورزشِ محبوب با توپ و دروازه"),
    ("زنبور عسل", "عسل می‌سازه و نیش هم داره"),
    ("قطار", "روی ریل حرکت می‌کنه"),
    ("آشپزخونه", "جایی که غذا پخت می‌شه"),
    ("چتر", "توی بارون بازش می‌کنی"),
    ("قهوه‌ای", "رنگِ شکلات"),
    ("شتر", "کشتیِ بیابون"),
    ("ماهی", "توی آب زندگی می‌کنه"),
    ("هدیه", "چیزی که با کادوپیچ می‌دی"),
    ("دستگاهِ چاپ", "متن رو روی کاغذ تکرار می‌کنه"),
    ("بارگاه", "جای آرامگاهِ پادشاهان"),
]

_WORDGUESS_MAX_WRONG = 6


@client.on(events.NewMessage(outgoing=True, pattern=pat(["حدس‌کلمه", "حدس کلمه", "حدسکلمه", "واژه", "hangman"])))
async def wordguess_handler(event):
    """
    حدسِ کلمه (مثل hangman): یه کلمه‌ی پنهان با جای‌خالی‌ها نشون داده می‌شه؛
    حرف حدس بزن یا کل کلمه رو یکجا بگو. تا ۶ اشتباه مجازِ.
    """
    arg = (event.pattern_match.group(1) or "").strip()
    chat_id = event.chat_id

    if not arg or arg.lower() in ("شروع", "start"):
        if len(WORDGUESS_GAMES) >= _MAX_WORDGUESS_GAMES:
            oldest = list(WORDGUESS_GAMES.keys())[:_MAX_WORDGUESS_GAMES // 2]
            for k in oldest:
                WORDGUESS_GAMES.pop(k, None)
        word, hint = random.choice(_WORDGUESS_WORDS)
        WORDGUESS_GAMES[chat_id] = {
            "word": word,
            "hint": hint,
            "revealed": ["_"] * len(word),
            "wrong": 0,
        }
        masked = " ".join("＿" for _ in word)
        return await event.edit(
            f"🔤 **حدسِ کلمه**\n"
            f"راهنما: {hint}\n"
            f"کلمه: `{masked}` ({len(word)} حرف)\n\n"
            f"حرف حدس بزن: `{PREFIX}حدس‌کلمه ب` یا کلِ کلمه: `{PREFIX}حدس‌کلمه <کلمه>`\n"
            f"اشتباهِ مجاز: {_WORDGUESS_MAX_WRONG} — لغو: `{PREFIX}حدس‌کلمه لغو`"
        )

    if arg.lower() in ("لغو", "cancel", "stop"):
        game = WORDGUESS_GAMES.pop(chat_id, None)
        if game:
            return await event.edit(f"🚫 لغو شد؛ کلمه «{game['word']}» بود")
        return await event.edit("بازی‌ای در حال اجرا نیست")

    game = WORDGUESS_GAMES.get(chat_id)
    if not game:
        return await event.edit(f"اول شروع کن: `{PREFIX}حدس‌کلمه شروع`")

    guess = arg.strip()
    word = game["word"]
    revealed = game["revealed"]

    if len(guess) == 1:
        # حدسِ یه حرف
        if guess in revealed:
            return await event.edit(f"«{guess}» رو قبلاً زدی")
        if guess in word:
            for i, ch in enumerate(word):
                if ch == guess:
                    revealed[i] = guess
        else:
            game["wrong"] += 1
    elif guess == word:
        # بردِ مستقیم با حدسِ کل کلمه
        del WORDGUESS_GAMES[chat_id]
        return await event.edit(f"🎉 آفرین! کلمه **{word}** بود (بدونِ اشتباه)")
    else:
        game["wrong"] += 1

    if "_" not in revealed:
        del WORDGUESS_GAMES[chat_id]
        return await event.edit(f"🎉 بردی! کلمه **{word}** بود (اشتباه: {game['wrong']})")
    if game["wrong"] >= _WORDGUESS_MAX_WRONG:
        del WORDGUESS_GAMES[chat_id]
        return await event.edit(
            f"💀 باختی! ({_WORDGUESS_MAX_WRONG} اشتباه)\nکلمه **{word}** بود"
        )

    remaining = _WORDGUESS_MAX_WRONG - game["wrong"]
    await event.edit(
        f"🔤 `{' '.join(revealed)}`\n"
        f"اشتباه‌ها: {game['wrong']}/{_WORDGUESS_MAX_WRONG} (باقی‌مونده: {remaining})"
    )


# ------------------------------------------------------------ ۳) مار‌پله ----
SNAKES_GAMES = {}  # chat_id -> {"pos": int, "bot": int | None, "vs_bot": bool}
SNAKES_INLINE_CHATS = {}  # repr(InputBotInlineMessageID) -> chat_id (پیامِ via-bot)
_MAX_SNAKES_GAMES = 50
_SNAKES_GOAL = 100

# پله‌ها (پایین → بالا): خانه‌ی شروعِ پله → مقصد
_SNAKES_LADDERS = {4: 25, 13: 46, 33: 49, 42: 63, 50: 69, 62: 81, 74: 92}
# مارها (سر → دُم): سرِ مار → مقصد
_SNAKES_SNAKES = {27: 5, 40: 3, 43: 18, 54: 31, 66: 45, 76: 58, 89: 53, 99: 41}

_SN_JUMPS = {
    **{cell: ("L", dest) for cell, dest in _SNAKES_LADDERS.items()},
    **{cell: ("S", dest) for cell, dest in _SNAKES_SNAKES.items()},
}


def _snakes_apply(pos: int, roll: int) -> tuple[int, str]:
    """
    حرکتِ یه مهره با قانونِ کامل: ردشدن از ۱۰۰ یعنی همون‌جا می‌مونی (برد فقط
    با رسیدنِ دقیق)، پله پرش به بالا، مار سقوط به پایین.
    خروجی: (موقعیتِ جدید، خطِ توضیح).
    """
    new = pos + roll
    if new > _SNAKES_GOAL:
        return pos, f"🎲 {roll} → بیشتر از {_SNAKES_GOAL} می‌شد؛ همون خانه ({pos}) موندی"
    if new in _SNAKES_LADDERS:
        dest = _SNAKES_LADDERS[new]
        return dest, f"🎲 {roll} → خانه‌ی {new} و 🪜 پله! پریدی به **{dest}**"
    if new in _SNAKES_SNAKES:
        dest = _SNAKES_SNAKES[new]
        return dest, f"🎲 {roll} → خانه‌ی {new} و 🐍 مار! افتادی به **{dest}**"
    return new, f"🎲 {roll} → خانه‌ی **{new}**"


_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def _fa_num(n: int) -> str:
    """تبدیل عدد به رقم‌های فارسی (برای نقشه و نوارِ پیشرفت)."""
    return "".join(_FA_DIGITS[int(d)] for d in str(n))


def _snakes_cell(n: int, markers: dict) -> str:
    """یه سلولِ نقشه: شماره‌ی فارسی + نشانِ گرافیکی. ثابت‌عرض برای ستون‌های مرتب."""
    m = markers.get(n)
    tail = {
        "P": "🔴", "B": "🔵", "X": "🟣",   # تو/ربات/هر دو
        "L": "🪜", "S": "🐍",                # شروعِ پله / سرِ مار
        "Le": "🟩", "Se": "🟫",              # مقصدِ پله / دُمِ مار
        "T": "🏁",                            # خانه‌ی برد
    }.get(m, "·")
    return f"{_fa_num(n):>2}{tail}"


def _snakes_board_text(game: dict, last_line: str = "") -> str:
    """
    نقشه‌ی گرافیکی premium: صفحه‌ی ۱۰×۱۰ با سلول‌های ایموجی‌دار، ردیف‌بندی
    مارپیچی، نوارِ پیشرفت و کارت‌های جمع‌وجورِ مارها/پله‌ها.
    🔴 تو | 🔵 ربات | 🟣 هر دو | 🪜 پله | 🐍 مار | 🏁 خانه‌ی برد | · خالی
    """
    markers = {cell: kind for cell, (kind, _) in _SN_JUMPS.items()}
    # مقصدِ هر پرش هم روی نقشه باشه: 🟩 تهِ پله، 🟫 دُمِ مار (سر و شروع از قبل هستن)
    for dest in list(_SNAKES_LADDERS.values()):
        markers.setdefault(dest, "Le")
    for dest in list(_SNAKES_SNAKES.values()):
        markers.setdefault(dest, "Se")
    markers[_SNAKES_GOAL] = "T"  # 🏁
    p, b = game.get("pos", 0), game.get("bot")
    if b is not None and b == p and p > 0:
        markers[p] = "X"
    else:
        if p > 0:
            markers[p] = "P"
        if b is not None and b > 0:
            markers[b] = "B"

    # ---------------- صفحه‌ی مارپیچی ۱۰×۱۰ ----------------
    rows = []
    for r in range(10, 0, -1):
        nums = list(range((r - 1) * 10 + 1, r * 10 + 1))
        if r % 2 == 0:
            nums.reverse()
        cells = " ".join(_snakes_cell(n, markers) for n in nums)
        rows.append(cells)
        if r > 1:
            rows.append("─" * 41)
    board = "\n".join(rows)

    # ---------------- نوارِ پیشرفت ----------------
    def bar(pos: int) -> str:
        filled = round(pos / _SNAKES_GOAL * 10)
        return "▰" * filled + "▱" * (10 - filled)

    p_bar, p_pct = bar(p), round(p / _SNAKES_GOAL * 100)
    players = f"🔴 تو  {p_bar} {_fa_num(p_pct)}٪  ({_fa_num(p)}/{_fa_num(_SNAKES_GOAL)})"
    if b is not None:
        b_pct = round(b / _SNAKES_GOAL * 100)
        players += f"\n🔵 ربات  {bar(b)} {_fa_num(b_pct)}٪  ({_fa_num(b)}/{_fa_num(_SNAKES_GOAL)})"

    # ---------------- کارت‌های مار/پله ----------------
    ladders = "  ".join(f"🪜{_fa_num(a)}→🟩{_fa_num(d)}" for a, d in sorted(_SNAKES_LADDERS.items()))
    snakes = "  ".join(f"🐍{_fa_num(a)}→🟫{_fa_num(d)}" for a, d in sorted(_SNAKES_SNAKES.items()))

    parts = [
        "🎲 **مارپله پرمیوم** 🎲",
        "",
        f"```\n{board}\n```",
        players,
        "",
        f"🟩 تهِ پله‌ها (🪜=سرِ پله): {ladders}",
        f"🟫 دُمِ مارها (🐍=سرِ مار): {snakes}",
    ]
    if last_line:
        parts += ["", last_line]
    parts += [
        "",
        f"🎯 با دکمه‌های زیر یا دستور: `{PREFIX}مارپله` تاس | `{PREFIX}مارپله نقشه` | `{PREFIX}مارپله لغو`",
    ]
    return "\n".join(parts)


def _snakes_markup(buttons):
    """لیستِ دکمه‌ها → شیءِ ReplyInlineMarkup برای requestهای خام تلگرام."""
    if not buttons:
        return None
    from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonRow
    return ReplyInlineMarkup(rows=[KeyboardButtonRow(buttons=row) for row in buttons])


def _snakes_buttons(game: dict):
    """دکمه‌های زیرِ پیامِ زنده — فقط وقتی باتِ کمکی وصل باشه واقعی می‌شن."""
    if bot_client is None:
        return None
    row1 = [Button.inline("🎲 تاس", b"sn:roll")]
    if game.get("vs_bot"):
        row1.append(Button.inline("🗺 نقشه", b"sn:map"))
    else:
        row1.append(Button.inline("🗺 نقشه", b"sn:map"))
    row1.append(Button.inline("🚫 لغو", b"sn:cancel"))
    return [row1]


async def _snakes_update(game, chat_id, text: str, fallback_event=None):
    """
    پیامِ زنده: همیشه همون پیامِ صفحه رو آپدیت می‌کنه.
    سه حالت — به ترتیب امتحان می‌شن:
      ۱) پیامِ via-bot (مثل پنل، هر چتی حتی جاهایی که بات اد نیست):
         آپدیت با EditInlineBotMessageRequest از طریق inline_message_id
      ۲) پیامِ عادیِ بات (جاهایی که بات اد هست): edit_message عادی بات
      ۳) اکانتِ خودِ کاربر (بدون دکمه) — همیشه کار می‌کنه
    اگه پیامِ قبلی حذف شده باشه، یه پیامِ جدید می‌سازه.
    """
    buttons = _snakes_buttons(game)

    # --- ۱) پیامِ via-bot: آپدیت با inline_message_id ---
    inline_mid = game.get("inline_msg_id")
    if inline_mid is not None and bot_client is not None:
        try:
            await bot_client(
                functions.messages.EditInlineBotMessageRequest(
                    id=inline_mid, message=text, reply_markup=_snakes_markup(buttons)
                )
            )
            return None  # پیام عادی نیست؛ برگشتِ None طبیعیه
        except Exception:
            pass  # منقضی/حذف شده — از این به بعد مسیرهای پایین

    # --- ۲) پیامِ عادیِ بات ---
    mid = game.get("msg_id")
    if mid and bot_client is not None:
        try:
            return await bot_client.edit_message(chat_id, mid, text, buttons=buttons)
        except Exception:
            pass  # پیام حذف شده/پیدا نشد — پایین دوباره می‌سازیم
    if mid and bot_client is None:
        try:
            return await client.edit_message(chat_id, mid, text)
        except Exception:
            pass
    if bot_client is not None:
        try:
            msg = await bot_client.send_message(chat_id, text, buttons=buttons, link_preview=False)
            game["msg_id"] = getattr(msg, "id", None)
            return msg
        except Exception:
            pass  # بات کمکی نتونست (مثلاً تو گروه نیست) — پایین با اکانت می‌فرستیم
    msg = await client.send_message(chat_id, text)
    game["msg_id"] = getattr(msg, "id", None)
    return msg


@client.on(events.NewMessage(outgoing=True, pattern=pat(["مار‌پله", "مارپله", "مار پله", "snakes"])))
async def snakes_handler(event):
    """
    مار‌پله‌ی ۱۰×۱۰ (۱۰۰ خانه) با صفحه‌ی متنیِ زنده در یک پیام.
    دو حالت: تک‌نفره (`.مارپله شروع`) و در برابرِ ربات (`.مارپله شروع ربات`).
    تاسِ تو واقعیه (InputMediaDice تلگرام)، تاسِ ربات فوری.
    """
    arg = (event.pattern_match.group(1) or "").strip()
    norm = arg.replace("\u200c", "").replace(" ", "").lower()
    chat_id = event.chat_id

    if norm in ("لغو", "cancel", "stop"):
        game = SNAKES_GAMES.pop(chat_id, None)
        if game is not None:
            mid = game.get("msg_id")  # پیامِ زنده هم پاک بشه
            if mid:
                for cl in (bot_client, client):
                    if cl is None:
                        continue
                    try:
                        await cl.delete_messages(chat_id, mid)
                        break
                    except Exception:
                        continue
            await event.edit("🚫 بازیِ مار‌پله لغو شد")
            try:
                await event.delete()
            except Exception:
                pass
            return
        return await event.edit("بازی‌ای در حال اجرا نیست")

    game = SNAKES_GAMES.get(chat_id)

    if norm in ("نقشه", "وضعیت", "board", "صفحه"):
        if not game:
            return await event.edit(f"بازی‌ای در جریان نیست؛ `{PREFIX}مار‌پله شروع`")
        if not game.get("msg_id"):  # بازیِ قدیمی بدون پیامِ زنده — پیامِ جدید بساز
            board = await event.edit(_snakes_board_text(game))
            game["msg_id"] = getattr(board, "id", None)
            return board
        return await _snakes_update(game, chat_id, _snakes_board_text(game))

    if norm in ("شروع", "start", "شروعربات", "ربات", "bot", "دونفره", "شروعدونفره", "با‌ربات", "باربات", "شروع با‌ربات", "شروع باربات", "شروعبا‌ربات", "شروعباربات"):
        vs_bot = norm not in ("شروع", "start")
        if len(SNAKES_GAMES) >= _MAX_SNAKES_GAMES:
            for k in list(SNAKES_GAMES.keys())[:_MAX_SNAKES_GAMES // 2]:
                SNAKES_GAMES.pop(k, None)
        # نگاشتِ via-bot هم سقف داشته باشد تا بازی‌های رهاشده نشت نکنند
        if len(SNAKES_INLINE_CHATS) >= _MAX_SNAKES_GAMES:
            for k in list(SNAKES_INLINE_CHATS.keys())[:_MAX_SNAKES_GAMES // 2]:
                SNAKES_INLINE_CHATS.pop(k, None)
        game = {"pos": 0, "bot": 0 if vs_bot else None, "vs_bot": vs_bot, "msg_id": None}
        SNAKES_GAMES[chat_id] = game
        mode_line = "🤖 **حالت: تو در برابرِ ربات**" if vs_bot else "🧑 **حالتِ تک‌نفره**"
        rules = (
            f"برای برد باید دقیقاً روی {_SNAKES_GOAL} بیفتی؛ اگه بیشتر شدی همون‌جا می‌مونی.\n"
            + ("اگه روی خانه‌ی حریف بیفتی، می‌فرستتش سرِ خونه!\n" if vs_bot else "")
        )
        # ---- ارسالِ نقشه به‌شکل via-bot (مثل پنل) تا دکمه‌ها در «هر چتی» کار کنن ----
        start_text = _snakes_board_text(game, f"🎮 بازیِ جدید شروع شد! {mode_line}\n{rules}")
        if bot_client is not None and runtime.BOT_USERNAME:
            try:
                results = await client.inline_query(runtime.BOT_USERNAME, "snakes")
                if not results:
                    raise RuntimeError("no inline results")
                sent = await results[0].click(chat_id, reply_to=event.reply_to_msg_id, silent=False)
                game["via"] = True
                # id پیامِ via رو برای آپدیت‌های بعدی (قبل از اولین callback) ذخیره کن
                try:
                    for upd in sent.updates if hasattr(sent, "updates") else []:
                        msg = getattr(upd, "message", None)
                        mid = getattr(msg, "id", None)
                        if mid:
                            game["msg_id"] = mid
                            break
                except Exception:
                    logger.debug("استخراجِ msg_id از inline updates شکست خورد", exc_info=True)
                try:
                    await event.delete()
                except Exception:
                    pass
                return sent
            except Exception:
                game["via"] = False  # inline فعال نیست — مسیرهای پایین
        board = await _snakes_update(
            game, chat_id, start_text
        )
        try:  # پیامِ دستور دیگه لازم نیست — نقشه‌ی زنده جایگزینشه
            await event.delete()
        except Exception:
            pass
        return board

    if not norm and game is None:
        return await event.edit(
            f"اول شروع کن: `{PREFIX}مار‌پله شروع` (تک‌نفره) یا `{PREFIX}مار‌پله شروع ربات` (با ربات)"
        )
    if norm:  # ورودیِ ناشناخته
        return await event.edit(
            f"دستورات: `{PREFIX}مار‌پله شروع` | `{PREFIX}مار‌پله شروع ربات` | `{PREFIX}مار‌پله` (تاس) | `{PREFIX}مار‌پله وضعیت` | `{PREFIX}مار‌پله لغو`"
        )

    # ---------------------------------------------- نوبتِ بازی‌کننده (تاس) ---
    await _snakes_take_turn(chat_id, game)


async def _snakes_take_turn(chat_id: int, game: dict):
    """
    یه نوبتِ کامل: تاسِ واقعیِ تلگرام برای بازیکن + حرکت + ربات + آپدیتِ پیامِ زنده.
    هم از دستور `.مارپله` صدا زده می‌شه هم از دکمه‌ی 🎲 تاس (callback).
    """
    value = None
    dice_msg = None
    for attempt in range(5):
        try:
            dice_msg, value = await _roll_real_dice(chat_id)
        except errors.FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            continue
        except Exception:
            _record_error()
            return await _snakes_update(game, chat_id, "❌ خطا در انداختنِ تاس؛ دوباره امتحان کن")
        if isinstance(value, int) and 1 <= value <= 6:
            break
        await asyncio.sleep(1)  # media تاس هنوز کامل نشده؛ دوباره بخون

    try:  # پیامِ تاس اضافیه — چت تمیز بمونه
        if dice_msg:
            await dice_msg.delete()
    except Exception:
        pass

    if not (isinstance(value, int) and 1 <= value <= 6):
        _record_error()
        return await _snakes_update(game, chat_id, "❌ تاس جواب نداد؛ دوباره بزن")

    notes = []
    game["pos"], p_line = _snakes_apply(game["pos"], value)
    notes.append(f"🧑 {p_line}")

    # حذفِ حریف: اگه روی خانه‌ی ربات بیفتی، ربات میره صفر
    if game["vs_bot"] and game["bot"] == game["pos"] and 0 < game["pos"] < _SNAKES_GOAL:
        game["bot"] = 0
        notes.append("💥 ربات رو زدی! رفت سرِ خونه")

    if game["pos"] >= _SNAKES_GOAL:
        del SNAKES_GAMES[chat_id]
        return await _snakes_update(
            game, chat_id,
            _snakes_board_text({"pos": _SNAKES_GOAL, "bot": game.get("bot"), "vs_bot": game["vs_bot"]},
                               "\n".join(notes) + "\n\n🎉 **بردی!**"),
        )

    # ------------------------------------------------- نوبتِ ربات (خودکار) ---
    if game["vs_bot"]:
        bot_roll = random.randint(1, 6)
        game["bot"], b_line = _snakes_apply(game["bot"], bot_roll)
        notes.append(f"🤖 {b_line}")
        if game["bot"] == game["pos"] and 0 < game["pos"] < _SNAKES_GOAL:
            game["pos"] = 0
            notes.append("💥 ربات تو رو زد! برگشتی سرِ خونه")
        if game["bot"] >= _SNAKES_GOAL:
            final = {"pos": game["pos"], "bot": _SNAKES_GOAL, "vs_bot": True}
            del SNAKES_GAMES[chat_id]
            return await _snakes_update(game, chat_id, _snakes_board_text(final, "\n".join(notes) + "\n\n🤖 **ربات برد! دوباره؟** `مار‌پله شروع ربات`"))

    await _snakes_update(game, chat_id, _snakes_board_text(game, "\n".join(notes)))


if bot_client is not None:

    @bot_client.on(events.InlineQuery(pattern=rf"^{re.escape('snakes')}"))
    async def snakes_inline_handler(event):
        """
        مثل پنل: اکانت با inline_query از بات نتیجه می‌گیره و result.click(chat_id)
        همون نقشه (با دکمه‌های واقعیِ بات) رو در «هر چتی» می‌فرسته.
        """
        if runtime.SELF_ID is not None and event.sender_id != runtime.SELF_ID:
            await event.answer([])
            return
        text = _snakes_board_text({"pos": 0, "bot": None, "vs_bot": False}, "🎮 شروع شد! 🎲 تاس بزن")
        builder = event.builder
        result = builder.article(
            title="🐍 مارپله پرمیوم",
            description="نقشه‌ی زنده با دکمه‌های تاس/نقشه/لغو",
            text=text,
            buttons=_snakes_buttons({"vs_bot": False}),
        )
        await event.answer([result])

    @bot_client.on(events.CallbackQuery(pattern=rb"^sn:"))
    async def snakes_callback_handler(event):
        """
        دکمه‌های پیامِ زنده: 🎲 تاس | 🗺 نقشه | 🚫 لغو.
        فقط صاحبِ اکانت اجازه‌ی کلیک داره (بقیه alert می‌گیرن).
        """
        if runtime.SELF_ID is not None and event.sender_id != runtime.SELF_ID:
            await event.answer("🎲 این بازی مالِ صاحبِ اکانته!", alert=True)
            return
        action = (event.data or b"").decode()
        # پیامِ via-bot: برای آپدیت‌های بعدی، inline_message_id رو نگه می‌داریم
        q_msg = getattr(event.query, "msg_id", None)
        chat_id = event.chat_id
        if chat_id is None and q_msg is not None:
            chat_id = SNAKES_INLINE_CHATS.get(repr(q_msg))  # از نگاشتِ via
        game = SNAKES_GAMES.get(chat_id) if chat_id is not None else None
        if game is not None and q_msg is not None:
            game["inline_msg_id"] = q_msg
            SNAKES_INLINE_CHATS[repr(q_msg)] = chat_id

        if action == "sn:cancel":
            if game is not None:
                SNAKES_GAMES.pop(chat_id, None)
                if q_msg is not None:
                    SNAKES_INLINE_CHATS.pop(repr(q_msg), None)
                await event.edit("🚫 بازیِ مار‌پله لغو شد", buttons=None)
            else:
                await event.answer("بازی‌ای در جریان نیست", alert=True)
            return

        if game is None:
            await event.answer("بازی تموم شده؛ `.مارپله شروع` کن", alert=True)
            return

        if action == "sn:map":
            await event.answer()
            return await _snakes_update(game, chat_id, _snakes_board_text(game, "🗺 وضعیت فعلیِ صفحه"))

        if action == "sn:roll":
            await event.answer("🎲 دارم تاس می‌ندازم...")
            try:
                await _snakes_take_turn(chat_id, game)
            except Exception:
                _record_error()
                try:
                    await event.answer("❌ خطا؛ دوباره امتحان کن", alert=True)
                except Exception:
                    pass
            return

        await event.answer()


# ------------------------------------------------------- ۴) حافظه‌ی اعداد ---
MEMORY_GAMES = {}  # chat_id -> {"digits": str, "level": int, "stage": int}
_MAX_MEMORY_GAMES = 50


@client.on(events.NewMessage(outgoing=True, pattern=pat(["حافظه", "memory"])))
async def memory_handler(event):
    """
    بازیِ حافظه‌ی اعداد: یه عدد کوتاه نشون داده می‌شه و بعد پاک می‌شه؛ تو باید
    تکرارش کنی. هر مرحله یه رقم بیشتر. با `حافظه توقف` ذخیره نمی‌شه ولی لیستِ
    رکوردِ این چت نگه داشته می‌شه.
    """
    arg = (event.pattern_match.group(1) or "").strip()
    chat_id = event.chat_id

    # تفکیک از `.حافظه`ِ حافظه‌ی AI (ai_memory.py با همین pattern ثبت شده):
    # بازی فقط «شروع/لغو/عدد» را مصرف می‌کند؛ بقیه برای handlerِ حافظه‌ی AI می‌ماند.
    _sub0 = arg.split()[0].lower() if arg.split() else ""
    if _sub0 not in ("شروع", "start", "لغو", "cancel", "stop") and not arg.lstrip("-").isdigit():
        return None

    if arg.lower() in ("لغو", "cancel", "stop"):
        game = MEMORY_GAMES.pop(chat_id, None)
        if game:
            return await event.edit(f"🚫 لغو شد؛ رکوردت این مرحله بود: **{game['level']} رقم**")
        return await event.edit("بازی‌ای در حال اجرا نیست")

    if arg.lstrip("-").isdigit():
        game = MEMORY_GAMES.get(chat_id)
        if not game:
            return await event.edit(f"اول شروع کن: `{PREFIX}حافظه شروع`")
        if arg == game["digits"]:
            level = game["level"] + 1
            game["level"] = level
            game["digits"] = "".join(random.choice("0123456789") for _ in range(level))
            await event.edit(f"✅ درست بود! مرحله‌ی بعد ({level} رقم)...")
            await asyncio.sleep(2.5)
            msg = await event.respond(f"🧠 به‌خاطر بسپار:\n||{game['digits']}||")
            await asyncio.sleep(max(2.0, level * 0.8))
            return await msg.edit(
                f"⏱ وقتِ پاسخ! عددِ {level} رقمی رو بزن: `{PREFIX}حافظه <عدد>`"
            )
        wrong = game["digits"]
        level = game["level"]
        del MEMORY_GAMES[chat_id]
        return await event.edit(
            f"❌ اشتباه بود! عددِ درست **{wrong}** بود\n"
            f"🏆 رکوردت: **{level} رقم** — دوباره: `{PREFIX}حافظه شروع`"
        )

    if arg.lower() in ("", "شروع", "start"):
        if len(MEMORY_GAMES) >= _MAX_MEMORY_GAMES:
            oldest = list(MEMORY_GAMES.keys())[:_MAX_MEMORY_GAMES // 2]
            for k in oldest:
                MEMORY_GAMES.pop(k, None)
        digits = "".join(random.choice("0123456789") for _ in range(3))
        MEMORY_GAMES[chat_id] = {"digits": digits, "level": 3, "stage": 1}
        msg = await event.edit(f"🧠 **بازیِ حافظه شروع شد!**\nبه‌خاطر بسپار:\n||{digits}||")
        await asyncio.sleep(3.0)
        return await msg.edit(f"⏱ عددِ ۳ رقمی رو بزن: `{PREFIX}حافظه <عدد>`")

    return await event.edit(
        f"مثال: `{PREFIX}حافظه شروع` برای شروع، `{PREFIX}حافظه 12345` برای پاسخ، `{PREFIX}حافظه لغو`"
    )
