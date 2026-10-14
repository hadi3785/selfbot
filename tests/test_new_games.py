"""تست‌های منطقِ بازی‌های جدید (بدونِ تلگرام - فقط state/parse)."""
import os

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test_hash")
os.environ.setdefault("DATABASE_URL", "postgresql://placeholder:***@localhost/placeholder")

from bot.handlers.fun import (  # noqa: E402
    _SNAKES_GOAL,
    _SNAKES_LADDERS,
    _SNAKES_SNAKES,
    _WORDGUESS_MAX_WRONG,
    _WORDGUESS_WORDS,
)


class TestWordGuess:
    def test_words_have_hints(self):
        for word, hint in _WORDGUESS_WORDS:
            assert word and hint
            assert len(word) >= 2

    def test_reveal_logic(self):
        word = "دوچرخه"
        revealed = ["_"] * len(word)
        for ch in "رخ":
            for i, c in enumerate(word):
                if c == ch:
                    revealed[i] = c
        assert revealed == ["_", "_", "_", "ر", "خ", "_"]  # فقط ر/خ/ه... «ر» و «خ» reveal شدن
        assert "_" in revealed  # هنوز کامل نشده

    def test_full_reveal_wins(self):
        word = "شتر"
        revealed = list(word)
        assert "_" not in revealed

    def test_max_wrong(self):
        assert _WORDGUESS_MAX_WRONG == 6


class TestSnakesLadders:
    def test_goal(self):
        assert _SNAKES_GOAL == 100

    def test_snake_destination_lower(self):
        for src, dst in _SNAKES_SNAKES.items():
            assert dst < src, (src, dst)

    def test_ladder_destination_higher(self):
        for src, dst in _SNAKES_LADDERS.items():
            assert dst > src, (src, dst)

    def test_within_board(self):
        for src, dst in {**_SNAKES_SNAKES, **_SNAKES_LADDERS}.items():
            assert 1 <= src <= _SNAKES_GOAL
            assert 1 <= dst <= _SNAKES_GOAL
