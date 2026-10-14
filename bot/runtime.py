"""
وضعیتِ زمانِ‌اجرا: نمونه‌ی TelegramClient، سشن مشترک HTTP، و اطلاعاتی که فقط
موقع اتصال (main()) پر می‌شن. همه‌ی ماژول‌های دیگه از اینجا `client` رو
import می‌کنن.
"""
import time
import aiohttp
from telethon import TelegramClient

from . import config

# اعتبارسنجیِ زودهنگامِ متغیرهای ضروری: به‌جای ValueErrorِ خامِ Telethon وسطِ
# استارتاپ (که روی Railway فقط یک crash-loop بی‌توضیح می‌سازد)، پیامِ واضح و
# راهنمادار بده و با exit-code غیرصفر خارج شو.
import sys

if not config.API_ID or not config.API_HASH:
    print(
        "❌ Missing environment variable: API_ID / API_HASH\n"
        "   از my.telegram.org → API development tools بگیر و در Railway\n"
        "   Variables (یا فایلِ .env) ست کن. سپس دوباره دیپلوی کن.",
        file=sys.stderr,
    )
    raise SystemExit(1)
if not config.SESSION_STRING:
    print(
        "⚠️ SESSION_STRING خالی است — از فایلِ selfbot_session استفاده می‌شود؛\n"
        "   روی Railway این یعنی سشنِ احرازنشده! با `python generate_session.py`\n"
        "   یک StringSession بساز و در متغیرِ SESSION_STRING بگذار.",
        file=sys.stderr,
    )

if config.SESSION_STRING:
    from telethon.sessions import StringSession
    try:
        _session = StringSession(config.SESSION_STRING)
    except Exception:
        # SESSION_STRING خراب/بریده/کپی‌نشده کامل — به‌جای ValueErrorِ خامِ
        # Telethon ("Not a valid string") پیامِ عملیاتیِ واضح بده.
        print(
            "❌ Telegram session is invalid.\n"
            "   مقدارِ SESSION_STRING معتبر نیست (خراب/ناقص). یک سشنِ جدید بساز:\n"
            "   `python generate_session.py` و کلِ خروجی را در SESSION_STRING بگذار.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    client = TelegramClient(
        _session,
        config.API_ID,
        config.API_HASH,
        device_model="selfbot-py",     # قابل‌شناسایی در «سشن‌های فعال» تلگرام
        system_version="linux",
        app_version="1.0",
        # --- پایداری اتصال ---
        catch_up=True,           # آپدیت‌های حینِ قطعی بعد از وصل‌شدن تحویل داده بشن
        auto_reconnect=True,     # (پیش‌فرض هم True است؛ صریح نوشتیم)
        retry_delay=2,           # بینِ تلاش‌های reconnect فقط ۲ ثانیه (پیش‌فرض ۱)
        request_retries=5,       # هر درخواست تا ۵ بار دوباره امتحان می‌شه
        connection_retries=10,   # اتصالِ اولیه/مجدد تا ۱۰ بار (پیش‌فرض ۵)
        flood_sleep_threshold=120,  # FloodWait تا ۱۲۰ ثانیه خودکار صبر می‌کنه (پیش‌فرض ۶۰)
        use_ipv6=False,          # روی Railway فقط IPv4 مطمئن‌تره
    )
else:
    client = TelegramClient("selfbot_session", config.API_ID, config.API_HASH)

# بات کمکیِ پنل (اختیاری) - فقط اگه BOT_TOKEN ست شده باشه ساخته می‌شه.
# نکته: این کلاینت هنوز به تلگرام وصل نیست؛ فقط توی main() با bot_client.start()
# با bot_token لاگین/وصل می‌شه. تا اون موقع bot_client غیر None ولی قطعه.
bot_client = (
    TelegramClient("selfbot_panel_bot", config.API_ID, config.API_HASH)
    if config.BOT_TOKEN
    else None
)

START_TIME = time.time()
SELF_ID = None  # توی main() موقع اتصال پر می‌شه
BOT_USERNAME = None  # توی main() بعد از وصل‌شدنِ bot_client پر می‌شه

HTTP_SESSION: "aiohttp.ClientSession | None" = None  # توی main() ساخته می‌شه


async def get_http_session() -> aiohttp.ClientSession:
    """یک aiohttp.ClientSession مشترک برمی‌گردونه (اگه هنوز ساخته نشده، می‌سازدش)."""
    global HTTP_SESSION
    if HTTP_SESSION is None or HTTP_SESSION.closed:
        HTTP_SESSION = aiohttp.ClientSession()
    return HTTP_SESSION


async def close_http_session():
    if HTTP_SESSION is not None and not HTTP_SESSION.closed:
        await HTTP_SESSION.close()


def set_self_id(user_id: int):
    global SELF_ID
    SELF_ID = user_id


def set_bot_username(username: str):
    global BOT_USERNAME
    BOT_USERNAME = username
