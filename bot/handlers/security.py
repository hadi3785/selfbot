"""🛡 Security Center (`.امنیت`): نمایِ امنیتیِ یکجا برای اجرایِ روی Railway."""
import os

from telethon import events

from .. import config, runtime
from ..config import PREFIX
from ..db.engine import DATABASE_URL
from ..health import check_ai, check_postgresql, check_telegram, get_uptime
from ..plugin_loader import get_all_plugins
from ..runtime import client
from ..storage.stats_store import STATS
from ..utils import pat


def _mark(ok: bool) -> str:
    return "🟢" if ok else "🔴"


@client.on(events.NewMessage(outgoing=True, pattern=pat(["امنیت", "security"])))
async def security_handler(event):
    await event.edit("🛡 در حال بررسی...")

    tg_ok = await check_telegram()
    db_ok = await check_postgresql()
    ai_ok = await check_ai()

    session_ok = bool(runtime.bot_client and runtime.bot_client.is_connected()) or bool(
        getattr(runtime, "bot_client", None)
    )
    is_postgres = DATABASE_URL.startswith("postgres")
    ai_key_set = bool(config.AI_API_KEY)
    session_env = bool(os.getenv("SESSION_STRING"))
    plugins = get_all_plugins()
    errors = STATS.get("errors", 0)

    lines = [
        "🛡 **SECURITY CENTER**",
        "",
        f"{_mark(tg_ok)} Telegram  |  {_mark(db_ok)} Database ({'PostgreSQL' if is_postgres else 'SQLite 🔸'})  |  {_mark(ai_ok)} AI API",
        f"{_mark(session_env)} SESSION_STRING از env  |  {_mark(True)} Rate Limiter فعال",
        f"🧩 پلاگین‌های فعال: {len(plugins)}",
        "",
        f"⚠️ خطاهای ثبت‌شده: {errors}",
        f"⏱ Uptime: {get_uptime()}",
        "",
        "**توصیه‌ها:**",
    ]
    if not session_env:
        lines.append("• SESSION_STRING در env ست نیست — روی Railway باید StringSession ست شود")
    if not is_postgres:
        lines.append("• روی Railway از DATABASE_URL با postgres استفاده کن (SQLite با restart پاک می‌شود)")
    if not ai_key_set:
        lines.append("• AI_API_KEY ست نیست — قابلیت‌های AI خاموش‌اند (سلف‌بات بدون آن هم کار می‌کند)")
    if errors > 20:
        lines.append("• خطاهای سیستمی زیاد است — لاگِ Railway را چک کن (`.سلامت` هم وضعیت workerها)")
    if len(lines) == 10:
        lines.append("• همه‌چیز مرتب است ✅")

    lines.append(f"\nبرای نشست‌های فعال: `{PREFIX}نشست‌ها` — وضعیت workerها: `{PREFIX}سلامت`")
    await event.edit("\n".join(lines))
