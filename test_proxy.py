import sys
from parser.http.client import AvitoHttpClient
from parser.cookies.manager import CookiesManager

proxy_url = "http://xHmHPcS8oz:kU4qO4Rsu3@193.168.224.119:39598"

client = AvitoHttpClient(use_random_impersonate=True)

print("1. Тест прокси на ipinfo.io...")
try:
    ip_info = client.get("https://ipinfo.io/json", proxy=proxy_url, retries=1)
    print("Успех! Ответ:")
    print(ip_info)
except Exception as e:
    print(f"Ошибка прокси: {e}")
    sys.exit(1)

print("\n2. Тест прокси на avito.ru (без кук)...")
try:
    # Без кук Авито скорее всего отдаст 403 или заставит решать капчу
    html = client.get("https://www.avito.ru", proxy=proxy_url, retries=1)
    print(f"Успех! Получено {len(html)} символов.")
except Exception as e:
    print(f"Ожидаемый ответ или блок: {e}")

print("\n3. Тест прокси на avito.ru (с локальными куками)...")
cm = CookiesManager()
cookies = cm.get_cookies()
if cookies:
    try:
        html = client.get("https://www.avito.ru", proxy=proxy_url, cookies=cookies, retries=1)
        print(f"Успех с куками! Получено {len(html)} символов.")
    except Exception as e:
        print(f"Блок с куками: {e}")
else:
    print("Локальные куки не найдены, пропускаем.")
