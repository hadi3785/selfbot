"""۷) پروفایل: setbio / setname / setpic / clock / clockstyle"""
from datetime import datetime, timedelta

from telethon import events, functions

from .. import config
from ..config import PREFIX
from ..runtime import client
from ..clock import (
    clock_state,
    CLOCK_STYLES,
    CLOCK_STYLE_ORDER,
    apply_clock_now as _apply_clock_now,
    persist_clock_state,
)
from ..utils import pat

@client.on(events.NewMessage(outgoing=True, pattern=pat(["بیو", "setbio"])))
async def setbio_handler(event):
    bio = event.pattern_match.group(1)
    if not bio:
        return await event.edit(f"مثال: `{PREFIX}بیو بیو جدید`")
    await client(functions.account.UpdateProfileRequest(about=bio))
    await event.edit("✅ بیو بروزرسانی شد")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["نام", "setname"])))
async def setname_handler(event):
    name = event.pattern_match.group(1)
    if not name:
        return await event.edit(f"مثال: `{PREFIX}نام نام جدید`")
    clock_state["base_name"] = name
    if clock_state["enabled"]:
        await _apply_clock_now()
    else:
        await client(functions.account.UpdateProfileRequest(first_name=name))
    await persist_clock_state()
    await event.edit("✅ نام پایه بروزرسانی شد")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["عکس", "setpic"], arg=False)))
async def setpic_handler(event):
    if not event.is_reply:
        return await event.edit("روی یک عکس ریپلای کن")
    reply = await event.get_reply_message()
    if not reply.photo:
        return await event.edit("پیام ریپلای‌شده عکس نیست")
    file_bytes = await client.download_media(reply, file=bytes)
    uploaded = await client.upload_file(file_bytes, file_name="pic.jpg")
    await client(functions.photos.UploadProfilePhotoRequest(file=uploaded))
    await event.edit("✅ عکس پروفایل تغییر کرد")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["ساعت", "clock"])))
async def clock_toggle_handler(event):
    arg = (event.pattern_match.group(1) or "").strip().lower()
    if arg in ("خاموش", "off"):
        clock_state["enabled"] = False
        await persist_clock_state()
        await event.edit("🕐 ساعت زنده خاموش شد")
    elif arg in ("روشن", "on"):
        clock_state["enabled"] = True
        await persist_clock_state()
        await event.edit("🕐 ساعت زنده روشن شد (طی چند ثانیه اعمال می‌شه)")
    else:
        await event.edit(f"استفاده: `{PREFIX}ساعت روشن` یا `{PREFIX}ساعت خاموش`")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["مدل‌ساعت", "شکل‌ساعت", "clockstyle"])))
async def clockstyle_handler(event):
    arg = (event.pattern_match.group(1) or "").strip().lower()
    if not arg or arg in ("فهرست", "list"):
        now = datetime.utcnow() + timedelta(hours=config.TIMEZONE_OFFSET)
        lines = ["🎨 **مدل‌های ساعت زنده:**\n"]
        for name in CLOCK_STYLE_ORDER:
            preview = CLOCK_STYLES[name](now.hour, now.minute)
            marker = "✅" if name == clock_state["style"] else "▫️"
            lines.append(f"{marker} `{name}` → {preview}")
        lines.append(f"\nبرای تغییر: `{PREFIX}مدل‌ساعت <نام>` یا `{PREFIX}مدل‌ساعت بعدی`")
        return await event.edit("\n".join(lines))

    if arg in ("بعدی", "next"):
        idx = CLOCK_STYLE_ORDER.index(clock_state["style"])
        new_style = CLOCK_STYLE_ORDER[(idx + 1) % len(CLOCK_STYLE_ORDER)]
    elif arg in CLOCK_STYLES:
        new_style = arg
    else:
        return await event.edit(f"استایل نامعتبره. برای دیدن فهرست: `{PREFIX}مدل‌ساعت فهرست`")

    clock_state["style"] = new_style
    preview = CLOCK_STYLES[new_style](*(datetime.utcnow() + timedelta(hours=config.TIMEZONE_OFFSET)).timetuple()[3:5])
    await persist_clock_state()
    await event.edit(f"✅ استایل ساعت روی `{new_style}` تنظیم شد\nنمونه: {preview}")
    await _apply_clock_now()

# ---------------------------------------------------------------- کاربر --
# بخشِ «پروفایلِ کاربر» (قبلاً فایلِ جدا user_profile.py بود؛ حالا در همین
# بخشِ پروفایل ادغام شده): پروفایلِ داخلیِ کاربران، برچسب و یادداشتِ خصوصی.
import logging  # noqa: E402

from ..repositories import user_profile_repo  # noqa: E402

logger = logging.getLogger("selfbot.handlers.profile")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["کاربر", "profile"])))
async def user_profile_handler(event):
    """نمایش اطلاعات کاربر."""
    args = (event.pattern_match.group(1) or "").strip().split()

    # اگر ریپلای شده، کاربر ریپلای را بگیر
    user_id = None
    if event.is_reply:
        reply = await event.get_reply_message()
        if reply and reply.sender_id:
            user_id = reply.sender_id

    # یا از آرگومان
    if not user_id and args and args[0].lstrip("-").isdigit():
        user_id = int(args[0])

    if not user_id and args:
        # آرگومان داده شده ولی شناسه‌ی عددی نیست — ساکتِ «پروفایلِ خودت» نکن
        return await event.edit(
            "❌ شناسه‌ی عددی بده یا روی پیامِ طرف ریپلای کن.\n"
            f"مثال: `{PREFIX}کاربر 123456789`"
        )

    if not user_id:
        # کاربر خودش
        me = await event.client.get_me()
        user_id = me.id

    try:
        user = await event.client.get_entity(user_id)
        profile = await user_profile_repo.get_or_create(user_id)

        lines = [
            "👤 **پروفایل کاربر**",
            "",
            f"🆔 ID: `{user_id}`",
            f"👤 نام: {user.first_name or 'نامشخص'}",
            f"🔹 نام‌کاربری: @{user.username}" if user.username else "",
            f"📱 شماره: {user.phone}" if hasattr(user, "phone") and user.phone else "",
            "",
            "🏷 **برچسب‌ها:**",
        ]

        if profile.tags:
            tags = [f"#{t.strip()}" for t in profile.tags.split(",") if t.strip()]
            lines.append("  " + " ".join(tags))
        else:
            lines.append("  (هیچ برچسبی)")

        if profile.is_vip:
            lines.append("⭐ **VIP**")

        if profile.notes:
            lines.append("")
            lines.append("📝 **یادداشت:**")
            lines.append(f"  {profile.notes}")

        lines.append("")
        lines.append(f"• افزودن برچسب: `{PREFIX}برچسب <کاربر> <برچسب>`")
        lines.append(f"• حذف برچسب: `{PREFIX}برچسب حذف <کاربر> <برچسب>`")
        lines.append(f"• یادداشت: `{PREFIX}یادداشت‌کاربر <کاربر> <متن>`")

        await event.edit("\n".join(lines))

    except Exception as e:
        await event.edit(f"❌ خطا: {e}")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["برچسب", "tag"])))
async def tag_handler(event):
    """مدیریت برچسب‌های کاربر."""
    args = (event.pattern_match.group(1) or "").strip().split()
    if not args:
        return await event.edit(
            f"❌ استفاده: `{PREFIX}برچسب <کاربر> <برچسب>` یا `{PREFIX}برچسب حذف <کاربر> <برچسب>`"
        )

    # تشخیص کاربر
    user_id = None
    if event.is_reply:
        reply = await event.get_reply_message()
        if reply and reply.sender_id:
            user_id = reply.sender_id

    if not user_id and args and (args[0].isdigit() or args[0].lstrip("-").isdigit()):
        user_id = int(args[0])
        args = args[1:]

    if not user_id:
        return await event.edit("❌ کاربر مشخص نشد. روی پیام ریپلای کنید یا ID را وارد کنید.")

    sub = args[0].lower() if args else ""
    if sub in ("حذف", "remove", "rm"):
        if len(args) < 2:
            return await event.edit(f"❌ استفاده: `{PREFIX}برچسب حذف <کاربر> <برچسب>`")
        tag = args[1]
        success = await user_profile_repo.remove_tag(user_id, tag)
        if success:
            await event.edit(f"✅ برچسب `{tag}` از کاربر {user_id} حذف شد.")
        else:
            await event.edit(f"❌ برچسب `{tag}` برای کاربر {user_id} یافت نشد.")
    else:
        tag = args[0] if args else ""
        if not tag:
            return await event.edit(f"❌ استفاده: `{PREFIX}برچسب <کاربر> <برچسب>`")
        success = await user_profile_repo.add_tag(user_id, tag)
        if success:
            await event.edit(f"✅ برچسب `{tag}` به کاربر {user_id} اضافه شد.")
        else:
            await event.edit("❌ خطا در افزودن برچسب.")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["یادداشت‌کاربر", "usernote"])))
async def user_note_handler(event):
    """افزودن یادداشت به کاربر."""
    args = (event.pattern_match.group(1) or "").strip().split()
    if not args:
        return await event.edit(f"❌ استفاده: `{PREFIX}یادداشت‌کاربر <کاربر> <متن>`")

    user_id = None
    if event.is_reply:
        reply = await event.get_reply_message()
        if reply and reply.sender_id:
            user_id = reply.sender_id

    if not user_id and args and (args[0].isdigit() or args[0].lstrip("-").isdigit()):
        user_id = int(args[0])
        args = args[1:]

    if not user_id:
        return await event.edit("❌ کاربر مشخص نشد. روی پیام ریپلای کنید یا ID را وارد کنید.")

    note = " ".join(args) if args else ""
    if not note:
        return await event.edit(f"❌ استفاده: `{PREFIX}یادداشت‌کاربر <کاربر> <متن>`")

    profile = await user_profile_repo.update_profile(user_id, notes=note)
    if profile:
        await event.edit(f"✅ یادداشت برای کاربر {user_id} ذخیره شد:\n{note}")
    else:
        await event.edit("❌ خطا در ذخیره یادداشت.")
