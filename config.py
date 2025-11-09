import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1993831036").split(',')))

# Проверка токена
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")
if ":" not in BOT_TOKEN:
    raise ValueError(f"Неверный формат токена: {BOT_TOKEN}")
