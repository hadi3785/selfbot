"""۱۲) آمار سلف‌بات"""
import asyncio
import time
from datetime import timedelta

from telethon import events

from .. import config
from ..config import PREFIX
from ..runtime import client, START_TIME
from ..storage.settings_toggles import toggles
from ..storage.stats_store import (
    STATS,
    save_stats,
    reset_stats,
    record_message as _record_message,
    record_command as _record_command,
)
from ..storage.activity_store import flush_message_activity
from ..utils import pat

@client.on(events.NewMessage())
async def stats_collector(event):
    """
    یه هندلر عمومیِ کم‌هزینه که روی *هر* پیامی (ورودی یا خروجی، دستور یا معمولی)
    اجرا می‌شه تا آمار کلی رو جمع کنه - بدون نیاز به دست‌کاری تک‌تک هندلرهای
    بالا. تشخیص «دستور واقعی» با چک‌کردن اولین کلمه‌ی بعد از پیشوند در
    ALL_COMMAND_NAMES انجام می‌شه (همون دیکشنری‌ای که pat() موقع ثبت هر
    دستور پر می‌کنه)، پس تایپ‌های اشتباه با پیشوند به‌اشتباه به‌عنوان دستورِ
    اجراشده شمرده نمی‌شن.
    """
    if not toggles["stats_enabled"]:
        return
    _record_message(event)
    if event.out and event.raw_text and event.raw_text.startswith(PREFIX):
        rest = event.raw_text[len(PREFIX):]
        first_word = rest.split(None, 1)[0] if rest.strip() else ""
        if first_word:
            _record_command(event, first_word)


def _format_uptime():
    return str(timedelta(seconds=int(time.time() - START_TIME)))


def _stats_summary_text():
    top_commands = sorted(STATS["commands_by_name"].items(), key=lambda kv: kv[1], reverse=True)[:5]
    if top_commands:
        cmd_lines = "\n".join(f"   {i+1}. `{name}` — {n} بار" for i, (name, n) in enumerate(top_commands))
    else:
        cmd_lines = "   (هنوز دستوری اجرا نشده)"

    per_chat = STATS["per_chat"]
    top_chats = sorted(per_chat.items(), key=lambda kv: kv[1]["messages"] + kv[1]["commands"], reverse=True)[:5]
    if top_chats:
        chat_lines = "\n".join(
            f"   – {info.get('title') or cid}: {info['messages']} پیام، {info['commands']} دستور"
            for cid, info in top_chats
        )
    else:
        chat_lines = "   (هنوز پیامی ثبت نشده)"

    return (
        "📊 **آمار سلف‌بات**\n\n"
        f"⏳ زمان فعالیت: `{_format_uptime()}`\n"
        f"⚙️ دستورات اجراشده: **{STATS['commands_total']}**\n"
        f"✉️ پیام‌های پردازش‌شده: **{STATS['messages_total']}**\n"
        f"🔁 ارسال‌خودکار موفق/ناموفق: **{STATS['autopost_ok']}** / **{STATS['autopost_fail']}**\n"
        f"❌ خطاهای سیستمی: **{STATS['errors']}**\n\n"
        f"🏆 پراستفاده‌ترین دستورها:\n{cmd_lines}\n\n"
        f"💬 فعال‌ترین چت‌ها:\n{chat_lines}\n\n"
        f"جزئیات کامل هر چت: `{PREFIX}آمار چت‌ها`\n"
        f"پاک‌کردن و شروع دوباره‌ی شمارش: `{PREFIX}آمار بازنشانی`"
    )


async def _stats_chats_text():
    per_chat = STATS["per_chat"]
    if not per_chat:
        return "هنوز آماری برای هیچ چتی ثبت نشده"
    ordered = sorted(per_chat.items(), key=lambda kv: kv[1]["messages"] + kv[1]["commands"], reverse=True)
    lines = ["💬 **آمار به‌تفکیک چت:**\n"]
    for cid, info in ordered[:20]:
        title = info.get("title")
        if not title:
            try:
                chat = await client.get_entity(int(cid))
                title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or cid
                info["title"] = title
            except Exception:
                title = cid
        lines.append(f"▫️ **{title}** — {info['messages']} پیام، {info['commands']} دستور")
    if len(ordered) > 20:
        lines.append(f"\n… و {len(ordered) - 20} چت دیگر")
    return "\n".join(lines)


@client.on(events.NewMessage(outgoing=True, pattern=pat(["آمار", "stats"])))
async def stats_handler(event):
    raw = (event.pattern_match.group(1) or "").strip().lower()
    sub = raw.split(maxsplit=1)[0] if raw else ""

    if not sub:
        await save_stats()
        return await event.edit(_stats_summary_text())

    if sub in ("چت‌ها", "چتها", "chats"):
        return await event.edit(await _stats_chats_text())

    if sub in ("بازنشانی", "ریست", "reset"):
        await reset_stats()
        return await event.edit("🗑 آمار پاک شد و شمارش از نو شروع شد")

    if sub in ("هوشمند", "insight", "تحلیل"):
        return await _smart_insights(event)

    await event.edit(f"دستور نامعتبره. برای دیدن آمار: `{PREFIX}آمار`")


async def _smart_insights(event):
    """📈 تحلیلِ هوشمندِ آمار: خلاصه‌ی عددی + AI Insight (بدونِ AI: الگوهای ساده)."""
    per_chat = STATS["per_chat"]
    total_msgs = STATS["messages_total"]
    total_cmds = STATS["commands_total"]
    top_commands = sorted(STATS["commands_by_name"].items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_chats = sorted(per_chat.items(), key=lambda kv: kv[1]["messages"] + kv[1]["commands"], reverse=True)[:3]

    # نرخِ دستور به پیام + فعالیت
    cmd_rate = (total_cmds / total_msgs * 100) if total_msgs else 0
    lines = [
        "📈 **تحلیلِ هوشمندِ آمار**",
        "",
        f"📨 پیام‌ها: {total_msgs:,}  |  ⌨️ دستورها: {total_cmds:,}  (نرخ: {cmd_rate:.0f}%)",
    ]
    if top_commands:
        lines.append("🏆 دستورهای محبوب: " + " • ".join(f"`{n}`×{c}" for n, c in top_commands))
    if top_chats:
        chat_txt = " • ".join(
            f"{info.get('title') or cid} ({info['messages']})" for cid, info in top_chats
        )
        lines.append(f"💬 فعال‌ترین چت‌ها: {chat_txt}")

    blob = "\n".join(lines)
    try:
        from .. import assistant_brain, ai as ai_mod

        out = await ai_mod.ask_ai(
            [
                {
                    "role": "system",
                    "content": (
                        "آمارِ استفاده‌ی یک سلف‌بات تلگرامی را می‌بینی. به فارسی در حداکثر ۴ خط "
                        "«🧠 تحلیلِ هوشمند» بنویس: الگوی استفاده، چت‌های فعال، و یک توصیه‌ی عملی. بدون مقدمه."
                    ),
                },
                {"role": "user", "content": blob + f"\nخطاهای سیستمی: {STATS['errors']}"},
            ],
            max_tokens=220,
        )
        lines.append("")
        lines.append(out.strip())
    except Exception:
        # بدونِ AI: insight محلی
        if cmd_rate > 30:
            lines.append("🧠 نرخِ دستورِ بالا — بیشترِ فعالیتِ اکانت اتوماتیک/ابزاری است.")
        elif total_msgs > 0:
            lines.append("🧠 اکانت در حالتِ گفتگوی طبیعی استفاده می‌شود.")
    await event.edit("\n".join(lines))


async def stats_saver():
    """هر چند ثانیه یک‌بار آمار رو روی دیسک ذخیره می‌کنه تا با ری‌استارت/ری‌دیپلوی از دست نره."""
    from .. import health
    while True:
        await asyncio.sleep(config.STATS_SAVE_INTERVAL)
        try:
            await save_stats()
            await flush_message_activity()
            health.update_worker_status("stats", "ok")
        except Exception:
            # قطعیِ موقتِ DB نباید workerِ آمار را برای همیشه از بین ببرد
            _record_error()
            logger.exception("ذخیره‌ی دوره‌ایِ آمار شکست خورد - دورِ بعد دوباره")
            try:
                health.update_worker_status("stats", "error", "save failed")
            except Exception:
                pass
