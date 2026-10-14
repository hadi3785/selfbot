"""
این اسکریپت رو فقط یک‌بار اجرا کن تا Session String بگیری.
بعدش مقدارش رو توی .env (یا Replit Secrets) با نام SESSION_STRING ذخیره کن
تا سلف‌بات دیگه نیازی به لاگین دوباره نداشته باشه.

اجرا: python generate_session.py
موقع اجرا شماره تلفن و کد تاییدی که تلگرام برات می‌فرسته رو وارد کن.
"""
import os
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

API_ID_RAW = os.getenv("API_ID", "")
if not API_ID_RAW:
    raise SystemExit("❌ متغیر محیطی API_ID تنظیم نشده. اول فایل .env رو بساز.")
API_ID = int(API_ID_RAW)
API_HASH = os.getenv("API_HASH", "")
if not API_HASH:
    raise SystemExit("❌ متغیر محیطی API_HASH تنظیم نشده. اول فایل .env رو بساز.")

with TelegramClient(
    StringSession(), API_ID, API_HASH,
    device_model="selfbot-py",
    system_version="linux",
    app_version="1.0",
    lang_code="fa",
    system_lang_code="fa",
) as client:
    print("\n✅ لاگین موفق بود.\n")
    print("این Session String شماست - آن را در .env در متغیر SESSION_STRING قرار دهید:\n")
    print(client.session.save())
    print("\n⚠️ این رشته معادل رمز عبور اکانتته - جایی به اشتراک نذارش.")

# نکته‌های مهم برای پایداری سشن:
# ۱) این سشن رو هم‌زمان در دو جا اجرا نکن (لوکال + Railway) — هم‌زمانی دو IP
#    باعث AuthKeyDuplicated و ابطالِ دائمی سشن می‌شه.
# ۲) اگه بعد از مدتی «غیرفعال شد»، اول لاگ Railway رو ببین: اگر
#    AuthKeyDuplicated بود، سشن جدید بساز؛ اگر قطعیِ شبکه بود، watchdog
#    خودش ری‌کانکت/ری‌استارت می‌کنه.
