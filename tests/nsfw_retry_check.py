"""تستِ retry در _is_nsfw_image: خالی/خالی/NSFW → True، همیشه‌خالی → False، خالی/SAFE → False"""
import asyncio
import os
import sys

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "postgresql://p:p@localhost/p")
sys.path.insert(0, "/data/workspace/selfbot/selfbot-main")

import bot.handlers.groupguard as gg


def raw_resp(content):
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}


# تست ۱: خالی، خالی، NSFW → True (۲ تلاش خالی و بعد تشخیص)
calls = {"n": 0}


async def fake_1(raw, *, return_raw=False):
    calls["n"] += 1
    if calls["n"] < 3:
        return raw_resp("")
    return raw_resp("NSFW")


# تست ۲: همیشه خالی → False بعد از ۳ تلاش (fail-open)
calls2 = {"n": 0}


async def fake_2(raw, *, return_raw=False):
    calls2["n"] += 1
    return raw_resp("")


# تست ۳: خالی بعد SAFE → False فوری (۲ تلاش)
calls3 = {"n": 0}


async def fake_3(raw, *, return_raw=False):
    calls3["n"] += 1
    if calls3["n"] == 1:
        return raw_resp("...")
    return raw_resp("SAFE")


# تست ۴: خطای سرویس → False فوری بدون retry
calls4 = {"n": 0}


async def fake_4(raw, *, return_raw=False):
    calls4["n"] += 1
    raise gg.ai.AIRequestError("boom")


loop = asyncio.get_event_loop()


async def main():
    results = []

    gg._classify_image = fake_1
    results.append(("خالی،خالی،NSFW → True", await gg._is_nsfw_image(b"x") is True and calls["n"] == 3))

    gg._classify_image = fake_2
    r2 = await gg._is_nsfw_image(b"x")
    results.append(("همیشه خالی → False بعد ۳ تلاش", r2 is False and calls2["n"] == 3))

    gg._classify_image = fake_3
    r3 = await gg._is_nsfw_image(b"x")
    results.append(("خالی بعد SAFE → False فوری", r3 is False and calls3["n"] == 2))

    gg._classify_image = fake_4
    r4 = await gg._is_nsfw_image(b"x")
    results.append(("خطای سرویس → False فوری", r4 is False and calls4["n"] == 1))

    ok = True
    for name, passed in results:
        print(("✓" if passed else "✗"), name)
        ok = ok and passed
    print("ALL OK" if ok else "FAILED")


loop.run_until_complete(main())
