"""تستِ منطقِ خالصِ کپی کانال (بدونِ Telethon/DB): پارس، دسته‌بندی با آلبوم، خطاها، سقفِ روزانه."""
import asyncio
import datetime as dt
import importlib.util
import os
import sys
from types import SimpleNamespace as NS

# بدونِ import کردنِ bot/__init__ (که config/telethon می‌خواد) ماژولِ خالص رو لود می‌کنیم
_p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bot", "channel_copy_core.py")
_spec = importlib.util.spec_from_file_location("channel_copy_core", _p)
core = importlib.util.module_from_spec(_spec)
sys.modules["channel_copy_core"] = core
_spec.loader.exec_module(core)


def msg(i, gid=None, service=False):
    return NS(id=i, grouped_id=gid, action=("x" if service else None))


async def agen(items):
    for it in items:
        yield it


def batches(items, size):
    async def run():
        return [b async for b in core.iter_batches(agen(items), size)]
    return asyncio.run(run())


def test_parse_chat_ref():
    assert core.parse_chat_ref("@durov") == ("username", "durov")
    assert core.parse_chat_ref("https://t.me/durov/123") == ("username", "durov")
    assert core.parse_chat_ref("t.me/c/1234567/89") == ("id", -1001234567)
    assert core.parse_chat_ref("-1001234567") == ("id", -1001234567)
    assert core.parse_chat_ref("1234567") == ("id", 1234567)
    for bad in ("", "a", "https://t.me/+AbCdEf", "t.me/joinchat/xyz", "no way!"):
        try:
            core.parse_chat_ref(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_parse_start_args():
    assert core.parse_start_args(["@a", "@b"]) == ("@a", "@b", 0, True)
    assert core.parse_start_args(["@a", "@b", "از", "100"]) == ("@a", "@b", 99, True)
    assert core.parse_start_args(["@a", "@b", "با‌نام"]) == ("@a", "@b", 0, False)
    assert core.parse_start_args(["@a", "@b", "بانام", "from", "5"]) == ("@a", "@b", 4, False)
    for bad in (["@a"], ["@a", "@b", "@c"], ["@a", "@b", "از"], ["@a", "@b", "از", "x"]):
        try:
            core.parse_start_args(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_batches_size_and_order():
    out = batches([msg(i) for i in range(1, 46)], 20)
    assert [len(b.ids) for b in out] == [20, 20, 5]
    assert [b.max_id for b in out] == [20, 40, 45]
    assert sum((b.ids for b in out), []) == list(range(1, 46))


def test_album_never_split():
    items = [msg(1), msg(2), msg(3, gid=7), msg(4, gid=7), msg(5, gid=7), msg(6)]
    out = batches(items, 4)
    # آلبوم (۳-۵) نباید نصف بشه: دسته‌ی اول [1,2]، دسته‌ی دوم [3,4,5,6]
    assert [b.ids for b in out] == [[1, 2], [3, 4, 5, 6]]
    out = batches([msg(i, gid=9) for i in range(1, 11)] + [msg(11)], 5)
    assert [len(b.ids) for b in out] == [10, 1]  # آلبومِ ۱۰تایی حتی بزرگ‌تر از batch_size کامل می‌مونه


def test_batch_cap_100():
    out = batches([msg(i) for i in range(1, 251)], 1000)
    assert max(len(b.ids) for b in out) == 100


def test_service_messages():
    out = batches([msg(1), msg(2, service=True), msg(3)], 20)
    assert len(out) == 1 and out[0].ids == [1, 3] and out[0].skipped == 1 and out[0].max_id == 3
    out = batches([msg(1, service=True), msg(2, service=True)], 20)
    assert out[0].ids == [] and out[0].skipped == 2 and out[0].max_id == 2
    # سرویسی بعد از آلبوم نباید max_id رو از آلبومِ ناتمام جلو ببره
    out = batches([msg(1, gid=5), msg(2, gid=5), msg(3, service=True), msg(4)], 2)
    assert [b.ids for b in out] == [[1, 2], [4]]
    assert out[0].max_id == 2 or out[0].max_id == 3  # آلبوم داخلِ دسته‌ست، پس جلو رفتن مشکلی نداره


class FloodWaitError(Exception):
    seconds = 42


class ChatForwardsRestrictedError(Exception):
    pass


class PeerFloodError(Exception):
    pass


class MessageIdInvalidError(Exception):
    pass


def test_classify():
    assert core.classify_error(FloodWaitError()) == ("wait", 42)
    assert core.classify_error(ChatForwardsRestrictedError())[0] == "fatal"
    assert core.classify_error(PeerFloodError())[0] == "fatal"
    assert core.classify_error(MessageIdInvalidError()) == ("skip", None)
    assert core.classify_error(RuntimeError("CHAT_FORWARDS_RESTRICTED"))[0] == "fatal"
    assert core.classify_error(RuntimeError("A wait of 17 seconds is required (FLOOD_WAIT_17)")) == ("wait", 17)
    assert core.classify_error(ValueError("boom")) == ("retry", None)


def test_window():
    now = dt.datetime(2026, 10, 14, 12, 0, tzinfo=dt.timezone.utc)
    assert core.check_window(now, None, 0, 100, 20) == (0.0, now, 0)
    assert core.check_window(now, now, 50, 0, 20)[0] == 0.0  # بدونِ سقف
    assert core.check_window(now, now, 50, 100, 20)[0] == 0.0
    wait, st, cnt = core.check_window(now + dt.timedelta(hours=1), now, 90, 100, 20)
    assert abs(wait - 23 * 3600) < 1 and st == now and cnt == 90
    # بعد از ۲۴ ساعت پنجره ریست می‌شه
    later = now + dt.timedelta(hours=25)
    assert core.check_window(later, now, 100, 100, 20) == (0.0, later, 0)


def test_format_status():
    job = dict(id=3, source_title="A", dest_title="B", source_id=1, dest_id=2, status="running",
               copied=50, skipped=2, total_hint=200, last_id=77, drop_author=True, last_error="")
    txt = core.format_status(job, {"state": "مکث", "t0": 0, "copied0": 0, "now": 100})
    assert "#3" in txt and "26%" in txt and "زمانِ باقی‌مانده" in txt and "#77" in txt


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in fns:
        f()
        print("ok", f.__name__)
    print(f"{len(fns)} tests passed")
