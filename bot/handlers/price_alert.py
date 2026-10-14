"""
دستورات هشدارِ قیمت: `.هشدارقیمت` - وقتی قیمتِ یه قلم (ارز/طلا/سکه، از همون
فیدِ TGJU که `.قیمت` ازش استفاده می‌کنه) به یه حدِ معین برسه، توی همون چتی که
هشدار توش ثبت شده اطلاع می‌ده.
"""
import asyncio
import logging

from telethon import events

from .. import config
from ..config import PREFIX
from ..runtime import client
from ..repositories import price_alert_repo
from ..storage.stats_store import record_error as _record_error
from ..utils import pat
from .tools import find_price_item, parse_price_value, _fetch_tgju_current

logger = logging.getLogger("selfbot.handlers.price_alert")

PRICE_ALERT_CHECK_INTERVAL = 300  # هر ۵ دقیقه - از حجمِ درخواست به TGJU جلوگیری می‌کنه

DIRECTION_WORDS = {
    "بالا": "above", "above": "above", ">": "above", "بیشتر": "above",
    "پایین": "below", "below": "below", "<": "below", "کمتر": "below",
}
DIRECTION_LABEL = {"above": "برسه به یا بیشتر از", "below": "برسه به یا کمتر از"}


@client.on(events.NewMessage(outgoing=True, pattern=pat(["هشدارقیمت", "pricealert"])))
async def price_alert_handler(event):
    raw = (event.pattern_match.group(1) or "").strip()
    parts = raw.split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    chat_id = event.chat_id

    if sub in ("افزودن", "add"):
        args = rest.split()
        if len(args) < 3:
            return await event.edit(
                f"مثال: `{PREFIX}هشدارقیمت افزودن دلار بالا 700000`\n"
                f"جهت: `بالا`/`پایین` (یا `above`/`below`)"
            )
        target_str, direction_word = args[-1], args[-2].lower()
        item_query = " ".join(args[:-2]).strip()

        direction = DIRECTION_WORDS.get(direction_word)
        if direction is None:
            return await event.edit(
                f"❌ جهتِ نامعتبر: «{args[-2]}». از `بالا` یا `پایین` استفاده کن."
            )
        try:
            target_price = parse_price_value(target_str)
        except ValueError:
            return await event.edit(f"❌ عددِ نامعتبر: «{target_str}»")

        item = find_price_item(item_query)
        if item is None:
            return await event.edit(
                f"❌ آیتمی با اسمِ «{item_query}» پیدا نشد یا بیش از یکی مچ شد "
                f"(دقیق‌تر بنویس). برای دیدنِ اسم‌ها: `{PREFIX}قیمت`"
            )
        key, label, unit = item
        alert = await price_alert_repo.add_alert(chat_id, key, label, direction, target_price)
        await event.edit(
            f"✅ هشدار ثبت شد (#{alert.id}): وقتی «{label}» {DIRECTION_LABEL[direction]} "
            f"**{target_price:,.0f}** {unit} برسه، همینجا خبر می‌دم."
        )
        return

    if sub in ("حذف", "remove", "delete"):
        if not rest.strip().isdigit():
            return await event.edit(f"مثال: `{PREFIX}هشدارقیمت حذف 3` (عددِ #آیدی از `{PREFIX}هشدارقیمت لیست`)")
        alert_id = int(rest.strip())
        success = await price_alert_repo.remove_alert(chat_id, alert_id)
        if success:
            await event.edit(f"✅ هشدارِ #{alert_id} حذف شد.")
        else:
            await event.edit("⚠️ هشداری با این آیدی توی این چت پیدا نشد.")
        return

    if sub in ("پاک", "clear"):
        count = await price_alert_repo.clear_alerts(chat_id)
        await event.edit(f"✅ {count} هشدار پاک شد." if count else "چیزی برای پاک‌کردن نبود.")
        return

    if sub in ("لیست", "list", ""):
        alerts = await price_alert_repo.list_alerts(chat_id)
        if not alerts:
            return await event.edit(
                "🔔 **هشدارِ قیمت**\n\n"
                "هیچ هشدارِ فعالی توی این چت نیست.\n\n"
                f"`{PREFIX}هشدارقیمت افزودن <آیتم> <بالا/پایین> <عدد>` — مثلاً `{PREFIX}هشدارقیمت افزودن دلار بالا 700000`\n"
                f"`{PREFIX}هشدارقیمت لیست` / `{PREFIX}هشدارقیمت حذف <id>` / `{PREFIX}هشدارقیمت پاک`\n"
                f"⏱ هر {PRICE_ALERT_CHECK_INTERVAL // 60} دقیقه یک‌بار چک می‌شه (نه لحظه‌ای)."
            )
        lines = [
            f"#{a.id} — {a.item_label}: {DIRECTION_LABEL[a.direction]} **{a.target_price:,.0f}**"
            for a in alerts
        ]
        return await event.edit("🔔 **هشدارهای فعالِ این چت**\n\n" + "\n".join(lines))

    return await event.edit(
        f"مثال: `{PREFIX}هشدارقیمت افزودن دلار بالا 700000` / `{PREFIX}هشدارقیمت لیست` / "
        f"`{PREFIX}هشدارقیمت حذف <id>` / `{PREFIX}هشدارقیمت پاک`"
    )


async def price_alert_worker():
    """هر PRICE_ALERT_CHECK_INTERVAL ثانیه یک‌بار، قیمت‌های فعلی رو با هشدارهای فعال مقایسه می‌کنه."""
    from .. import health

    while True:
        await asyncio.sleep(PRICE_ALERT_CHECK_INTERVAL)
        try:
            alerts = await price_alert_repo.list_all_untriggered()
            if not alerts:
                health.update_worker_status("price_alert", "ok")
                continue
            current = await _fetch_tgju_current()
            for alert in alerts:
                item = current.get(alert.item_key) or {}
                raw_price = item.get("p")
                if not raw_price:
                    continue
                try:
                    price = parse_price_value(raw_price)
                except ValueError:
                    continue
                hit = (
                    (alert.direction == "above" and price >= alert.target_price)
                    or (alert.direction == "below" and price <= alert.target_price)
                )
                if not hit:
                    continue
                await price_alert_repo.mark_triggered(alert.id)
                try:
                    await client.send_message(
                        alert.chat_id,
                        f"🔔 **هشدارِ قیمت**: «{alert.item_label}» {DIRECTION_LABEL[alert.direction]} "
                        f"**{alert.target_price:,.0f}** رسید (قیمتِ الان: **{raw_price}**)",
                    )
                except Exception:
                    _record_error()
                    logger.exception("خطا در ارسالِ اعلانِ هشدارِ قیمت")
            health.update_worker_status("price_alert", "ok")
        except Exception:
            _record_error()
            logger.exception("خطا در چکِ دوره‌ایِ هشدارِ قیمت")
            health.update_worker_status("price_alert", "error")
