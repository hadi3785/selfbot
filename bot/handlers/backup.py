"""۱۰) بکاپ‌گیری: پیام‌ها (متن/JSON)، رسانه‌ها، لیست چت‌ها، و کل تنظیمات بات"""
import datetime as dt
import json
import logging
from datetime import datetime, timezone
from io import BytesIO

from telethon import events

from .. import config
from ..config import PREFIX
from ..runtime import client
from ..clock import clock_state, CLOCK_STYLES, persist_clock_state
from ..storage.notes_store import load_notes, save_note
from ..storage.autopost_store import (
    autopost_state,
    save_autopost,
    add_autopost_chat,
    clear_autopost_chats,
)
from ..storage.assistant_store import (
    add_schedule_window,
    assistant_state,
    clear_schedule_windows,
    save_assistant,
)
from ..storage.font_store import font_state, save_font_state
from ..storage.settings_toggles import toggles as _global_toggles, set_toggle as _set_toggle
from ..storage.group_guard_store import (
    group_guard_state,
    set_link_filter as _set_link_filter,
    set_porn_filter as _set_porn_filter,
    set_spam_filter as _set_spam_filter,
    set_profanity_filter as _set_profanity_filter,
    set_welcome_enabled as _set_welcome_enabled,
    set_welcome_text as _set_welcome_text,
)
from ..repositories import (
    daily_digest_repo,
    message_tracker_repo,
    warn_repo,
    word_filter_repo,
)
from ..storage.stats_store import STATS, record_error as _record_error
from ..utils import pat

logger = logging.getLogger("selfbot.handlers.backup")

BACKUP_MAX_MESSAGES = config.BACKUP_MAX_MESSAGES
BACKUP_MAX_MEDIA = config.BACKUP_MAX_MEDIA

async def _gather_config_snapshot():
    """
    همه‌ی تنظیمات/وضعیتِ ذخیره‌شدنیِ بات (که حالا منبع اصلی‌شون PostgreSQL
    است) رو توی یک دیکشنری واحد جمع می‌کنه - این JSON فقط برای Export/Backup/
    Import دستیِ کاربره؛ PostgreSQL منبع اصلیِ داده باقی می‌مونه.
    """
    return {
        "_kind": "selfbot_config_backup",
        "_version": 4,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": await load_notes(),
        "autopost": dict(autopost_state),
        "assistant": {
            "mode": assistant_state["mode"],
            "text": assistant_state["text"],
            "delay": assistant_state["delay"],
            "include": list(assistant_state["include"]),
            "exclude": list(assistant_state["exclude"]),
            "auto_detect": assistant_state["auto_detect"],
            "manual_enabled": assistant_state["enabled"] if not assistant_state["auto_detect"] else False,
            "ai_mode": assistant_state["ai_mode"],
            "schedule_enabled": assistant_state["schedule_enabled"],
            "schedule_windows": [
                {
                    "label": w["label"],
                    "start_minute": w["start_minute"],
                    "end_minute": w["end_minute"],
                }
                for w in assistant_state["schedule_windows"]
            ],
        },
        "font": dict(font_state),
        "clock": {
            "enabled": clock_state["enabled"],
            "style": clock_state["style"],
            "base_name": clock_state["base_name"],
        },
        "group_guard": {
            "link_filter_chats": list(group_guard_state["link_filter_chats"]),
            "porn_filter_chats": list(group_guard_state["porn_filter_chats"]),
            "spam_filter_chats": list(group_guard_state["spam_filter_chats"]),
            "profanity_filter_chats": list(group_guard_state["profanity_filter_chats"]),
            "welcome": {
                str(cid): entry for cid, entry in group_guard_state["welcome"].items()
            },
        },
        "word_filter": [
            {
                "chat_id": f.chat_id,
                "word": f.word,
                "action": f.action,
                "case_sensitive": f.case_sensitive,
                "is_regex": f.is_regex,
            }
            for f in await word_filter_repo.list_all()
        ],
        "warn_settings": [
            {
                "chat_id": s.chat_id,
                "enabled": s.enabled,
                "warn_limit": s.warn_limit,
                "action_on_limit": s.action_on_limit,
                "mute_duration_minutes": s.mute_duration_minutes,
                "auto_reset_days": s.auto_reset_days,
            }
            for s in await warn_repo.list_all_settings()
        ],
        "daily_digest": {
            "settings": (lambda s: {
                "enabled": s.enabled, "mode": s.mode, "hour": s.hour, "minute": s.minute,
            })(await daily_digest_repo.get_settings()),
            "chats": await daily_digest_repo.list_chats(),
        },
        "message_tracker": {
            "channels": await message_tracker_repo.list_channels(),
        },
        "global_toggles": dict(_global_toggles),
        "stats": dict(STATS),
        # ---- دستیار شخصی (v10) ----
        "ai_memory": await _snapshot_ai_memory(),
        "tasks": await _snapshot_tasks(),
        "schedules": await _snapshot_schedules(),
    }


async def _apply_config_snapshot(data):
    """
    یه اسنپ‌شات (خروجیِ _gather_config_snapshot) رو روی وضعیت زنده‌ی بات اعمال
    می‌کنه و PostgreSQL رو هم به‌روز می‌کنه (نه فایل JSON - JSON فقط قالبِ
    Import/Export هست). کلیدهایی که توی فایل بکاپ نباشن دست‌نخورده می‌مونن
    (merge، نه جایگزینیِ کامل).
    """
    applied = []

    if isinstance(data.get("notes"), dict):
        for key, text in data["notes"].items():
            await save_note(key, text)
        applied.append("یادداشت‌ها")

    if isinstance(data.get("autopost"), dict):
        a = data["autopost"]
        autopost_state["enabled"] = a.get("enabled", autopost_state["enabled"])
        autopost_state["interval_minutes"] = a.get("interval_minutes", autopost_state["interval_minutes"])
        autopost_state["text"] = a.get("text", autopost_state["text"])
        await save_autopost()
        chats = a.get("chats")
        if isinstance(chats, dict):
            await clear_autopost_chats()
            for cid_str, title in chats.items():
                await add_autopost_chat(int(cid_str), title)
        applied.append("ارسال‌خودکار")

    if isinstance(data.get("assistant"), dict):
        a = data["assistant"]
        assistant_state["mode"] = a.get("mode", assistant_state["mode"])
        assistant_state["text"] = a.get("text", assistant_state["text"])
        assistant_state["delay"] = a.get("delay", assistant_state["delay"])
        assistant_state["include"] = set(a.get("include", []))
        assistant_state["exclude"] = set(a.get("exclude", []))
        assistant_state["auto_detect"] = a.get("auto_detect", assistant_state["auto_detect"])
        assistant_state["ai_mode"] = a.get("ai_mode", assistant_state["ai_mode"])
        assistant_state["schedule_enabled"] = a.get("schedule_enabled", assistant_state["schedule_enabled"])
        if not assistant_state["auto_detect"]:
            assistant_state["enabled"] = a.get("manual_enabled", False)
        await save_assistant()
        windows = a.get("schedule_windows")
        if isinstance(windows, list):
            await clear_schedule_windows()
            for w in windows:
                if isinstance(w, dict) and "start_minute" in w and "end_minute" in w:
                    await add_schedule_window(
                        str(w.get("label", "")), int(w["start_minute"]), int(w["end_minute"])
                    )
        applied.append("منشی")

    if isinstance(data.get("font"), dict):
        font_state.update(data["font"])
        await save_font_state()
        applied.append("فونت")

    if isinstance(data.get("clock"), dict):
        if "enabled" in data["clock"]:
            clock_state["enabled"] = bool(data["clock"]["enabled"])
        if data["clock"].get("style") in CLOCK_STYLES:
            clock_state["style"] = data["clock"]["style"]
        if data["clock"].get("base_name"):
            clock_state["base_name"] = data["clock"]["base_name"]
        await persist_clock_state()
        applied.append("ساعت")

    if isinstance(data.get("group_guard"), dict):
        g = data["group_guard"]
        for cid in g.get("link_filter_chats", []):
            try:
                await _set_link_filter(int(cid), True)
            except (TypeError, ValueError):
                continue
        for cid in g.get("porn_filter_chats", []):
            try:
                await _set_porn_filter(int(cid), True)
            except (TypeError, ValueError):
                continue
        for cid in g.get("spam_filter_chats", []):
            try:
                await _set_spam_filter(int(cid), True)
            except (TypeError, ValueError):
                continue
        for cid in g.get("profanity_filter_chats", []):
            try:
                await _set_profanity_filter(int(cid), True)
            except (TypeError, ValueError):
                continue
        welcome = g.get("welcome")
        if isinstance(welcome, dict):
            for cid_str, entry in welcome.items():
                try:
                    cid = int(cid_str)
                except (TypeError, ValueError):
                    continue
                if not isinstance(entry, dict):
                    continue
                if entry.get("text"):
                    await _set_welcome_text(cid, entry["text"])
                await _set_welcome_enabled(cid, bool(entry.get("enabled")))
        applied.append("مدیریت گروه پیشرفته")

    if isinstance(data.get("word_filter"), list) and data["word_filter"]:
        count = 0
        for f in data["word_filter"]:
            if not isinstance(f, dict):
                continue
            try:
                cid = int(f["chat_id"])
                word = str(f["word"])
            except (KeyError, TypeError, ValueError):
                continue
            try:
                await word_filter_repo.add_word_filter(
                    cid, word,
                    action=f.get("action", "delete"),
                    case_sensitive=bool(f.get("case_sensitive", False)),
                    is_regex=bool(f.get("is_regex", False)),
                )
                count += 1
            except ValueError:
                pass  # از قبل وجود داشت - نادیده بگیر، خطا نیست
        applied.append(f"فیلترِ کلمات ({count} مورد)")

    if isinstance(data.get("warn_settings"), list) and data["warn_settings"]:
        for s in data["warn_settings"]:
            if not isinstance(s, dict):
                continue
            try:
                cid = int(s["chat_id"])
            except (KeyError, TypeError, ValueError):
                continue
            await warn_repo.update_warn_settings(
                cid,
                enabled=s.get("enabled"),
                warn_limit=s.get("warn_limit"),
                action_on_limit=s.get("action_on_limit"),
                mute_duration_minutes=s.get("mute_duration_minutes"),
                auto_reset_days=s.get("auto_reset_days"),
            )
        applied.append("تنظیماتِ اخطار")

    if isinstance(data.get("daily_digest"), dict):
        dd = data["daily_digest"]
        settings = dd.get("settings")
        if isinstance(settings, dict):
            current = await daily_digest_repo.get_settings()
            await daily_digest_repo.save_settings(
                enabled=settings.get("enabled", current.enabled),
                mode=settings.get("mode", current.mode),
                hour=settings.get("hour", current.hour),
                minute=settings.get("minute", current.minute),
                last_run_date=current.last_run_date,
            )
        chats = dd.get("chats")
        if isinstance(chats, dict):
            await daily_digest_repo.clear_chats()
            for cid_str, title in chats.items():
                try:
                    await daily_digest_repo.upsert_chat(int(cid_str), title)
                except (TypeError, ValueError):
                    continue
        applied.append("خلاصه‌روز")

    if isinstance(data.get("message_tracker"), dict):
        channels = data["message_tracker"].get("channels")
        if isinstance(channels, dict):
            await message_tracker_repo.clear_channels()
            for cid_str, title in channels.items():
                try:
                    await message_tracker_repo.upsert_channel(int(cid_str), title)
                except (TypeError, ValueError):
                    continue
            applied.append("ردیابِ ویرایش/حذف")

    if isinstance(data.get("global_toggles"), dict):
        for key, value in data["global_toggles"].items():
            if key in _global_toggles:
                try:
                    await _set_toggle(key, bool(value))
                except Exception:
                    continue
        applied.append("سوییچ‌های سراسری")

    # ---- دستیار شخصی (v10): حافظه AI / کارها / زمان‌بندی‌ها ----
    if isinstance(data.get("ai_memory"), list):
        from ..repositories import ai_memory_repo

        restored = 0
        for it in data["ai_memory"]:
            try:
                await ai_memory_repo.save_memory(
                    str(it.get("category", ""))[:32],
                    str(it.get("key", ""))[:128],
                    str(it.get("value", "")),
                )
                restored += 1
            except Exception:
                continue
        if restored:
            applied.append(f"حافظه‌ی AI ({restored})")

    if isinstance(data.get("tasks"), list):
        from ..repositories import tasks_repo

        restored = 0
        for it in data["tasks"]:
            try:
                due = it.get("due_at")
                if isinstance(due, str) and due:
                    due = dt.datetime.fromisoformat(due)
                else:
                    due = None
                await tasks_repo.add_task(str(it.get("text", "")), due_at=due, priority=int(it.get("priority") or 0))
                restored += 1
            except Exception:
                continue
        if restored:
            applied.append(f"کارها ({restored})")

    if isinstance(data.get("schedules"), list):
        from ..storage.scheduler_store import create_job

        restored = 0
        for it in data["schedules"]:
            try:
                run_at = dt.datetime.fromisoformat(it["run_at"])
                if run_at.tzinfo is None:
                    run_at = run_at.replace(tzinfo=dt.timezone.utc)
                if run_at > dt.datetime.now(dt.timezone.utc):
                    await create_job(int(it["chat_id"]), str(it["text"]), run_at, str(it.get("kind", "reminder")))
                    restored += 1
            except Exception:
                continue
        if restored:
            applied.append(f"زمان‌بندی‌ها ({restored})")

    return applied


async def send_settings_backup(caption_note: str = "") -> None:
    """
    گردآوری و ارسالِ بکاپِ کاملِ تنظیمات به Saved Messages - هم توسطِ
    `.پشتیبان تنظیمات` صدا زده می‌شه، هم توسطِ عملیاتِ backup توی موتورِ
    اتوماسیون (bot/automation_engine.py).
    """
    snapshot = await _gather_config_snapshot()
    content = json.dumps(snapshot, ensure_ascii=False, indent=2)
    bio = BytesIO(content.encode("utf-8"))
    bio.name = f"selfbot_config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    caption = (
        "⚙️ بکاپ تنظیمات سلف‌بات (یادداشت‌ها، منشی، ارسال‌خودکار، فونت، ساعت، "
        "مدیریت‌گروه، فیلترِ کلمات، اخطار، خلاصه‌روز، ردیاب، سوییچ‌های سراسری، آمار)\n"
        f"برای بازیابی: روی همین فایل ریپلای کن و بنویس `{PREFIX}بازیابی`"
    )
    if caption_note:
        caption = f"{caption_note}\n\n{caption}"
    await client.send_file("me", bio, caption=caption)


async def _snapshot_ai_memory() -> list:
    from ..db.models_ext import AIMemory
    from sqlalchemy import select
    from ..db.engine import session_scope

    async with session_scope() as session:
        rows = (await session.execute(select(AIMemory))).scalars().all()
        return [
            {"category": r.category, "key": r.key, "value": r.value} for r in rows
        ]


async def _snapshot_tasks() -> list:
    from ..repositories import tasks_repo

    return await tasks_repo.list_tasks(done=False, limit=500) + await tasks_repo.list_tasks(done=True, limit=500)


async def _snapshot_schedules() -> list:
    from ..storage.scheduler_store import list_jobs

    out = []
    for kind in ("schedule", "reminder"):
        for j in await list_jobs(kind):
            out.append(
                {
                    "kind": kind,
                    "chat_id": j.chat_id,
                    "text": j.text,
                    "run_at": j.run_at.isoformat() if j.run_at else None,
                }
            )
    return out


@client.on(events.NewMessage(outgoing=True, pattern=pat(["پشتیبان", "backup"])))
async def backup_handler(event):
    args = (event.pattern_match.group(1) or "").strip()
    parts = args.split(None, 1)
    sub = parts[0].lower() if parts else ""

    # ---- .پشتیبان تنظیمات : بکاپ کامل تنظیمات/وضعیتِ بات (برای بازگردانی بعد از ری‌دیپلوی) ----
    if sub in ("تنظیمات", "settings", "config"):
        await event.edit("⏳ در حال آماده‌سازی بکاپ تنظیمات...")
        await send_settings_backup()
        return await event.edit("✅ بکاپ تنظیمات به Saved Messages ارسال شد")

    # ---- .پشتیبان چت‌ها : بکاپ لیست همه‌ی چت‌ها/دیالوگ‌های اکانت ----
    if sub in ("چت‌ها", "چتها", "chats", "dialogs"):
        await event.edit("⏳ در حال جمع‌آوری لیست چت‌ها...")
        lines = []
        async for d in client.iter_dialogs():
            kind = "کانال" if (d.is_channel and not d.is_group) else ("گروه" if d.is_group else "خصوصی")
            extra = f" — {d.unread_count} خوانده‌نشده" if d.unread_count else ""
            lines.append(f"[{kind}] {d.name} — id={d.id}{extra}")
        content = "\n".join(lines) or "(چتی پیدا نشد)"
        bio = BytesIO(content.encode("utf-8"))
        bio.name = "chats_backup.txt"
        await client.send_file("me", bio, caption=f"📇 بکاپ لیست {len(lines)} چت")
        return await event.edit("✅ بکاپ لیست چت‌ها به Saved Messages ارسال شد")

    # ---- .پشتیبان رسانه <عدد> : دانلود و فوروارد رسانه‌های N پیام آخر به Saved Messages ----
    if sub in ("رسانه", "media"):
        n_str = parts[1].strip() if len(parts) > 1 else ""
        n = int(n_str) if n_str.isdigit() else 200
        n = min(n, BACKUP_MAX_MESSAGES)
        await event.edit(f"⏳ در حال بررسی {n} پیام آخر برای رسانه...")
        sent = 0
        hit_cap = False
        async for m in client.iter_messages(event.chat_id, limit=n):
            if not m.media:
                continue
            if sent >= BACKUP_MAX_MEDIA:
                hit_cap = True
                break
            try:
                date = m.date.strftime("%Y-%m-%d %H:%M")
                await client.send_file("me", m.media, caption=f"🗂 از چت {event.chat_id} — {date}")
                sent += 1
            except Exception:
                _record_error()
                logger.exception("خطا در بکاپ رسانه")
        note = f" (به سقف {BACKUP_MAX_MEDIA} فایل رسیدیم، بقیه ارسال نشدن)" if hit_cap else ""
        return await event.edit(f"✅ {sent} فایل رسانه به Saved Messages ارسال شد{note}")

    # ---- .پشتیبان json <عدد> : بکاپ ساختاریافته‌ی پیام‌ها (برای پردازش برنامه‌ای) ----
    as_json = sub in ("json", "جیسون")
    n_str = (parts[1].strip() if len(parts) > 1 else "") if as_json else args
    n = int(n_str) if n_str and n_str.isdigit() else 100
    n = min(n, BACKUP_MAX_MESSAGES)
    await event.edit(f"⏳ در حال گرفتن بکاپ {n} پیام آخر...")

    if as_json:
        items = []
        async for m in client.iter_messages(event.chat_id, limit=n):
            sender = await m.get_sender()
            name = getattr(sender, "first_name", None) if sender else None
            items.append({
                "id": m.id,
                "date": m.date.isoformat(),
                "sender_id": m.sender_id,
                "sender_name": name,
                "text": m.raw_text or None,
                "media_type": type(m.media).__name__ if m.media else None,
            })
        items.reverse()
        content = json.dumps(items, ensure_ascii=False, indent=2)
        bio = BytesIO(content.encode("utf-8"))
        bio.name = "backup.json"
    else:
        lines = []
        async for m in client.iter_messages(event.chat_id, limit=n):
            sender = await m.get_sender()
            name = getattr(sender, "first_name", "؟") if sender else "؟"
            date = m.date.strftime("%Y-%m-%d %H:%M")
            lines.append(f"[{date}] {name}: {m.raw_text or '(media)'}")
        lines.reverse()
        content = "\n".join(lines) or "(چتی برای بکاپ پیدا نشد)"
        bio = BytesIO(content.encode("utf-8"))
        bio.name = "backup.txt"

    await client.send_file("me", bio, caption=f"📦 بکاپ {n} پیام از چت {event.chat_id}")
    await event.edit("✅ بکاپ به Saved Messages ارسال شد")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["بازیابی", "restore"], arg=False)))
async def restore_handler(event):
    """با ریپلای روی فایلِ خروجیِ `.پشتیبان تنظیمات`، تنظیمات بات رو (در PostgreSQL) برمی‌گردونه."""
    if not event.is_reply:
        return await event.edit(f"روی فایل بکاپِ تنظیمات (خروجیِ `{PREFIX}پشتیبان تنظیمات`) ریپلای کن")
    reply = await event.get_reply_message()
    if not reply.file:
        return await event.edit("پیام ریپلای‌شده فایل نداره")
    await event.edit("⏳ در حال بازیابی تنظیمات...")
    try:
        raw = await client.download_media(reply, file=bytes)
        data = json.loads(raw.decode("utf-8"))
        if data.get("_kind") != "selfbot_config_backup":
            return await event.edit("❌ این فایل، بکاپ تنظیماتِ سلف‌بات نیست")
        applied = await _apply_config_snapshot(data)
        if not applied:
            return await event.edit("چیزی برای بازیابی توی این فایل پیدا نشد")
        await event.edit("✅ بازیابی شد: " + "، ".join(applied))
    except json.JSONDecodeError:
        await event.edit("❌ فایل معتبر (JSON) نیست")
    except Exception as e:
        _record_error()
        await event.edit(f"❌ خطا در بازیابی: {e}")
