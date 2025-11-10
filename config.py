import os

# Читаем .env файл напрямую
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')

print(f"Читаем .env из: {env_path}")

# Проверяем существование файла
if not os.path.exists(env_path):
    raise FileNotFoundError(f"Файл .env не найден по пути: {env_path}")

# Читаем файл
with open(env_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Парсим переменные
env_vars = {}
for line in lines:
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        env_vars[key.strip()] = value.strip()

# Получаем переменные
BOT_TOKEN = env_vars.get("BOT_TOKEN")
ADMIN_IDS = env_vars.get("ADMIN_IDS", "1993831036")
YOOKASSA_SHOP_ID = env_vars.get("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = env_vars.get("YOOKASSA_SECRET_KEY", "")

# Отладочная информация
print(f"BOT_TOKEN: {BOT_TOKEN}")
print(f"ADMIN_IDS: {ADMIN_IDS}")

# Проверка токена
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле")
if ":" not in BOT_TOKEN:
    raise ValueError(f"Неверный формат токена: {BOT_TOKEN}")

# Преобразуем ADMIN_IDS в список чисел
ADMIN_IDS = list(map(int, ADMIN_IDS.split(',')))
