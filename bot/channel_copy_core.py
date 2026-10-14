"""هسته‌ی منطقیِ «کپی کانال» (`.کپی‌کانال`) — بدونِ وابستگی به Telethon/SQLAlchemy.

همه‌ی منطقِ خالص (پارس ورودی، دسته‌بندیِ پیام‌ها با حفظِ آلبوم، طبقه‌بندیِ
خطاهای تلگرام، پنجره‌ی سقفِ روزانه، متنِ وضعیت) اینجاست تا بدونِ اتصال به
تلگرام قابلِ تست باشه. خودِ ارسال/اتصال در handlers/channel_copy.py انجام می‌شه.

محدودیت‌های تلگرام که اینجا رعایت می‌شن:
  • هر درخواستِ forwardMessages حداکثر ۱۰۰ پیام (ما به‌طورِ پیش‌فرض ۲۰).
  • آلبوم‌ها (grouped_id) هرگز بینِ دو درخواست نصف نمی‌شن.
  • FloodWait / SlowMode: دقیقاً به‌اندازه‌ی خواسته‌شده صبر می‌کنیم.
  • خطاهای قطعی (دسترسی/PeerFlood/محتوای محافظت‌شده) → توقف، نه دورزدن.
  • سقفِ روزانه‌ی پیامِ کپی‌شده (پنجره‌ی ۲۴ ساعته).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

TELEGRAM_MAX_FORWARD_BATCH = 100
DAY = dt.timedelta(hours=24)


# ------------------------------------------------------------ parsing ---
_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_TME_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(.+)$", re.IGNORECASE)


def parse_chat_ref(raw: str) -> tuple[str, Any]:
    """
    ورودیِ کاربر برای مبدأ/مقصد → ("username", str) یا ("id", int).
    پشتیبانی: @user ، user ، t.me/user ، t.me/user/123 ، t.me/c/<id>/<msg> ،
    شناسه‌ی عددی (‎-100…‎ یا بدونِ پیشوند). لینکِ دعوتِ خصوصی (t.me/+…) قابلِ
    استفاده نیست چون بدونِ عضویت entity نمی‌ده → ValueError با راهنما.
    """
    s = (raw or "").strip().strip("<>").strip()
    if not s:
        raise ValueError("آدرسِ کانال خالیه")

    m = _TME_RE.match(s)
    if m:
        path = m.group(1).split("?")[0].strip("/")
        parts = path.split("/")
        first = parts[0]
        if first.startswith("+") or first.lower() == "joinchat":
            raise ValueError(
                "لینکِ دعوتِ خصوصی پشتیبانی نمی‌شه. اول با اکانتت عضوِ کانال شو، "
                "بعد یوزرنیم یا شناسه‌ی عددیِ کانال رو بده."
            )
        if first.lower() == "c" and len(parts) >= 2 and parts[1].isdigit():
            return "id", int(f"-100{parts[1]}")
        s = first

    if s.startswith("@"):
        s = s[1:]
    if re.fullmatch(r"-?\d+", s):
        return "id", int(s)
    if _USERNAME_RE.match(s):
        return "username", s
    raise ValueError(f"«{raw}» آدرسِ معتبرِ کانال نیست (از @username یا شناسه‌ی عددی استفاده کن)")


_WITH_AUTHOR_FLAGS = {"با‌نام", "بانام", "با_نام", "withauthor", "with-author", "with_author", "نام"}
_FROM_FLAGS = {"از", "from"}


def parse_start_args(tokens: list[str]) -> tuple[str, str, int, bool]:
    """
    ['@src', '@dst', 'از', '1200', 'با‌نام'] → (src_raw, dst_raw, from_id, drop_author)
    drop_author=True یعنی بدونِ برچسبِ «Forwarded from» (کپیِ تمیز - پیش‌فرض).
    """
    refs: list[str] = []
    from_id = 0
    drop_author = True
    i = 0
    while i < len(tokens):
        t = tokens[i]
        low = t.lower()
        if low in _FROM_FLAGS:
            if i + 1 >= len(tokens) or not tokens[i + 1].isdigit():
                raise ValueError("بعد از «از» باید شماره‌ی پیام بیاد (مثلاً: از 1200)")
            from_id = max(int(tokens[i + 1]) - 1, 0)  # min_id انحصاریه؛ «از N» یعنی خودِ N هم کپی بشه
            i += 2
            continue
        if low in _WITH_AUTHOR_FLAGS:
            drop_author = False
            i += 1
            continue
        refs.append(t)
        i += 1
    if len(refs) != 2:
        raise ValueError("باید دقیقاً دو آدرس بدی: مبدأ و مقصد")
    return refs[0], refs[1], from_id, drop_author


# ---------------------------------------------------------- batching ---
@dataclass
class Batch:
    ids: list[int] = field(default_factory=list)   # شناسه‌ی پیام‌های قابلِ فوروارد
    skipped: int = 0                               # پیام‌های سرویسی/ردشده در این دسته
    max_id: int = 0                                # بزرگ‌ترین شناسه‌ی پردازش‌شده


def _is_service(m: Any) -> bool:
    return bool(getattr(m, "action", None)) or m.__class__.__name__ == "MessageService"


async def iter_batches(messages: AsyncIterator[Any], batch_size: int) -> AsyncIterator[Batch]:
    """
    پیام‌ها (صعودی بر اساسِ id) → دسته‌هایی با حداکثر batch_size پیام.
    • پیام‌های سرویسی (عضو شد/پین/…) فوروارد نمی‌شن؛ فقط شمرده می‌شن.
    • پیام‌های هم‌آلبوم (grouped_id یکسان و پشتِ‌سرهم) همیشه توی یک دسته می‌مونن.
    • max_id هر دسته فقط شاملِ پیام‌های «کاملاً» داخلِ همون دسته‌ست؛ پس ادامه از
      روی last_id هیچ پیام/آلبومی رو جا نمی‌ندازه.
    """
    batch_size = max(1, min(batch_size, TELEGRAM_MAX_FORWARD_BATCH))
    cur = Batch()
    ready: list[Batch] = []
    album: list[Any] = []
    album_gid: Any = None

    def add_unit(unit: list[Any]) -> None:
        nonlocal cur
        if cur.ids and len(cur.ids) + len(unit) > batch_size:
            ready.append(cur)
            cur = Batch()
        for u in unit:
            cur.ids.append(u.id)
            cur.max_id = max(cur.max_id, u.id)
        if len(cur.ids) >= batch_size:
            ready.append(cur)
            cur = Batch()

    def close_album() -> None:
        nonlocal album, album_gid
        if album:
            add_unit(album)
            album, album_gid = [], None

    async for m in messages:
        if _is_service(m):
            close_album()  # آلبومِ در انتظار قبل از شمارشِ این پیام بسته می‌شه (ترتیبِ max_id حفظ بشه)
            cur.skipped += 1
            cur.max_id = max(cur.max_id, m.id)
        else:
            gid = getattr(m, "grouped_id", None)
            if gid is not None and album and gid == album_gid:
                album.append(m)
            else:
                close_album()
                if gid is not None:
                    album, album_gid = [m], gid
                else:
                    add_unit([m])
        for b in ready:
            yield b
        ready.clear()

    close_album()
    for b in ready:
        yield b
    if cur.ids or cur.skipped:
        yield cur


# ------------------------------------------------------ error classes ---
_WAIT_ERRORS = {"FloodWaitError", "SlowModeWaitError", "FloodPremiumWaitError"}

_FATAL_ERRORS = {
    "ChatForwardsRestrictedError": "فورواردِ این کانال/چت توسطِ مالکش بسته شده (محتوای محافظت‌شده)؛ کپی ممکن نیست.",
    "ChatWriteForbiddenError": "اجازه‌ی ارسال توی کانالِ مقصد رو نداری.",
    "ChatAdminRequiredError": "برای ارسال توی مقصد باید ادمین (با دسترسیِ انتشارِ پست) باشی.",
    "ChatRestrictedError": "ارسال توی مقصد برات محدود شده.",
    "UserBannedInChannelError": "توی یکی از کانال‌ها بن/محدود شدی.",
    "ChannelPrivateError": "دسترسی به یکی از کانال‌ها رو از دست دادی (خصوصی شده یا اخراج شدی).",
    "ChannelInvalidError": "یکی از کانال‌ها نامعتبره/حذف شده.",
    "ChannelBannedError": "یکی از کانال‌ها توسطِ تلگرام مسدود شده.",
    "ChatIdInvalidError": "شناسه‌ی چت نامعتبره.",
    "PeerFloodError": "تلگرام اکانت رو موقتاً به‌خاطرِ تعدادِ زیادِ درخواست محدود کرده (PeerFlood). چند ساعت صبر کن و بعد «ادامه» بزن.",
    "AuthKeyUnregisteredError": "سشن باطل شده.",
    "UserDeactivatedError": "اکانت غیرفعال شده.",
    "UserDeactivatedBanError": "اکانت مسدود شده.",
}

_SKIP_ERRORS = {"MessageIdInvalidError", "MessageEmptyError", "MediaEmptyError", "MessageNotModifiedError"}

_FATAL_BY_MESSAGE = (
    ("CHAT_FORWARDS_RESTRICTED", "ChatForwardsRestrictedError"),
    ("CHAT_WRITE_FORBIDDEN", "ChatWriteForbiddenError"),
    ("CHAT_ADMIN_REQUIRED", "ChatAdminRequiredError"),
    ("PEER_FLOOD", "PeerFloodError"),
    ("USER_BANNED_IN_CHANNEL", "UserBannedInChannelError"),
)


def classify_error(exc: BaseException) -> tuple[str, Any]:
    """
    ('wait', ثانیه) | ('fatal', پیامِ فارسی) | ('skip', None) | ('retry', None)
    بر اساسِ «نامِ کلاس» (و در صورتِ نبودِ کلاسِ اختصاصی در نسخه‌ی Telethon، متنِ RPC)
    تا به نسخه‌ی خاصی از Telethon وابسته نباشیم.
    """
    name = exc.__class__.__name__
    if name in _WAIT_ERRORS:
        secs = getattr(exc, "seconds", None)
        try:
            secs = int(secs)
        except (TypeError, ValueError):
            secs = 30
        return "wait", max(secs, 1)
    if name in _FATAL_ERRORS:
        return "fatal", _FATAL_ERRORS[name]
    if name in _SKIP_ERRORS:
        return "skip", None
    text = str(exc).upper()
    for needle, key in _FATAL_BY_MESSAGE:
        if needle in text:
            return "fatal", _FATAL_ERRORS[key]
    if "FLOOD_WAIT" in text:
        m = re.search(r"(\d+)", text)
        return "wait", int(m.group(1)) if m else 30
    return "retry", None


# ------------------------------------------------------- daily window ---
def check_window(
    now: dt.datetime,
    window_start: dt.datetime | None,
    window_count: int,
    limit: int,
    n: int,
) -> tuple[float, dt.datetime | None, int]:
    """
    سقفِ روزانه (پنجره‌ی ۲۴ساعته از اولین ارسال).
    خروجی: (ثانیه‌ی انتظار — ۰ یعنی مجازه, window_start, window_count) بعد از ریستِ احتمالی.
    فراخواننده بعد از ارسالِ موفق، window_count رو با تعدادِ واقعیِ کپی‌شده زیاد می‌کنه.
    """
    if limit <= 0:
        return 0.0, window_start, window_count
    if window_start is None or now - window_start >= DAY:
        return 0.0, now, 0
    if window_count > 0 and window_count + n > limit:
        wait = (window_start + DAY - now).total_seconds()
        return max(wait, 1.0), window_start, window_count
    return 0.0, window_start, window_count


# ----------------------------------------------------------- display ---
STATUS_LABELS = {
    "running": "در حال اجرا ▶️",
    "paused": "متوقف ⏸",
    "done": "تمام‌شده ✅",
    "error": "خطا ❌",
}


def _fmt_duration(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ساعت و {m} دقیقه"
    if m:
        return f"{m} دقیقه"
    return f"{s} ثانیه"


def format_status(job: dict, live: dict | None = None) -> str:
    live = live or {}
    copied, skipped, total = job["copied"], job["skipped"], job.get("total_hint", 0)
    lines = [
        f"📦 **کپی کانال #{job['id']}**",
        f"• مبدأ: {job['source_title'] or job['source_id']}",
        f"• مقصد: {job['dest_title'] or job['dest_id']}",
        f"• وضعیت: {STATUS_LABELS.get(job['status'], job['status'])}",
    ]
    if total > 0:
        pct = min(int((copied + skipped) * 100 / total), 100)
        lines.append(f"• پیشرفت: {copied} کپی‌شده از حدودِ {total} ({pct}%)")
    else:
        lines.append(f"• کپی‌شده: {copied}")
    if skipped:
        lines.append(f"• ردشده: {skipped} (پیامِ سرویسی/حذف‌شده)")
    lines.append(f"• آخرین پیامِ پردازش‌شده: #{job['last_id']}")
    lines.append("• حالت: " + ("با نامِ مبدأ" if not job.get("drop_author", True) else "بدونِ برچسبِ فوروارد"))

    if job["status"] == "running":
        if live.get("state"):
            lines.append(f"• الان: {live['state']}")
        t0, c0 = live.get("t0"), live.get("copied0", 0)
        now = live.get("now")
        if t0 is not None and now is not None and copied > c0 and total > 0:
            rate = (copied - c0) / max(now - t0, 1)
            remaining = max(total - copied - skipped, 0)
            if rate > 0 and remaining:
                lines.append(f"• زمانِ باقی‌مانده (تقریبی): {_fmt_duration(remaining / rate)}")
    if job.get("last_error"):
        lines.append(f"• ⚠️ {job['last_error']}")
    return "\n".join(lines)
