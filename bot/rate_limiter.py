"""
محدود کننده نرخ برای پیام‌های خروجی (جلوگیری از FloodWaitError).
از این ابزاره برای جلوگیری از ارسال همزمان پیام به تعداد زیاد استفاده میشه.
"""
import time
import asyncio
from collections import defaultdict


class RateLimiter:
    """
    محدود کننده ساده برای جلوگیری از ارسال پیام به تنخای زیاد.
    مثال: ارسال به تنهایی در یک بازه زمانی.
    """

    def __init__(self, max_per_second: float = 1.0, max_per_minute: float = 20.0):
        self._max_per_second = max_per_second
        self._max_per_minute = max_per_minute
        self._last_send: dict[str, float] = defaultdict(float)
        self._send_count_minute: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def wait(self, key: str = "default") -> None:
        """صبر کن تا وقت مجاز بشه."""
        async with self._lock:
            now = time.monotonic()
            # بررسی از فاصله ثانیه‌ای
            elapsed = now - self._last_send[key]
            min_interval = 1.0 / self._max_per_second
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            # بررسی از سقف دقیقه‌ای
            now = time.monotonic()
            window = [t for t in self._send_count_minute[key] if now - t < 60]
            self._send_count_minute[key] = window
            if len(window) >= self._max_per_minute:
                wait_time = 60 - (now - window[0]) + 0.1
                await asyncio.sleep(wait_time)
                self._send_count_minute[key] = []
            self._last_send[key] = time.monotonic()
            self._send_count_minute[key].append(time.monotonic())


# نسخه سراسری برای ارسال پیام خروجی
outgoing_limiter = RateLimiter(max_per_second=0.5, max_per_minute=15)
