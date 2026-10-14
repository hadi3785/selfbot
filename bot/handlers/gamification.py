"""🎮 سیستم XP/Level/دستاوردِ واحد (`.XP`) — روی داده‌های موجود، بدونِ جدولِ جدید.

XP از: امتیازِ اتاقِ فرار (۱ امتیاز=۱XP) + کارهای انجام‌شده (۲۰XP) + یادداشت‌ها (۱۰XP)
+ دستورهای اجراشده (۱XP هر ۱۰ تا) ساخته می‌شود. Level = floor(sqrt(xp/100)) + 1.
"""
import math

from telethon import events

from ..config import PREFIX
from ..repositories import escape_repo, tasks_repo
from ..runtime import client
from ..storage.notes_store import load_notes
from ..storage.stats_store import STATS
from ..utils import pat


def level_of(xp: int) -> int:
    return int(math.isqrt(max(0, xp) // 100)) + 1


def xp_for_level(level: int) -> int:
    """XP لازم برای رسیدن به level (شروعِ همان لِول)."""
    return (level - 1) ** 2 * 100


@client.on(events.NewMessage(outgoing=True, pattern=pat(["XP", "xp", "لول", "سطح"])))
async def xp_handler(event):
    await event.edit("🎮 در حال محاسبه...")

    # امتیازِ فرار
    try:
        esc = await escape_repo.stats_summary()
        esc_xp = int(esc.get("top_score") or 0)
        solved = int(esc.get("most_solved") or 0)
    except Exception:
        esc_xp = solved = 0

    # کارها
    try:
        done_tasks = len(await tasks_repo.list_tasks(done=True, limit=500))
    except Exception:
        done_tasks = 0

    # یادداشت‌ها
    try:
        notes = len(await load_notes())
    except Exception:
        notes = 0

    cmds = STATS.get("commands_total", 0)

    xp = esc_xp + done_tasks * 20 + notes * 10 + cmds // 10
    level = level_of(xp)
    cur_floor = xp_for_level(level)
    next_floor = xp_for_level(level + 1)
    progress = int((xp - cur_floor) / max(1, (next_floor - cur_floor)) * 20)
    bar = "█" * progress + "░" * (20 - progress)

    # دستاوردها
    ach = []
    if esc_xp > 0:
        ach.append("🏆 اولین بردِ فرار")
    if solved >= 5:
        ach.append("🧠 نابغه‌ی معما (۵+ اتاق)")
    if done_tasks >= 10:
        ach.append("✅ ۱۰ کارِ انجام‌شده")
    if notes >= 10:
        ach.append("📒 ۱۰ یادداشت")
    if cmds >= 500:
        ach.append("⌨️ ۵۰۰ دستور")
    if level >= 5:
        ach.append(f"🔥 لِول {level}")
    ach_txt = "\n".join(f"• {a}" for a in ach) if ach else "• هنوز دستاوردی باز نشده — بازی کن!"

    await event.edit(
        f"🏆 **Level {level}**\n"
        f"XP: **{xp:,}** / {next_floor:,}\n"
        f"[{bar}] {progress * 5}%\n\n"
        f"🎮 اتاق‌های حل‌شده: {solved}  |  ⌨️ دستورها: {cmds:,}\n"
        f"✅ کارها: {done_tasks}  |  📒 یادداشت‌ها: {notes}\n\n"
        f"🎖 **دستاوردها:**\n{ach_txt}"
    )
