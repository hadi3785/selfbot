"""📦 کپی کانال: `.کپی‌کانال` — فورواردِ همه‌ی پست‌های یک کانال به کانالِ دیگه.

مثال‌ها:
  .کپی‌کانال شروع @مبدا @مقصد            (از اولین پست؛ بدونِ برچسبِ Forwarded from)
  .کپی‌کانال شروع @مبدا @مقصد از 1200    (از پیامِ شماره‌ی 1200 به بعد)
  .کپی‌کانال شروع @مبدا @مقصد از 1403/05/01   (از تاریخِ شمسی به بعد — میلادی هم می‌شه)
  .کپی‌کانال شروع @مبدا @مقصد از امروز    (امروز/دیروز/پریروز + ساعتِ اختیاری)
  .کپی‌کانال شروع @مبدا @مقصد با‌نام      (با نامِ کانالِ مبدأ)
  .کپی‌کانال وضعیت / توقف / ادامه / لیست / حذف 3

رعایتِ محدودیت‌های تلگرام:
  • فوروارد دسته‌ای (پیش‌فرض ۲۰ پیام در هر درخواست؛ سقفِ تلگرام ۱۰۰) و آلبوم‌ها سالم می‌مونن
  • مکثِ ثابت بینِ دسته‌ها + صبر دقیق روی FloodWait/SlowMode
  • سقفِ روزانه فقط اگه CHANNEL_COPY_DAILY_LIMIT رو بزرگ‌تر از ۰ بذاری فعاله (پیش‌فرض: بدونِ سقف)
  • پیشرفت توی دیتابیس ذخیره می‌شه؛ بعد از توقف/ری‌استارت با «ادامه» دنبال می‌شه
  • کانال‌های با «محتوای محافظت‌شده» (noforwards) کپی نمی‌شن — این محدودیت دور زده نمی‌شه
"""
import asyncio
import datetime as dt
import logging
import time

from telethon import events, utils as tl_utils
from telethon.tl.types import Channel, Chat, PeerChannel

from .. import config
from ..channel_copy_core import (
    check_window,
    classify_error,
    find_start_id,
    format_from_date,
    format_status,
    iter_batches,
    parse_chat_ref,
    parse_start_args,
)
from ..repositories import channel_copy_repo as repo
from ..runtime import client
from ..utils import pat

logger = logging.getLogger(__name__)

_TASKS: dict[int, asyncio.Task] = {}
_STOP: dict[int, asyncio.Event] = {}
_LIVE: dict[int, dict] = {}

_MAX_ATTEMPTS = 5
_MAX_BAD_BATCHES_IN_ROW = 5
_PER_MESSAGE_FALLBACK_DELAY = 3.0

USAGE = (
    "📦 **کپی کانال**\n"
    f"`{config.PREFIX}کپی‌کانال شروع @مبدا @مقصد` — از اولین پست\n"
    f"`{config.PREFIX}کپی‌کانال شروع @مبدا @مقصد از 1200` — از پیامِ 1200 به بعد\n"
    f"`{config.PREFIX}کپی‌کانال شروع @مبدا @مقصد از 1403/05/01` — از تاریخِ شمسی به بعد\n"
    f"`{config.PREFIX}کپی‌کانال شروع @مبدا @مقصد از 2024-08-22 ساعت 10:30` — تاریخِ میلادی + ساعت\n"
    f"`{config.PREFIX}کپی‌کانال شروع @مبدا @مقصد از امروز` — امروز / دیروز / پریروز\n"
    f"`{config.PREFIX}کپی‌کانال شروع @مبدا @مقصد با‌نام` — با برچسبِ Forwarded from\n"
    f"`{config.PREFIX}کپی‌کانال وضعیت` | `توقف` | `ادامه [شماره]` | `لیست` | `حذف <شماره>`\n\n"
    "• مقصد باید کانالی باشه که توش ادمین (با دسترسیِ انتشار) هستی.\n"
    "• کانال‌های با «محتوای محافظت‌شده» کپی نمی‌شن."
)


class _Fatal(Exception):
    pass


class _Stopped(Exception):
    pass


# --------------------------------------------------------------- utils ---
async def _sleep(stop: asyncio.Event, seconds: float) -> bool:
    """مکثِ قابلِ قطع. True یعنی «توقف» درخواست شده."""
    if stop.is_set():
        return True
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(seconds, 0))
        return True
    except asyncio.TimeoutError:
        return False


async def _notify(text: str) -> None:
    """اعلان توی Saved Messages (نه توی کانالِ مقصد/مبدأ تا پست‌ها آلوده نشن)."""
    try:
        await client.send_message("me", text)
    except Exception:
        logger.warning("ارسالِ اعلانِ کپی‌کانال ناموفق بود", exc_info=True)


async def _resolve(kind_value: tuple[str, object] | None, stored_id: int | None, stored_ref: str = ""):
    """entity رو پیدا می‌کنه. بعد از ری‌استارت کَشِ entity خالیه → یک‌بار get_dialogs."""
    candidates = []
    if kind_value is not None:
        kind, val = kind_value
        candidates.append(PeerChannel(val) if kind == "id" and val > 0 else val)
    if stored_id is not None:
        candidates.append(stored_id)
    if stored_ref and not stored_ref.lstrip("-").isdigit():
        candidates.append(stored_ref)

    # تلاش اول: مستقیم
    for c in candidates:
        try:
            return await asyncio.wait_for(client.get_entity(c), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("get_entity(%r) timeout شد", c)
            continue
        except (ValueError, TypeError):
            continue
        except Exception as e:
            logger.debug("get_entity(%r) failed: %s", c, e)
            continue
    
    # تلاش دوم: بعد از get_dialogs
    try:
        await asyncio.wait_for(client.get_dialogs(), timeout=15)
    except asyncio.TimeoutError:
        logger.warning("get_dialogs timeout شد")
    except Exception:
        logger.warning("get_dialogs ناموفق بود", exc_info=True)
    
    for c in candidates:
        try:
            return await asyncio.wait_for(client.get_entity(c), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("get_entity(%r) timeout شد (دومین تلاش)", c)
            continue
        except (ValueError, TypeError):
            continue
        except Exception as e:
            logger.debug("get_entity(%r) failed (دومین تلاش): %s", c, e)
            continue
    
    return None


def _title(entity) -> str:
    return getattr(entity, "title", None) or getattr(entity, "username", None) or str(entity.id)


async def _validate_pair(src, dst) -> str | None:
    """None = مشکلی نیست؛ وگرنه متنِ خطا."""
    for e, label in ((src, "مبدأ"), (dst, "مقصد")):
        if not isinstance(e, (Channel, Chat)):
            return f"{label} باید کانال یا گروه باشه (نه کاربر/بات)."
    if tl_utils.get_peer_id(src) == tl_utils.get_peer_id(dst):
        return "مبدأ و مقصد یکی‌ان."
    if getattr(src, "noforwards", False):
        return (
            "این کانال «محتوای محافظت‌شده» داره (مالکش فوروارد/ذخیره رو بسته)؛ "
            "تلگرام اجازه‌ی کپی نمی‌ده و این محدودیت دور زده نمی‌شه."
        )
    if isinstance(dst, Channel):
        try:
            perms = await asyncio.wait_for(client.get_permissions(dst), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("get_permissions timeout شد")
            return "درخواست دسترسی‌ها timeout شد. دوباره تلاش کن."
        except Exception as e:
            logger.warning("get_permissions failed: %s", e)
            return f"نتونستم دسترسی‌هات رو توی مقصد بررسی کنم: {e}"
        
        if perms is None:
            # اگر مالک کانال هستی ولی perms برنمی‌گرده، احتمالاً مشکل cache است
            # بذار بدون چک ادامه بده و اگر واقعاً مشکل باشه موقع فوروارد معلوم می‌شه
            logger.warning("perms is None for channel %s - skipping permission check", dst.id)
        elif dst.broadcast:
            if not (perms.is_creator or getattr(perms, "post_messages", False)):
                return "توی کانالِ مقصد دسترسیِ انتشارِ پست نداری (باید سازنده یا ادمین باشی)."
        elif not (perms.is_creator or perms.is_admin or getattr(perms, "send_messages", True)):
            return "توی گروهِ مقصد اجازه‌ی ارسال نداری."
    return None


# ------------------------------------------------------------- forward ---
async def _fetch_dates(src, ids: list[int]) -> dict[int, dt.datetime]:
    """
    شناسه‌ها → تاریخشون (فقطِ پیام‌های موجود)؛ برای پیدا کردنِ مرزِ تاریخ.
    هر درخواست حداکثرِ ۱۰۰ شناسه (سقفِ channels.getMessages) + صبرِ احتمالی روی FloodWait.
    """
    out: dict[int, dt.datetime] = {}
    ids = [i for i in dict.fromkeys(int(x) for x in ids) if i > 0]
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        res = None
        for attempt in range(3):
            try:
                res = await asyncio.wait_for(client.get_messages(src, ids=chunk), timeout=45)
                break
            except asyncio.TimeoutError:
                logger.warning("get_messages(ids) timeout شد (تلاش %s)", attempt + 1)
                continue
            except Exception as e:
                kind, val = classify_error(e)
                if kind == "wait":
                    logger.info("کپی‌کانال: تلگرام %s ثانیه صبر خواست (خوندنِ تاریخ‌ها)", val)
                    await asyncio.sleep(val + 1)
                    continue
                if kind == "fatal":
                    raise
                logger.warning("get_messages(ids) خطا: %r", e)
                await asyncio.sleep(2)
        if res is None:
            continue
        for m in res:
            if m is None:
                continue
            mid, d = getattr(m, "id", None), getattr(m, "date", None)
            if mid and d is not None:
                out[int(mid)] = d
        await asyncio.sleep(0.3)  # ملایم با تلگرام؛ کلِ جستجو چند ثانیه بیشتر طول نمی‌کشه
    return out


async def _start_id_by_date(src, from_date: dt.datetime) -> int | None:
    """اولین شناسه‌ی پیامِ «از تاریخِ خواسته‌شده به بعد» — یا None."""
    # از وقتِ کاربر (بدونِ tz) به UTC — پیام‌های تلگرام UTC هستن
    target = (from_date - dt.timedelta(hours=config.TIMEZONE_OFFSET)).replace(tzinfo=dt.timezone.utc)
    try:
        latest = list(await asyncio.wait_for(client.get_messages(src, limit=1), timeout=30))
    except Exception:
        logger.warning("گرفتنِ آخرین پیامِ مبدأ ناموفق بود", exc_info=True)
        latest = []
    high = int(latest[0].id) if latest else 0
    return await find_start_id(lambda ids: _fetch_dates(src, ids), 1, high, target)


async def _do_forward(dst, src, ids: list[int], drop_author: bool):
    kwargs = {"from_peer": src, "silent": True}
    if drop_author:
        kwargs["drop_author"] = True
    try:
        return await client.forward_messages(dst, ids, **kwargs)
    except TypeError as e:
        if "drop_author" in str(e):
            raise _Fatal("نسخه‌ی Telethon قدیمیه (drop_author پشتیبانی نمی‌شه). با `pip install -U telethon` به‌روزش کن.")
        raise


def _count(res, n: int) -> tuple[int, int]:
    if res is None:
        return 0, n
    if isinstance(res, (list, tuple)):
        ok = sum(1 for m in res if m is not None)
    else:
        ok = 1
    return min(ok, n), max(n - ok, 0)


async def _forward_safe(job_id: int, dst, src, ids: list[int], drop_author: bool, stop: asyncio.Event) -> tuple[int, int]:
    """(کپی‌شده, ردشده). _Fatal/_Stopped می‌اندازه."""
    live = _LIVE.setdefault(job_id, {})
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            res = await _do_forward(dst, src, ids, drop_author)
            return _count(res, len(ids))
        except (_Fatal, _Stopped):
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:
            kind, val = classify_error(e)
            if kind == "wait":
                live["state"] = f"انتظارِ تلگرام ({val} ثانیه)"
                logger.info("کپی‌کانال #%s: wait %ss (%s)", job_id, val, e.__class__.__name__)
                if await _sleep(stop, val + 1):
                    raise _Stopped()
                continue
            if kind == "fatal":
                raise _Fatal(val)
            if kind == "skip":
                break
            logger.warning("کپی‌کانال #%s: خطا (تلاش %s/%s): %r", job_id, attempt, _MAX_ATTEMPTS, e)
            if await _sleep(stop, 5 * attempt):
                raise _Stopped()

    if len(ids) == 1:
        return 0, 1
    # فال‌بک: تک‌تک (فقط در مسیرِ خطا؛ ممکنه آلبومِ دارایِ پیامِ خراب از هم جدا بشه)
    ok = bad = 0
    for mid in ids:
        o, b = await _forward_safe(job_id, dst, src, [mid], drop_author, stop)
        ok, bad = ok + o, bad + b
        if await _sleep(stop, _PER_MESSAGE_FALLBACK_DELAY):
            raise _Stopped()
    return ok, bad


async def _run_job(job_id: int) -> None:
    stop = _STOP[job_id]
    live = _LIVE.setdefault(job_id, {})
    try:
        job = await repo.get_job(job_id)
        if not job:
            return
        src = await _resolve(None, job["source_id"], job["source_ref"])
        dst = await _resolve(None, job["dest_id"], job["dest_ref"])
        if src is None or dst is None:
            raise _Fatal("مبدأ یا مقصد پیدا نشد (عضو هستی؟).")
        err = await _validate_pair(src, dst)
        if err:
            raise _Fatal(err)

        copied, skipped, last_id = job["copied"], job["skipped"], job["last_id"]
        w_start, w_count = job["window_start"], job["window_count"]
        if w_start is not None and w_start.tzinfo is None:
            w_start = w_start.replace(tzinfo=dt.timezone.utc)
        drop_author = job["drop_author"]
        limit = config.CHANNEL_COPY_DAILY_LIMIT
        delay = config.CHANNEL_COPY_DELAY_SECONDS
        live.update(t0=time.time(), copied0=copied, state="شروع")
        bad_in_row = 0

        async for batch in iter_batches(
            client.iter_messages(src, min_id=last_id, reverse=True), config.CHANNEL_COPY_BATCH_SIZE
        ):
            if stop.is_set():
                break

            if not batch.ids:  # فقط پیام‌های سرویسی
                skipped += batch.skipped
                last_id = max(last_id, batch.max_id)
                await repo.update_progress(
                    job_id, last_id=last_id, copied=copied, skipped=skipped,
                    window_start=w_start, window_count=w_count,
                )
                continue

            # سقفِ روزانه
            while True:
                now = dt.datetime.now(dt.timezone.utc)
                wait, w_start, w_count = check_window(now, w_start, w_count, limit, len(batch.ids))
                if wait <= 0:
                    break
                live["state"] = f"سقفِ روزانه پر شد؛ {int(wait // 60)} دقیقه‌ی دیگه ادامه می‌دم"
                if await _sleep(stop, min(wait, 60)):
                    break
            if stop.is_set():
                break

            live["state"] = f"در حالِ کپیِ {len(batch.ids)} پیام"
            ok, bad = await _forward_safe(job_id, dst, src, batch.ids, drop_author, stop)

            copied += ok
            skipped += bad + batch.skipped
            last_id = max(last_id, batch.max_id)
            w_count += ok
            await repo.update_progress(
                job_id, last_id=last_id, copied=copied, skipped=skipped,
                window_start=w_start, window_count=w_count,
            )

            bad_in_row = bad_in_row + 1 if ok == 0 else 0
            if bad_in_row >= _MAX_BAD_BATCHES_IN_ROW:
                raise _Fatal(f"{_MAX_BAD_BATCHES_IN_ROW} دسته‌ی پشتِ‌سرهم ناموفق بود؛ برای جلوگیری از مشکل متوقف شد.")

            live["state"] = f"مکثِ {int(delay)} ثانیه بینِ دسته‌ها"
            if await _sleep(stop, delay):
                break

        if stop.is_set():
            await repo.set_status(job_id, "paused", "با دستور متوقف شد")
            await _notify(f"⏸ کپی کانال #{job_id} متوقف شد ({copied} پیام کپی شده). با «{config.PREFIX}کپی‌کانال ادامه» دنبال کن.")
        else:
            await repo.set_status(job_id, "done", "")
            await _notify(f"✅ کپی کانال #{job_id} تمام شد: {copied} پیام کپی شد" + (f"، {skipped} مورد رد شد." if skipped else "."))

    except _Stopped:
        await repo.set_status(job_id, "paused", "با دستور متوقف شد")
    except _Fatal as e:
        logger.warning("کپی‌کانال #%s متوقف شد: %s", job_id, e)
        await repo.set_status(job_id, "error", str(e))
        await _notify(f"❌ کپی کانال #{job_id} متوقف شد:\n{e}\n(پیشرفت ذخیره شده؛ بعد از رفعِ مشکل «{config.PREFIX}کپی‌کانال ادامه» بزن.)")
    except asyncio.CancelledError:
        await repo.set_status(job_id, "paused", "پروسه بسته شد")
        raise
    except Exception as e:
        logger.exception("کپی‌کانال #%s: خطای پیش‌بینی‌نشده", job_id)
        await repo.set_status(job_id, "error", f"خطای پیش‌بینی‌نشده: {e!r}")
        await _notify(f"❌ کپی کانال #{job_id} با خطای پیش‌بینی‌نشده متوقف شد: {e!r}")
    finally:
        _TASKS.pop(job_id, None)
        _STOP.pop(job_id, None)
        _LIVE.pop(job_id, None)


def _spawn(job_id: int) -> None:
    _STOP[job_id] = asyncio.Event()
    _LIVE[job_id] = {}
    _TASKS[job_id] = asyncio.create_task(_run_job(job_id))


def _running_id() -> int | None:
    for jid, t in _TASKS.items():
        if not t.done():
            return jid
    return None


def _status_text(job: dict) -> str:
    live = dict(_LIVE.get(job["id"], {}))
    live["now"] = time.time()
    return format_status(job, live)


# ------------------------------------------------------------ commands ---
@client.on(events.NewMessage(outgoing=True, pattern=pat(["کپی‌کانال", "کپی_کانال", "کپیکانال", "copychannel"])))
async def channel_copy_handler(event):
    arg = (event.pattern_match.group(1) or "").strip()
    tokens = arg.split()
    sub = tokens[0].lower() if tokens else ""
    rest = tokens[1:]

    if sub in ("راهنما", "help"):
        return await event.edit(USAGE)

    if sub in ("وضعیت", "status", ""):
        job = await (repo.get_job(int(rest[0])) if rest and rest[0].isdigit() else repo.get_latest_job())
        if not job:
            return await event.edit(USAGE)
        return await event.edit(_status_text(job))

    if sub in ("لیست", "list"):
        jobs = await repo.list_jobs(10)
        if not jobs:
            return await event.edit("هنوز کاری ثبت نشده.")
        lines = ["📋 **کارهای کپی کانال**"]
        for j in jobs:
            lines.append(
                f"#{j['id']} {j['source_title'] or j['source_id']} → {j['dest_title'] or j['dest_id']} "
                f"| {j['copied']} پیام | {j['status']}"
            )
        return await event.edit("\n".join(lines))

    if sub in ("توقف", "stop"):
        jid = _running_id()
        if jid is None:
            return await event.edit("کارِ فعالی نیست.")
        _STOP[jid].set()
        return await event.edit(f"⏸ درخواستِ توقفِ کار #{jid} ثبت شد (بعد از دسته‌ی جاری متوقف می‌شه).")

    if sub in ("حذف", "delete"):
        if not rest or not rest[0].isdigit():
            return await event.edit("شماره‌ی کار رو بده: `.کپی‌کانال حذف 3`")
        jid = int(rest[0])
        if jid in _TASKS:
            return await event.edit("این کار در حالِ اجراست؛ اول «توقف» بزن.")
        ok = await repo.delete_job(jid)
        return await event.edit("🗑 حذف شد." if ok else "کاری با این شماره نیست.")

    if sub in ("ادامه", "resume"):
        if _running_id() is not None:
            return await event.edit("یک کپی در حالِ اجراست؛ همزمان فقط یکی مجازه.")
        if rest and rest[0].isdigit():
            job = await repo.get_job(int(rest[0]))
        else:
            job = await repo.get_latest_job()
        if not job:
            return await event.edit("کاری برای ادامه پیدا نشد.")
        if job["status"] == "done":
            return await event.edit("این کار قبلاً تموم شده.")
        await repo.set_status(job["id"], "running", "")
        _spawn(job["id"])
        return await event.edit(f"▶️ کار #{job['id']} از پیامِ #{job['last_id']} ادامه پیدا کرد.")

    # شروع: هم «شروع a b» و هم «a b» (بدونِ زیردستور)
    if sub in ("شروع", "start"):
        tokens_for_start = rest
    else:
        tokens_for_start = tokens
    try:
        src_raw, dst_raw, from_id, from_date, drop_author = parse_start_args(list(tokens_for_start))
        src_ref, dst_ref = parse_chat_ref(src_raw), parse_chat_ref(dst_raw)
    except ValueError as e:
        return await event.edit(f"⚠️ {e}\n\n{USAGE}")

    if _running_id() is not None:
        return await event.edit("یک کپی در حالِ اجراست؛ همزمان فقط یکی مجازه (وضعیت/توقف).")

    msg = await event.edit("🔎 در حالِ بررسیِ کانال‌ها… (ممکنه تا 30 ثانیه طول بکشه)")
    
    try:
        src = await _resolve(src_ref, None)
    except Exception as e:
        logger.exception("خطا در resolve کردن مبدأ")
        return await msg.edit(f"❌ خطا در پیدا کردن مبدأ: {e}")
    
    if src is None:
        return await msg.edit("⚠️ کانالِ مبدأ پیدا نشد (باید عضوش باشی یا عمومی باشه).")
    
    try:
        dst = await _resolve(dst_ref, None)
    except Exception as e:
        logger.exception("خطا در resolve کردن مقصد")
        return await msg.edit(f"❌ خطا در پیدا کردن مقصد: {e}")
    
    if dst is None:
        return await msg.edit("⚠️ کانالِ مقصد پیدا نشد (باید عضوش باشی).")
    
    try:
        err = await _validate_pair(src, dst)
    except Exception as e:
        logger.exception("خطا در validate_pair")
        return await msg.edit(f"❌ خطا در بررسی کانال‌ها: {e}")
    
    if err:
        return await msg.edit(f"⛔ {err}")

    total = 0
    try:
        total = int(getattr(await client.get_messages(src, limit=0), "total", 0) or 0)
    except Exception:
        logger.debug("total شمارش نشد", exc_info=True)

    start_note = ""
    if from_date is not None:
        await msg.edit(
            f"🔎 دارم اولین پیامِ **{format_from_date(from_date)}** رو توی کانالِ مبدأ پیدا می‌کنم… (تا یک دقیقه)"
        )
        try:
            start_id = await _start_id_by_date(src, from_date)
        except Exception as e:
            logger.exception("خطا در پیدا کردنِ مرزِ تاریخ")
            return await msg.edit(f"❌ خطا در پیدا کردنِ پیام‌هایِ این تاریخ: {e}")
        if not start_id:
            return await msg.edit(
                "⚠️ از تاریخِ خواسته‌شده هیچ پیامی توی کانالِ مبدأ پیدا نشد "
                "(تاریخ از آخرین پیام جدیدتره یا کانال خالیه)."
            )
        from_id = max(int(start_id) - 1, 0)
        start_note = f"• شروع از تاریخ: {format_from_date(from_date)} (از پیامِ #{start_id})\n"
        # درصدِ پیشرفت: پیام‌هایِ قبلِ این تاریخ رو از کلِ کانال کم می‌کنیم
        if total > 0:
            try:
                before = int(
                    getattr(await client.get_messages(src, max_id=start_id, limit=0), "total", 0) or 0
                )
                if 0 <= before < total:
                    total -= before
            except Exception:
                logger.debug("شمارشِ پیام‌هایِ قبل از تاریخ نشد", exc_info=True)

    job = await repo.create_job(
        source_id=tl_utils.get_peer_id(src), source_title=_title(src), source_ref=src_raw,
        dest_id=tl_utils.get_peer_id(dst), dest_title=_title(dst), dest_ref=dst_raw,
        last_id=from_id, total_hint=total, drop_author=drop_author, from_date=from_date,
    )
    _spawn(job["id"])

    per_hour = int(config.CHANNEL_COPY_BATCH_SIZE * 3600 / (config.CHANNEL_COPY_DELAY_SECONDS + 1))
    limit = config.CHANNEL_COPY_DAILY_LIMIT
    cap = f"سقفِ روزانه {limit} پیام" if limit else "بدونِ سقفِ روزانه"
    await event.edit(
        f"▶️ کپی کانال #{job['id']} شروع شد\n"
        + start_note +
        f"• {_title(src)} → {_title(dst)}\n"
        f"• دسته‌های {config.CHANNEL_COPY_BATCH_SIZE}تایی، مکثِ {int(config.CHANNEL_COPY_DELAY_SECONDS)} ثانیه "
        f"(حداکثر ~{per_hour} پیام در ساعت؛ {cap})\n"
        f"• پیشرفت: `{config.PREFIX}کپی‌کانال وضعیت` | توقف: `{config.PREFIX}کپی‌کانال توقف`"
    )
