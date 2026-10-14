"""
دستورات گراف آماری با matplotlib.
"""

import io
import datetime as dt
from telethon import events

from ..config import PREFIX
from ..runtime import client
from ..storage.activity_store import get_pending_message_count
from ..utils import pat


async def _generate_activity_graph(chat_id: int, days: int = 7):
    """تولید گراف فعالیت گروه به صورت تصویر."""
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    
    from ..repositories import activity_repo
    logs = await activity_repo.get_logs(chat_id, days)
    
    if not logs:
        return None
    
    # داده‌ها
    dates = [log.log_date for log in logs]
    messages = [log.messages_sent for log in logs]
    warnings = [log.warnings_given for log in logs]
    deleted = [log.messages_deleted for log in logs]
    joined = [log.members_joined for log in logs]
    left = [log.members_left for log in logs]

    # پیام‌هایی که هنوز flush نشدن رو به «امروز» اضافه می‌کنیم (اگه امروز جزوِ
    # بازه‌ی نمایش‌داده‌شده باشه) تا گراف تا لحظه‌ی اجرا به‌روز باشه
    today_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    if dates and dates[0] == today_str:
        messages[0] += get_pending_message_count(chat_id)
    
    # ایجاد نمودار
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_facecolor('#1e1e2e')
    fig.patch.set_facecolor('#1e1e2e')
    
    ax.plot(dates, messages, marker='o', label='پیام‌ها', color='#89b4fa', linewidth=2)
    ax.plot(dates, warnings, marker='s', label='هشدارها', color='#f9e2af', linewidth=2)
    ax.plot(dates, deleted, marker='^', label='حذف‌شده', color='#f38ba8', linewidth=2)
    ax.plot(dates, joined, marker='v', label='ورود', color='#a6e3a1', linewidth=2)
    ax.plot(dates, left, marker='x', label='خروج', color='#cba6f7', linewidth=2)
    
    ax.set_xlabel('تاریخ', color='#cdd6f4', fontsize=12)
    ax.set_ylabel('تعداد', color='#cdd6f4', fontsize=12)
    ax.set_title(f'فعالیت گروه در {days} روز اخیر', color='#cdd6f4', fontsize=14)
    ax.legend(loc='upper left', facecolor='#1e1e2e', edgecolor='#313244', labelcolor='#cdd6f4')
    ax.tick_params(colors='#cdd6f4')
    ax.grid(True, color='#313244', linestyle='--', alpha=0.5)
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # ذخیره در حافظه
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    return buf


@client.on(events.NewMessage(outgoing=True, pattern=pat(["آمارگراف", "statgraph"])))
async def stats_graph_cmd(event):
    """نمایش گراف آماری گروه."""
    if not event.is_group:
        return await event.edit("این دستور فقط توی گروه‌ها کار می‌کنه")
    
    raw = (event.pattern_match.group(1) or "").strip()
    days = 7
    if raw.isdigit():
        days = int(raw)
        if days < 1 or days > 30:
            return await event.edit("تعداد روز باید بین ۱ تا ۳۰ باشد.")
    
    await event.edit(f"⏳ در حال تولید گراف برای {days} روز اخیر...")
    
    try:
        import matplotlib
    except ImportError:
        return await event.edit("❌ کتابخانه matplotlib نصب نیست. لطفاً آن را نصب کنید: `pip install matplotlib`")
    
    buf = await _generate_activity_graph(event.chat_id, days)
    if buf is None:
        return await event.edit("❌ داده‌ای برای این بازه زمانی وجود ندارد.")
    
    # ارسال تصویر
    await client.send_file(event.chat_id, buf, caption=f"📊 گراف فعالیت گروه ({days} روز اخیر)", reply_to=event.id)
    await event.delete()