"""
دستورات مبدل واحد.
"""

import re
from telethon import events

from ..config import PREFIX
from ..runtime import client
from ..utils import pat


# تعریف تبدیل‌ها
CONVERTERS = {
    # طول
    "km": {"to_m": lambda x: x * 1000, "from_m": lambda x: x / 1000},
    "m": {"to_m": lambda x: x, "from_m": lambda x: x},
    "cm": {"to_m": lambda x: x / 100, "from_m": lambda x: x * 100},
    "mm": {"to_m": lambda x: x / 1000, "from_m": lambda x: x * 1000},
    "mile": {"to_m": lambda x: x * 1609.34, "from_m": lambda x: x / 1609.34},
    "yard": {"to_m": lambda x: x * 0.9144, "from_m": lambda x: x / 0.9144},
    "foot": {"to_m": lambda x: x * 0.3048, "from_m": lambda x: x / 0.3048},
    "inch": {"to_m": lambda x: x * 0.0254, "from_m": lambda x: x / 0.0254},
    
    # وزن
    "kg": {"to_g": lambda x: x * 1000, "from_g": lambda x: x / 1000},
    "g": {"to_g": lambda x: x, "from_g": lambda x: x},
    "lb": {"to_g": lambda x: x * 453.592, "from_g": lambda x: x / 453.592},
    "oz": {"to_g": lambda x: x * 28.3495, "from_g": lambda x: x / 28.3495},
    
    # دما
    "c": {"to_c": lambda x: x, "from_c": lambda x: x},
    "f": {"to_c": lambda x: (x - 32) * 5/9, "from_c": lambda x: x * 9/5 + 32},
    "k": {"to_c": lambda x: x - 273.15, "from_c": lambda x: x + 273.15},
    
    # حجم
    "l": {"to_l": lambda x: x, "from_l": lambda x: x},
    "ml": {"to_l": lambda x: x / 1000, "from_l": lambda x: x * 1000},
    "gal": {"to_l": lambda x: x * 3.78541, "from_l": lambda x: x / 3.78541},
    
    # سرعت
    "kmh": {"to_ms": lambda x: x / 3.6, "from_ms": lambda x: x * 3.6},
    "ms": {"to_ms": lambda x: x, "from_ms": lambda x: x},
    "mph": {"to_ms": lambda x: x * 0.44704, "from_ms": lambda x: x / 0.44704},
}


def _parse_value(val_str):
    """پارس عدد با پشتیبانی از ممیز."""
    try:
        return float(val_str)
    except ValueError:
        return None


@client.on(events.NewMessage(outgoing=True, pattern=pat(["مبدل", "convert"])))
async def convert_cmd_handler(event):
    """تبدیل واحدها."""
    raw = (event.pattern_match.group(1) or "").strip()
    if not raw:
        return await event.edit(
            f"📐 **مبدل واحد**\n\n"
            f"استفاده:\n"
            f"`{PREFIX}مبدل <عدد> <واحد مبدا> <واحد مقصد>`\n\n"
            f"مثال:\n"
            f"`{PREFIX}مبدل 10 km mile`\n"
            f"`{PREFIX}مبدل 25 c f` (دما)\n"
            f"`{PREFIX}مبدل 5 kg lb`\n\n"
            f"واحدهای پشتیبانی‌شده:\n"
            f"طول: km, m, cm, mm, mile, yard, foot, inch\n"
            f"وزن: kg, g, lb, oz\n"
            f"دما: c, f, k\n"
            f"حجم: l, ml, gal\n"
            f"سرعت: kmh, ms, mph"
        )
    
    parts = raw.split()
    if len(parts) < 3:
        return await event.edit("❌ فرمت: `<عدد> <واحد مبدا> <واحد مقصد>`")
    
    val_str = parts[0]
    from_unit = parts[1].lower()
    to_unit = parts[2].lower()
    
    val = _parse_value(val_str)
    if val is None:
        return await event.edit("❌ عدد نامعتبر است.")
    
    # تشخیص دسته واحدها
    categories = {
        "length": ["km", "m", "cm", "mm", "mile", "yard", "foot", "inch"],
        "weight": ["kg", "g", "lb", "oz"],
        "temperature": ["c", "f", "k"],
        "volume": ["l", "ml", "gal"],
        "speed": ["kmh", "ms", "mph"],
    }
    
    from_cat = None
    to_cat = None
    for cat, units in categories.items():
        if from_unit in units:
            from_cat = cat
        if to_unit in units:
            to_cat = cat
    
    if from_cat is None:
        return await event.edit(f"❌ واحد '{from_unit}' پشتیبانی نمی‌شود.")
    if to_cat is None:
        return await event.edit(f"❌ واحد '{to_unit}' پشتیبانی نمی‌شود.")
    if from_cat != to_cat:
        return await event.edit(f"❌ واحدها از دسته‌های مختلف هستند. نمی‌توان {from_unit} را به {to_unit} تبدیل کرد.")
    
    # تبدیل
    try:
        if from_cat == "length":
            # تبدیل به متر
            if from_unit == "km":
                base = val * 1000
            elif from_unit == "cm":
                base = val / 100
            elif from_unit == "mm":
                base = val / 1000
            elif from_unit == "mile":
                base = val * 1609.34
            elif from_unit == "yard":
                base = val * 0.9144
            elif from_unit == "foot":
                base = val * 0.3048
            elif from_unit == "inch":
                base = val * 0.0254
            else:  # m
                base = val
            
            # تبدیل از متر
            if to_unit == "km":
                result = base / 1000
            elif to_unit == "cm":
                result = base * 100
            elif to_unit == "mm":
                result = base * 1000
            elif to_unit == "mile":
                result = base / 1609.34
            elif to_unit == "yard":
                result = base / 0.9144
            elif to_unit == "foot":
                result = base / 0.3048
            elif to_unit == "inch":
                result = base / 0.0254
            else:  # m
                result = base
        
        elif from_cat == "weight":
            # تبدیل به گرم
            if from_unit == "kg":
                base = val * 1000
            elif from_unit == "lb":
                base = val * 453.592
            elif from_unit == "oz":
                base = val * 28.3495
            else:  # g
                base = val
            
            # تبدیل از گرم
            if to_unit == "kg":
                result = base / 1000
            elif to_unit == "lb":
                result = base / 453.592
            elif to_unit == "oz":
                result = base / 28.3495
            else:  # g
                result = base
        
        elif from_cat == "temperature":
            # تبدیل به سلسیوس
            if from_unit == "f":
                base = (val - 32) * 5/9
            elif from_unit == "k":
                base = val - 273.15
            else:  # c
                base = val
            
            # تبدیل از سلسیوس
            if to_unit == "f":
                result = base * 9/5 + 32
            elif to_unit == "k":
                result = base + 273.15
            else:  # c
                result = base
        
        elif from_cat == "volume":
            # تبدیل به لیتر
            if from_unit == "ml":
                base = val / 1000
            elif from_unit == "gal":
                base = val * 3.78541
            else:  # l
                base = val
            
            # تبدیل از لیتر
            if to_unit == "ml":
                result = base * 1000
            elif to_unit == "gal":
                result = base / 3.78541
            else:  # l
                result = base
        
        elif from_cat == "speed":
            # تبدیل به متر بر ثانیه
            if from_unit == "kmh":
                base = val / 3.6
            elif from_unit == "mph":
                base = val * 0.44704
            else:  # ms
                base = val
            
            # تبدیل از متر بر ثانیه
            if to_unit == "kmh":
                result = base * 3.6
            elif to_unit == "mph":
                result = base / 0.44704
            else:  # ms
                result = base
        
        else:
            return await event.edit("❌ خطای داخلی.")
        
        # نمایش نتیجه
        # فرمت‌بندی عدد
        if abs(result) >= 1e6:
            result_str = f"{result:.2e}"
        elif abs(result) < 0.001:
            result_str = f"{result:.6f}"
        elif abs(result) < 1:
            result_str = f"{result:.4f}"
        else:
            result_str = f"{result:.4f}".rstrip('0').rstrip('.')
            if not result_str:
                result_str = "0"
        
        await event.edit(f"✅ {val} {from_unit} = **{result_str} {to_unit}**")
        
    except Exception as e:
        await event.edit(f"❌ خطا در تبدیل: {e}")