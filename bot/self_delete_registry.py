"""
رجیستریِ سبک و مشترک برای هماهنگیِ «حذفِ عمدیِ خودمون» با ردیابِ ویرایش/حذف.

چرا لازمه: دستورهای `.حذف`/`.پاکسازی` (bot/handlers/messages.py) می‌تونن
با ریپلای‌کردن، پیامِ کسِ دیگه‌ای رو هم حذف کنن (مثلاً پاک‌سازیِ یه گروه).
بدونِ این رجیستری، ردیابِ ویرایش/حذف (bot/handlers/message_tracker.py) این
حذفِ عمدیِ خودمون رو هم می‌بینه و اشتباهی به‌عنوانِ «طرفِ مقابل پیامش رو
حذف کرد» به کانالِ ردیاب گزارش می‌ده - در حالی‌که واقعاً خودِ owner تصمیم
گرفته اون پیام رو (از دیدِ خودش) پاک کنه، نه فرستنده‌ی اصلی.

این ماژول عمداً به هیچ ماژولِ دیگه‌ای از bot وابسته نیست (فقط time) تا هم
messages.py (که علامت می‌زنه) هم message_tracker.py (که چک می‌کنه) بدونِ
ریسکِ circular import بتونن importش کنن.
"""
import time

_recent: dict = {}  # (chat_id, message_id) -> زمانِ علامت‌گذاری
_MAX_AGE_SECONDS = 30  # حذفِ واقعی معمولاً چند صدم‌ثانیه بعد از علامت‌گذاری اتفاق می‌افته
_MAX_ENTRIES = 500


def mark(chat_id, message_id) -> None:
    """درست قبل از حذفِ عمدیِ پیامِ کسِ دیگه (با دستوری مثلِ `.حذف`/`.پاکسازی`) صدا زده بشه."""
    _recent[(chat_id, message_id)] = time.time()
    if len(_recent) > _MAX_ENTRIES:
        oldest_key = min(_recent, key=_recent.get)
        _recent.pop(oldest_key, None)


def consume(chat_id, message_id) -> bool:
    """
    اگه این پیام به‌تازگی (طیِ چند ثانیه‌ی اخیر) عمداً توسطِ خودمون حذف شده
    بوده True برمی‌گردونه و علامتش رو مصرف/پاک می‌کنه؛ در غیرِاین‌صورت False.
    """
    ts = _recent.pop((chat_id, message_id), None)
    if ts is None:
        return False
    return (time.time() - ts) <= _MAX_AGE_SECONDS
