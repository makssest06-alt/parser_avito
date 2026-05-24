import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "").strip()
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
DEFAULT_MOBILE_PROXY = os.getenv("DEFAULT_MOBILE_PROXY", "").strip()
PAYMENT_TEST_MODE = os.getenv("PAYMENT_TEST_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")
if ":" not in BOT_TOKEN:
    raise ValueError("Неверный формат BOT_TOKEN")

try:
    ADMIN_IDS = [int(value.strip()) for value in ADMIN_IDS_RAW.split(",") if value.strip()]
except ValueError as exc:
    raise ValueError("ADMIN_IDS должен быть списком чисел через запятую") from exc
