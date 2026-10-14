"""
ذخیره‌سازی فیلترِ کلماتِ ممنوعه‌ی سفارشیِ گروه - از طریق Repository Layer.
"""

from typing import List

from ..repositories import word_filter_repo
from ..db.models_ext import GroupWordFilter


async def add_word_filter(
    chat_id: int,
    word: str,
    action: str = "delete",
    case_sensitive: bool = False,
    is_regex: bool = False,
) -> GroupWordFilter:
    return await word_filter_repo.add_word_filter(
        chat_id, word, action, case_sensitive, is_regex
    )


async def remove_word_filter(chat_id: int, word: str) -> bool:
    return await word_filter_repo.remove_word_filter(chat_id, word)


async def get_word_filters(chat_id: int) -> List[GroupWordFilter]:
    return await word_filter_repo.get_word_filters(chat_id)


async def clear_word_filters(chat_id: int) -> int:
    return await word_filter_repo.clear_word_filters(chat_id)


async def search_word_in_filters(chat_id: int, text: str) -> List[GroupWordFilter]:
    return await word_filter_repo.search_word_in_filters(chat_id, text)
