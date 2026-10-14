"""⭐ امتیاز/XP/رتبه‌ی اتاق فرار.

قواعد:
- حلِ پازل: +reward پازل | سرنخِ نو: +25 | آیتمِ مخفی: +40 | پایان: بونوسِ زمان
- خطا/دام: −15 (HP هم کم می‌شود در دام‌ها) | hint: 20/35/50
- امتیاز هرگز زیرِ صفر نمی‌رود؛ اسپمِ hint سقفِ جریمه دارد (فقط ۵ بارِ اول کامل)
- رتبه بر اساس score: مبتدی/کهنه‌کار/استاد/افسانه
"""
from __future__ import annotations

HINT_COSTS = (20, 35, 50)
HINT_CAP = 5  # بیش از این، hint جریمه‌اش نصف می‌شود (ضدِ اسپم)
MAX_SCORE = 999_999

SCORE_CLUE = 25
SCORE_HIDDEN_ITEM = 40
SCORE_TRAP = 15
SCORE_WRONG_ANSWER = 10
SCORE_END_BONUS = 200
SCORE_PERFECT_BONUS = 250


def rank_of(score: int) -> str:
    if score >= 1500:
        return "🏆 افسانه"
    if score >= 800:
        return "🥇 استاد"
    if score >= 300:
        return "🥈 کهنه‌کار"
    return "🥉 مبتدی"


def xp_of(score: int) -> int:
    return max(0, score // 2)


def apply_score(current: int, delta: int) -> int:
    return max(0, min(MAX_SCORE, current + delta))


def time_bonus(seconds: int, limit_seconds: int | None = None) -> int:
    """هرچه سریع‌تر، بیشتر؛ تا سقف ۱۵۰."""
    if seconds <= 0:
        return 150
    if limit_seconds:
        ratio = max(0.0, 1 - seconds / max(1, limit_seconds))
        return int(150 * ratio)
    return max(0, 150 - min(150, seconds // 60))
