"""تست‌های قابلیت‌های جدید: تبدیل تاریخِ شمسی و پارسِ تکرار."""
import os

import pytest

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("DATABASE_URL", "postgresql://placeholder:***@localhost/placeholder")
os.environ.setdefault("TIMEZONE_OFFSET", "3.5")

from bot.handlers.extras import gregorian_to_jalali, jalali_to_gregorian  # noqa: E402
from bot.handlers.recurring import parse_recurring  # noqa: E402


class TestJalali:
    def test_known_nowruz_dates(self):
        assert gregorian_to_jalali(2025, 3, 21) == (1404, 1, 1)
        assert gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
        assert jalali_to_gregorian(1404, 1, 1) == (2025, 3, 21)
        assert jalali_to_gregorian(1403, 1, 1) == (2024, 3, 20)

    def test_today(self):
        assert gregorian_to_jalali(2026, 8, 30) == (1405, 6, 8)

    def test_roundtrip_random(self):
        import random

        random.seed(42)
        for _ in range(500):
            d = random.randint(1, 28)
            m = random.randint(1, 12)
            jy = random.randint(1300, 1500)
            gy, gm, gd = jalali_to_gregorian(jy, m, d)
            assert gregorian_to_jalali(gy, gm, gd) == (jy, m, d)


class TestParseRecurring:
    def test_interval_valid(self):
        assert parse_recurring("30دقیقه") == (1800, None, None)
        assert parse_recurring("2h") == (7200, None, None)
        assert parse_recurring("1روز") == (86400, None, None)
        assert parse_recurring("45m") == (2700, None, None)

    def test_interval_too_short_rejected(self):
        assert parse_recurring("30s") is None
        assert parse_recurring("0m") is None

    def test_daily_time(self):
        assert parse_recurring("08:00") == ("daily", 8, 0)
        assert parse_recurring("23:59") == ("daily", 23, 59)

    def test_daily_invalid(self):
        assert parse_recurring("25:00") is None
        assert parse_recurring("08:60") is None

    def test_garbage(self):
        assert parse_recurring("هر") is None
        assert parse_recurring("") is None
        assert parse_recurring("abc") is None
