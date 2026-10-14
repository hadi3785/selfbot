"""تستِ شبیه‌سازی‌شده‌ی استارتاپ: main() با BOT_TOKEN باید بدونِ UnboundLocalError
از بلوکِ bot_client عبور کند (crash-loopِ نسخه‌ی قبلی)."""
import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x" * 32)
os.environ.setdefault("BOT_TOKEN", "123:fake")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.pop("SESSION_STRING", None)

import main as mm  # noqa: E402


async def run():
    patches = [
        mock.patch.object(mm, "load_all_persistent_state", new=mock.AsyncMock()),
        mock.patch.object(mm, "load_all_plugins", new=mock.AsyncMock(return_value={})),
        mock.patch.object(mm.client, "get_me",
                          new=mock.AsyncMock(return_value=mock.Mock(id=1, first_name="T"))),
        mock.patch.object(mm.bot_client, "start", new=mock.AsyncMock()),
        mock.patch.object(mm.bot_client, "get_me",
                          new=mock.AsyncMock(return_value=mock.Mock(username="ubot"))),
        mock.patch.object(mm.bot_client, "run_until_disconnected",
                          new=mock.AsyncMock(return_value=None)),
        mock.patch.object(mm.client, "run_until_disconnected",
                          new=mock.AsyncMock(return_value=None)),
    ]
    for w in ("clock_updater", "autopost_worker", "assistant_status_watcher",
              "assistant_session_poller", "assistant_status_poller", "scheduler_worker",
              "daily_digest_worker", "stats_saver", "message_tracker_cleanup_worker",
              "price_alert_worker", "recurring_worker", "connection_watchdog"):
        patches.append(mock.patch.object(mm, w, new=lambda: asyncio.sleep(999)))
    patches += [
        mock.patch.object(mm, "save_stats", new=mock.AsyncMock()),
        mock.patch.object(mm, "flush_message_activity", new=mock.AsyncMock()),
        mock.patch.object(mm, "close_http_session", new=mock.AsyncMock()),
        mock.patch.object(mm, "dispose_engine", new=mock.AsyncMock()),
        mock.patch.object(mm.client, "disconnect", new=mock.AsyncMock()),
        mock.patch.object(mm.bot_client, "disconnect", new=mock.AsyncMock()),
    ]
    for p in patches:
        p.start()
    try:
        # main() باید به انتظارِ disconnect برسد (اینجا mock فوراً برمی‌گردد)
        await asyncio.wait_for(mm.main(), timeout=6)
    finally:
        for p in patches:
            p.stop()


asyncio.run(run())
print("✅ main() با BOT_TOKEN بدونِ UnboundLocalError کامل اجرا شد")
