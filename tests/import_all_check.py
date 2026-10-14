"""import تمیزِ همه‌ی ماژول‌ها (با env placeholder) — timeout 120s."""
import os
import sys
import importlib
import logging

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "x")
os.environ.setdefault("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("BOT_TOKEN", "1:fake")
os.environ["HERMES_IMPORT_CHECK"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.disable(logging.CRITICAL)

fails, mods = [], []
for root, dirs, files in os.walk("bot"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if f.endswith(".py"):
            mods.append(os.path.relpath(os.path.join(root, f), ".")[:-3].replace("/", "."))
for mod in sorted(mods):
    try:
        importlib.import_module(mod)
    except Exception as e:
        fails.append((mod, f"{type(e).__name__}: {e}"))
for m, e in fails:
    print("FAIL", m, e)
print(f"{len(mods) - len(fails)}/{len(mods)} clean")
sys.exit(1 if fails else 0)
