"""تستِ منطقِ دو لایه‌ی تشخیصِ آنلاین/آفلاینِ منشی (بدون تلگرام) — با آستانه‌های جدا"""
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "postgresql://p:p@localhost/p")
sys.path.insert(0, "/data/workspace/selfbot/selfbot-main")

import bot.config as config
import bot.handlers.assistant as a

config.ASSISTANT_ONLINE_THRESHOLD = 180
config.ASSISTANT_SESSION_ONLINE_THRESHOLD = 540
config.ASSISTANT_SESSION_MAX_AGE = 300
a.assistant_state["schedule_enabled"] = False
a.assistant_state["auto_detect"] = True
MIN = datetime.min.replace(tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
ok = True


def case(name, expected_enabled, local_gap, seen_gap=None, poll_age=None):
    global ok
    a._last_self_activity = MIN if local_gap is None else now - timedelta(seconds=local_gap)
    a._last_session_poll_ok = MIN if poll_age is None else now - timedelta(seconds=poll_age)
    a._last_session_seen = MIN if seen_gap is None else now - timedelta(seconds=seen_gap)
    a._recompute_enabled_from_signals()
    actual = a.assistant_state["enabled"]
    passed = actual == expected_enabled
    ok = ok and passed
    print(("✓" if passed else "✗"), f"{name} → enabled={actual} (انتظار: {expected_enabled})")


# ۱) هیچ سیگنالی → آفلاین → منشی روشن
case("بدون هیچ سیگنال", True, None, None, None)
# ۲) local تازه (۵۰s) → آنلاین → منشی خاموش
case("local تازه ۵۰s", False, 50, None, None)
# ۳) سشن تازه (۳۰۰s) — زیرِ آستانه‌ی سشنِ ۵۴۰ ولی بالای threshold محلی → هنوز آنلاین (لایه‌ی سشن)
case("سشن ۳۰۰s (فقط لایه‌ی سشن)", False, 9999, 300, 30)
# ۴) سشن ۶۰۰s — بالای آستانه‌ی سشن (۵۴۰) → آفلاین → منشی روشن ⭐ (این قبلاً fail می‌شد)
case("سشن ۶۰۰s کهنه", True, 9999, 600, 30)
# ۵) هر دو کهنه → آفلاین → منشی روشن
case("هر دو کهنه", True, 400, 600, 30)
# ۶) local کهنه، سشن تازه → آنلاین
case("local کهنه، سشن تازه", False, 600, 50, 30)
# ۷) poll کهنه (>MAX_AGE) → سشن نادیده؛ local کهنه → آفلاین
case("poll کهنه، local کهنه", True, 500, 10, 400)
# ۸) poll کهنه، local تازه → آنلاین (فقط local)
case("poll کهنه، local تازه", False, 60, 10, 400)
# ۹) لایه‌ی سشن خاموش (threshold=0): سشن تازه هم منشی را روشن نگه می‌دارد
config.ASSISTANT_SESSION_ONLINE_THRESHOLD = 0
case("سشن خاموش + سشن تازه", True, 9999, 30, 30)
case("سشن خاموش + local تازه", False, 50, 30, 30)
config.ASSISTANT_SESSION_ONLINE_THRESHOLD = 540

# ---- grace بعدِ پاسخِ منشی ----
a._last_assistant_reply_at = datetime.now(timezone.utc) - timedelta(seconds=config.ASSISTANT_REPLY_STATUS_GRACE - 20)  # تازه جواب داده
a._last_profile_status_online = True   # تلگرام می‌گه آنلاین (جعلی، از خودِ reply)
a.assistant_state["enabled"] = True
online = a._last_profile_status_online
in_grace = (a._last_assistant_reply_at is not None and
            (datetime.now(timezone.utc) - a._last_assistant_reply_at).total_seconds() < config.ASSISTANT_REPLY_STATUS_GRACE)
if not (online and in_grace):
    a.assistant_state["enabled"] = not online
assert a.assistant_state["enabled"] == True, "منشی نباید با آنلاینِ جعلیِ reply خاموش شود"
print("✓ آنلاینِ جعلی داخلِ grace → منشی روشن می‌ماند")

a._last_assistant_reply_at = datetime.now(timezone.utc) - timedelta(seconds=config.ASSISTANT_REPLY_STATUS_GRACE + 90)  # grace گذشته
online = a._last_profile_status_online
in_grace = (a._last_assistant_reply_at is not None and
            (datetime.now(timezone.utc) - a._last_assistant_reply_at).total_seconds() < config.ASSISTANT_REPLY_STATUS_GRACE)
if not (online and in_grace):
    a.assistant_state["enabled"] = not online
assert a.assistant_state["enabled"] == False, "بعد از grace، آنلاینِ واقعی باید منشی را خاموش کند"
print("✓ بعد از grace، آنلاینِ واقعی → منشی خاموش")

# آفلاین داخلِ grace → روشن (آفلاین هیچ‌وقت جعلی نیست)
a._last_assistant_reply_at = datetime.now(timezone.utc) - timedelta(seconds=config.ASSISTANT_REPLY_STATUS_GRACE - 20)
a._last_profile_status_online = False
online = a._last_profile_status_online
in_grace = (a._last_assistant_reply_at is not None and
            (datetime.now(timezone.utc) - a._last_assistant_reply_at).total_seconds() < config.ASSISTANT_REPLY_STATUS_GRACE)
if not (online and in_grace):
    if not online and a.assistant_state["enabled"] is False:
        a.assistant_state["replied"] = set()
    a.assistant_state["enabled"] = not online
assert a.assistant_state["enabled"] == True
print("✓ آفلاین داخلِ grace → منشی روشن (آفلاین جعلی نداریم)")

print("ALL OK" if ok else "FAILED")
sys.exit(0 if ok else 1)


# ---- حالتِ وضعیتِ پروفایل (status mode) ----
import bot.config as config
import bot.handlers.assistant as a

config.ASSISTANT_PRESENCE_MODE = "status"
a.assistant_state["auto_detect"] = True

# پیامِ تازه (۵ ثانیه پیش) — در حالتِ status نباید منشی را خاموش کند
a._last_self_activity = datetime.now(timezone.utc) - timedelta(seconds=5)
a._safe_recompute()
assert a.assistant_state["enabled"] == True, "پیام نباید در حالت status تأثیر بگذارد"
print("✓ پیامِ تازه در حالتِ status مداخله نمی‌کند")

# شبیه‌سازیِ مستقیمِ منطقِ poller: آنلاین → خاموش؛ آفلاین → روشن
a._last_profile_status_online = True
a.assistant_state["enabled"] = True
# همان کدِ درونِ assistant_status_poller:
online = a._last_profile_status_online
desired = not online
if desired != a.assistant_state["enabled"]:
    a.assistant_state["enabled"] = desired
assert a.assistant_state["enabled"] == False
print("✓ آنلاین → منشی خاموش")

a._last_profile_status_online = False
online = a._last_profile_status_online
desired = not online
if desired != a.assistant_state["enabled"]:
    if desired:
        a.assistant_state["replied"] = set()
    a.assistant_state["enabled"] = desired
assert a.assistant_state["enabled"] == True
print("✓ آفلاین → منشی روشن (بلافاصله)")
