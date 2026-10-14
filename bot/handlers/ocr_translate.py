"""
دستورات استخراج متن از تصویر (OCR) + ترجمه هوشمند.
"""

import io
import base64
from telethon import events

from ..config import PREFIX, AI_API_KEY
from ..runtime import client
from .. import ai
from ..utils import pat
from ..storage.stats_store import record_error as _record_error


async def _extract_text_from_image(image_bytes: bytes) -> str:
    """استخراج متن از تصویر با استفاده از Tesseract (محلی) یا AI."""
    local_error = None
    try:
        import pytesseract
        from PIL import Image
        import tempfile
        import os
        
        # ذخیره موقت
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(image_bytes)
            temp_path = f.name
        
        try:
            # اجرای Tesseract با پشتیبانی از فارسی و انگلیسی
            img = Image.open(temp_path)
            text = pytesseract.image_to_string(img, lang='fas+eng')
            return text.strip()
        finally:
            os.unlink(temp_path)
    except Exception as e:
        # هم نصب‌نبودنِ پکیجِ pytesseract (ImportError) و هم نصب‌نبودنِ خودِ
        # باینریِ tesseract-ocr روی سیستم (TesseractNotFoundError - که
        # ImportError نیست و قبلاً این fallback رو دور می‌زد) و هر خطای
        # دیگه‌ای توی موتورِ محلی، باید بره سراغِ AI - نه اینکه کاربر یه
        # Exceptionِ خام ببینه.
        local_error = e

    # موتورِ محلی جواب نداد؛ اگه AI تنظیم شده، از اون استفاده کن
    if AI_API_KEY:
        try:
            # تبدیل به base64
            b64 = base64.b64encode(image_bytes).decode('ascii')
            messages = [
                {"role": "system", "content": "متن موجود در تصویر را استخراج کن. فقط متن را برگردان."},
                {"role": "user", "content": [
                    {"type": "text", "text": "متن این تصویر را استخراج کن."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ]}
            ]
            response = await ai.ask_ai(messages, max_tokens=500)
            return response.strip()
        except Exception as e:
            raise Exception(f"خطا در استخراج با AI: {e}")
    else:
        raise Exception(f"استخراجِ محلی ناموفق بود ({local_error}) و AI_API_KEY هم تنظیم نشده است.")


@client.on(events.NewMessage(outgoing=True, pattern=pat(["عکس‌ترجمه", "imgtranslate"])))
async def ocr_translate_handler(event):
    """استخراج متن از تصویر و ترجمه به فارسی."""
    if not event.is_reply:
        return await event.edit(
            f"روی یک عکس ریپلای کن و دستور `{PREFIX}عکس‌ترجمه` را بفرست.\n"
            f"متن استخراج‌شده از عکس به فارسی ترجمه می‌شود."
        )
    
    reply = await event.get_reply_message()
    if not reply or not (reply.photo or reply.document):
        return await event.edit("❌ لطفاً روی یک عکس یا فایل تصویری ریپلای کن.")
    
    await event.edit("⏳ در حال دانلود و تحلیل تصویر...")
    
    try:
        # دانلود تصویر
        image_bytes = await client.download_media(reply, bytes)
        if not image_bytes:
            return await event.edit("❌ دانلود تصویر ناموفق بود.")
        
        # استخراج متن
        text = await _extract_text_from_image(image_bytes)
        if not text.strip():
            return await event.edit("⚠️ متنی در تصویر پیدا نشد.")
        
        # ترجمه به فارسی
        if AI_API_KEY:
            try:
                messages = [
                    {"role": "system", "content": "متن داده شده را به فارسی روان ترجمه کن. فقط ترجمه را برگردان."},
                    {"role": "user", "content": text}
                ]
                translated = await ai.ask_ai(messages, max_tokens=500)
            except Exception as e:
                translated = f"[خطا در ترجمه: {e}]"
        else:
            translated = "[AI_API_KEY تنظیم نشده. ترجمه انجام نشد.]"
        
        # نتیجه
        result = f"📝 **متن استخراج‌شده:**\n{text}\n\n🌐 **ترجمه به فارسی:**\n{translated}"
        await event.edit(result)
        
    except Exception as e:
        _record_error()
        await event.edit(f"❌ خطا: {e}")