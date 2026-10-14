"""📊 داشبوردِ «Personal Command Center» — اطلاعات‌محور، نه دستورمحور.

۶ بخش (طبق فایلِ ایده‌ها):
  👤 Status → 🚨 Attention → ⚡ Quick Actions → 📅 Today → 🧠 AI Insight → 🕘 Recent

دینامیک: پیامِ اولِ داشبورد بسته به وضعیت عوض می‌شود (کارِ عقب‌افتاده، پیامِ مهمِ
بی‌پاسخ، یادآوریِ نزدیک، یا «همه‌چیز مرتب است»). AI Insight هم اگر AI فعال باشد
با مدل ساخته می‌شود، وگرنه با قواعدِ محلی.
"""
import datetime as dt

from telethon import Button, events

from ..config import PREFIX, TIMEZONE_OFFSET
from ..health import get_uptime
from ..repositories import escape_repo, inbox_repo, tasks_repo
from ..repositories.settings_repo import get_setting_json
from ..runtime import client
from ..storage.scheduler_store import list_jobs
from ..storage.settings_toggles import toggles
from ..storage.stats_store import STATS, record_error as _record_error
from ..utils import pat

_RECENT_KEY = "panel_recent"
_MAX_RECENT = 4


def _fmt_uptime() -> str:
    try:
        return get_uptime()
    except Exception:
        return "—"


def _aware(d: dt.datetime | None) -> dt.datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _fmt_local(utc_dt: dt.datetime) -> str:
    naive = utc_dt.replace(tzinfo=None) if utc_dt.tzinfo else utc_dt
    return (naive + dt.timedelta(hours=TIMEZONE_OFFSET)).strftime("%H:%M")


async def _gather() -> dict:
    """همه‌ی شمارنده‌ها؛ هر بخش fail-safe."""
    d = {
        "unread": 0, "important": 0,
        "tasks_open": [], "overdue": [], "today_due": [],
        "reminders": [], "next_rem": None, "next_rem_in_min": None,
        "games": 0, "wins": 0,
        "msgs": STATS.get("messages_total", 0),
        "cmds": STATS.get("commands_total", 0),
        "autopilot": toggles.get("autopilot_enabled", False),
        "ai_ready": False, "ai_model": "",
        "recents": [],
    }
    now = dt.datetime.now(dt.timezone.utc)
    now_local = now + dt.timedelta(hours=TIMEZONE_OFFSET)
    end_today_utc = (now_local.replace(hour=23, minute=59, second=59, microsecond=0)
                     - dt.timedelta(hours=TIMEZONE_OFFSET)).replace(tzinfo=dt.timezone.utc)

    try:
        ib = await inbox_repo.get_stats()
        d["unread"] = ib.get("unread", 0)
        d["important"] = ib.get("important", 0)
    except Exception:
        pass

    try:
        tasks = await tasks_repo.list_tasks(done=False, limit=200)
        d["tasks_open"] = tasks
        for t in tasks:
            due = _aware(t.get("due_at"))
            if not due:
                continue
            if due < now:
                d["overdue"].append(t)
            elif due <= end_today_utc:
                d["today_due"].append(t)
    except Exception:
        pass

    try:
        jobs = await list_jobs("reminder")
        d["reminders"] = jobs
        future = sorted(
            (j for j in jobs if _aware(j.run_at) and _aware(j.run_at) > now),
            key=lambda j: _aware(j.run_at),
        )
        if future:
            d["next_rem"] = _aware(future[0].run_at)
            d["next_rem_in_min"] = int((_aware(future[0].run_at) - now).total_seconds() // 60)
    except Exception:
        pass

    try:
        esc = await escape_repo.stats_summary()
        d["games"] = esc.get("most_solved", 0) or 0
        d["wins"] = esc.get("top_score", 0) or 0
    except Exception:
        pass

    try:
        from .. import config

        d["ai_ready"] = bool(config.AI_API_KEY)
        d["ai_model"] = getattr(config, "AI_MODEL", "") or ""
    except Exception:
        pass

    try:
        rec = await get_setting_json(_RECENT_KEY, [])
        if isinstance(rec, list):
            norm = []
            for it in rec:
                if isinstance(it, list) and it and isinstance(it[0], str):
                    norm.append([it[0], float(it[1]) if len(it) > 1 else 0.0])
                elif isinstance(it, str):
                    norm.append([it, 0.0])
            d["recents"] = norm[:_MAX_RECENT]
    except Exception:
        pass
    return d


# بخش‌های قابلِ خاموش/روشن (Personalization)
_DASH_SECTIONS = {
    "attention": "🚨 نیاز به توجه",
    "today": "📅 امروز",
    "quick": "⚡ Quick Actions",
    "insight": "🧠 AI Insight",
    "recent": "🕘 اخیراً",
    "favorites": "⭐ موردعلاقه‌ها",
}


async def _dash_sections_on() -> dict:
    """پیش‌فرض: همه روشن. مقادیر از settings (panel_dash_sections: JSON)."""
    on = {k: True for k in _DASH_SECTIONS}
    try:
        saved = await get_setting_json("panel_dash_sections", None)
        if isinstance(saved, dict):
            for k, v in saved.items():
                if k in on:
                    on[k] = bool(v)
    except Exception:
        pass
    return on


async def _toggle_dash_section(section: str) -> bool | None:
    """toggleِ یک بخش؛ خروجی None = بخشِ نامعتبر."""
    if section not in _DASH_SECTIONS:
        return None
    on = await _dash_sections_on()
    on[section] = not on[section]
    from ..repositories.settings_repo import set_setting_json

    await set_setting_json("panel_dash_sections", on)
    return on[section]


def _attention_lines(d: dict, now: dt.datetime) -> list[str]:
    """🚨 NEEDS ATTENTION — فقط چیزهایی که واقعاً نیاز به توجه دارند."""
    items = []
    if d["important"]:
        items.append(f"🔴 {d['important']} پیامِ مهم در اینباکس")
    if d["overdue"]:
        items.append(f"🟡 {len(d['overdue'])} کارِ عقب‌افتاده")
    if d["next_rem_in_min"] is not None and d["next_rem_in_min"] <= 60:
        label = f"در {d['next_rem_in_min']} دقیقه" if d["next_rem_in_min"] > 0 else "همین حالا"
        items.append(f"⏰ یادآوری {label}")
    return items


def _greeting(d: dict, now_local: dt.datetime) -> str:
    """پیامِ دینامیکِ اول — حالِ امروزِ کاربر را در یک خط می‌گوید."""
    problems = len(d["overdue"]) + (1 if d["important"] else 0)
    if problems >= 2:
        return f"⚠️ {problems} مورد نیاز به توجه دارند"
    if d["overdue"]:
        return "⚠️ یک کار عقب‌افتاده داری"
    if d["important"]:
        return "📥 یک پیامِ مهم منتظرِ توست"
    if d["next_rem_in_min"] is not None and d["next_rem_in_min"] <= 15:
        return f"⏰ یک یادآوری تا {d['next_rem_in_min']} دقیقه دیگر"
    if not d["tasks_open"] and not d["reminders"]:
        return "🎉 همه‌چیز مرتب است"
    return "✅ وضعیتت خوبه — کارها پیش می‌ره"


def _task_suggestion(d: dict) -> str | None:
    """یک پیشنهادِ عملیِ محلی (بدونِ AI): اولویت با عقب‌افتاده‌ها/مهم‌ها."""
    if d["overdue"]:
        t = d["overdue"][0]
        return f"اول کارِ «{t['text'][:40]}» را انجام بده — عقب‌افتاده است"
    important = next((t for t in d["tasks_open"] if t.get("priority", 0) >= 1), None)
    if important:
        return f"کارِ مهمِ «{important['text'][:40]}» را انجام بده"
    if d["today_due"]:
        t = d["today_due"][0]
        return f"کارِ «{t['text'][:40]}» ددلاینش امروزه"
    return None


async def _ai_insight(d: dict, local_summary: str) -> str:
    """🧠 AI INSIGHT — با AI (اگر هست) وگرنه خلاصه‌ی محلیِ قاعده‌مند."""
    if d["ai_ready"]:
        try:
            from .. import ai

            out = await ai.ask_ai(
                [
                    {
                        "role": "system",
                        "content": (
                            "وضعیتِ روزانه‌ی یک مدیر را می‌بینی. به فارسی، حداکثر ۳ خط، "
                            "یک تحلیلِ کوتاه + یک پیشنهادِ عملیِ مشخص. بدونِ مقدمه، بدونِ «شما»."
                        ),
                    },
                    {"role": "user", "content": local_summary[:800]},
                ],
                max_tokens=140,
            )
            out = (out or "").strip()
            if out:
                return out
        except Exception:
            pass
    return local_summary


async def build_dashboard() -> str:
    """متنِ داشبورد (مشترک بین دستور و دکمه‌ی پنل) — با Personalization."""
    d = await _gather()
    now = dt.datetime.now(dt.timezone.utc)
    local_now = now + dt.timedelta(hours=TIMEZONE_OFFSET)
    sec_on = await _dash_sections_on()
    import time as _time

    from .panel import _CATEGORY_BY_KEY

    favs = []
    try:
        favs = await get_setting_json("panel_favorites", [])
        if not isinstance(favs, list):
            favs = []
    except Exception:
        favs = []
    favs = [k for k in favs[:4] if k in _CATEGORY_BY_KEY]

    # ── 👤 STATUS (همیشه)
    ai_state = "🟢 Ready" if d["ai_ready"] else "⚫ خاموش"
    lines = [
        "╭────── 🤖 HADI ASSISTANT ──────╮",
        f"🟢 آنلاین  •  ⏱ {_fmt_uptime()}",
        f"🕐 {local_now.strftime('%Y-%m-%d')} — {_greeting(d, local_now)}",
        "├───────────────────────────┤",
    ]

    # ── 🚨 ATTENTION
    if sec_on.get("attention"):
        att = _attention_lines(d, now)
        if att:
            lines.append("🚨 **نیاز به توجه**")
            lines.extend(f"• {a}" for a in att)
        else:
            lines.append("🚨 ✅ Everything looks good")
        lines.append("├───────────────────────────┤")

    # ── ⭐ FAVORITES (حداکثر ۴)
    if sec_on.get("favorites") and favs:
        lines.append("⭐ **موردعلاقه‌ها**")
        lines.append(" • ".join(
            f"{_CATEGORY_BY_KEY[k]['emoji']} {_CATEGORY_BY_KEY[k]['title']}" for k in favs
        ))
        lines.append("├───────────────────────────┤")

    # ── 📅 TODAY
    if sec_on.get("today"):
        rem_next = f" • ⏭ بعدی {_fmt_local(d['next_rem'])}" if d["next_rem"] else ""
        lines += [
            "📅 **امروز**",
            f"📝 {len(d['tasks_open'])} کارِ باز  •  📅 {len(d['today_due'])} ددلاینِ امروز",
            f"⏰ {len(d['reminders'])} یادآوری{rem_next}",
            f"📥 {d['unread']} خوانده‌نشده  •  🔴 {d['important']} مهم",
            "├───────────────────────────┤",
        ]

    # ── 🧠 AI INSIGHT
    if sec_on.get("insight"):
        local_summary = (
            f"کارهای باز: {len(d['tasks_open'])}، عقب‌افتاده: {len(d['overdue'])}، "
            f"ددلاینِ امروز: {len(d['today_due'])}، پیام‌های مهم: {d['important']}، "
            f"یادآوری‌ها: {len(d['reminders'])}"
        )
        insight = await _ai_insight(d, local_summary)
        suggestion = _task_suggestion(d)
        lines.append("🧠 **AI INSIGHT**")
        lines.append(f"🤖 AI: {ai_state}" + (f" ({d['ai_model']})" if d["ai_model"] else ""))
        lines.append(f"💡 {insight}")
        if suggestion:
            lines.append(f"🎯 پیشنهاد: {suggestion}")
        lines.append("├───────────────────────────┤")

    # ── 🕘 RECENT با «چند دقیقه پیش»
    if sec_on.get("recent") and d["recents"]:
        labels = []
        for it in d["recents"]:
            key, ts = (it if isinstance(it, list) else [it, 0.0])[:2]
            if key not in _CATEGORY_BY_KEY:
                continue
            cat = _CATEGORY_BY_KEY[key]
            ago = ""
            mins = int((_time.time() - float(ts)) // 60) if ts else None
            if mins is not None and mins >= 0:
                ago = f" ({mins}د پیش)" if mins < 60 else f" ({mins // 60}س پیش)"
            labels.append(f"{cat['emoji']} {cat['title']}{ago}")
        if labels:
            lines.append("🕘 اخیر: " + " • ".join(labels[:4]))

    # ── ⚡ QUICK ACTIONS
    if sec_on.get("quick"):
        lines += [
            "⚡ **QUICK ACTIONS**",
            f"`{PREFIX}پرسش` • `{PREFIX}اینباکس` • `{PREFIX}کار` • `{PREFIX}یادآوری`",
        ]

    lines += [
        f"📊 {d['msgs']:,} پیام  •  {d['cmds']:,} دستور  •  🎮 {d['games']} فرار",
        "╰───────────────────────────╯",
    ]
    return "\n".join(lines)


def _dashboard_buttons() -> list:
    """دکمه‌های داشبورد — مثل بقیه‌ی صفحاتِ پنل: بروزرسانی + پنل/بستن."""
    from .panel import _cb

    return [
        [
            Button.inline("🔄 بروزرسانی", _cb("refresh:dashboard")),
            Button.inline("⚙️ بخش‌ها", _cb("dashcfg")),
            Button.inline("🔙 پنل", _cb("home")),
        ],
        [Button.inline("✖️ بستن", _cb("close"))],
    ]


@client.on(events.NewMessage(outgoing=True, pattern=pat(["داشبورد", "dashboard"])))
async def dashboard_handler(event):
    await event.edit("📊 در حال جمع‌کردنِ داشبورد...")
    try:
        text = await build_dashboard()
        await event.edit(text, buttons=_dashboard_buttons())
    except Exception as e:
        _record_error()
        await event.edit(f"❌ خطا در داشبورد: {e}")
