import random
import re
import time
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from curl_cffi import requests
from curl_cffi.requests.errors import RequestsError

from .exceptions import BlockError, ProxyError, FetchError

logger = logging.getLogger(__name__)

# Современные профили curl_cffi. Старые Chrome 110/116 часто выглядят подозрительно.
IMPERSONATE_LIST = [
    "chrome136",
    "chrome131",
    "chrome124",
    "chrome120",
    "edge",
]

DEFAULT_USER_AGENTS = {
    "chrome136": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "chrome131": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "chrome124": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "chrome120": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "edge": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0",
}


@dataclass
class FetchResult:
    text: str
    status_code: int
    cookies: dict
    impersonate: str

class AvitoHttpClient:
    def __init__(self, use_random_impersonate: bool = True):
        self.use_random_impersonate = use_random_impersonate

    def get(
        self,
        url: str,
        proxy: str = None,
        cookies: dict = None,
        user_agent: str = None,
        retries: int = 3,
        timeout: int = 15,
    ) -> str:
        return self.get_response(
            url=url,
            proxy=proxy,
            cookies=cookies,
            user_agent=user_agent,
            retries=retries,
            timeout=timeout,
        ).text

    def get_response(
        self,
        url: str,
        proxy: str = None,
        cookies: dict = None,
        user_agent: str = None,
        impersonate: str = None,
        referer: str = None,
        retries: int = 3,
        timeout: int = 15,
    ) -> FetchResult:
        """
        Выполняет GET запрос к Avito.
        Возвращает HTML текст страницы.
        Вызывает исключения (BlockError, ProxyError, FetchError) при проблемах.
        """
        attempt = 0
        while attempt < retries:
            attempt += 1
            
            # Рандомизация отпечатка для каждого запроса (или сессии)
            current_impersonate = impersonate or (random.choice(IMPERSONATE_LIST) if self.use_random_impersonate else "chrome136")
            
            proxies = {"http": proxy, "https": proxy} if proxy else None
            headers = self._build_headers(
                url=url,
                user_agent=user_agent,
                impersonate=current_impersonate,
                referer=referer,
            )

            try:
                logger.debug(f"Запрос {url} (Попытка {attempt}/{retries}) | Impersonate: {current_impersonate} | Proxy: {proxy}")
                with requests.Session() as session:
                    response = session.get(
                        url,
                        impersonate=current_impersonate,
                        proxies=proxies,
                        cookies=cookies,
                        headers=headers,
                        timeout=timeout
                    )

                self._check_for_blocks(response)
                
                return FetchResult(
                    text=response.text,
                    status_code=response.status_code,
                    cookies=self._extract_cookies(response),
                    impersonate=current_impersonate,
                )

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
            raise BlockError(
                "HTTP 429: Too Many Requests (Бан IP или нужна капча)",
                status_code=response.status_code,
                response_cookies=self._extract_cookies(response),
            )
        if response.status_code == 403:
            raise BlockError(
                "HTTP 403: Forbidden (Доступ запрещен, блок IP/Куки)",
                status_code=response.status_code,
                response_cookies=self._extract_cookies(response),
            )
        
        # Проверка по содержимому (Firewall, Captcha)
        html = response.text or ""
        text = html.lower()
        if (
            "доступ ограничен" in text
            or "проблема с ip" in text
            or "доступ с вашего ip" in text
            or "ваш ip" in text and "огранич" in text
            or "too many requests" in text
        ):
            raise BlockError(
                "Cloudflare / Avito Firewall: проблема с IP",
                status_code=response.status_code,
                response_cookies=self._extract_cookies(response),
            )
        if (
            "ой! мы заметили подозрительную активность" in text
            or "подтвердите, что вы не робот" in text
            or "captcha" in text
            or "капч" in text
        ):
            raise BlockError(
                "Avito Captcha: Требуется разгадать капчу",
                status_code=response.status_code,
                response_cookies=self._extract_cookies(response),
            )

    @staticmethod
    def _extract_cookies(response) -> dict:
        try:
            if hasattr(response.cookies, "get_dict"):
                return response.cookies.get_dict()
            return dict(response.cookies)
        except Exception:
            return {}

    def _build_headers(self, url: str, user_agent: str | None, impersonate: str, referer: str | None) -> dict:
        chrome_major = self._profile_major(impersonate)
        effective_user_agent = self._normalize_user_agent(user_agent, impersonate, chrome_major)
        platform = "Windows"
        sec_ch_ua = self._sec_ch_ua(effective_user_agent, chrome_major)

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Priority": "u=0, i",
            "Sec-CH-UA": sec_ch_ua,
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": f'"{platform}"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": self._sec_fetch_site(url, referer),
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": effective_user_agent,
        }
        if referer:
            headers["Referer"] = referer
        return headers

    @staticmethod
    def _chrome_major(user_agent: str) -> str | None:
        match = re.search(r"(?:Chrome|Edg)/(\d+)", user_agent or "")
        return match.group(1) if match else None

    @staticmethod
    def _profile_major(impersonate: str) -> str:
        match = re.search(r"(\d+)", impersonate or "")
        return match.group(1) if match else "136"

    def _normalize_user_agent(self, user_agent: str | None, impersonate: str, chrome_major: str) -> str:
        if not user_agent:
            return DEFAULT_USER_AGENTS.get(impersonate) or DEFAULT_USER_AGENTS["chrome136"]

        if impersonate == "edge":
            if "Edg/" not in user_agent and "Edge/" not in user_agent:
                return DEFAULT_USER_AGENTS["edge"]
            return re.sub(r"(Chrome|Edg)/(\d+)", rf"\g<1>/{chrome_major}", user_agent)

        if "Chrome/" not in user_agent or "Edg/" in user_agent or "Edge/" in user_agent:
            return DEFAULT_USER_AGENTS.get(impersonate) or DEFAULT_USER_AGENTS["chrome136"]
        return re.sub(r"Chrome/(\d+)", f"Chrome/{chrome_major}", user_agent)

    @staticmethod
    def _sec_ch_ua(user_agent: str, chrome_major: str) -> str:
        if "Edg/" in user_agent or "Edge/" in user_agent:
            return f'"Chromium";v="{chrome_major}", "Microsoft Edge";v="{chrome_major}", "Not.A/Brand";v="24"'
        return f'"Chromium";v="{chrome_major}", "Google Chrome";v="{chrome_major}", "Not.A/Brand";v="24"'

    @staticmethod
    def _sec_fetch_site(url: str, referer: str | None) -> str:
        if not referer:
            return "none"
        try:
            return "same-origin" if urlparse(url).netloc == urlparse(referer).netloc else "cross-site"
        except Exception:
            return "same-origin"
