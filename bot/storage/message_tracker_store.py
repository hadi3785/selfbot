"""لیستِ کانال‌های مقصدِ ردیابِ ویرایش/حذفِ پیام - PostgreSQL از طریق Repository Layer.

توجه: روشن/خاموش‌بودنِ خودِ قابلیت (message_tracker_enabled) اینجا نیست؛
چون فقط یک سوییچِ ساده‌ست (بدونِ تنظیماتِ دیگه)، مثلِ notifications_enabled
توی جدولِ عمومیِ settings نگه داشته می‌شه - نگاه کن به
bot/storage/settings_toggles.py.
"""
from ..repositories import message_tracker_repo

message_tracker_state = {"channels": {}}


async def init_message_tracker_state() -> None:
    message_tracker_state["channels"] = await message_tracker_repo.list_channels()


async def add_tracker_channel(chat_id: int, title: str) -> None:
    message_tracker_state["channels"][str(chat_id)] = title
    await message_tracker_repo.upsert_channel(chat_id, title)


async def remove_tracker_channel(chat_id: int):
    removed = message_tracker_state["channels"].pop(str(chat_id), None)
    if removed is not None:
        await message_tracker_repo.remove_channel(chat_id)
    return removed


async def clear_tracker_channels() -> None:
    message_tracker_state["channels"].clear()
    await message_tracker_repo.clear_channels()
