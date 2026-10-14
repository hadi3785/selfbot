"""
موتور اتوماسیون - اجرای قوانین بر اساس رویدادها
"""
import logging
import json
import time
from typing import Dict, Any, Optional, List

from .repositories import automation_repo
from .storage.scheduler_store import create_job
from .storage.notes_store import save_note
from .repositories.inbox_repo import save_item
from . import runtime
from .runtime import client

logger = logging.getLogger("selfbot.automation_engine")

# نگاشت عملیات به توابع
_action_handlers = {}


def register_action(action_type: str):
    """دکوریتور برای ثبت هندلر عملیات."""
    def decorator(func):
        _action_handlers[action_type] = func
        return func
    return decorator


@register_action("reply")
async def _handle_reply(rule, context: Dict[str, Any]):
    """ارسال پاسخ."""
    chat_id = context.get("chat_id")
    message_id = context.get("message_id")
    if not chat_id:
        return

    try:
        await client.send_message(
            chat_id,
            rule.action_value,
            reply_to=message_id,
        )
    except Exception as e:
        logger.error(f"خطا در ارسال پاسخ: {e}")


@register_action("ai")
async def _handle_ai(rule, context: Dict[str, Any]):
    """پاسخ با AI."""
    from . import ai
    chat_id = context.get("chat_id")
    message_id = context.get("message_id")
    if not chat_id:
        return

    try:
        response = await ai.ask_ai([
            {"role": "user", "content": rule.action_value}
        ], max_tokens=300)
        if response:
            await client.send_message(
                chat_id,
                response,
                reply_to=message_id,
            )
    except Exception as e:
        logger.error(f"خطا در پاسخ AI: {e}")


@register_action("note")
async def _handle_note(rule, context: Dict[str, Any]):
    """ذخیره یادداشت."""
    key = context.get("key", "auto")
    try:
        await save_note(key, rule.action_value)
    except Exception as e:
        logger.error(f"خطا در ذخیره یادداشت: {e}")


@register_action("schedule")
async def _handle_schedule(rule, context: Dict[str, Any]):
    """زمان‌بندی کار."""
    # action_value format: "time|text"
    parts = rule.action_value.split("|", 1)
    if len(parts) != 2:
        return
    time_str, text = parts
    from .handlers.scheduler import parse_time
    parsed = parse_time(time_str.strip())
    if parsed:
        run_at, _local_display = parsed
        try:
            await create_job(runtime.SELF_ID or context.get("chat_id"), text.strip(), run_at, "schedule")
        except Exception as e:
            logger.error(f"خطا در زمان‌بندی: {e}")


@register_action("notify")
async def _handle_notify(rule, context: Dict[str, Any]):
    """ارسال اعلان."""
    chat_id = context.get("chat_id")
    if not chat_id:
        return

    try:
        await client.send_message(
            chat_id,
            f"🔔 **اعلان اتوماسیون**\n\n{rule.action_value}",
        )
    except Exception as e:
        logger.error(f"خطا در ارسال اعلان: {e}")


@register_action("save")
async def _handle_save(rule, context: Dict[str, Any]):
    """ذخیره در صندوق ورودی."""
    chat_id = context.get("chat_id")
    message_id = context.get("message_id")
    text = context.get("text", rule.action_value)
    if not chat_id or not message_id:
        return

    try:
        await save_item(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            sender_id=context.get("sender_id"),
        )
    except Exception as e:
        logger.error(f"خطا در ذخیره: {e}")


@register_action("guard")
async def _handle_guard(rule, context: Dict[str, Any]):
    """
    روشن/خاموش‌کردنِ یکی از فیلترهای مدیریتِ گروه برای چتی که پیام توش اومده.
    action_value فرمتش: "<فیلتر>:<on|off>" - فیلتر یکی از:
    link (لینک), porn (پورن), spam (اسپم), profanity (فحش).
    مثال: "spam:on" یا "profanity:off"
    """
    from .storage.group_guard_store import (
        set_link_filter, set_porn_filter, set_spam_filter, set_profanity_filter,
    )

    chat_id = context.get("chat_id")
    if not chat_id:
        return

    raw = (rule.action_value or "").strip().lower()
    if ":" not in raw:
        logger.warning("مقدارِ نامعتبر برای عملیاتِ guard (باید <فیلتر>:<on|off> باشه): %r", rule.action_value)
        return
    filter_name, _, state = raw.partition(":")
    filter_name = filter_name.strip()
    enabled = state.strip() in ("on", "روشن", "true", "1")

    setters = {
        "link": set_link_filter,
        "لینک": set_link_filter,
        "porn": set_porn_filter,
        "پورن": set_porn_filter,
        "spam": set_spam_filter,
        "اسپم": set_spam_filter,
        "profanity": set_profanity_filter,
        "فحش": set_profanity_filter,
    }
    setter = setters.get(filter_name)
    if setter is None:
        logger.warning("فیلترِ ناشناخته برای عملیاتِ guard: %r", filter_name)
        return
    try:
        await setter(chat_id, enabled)
    except Exception as e:
        logger.error(f"خطا در اجرای عملیاتِ guard: {e}")


@register_action("backup")
async def _handle_backup(rule, context: Dict[str, Any]):
    """گرفتنِ یه بکاپِ کاملِ تنظیمات و ارسالش به Saved Messages."""
    from .handlers.backup import send_settings_backup

    try:
        await send_settings_backup(caption_note=f"⚡ بکاپِ خودکار (از قانونِ اتوماسیونِ «{rule.name}»)")
    except Exception as e:
        logger.error(f"خطا در بکاپِ خودکار: {e}")


@register_action("autopost")
async def _handle_autopost(rule, context: Dict[str, Any]):
    """یه دورِ ارسالِ خودکار رو فوری صف می‌کنه (دقیقاً هم‌رفتار با `.ارسال‌خودکار فوری`)."""
    from .storage.autopost_store import set_force_now

    try:
        set_force_now(True)
    except Exception as e:
        logger.error(f"خطا در صف‌کردنِ ارسالِ خودکار: {e}")


# جلوگیری از اجرای بیش‌ازحدِ یه قانون روی یه چت (مثلاً وقتی یه نفر پیام‌های
# پشتِ‌سرهم می‌فرسته که کلیدواژه‌ی trigger توشونه): بدونِ این، عملیات‌های
# پرهزینه مثلِ ai (هزینه‌ی API)، backup (I/O + کوئریِ دیتابیس)، یا reply
# (ریسکِ محدودیتِ فلادِ تلگرام) می‌تونستن ده‌ها بار در ثانیه اجرا بشن.
_MIN_TRIGGER_INTERVAL_SECONDS = 5
_MAX_COOLDOWN_ENTRIES = 500
_last_triggered: Dict[tuple, float] = {}


def _check_and_update_cooldown(rule_id: int, chat_id: Any) -> bool:
    """True یعنی مجازه اجرا بشه؛ False یعنی هنوز توی cooldown-ه و باید رد بشه."""
    key = (rule_id, chat_id)
    now = time.time()
    last = _last_triggered.get(key, 0.0)
    if now - last < _MIN_TRIGGER_INTERVAL_SECONDS:
        return False
    if key not in _last_triggered and len(_last_triggered) >= _MAX_COOLDOWN_ENTRIES:
        oldest_keys = sorted(_last_triggered, key=_last_triggered.get)[: _MAX_COOLDOWN_ENTRIES // 2]
        for k in oldest_keys:
            _last_triggered.pop(k, None)
    _last_triggered[key] = now
    return True


async def trigger_event(event_type: str, context: Dict[str, Any]):
    """
    اجرای قوانین منطبق با یک رویداد.
    """
    try:
        rules = await automation_repo.get_rules_for_event(event_type, context)
    except Exception:
        logger.exception("خطا در خواندن قوانین منطبق برای رویداد %s", event_type)
        return

    if not rules:
        return

    logger.debug("اجرای %d قانون برای رویداد %s", len(rules), event_type)

    for rule in rules:
        try:
            # بررسی شرط (اگر وجود داشته باشد)
            if rule.condition:
                condition_met = await _evaluate_condition(rule.condition, context)
                if not condition_met:
                    continue

            if not _check_and_update_cooldown(rule.id, context.get("chat_id")):
                continue

            # اجرای عملیات
            handler = _action_handlers.get(rule.action_type)
            if handler:
                await handler(rule, context)
            else:
                logger.warning(f"هندلر برای {rule.action_type} یافت نشد")

        except Exception as e:
            logger.exception(f"خطا در اجرای قانون {rule.id}: {e}")


async def _evaluate_condition(condition: str, context: Dict[str, Any]) -> bool:
    """
    ارزیابی شرط به صورت ساده.
    فرمت‌های پشتیبانی‌شده:
    - "keyword in message" → بررسی وجود کلمه در پیام
    - "sender_id == 123" → بررسی فرستنده
    - "chat_id == 456" → بررسی چت
    """
    condition = condition.strip()

    # بررسی شرط کلیدواژه
    if "in message" in condition:
        keyword = condition.replace("in message", "").strip().strip('"\'')
        message = context.get("text", "")
        return keyword.lower() in message.lower()

    # بررسی شرط برابری
    if "==" in condition:
        parts = condition.split("==", 1)
        left = parts[0].strip()
        right = parts[1].strip().strip('"\'')
        context_value = context.get(left)
        if context_value is not None:
            return str(context_value) == right

    return False  # شرط نامشخص → رد (امنیت: پیش‌فرض عدم اطمینان)