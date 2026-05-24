import random
import time
import logging
from curl_cffi import requests
from curl_cffi.requests.errors import RequestsError

from .exceptions import BlockError, ProxyError, FetchError

logger = logging.getLogger(__name__)

# Популярные браузеры для curl_cffi
IMPERSONATE_LIST = [
    "chrome110", "chrome116", "chrome120", 
    "safari15_3"
]

class AvitoHttpClient:
    def __init__(self, use_random_impersonate: bool = True):
        self.use_random_impersonate = use_random_impersonate
        self.session = requests.Session()
        # Базовые заголовки, чтобы быть похожими на реальный браузер (будут дополняться curl_cffi)
        self.session.headers.update({
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        })

    def get(
        self,
        url: str,
        proxy: str = None,
        cookies: dict = None,
        user_agent: str = None,
        retries: int = 3,
        timeout: int = 15,
    ) -> str:
        """
        Выполняет GET запрос к Avito.
        Возвращает HTML текст страницы.
        Вызывает исключения (BlockError, ProxyError, FetchError) при проблемах.
        """
        attempt = 0
        while attempt < retries:
            attempt += 1
            
            # Рандомизация отпечатка для каждого запроса (или сессии)
            impersonate = random.choice(IMPERSONATE_LIST) if self.use_random_impersonate else "chrome120"
            
            proxies = {"http": proxy, "https": proxy} if proxy else None
            headers = {"User-Agent": user_agent} if user_agent else None

            try:
                logger.debug(f"Запрос {url} (Попытка {attempt}/{retries}) | Impersonate: {impersonate} | Proxy: {proxy}")
                response = self.session.get(
                    url,
                    impersonate=impersonate,
                    proxies=proxies,
                    cookies=cookies,
                    headers=headers,
                    timeout=timeout
                )

                self._check_for_blocks(response)
                
                return response.text

            except RequestsError as e:
                logger.warning(f"Ошибка сети (попытка {attempt}): {e}")
                if attempt == retries:
                    raise ProxyError(f"Ошибка прокси/сети после {retries} попыток: {e}")
                time.sleep(2)
            except BlockError as e:
                # Если 429 - мы можем подождать 1-2 секунды и попробовать снова с теми же куками
                if "429" in str(e) and attempt < retries:
                    logger.warning(f"Получен 429. Ждем 2 сек перед повтором (Попытка {attempt}/{retries})...")
                    time.sleep(2)
                    continue
                    
                logger.warning(f"Обнаружена блокировка: {e}")
                # При 403 или повторяющемся 429 пробрасываем выше для смены IP/разблокировки
                raise
            except Exception as e:
                logger.error(f"Неизвестная ошибка: {e}")
                if attempt == retries:
                    raise FetchError(f"Не удалось загрузить страницу: {e}")
                time.sleep(2)

    def _check_for_blocks(self, response):
        """Анализирует ответ на предмет блокировок от Avito."""
        if response.status_code == 429:
            raise BlockError("HTTP 429: Too Many Requests (Бан IP или нужна капча)")
        if response.status_code == 403:
            raise BlockError("HTTP 403: Forbidden (Доступ запрещен, блок IP/Куки)")
        
        # Проверка по содержимому (Firewall, Captcha)
        html = response.text
        if "Доступ ограничен" in html or "проблема с IP" in html:
            raise BlockError("Cloudflare / Avito Firewall: проблема с IP")
        if "Ой! Мы заметили подозрительную активность" in html or "Подтвердите, что вы не робот" in html:
            raise BlockError("Avito Captcha: Требуется разгадать капчу")
