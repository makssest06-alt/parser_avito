import asyncio
import html
import json
import random
import re
import time
from urllib.parse import unquote, urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, timedelta

from bs4 import BeautifulSoup
from curl_cffi import requests
from loguru import logger
from pydantic import ValidationError
from typing import List

from common_data import HEADERS
from database import Database
from dto import Proxy, AvitoConfig
from tg_sender import SendAdToTg
from models import Item, ItemsResponse
from parser.http.client import AvitoHttpClient
from parser.cookies.manager import CookiesManager
from parser.channels.manager import ChannelManager, ParserChannel
from parser.http.exceptions import BlockError, ProxyError, FetchError

DEBUG_MODE = False


logger.add("logs/app.log", rotation="5 MB", retention="5 days", level="DEBUG")


class AvitoParse:
    def __init__(
            self,
            config: AvitoConfig,
            stop_event=None
    ):
        self.config = config
        self.proxy_obj = self.get_proxy_obj()
        self.db_handler = Database()
        self.tg_handler = self.get_tg_handler()
        self.xlsx_handler = None
        self.stop_event = stop_event
        
        self.http_client = AvitoHttpClient(use_random_impersonate=True)
        self.cookies_manager = CookiesManager()
        self.channel_manager = ChannelManager()
        self.current_channel: ParserChannel | None = None
        self.last_failure_reason: str | None = None
        
        self.good_request_count = 0
        self.bad_request_count = 0

        # log_config(config=self.config) # Temporarily removed or you can re-import it


    def get_tg_handler(self) -> SendAdToTg | None:
        if all([self.config.tg_token, self.config.tg_chat_id]):
            return SendAdToTg(bot_token=self.config.tg_token, chat_id=self.config.tg_chat_id)
        return None

    def _send_to_tg(self, ads: list[Item]) -> None:
        for ad in ads:
            self.tg_handler.send_to_tg(ad=ad)

    def get_proxy_obj(self) -> Proxy | None:
        from mobile_proxy_manager import proxy_manager
        proxy = proxy_manager.get_random_proxy()
        if proxy:
            return proxy
        return None

    def get_formatted_proxy(self) -> str | None:
        if not self.proxy_obj:
            return None
        proxy_string = self.proxy_obj.proxy_string
        
        # Если прокси уже отформатирован с http/https
        if proxy_string.startswith(("http://", "https://", "socks4://", "socks5://", "socks5h://")):
            return proxy_string

        # Пытаемся понять формат. 
        # Если строка вида login:pass@ip:port
        if '@' in proxy_string:
            part1, part2 = proxy_string.split('@', 1)
            # part1 = login:pass, part2 = ip:port
            if ':' in part1 and not part1.replace(':', '').isdigit():
                # Это точно login:pass
                return f"http://{proxy_string}"
            else:
                # Наоборот, это ip:port@login:pass (как было в старом коде)
                return f"http://{part2}@{part1}"
        
        return f"http://{proxy_string}"

    def fetch_data(self, url: str, block_retries: int = 1) -> str | None:
        channel = self.channel_manager.acquire_channel()
        self.current_channel = channel

        if channel:
            proxy = channel.formatted_proxy
            cookies = channel.cookies
            user_agent = channel.user_agent
            impersonate = channel.impersonate
        else:
            if self.channel_manager.api_client:
                self.last_failure_reason = "NO_AVAILABLE_CHANNELS"
                logger.warning("Нет доступных parser channels. Запрос Avito пропущен до освобождения прокси.")
                return None
            proxy = self.get_formatted_proxy()
            cookies = self.cookies_manager.get_cookies()
            user_agent = self.cookies_manager.get_user_agent()
            impersonate = None

        try:
            used_cookies = bool(cookies)
            if channel and self.channel_manager.should_warmup(channel):
                logger.info(f"Канал #{channel.id}: прогрев через главную Avito перед рабочим запросом.")
                warmup_result = self.http_client.get_response(
                    url="https://www.avito.ru/",
                    proxy=proxy,
                    cookies=cookies,
                    user_agent=user_agent,
                    impersonate=impersonate,
                    retries=1,
                    timeout=20,
                )
                self.channel_manager.mark_warmup_success(channel, warmup_result.cookies)
                channel = self.channel_manager.get_channel(channel.id) or channel
                self.current_channel = channel
                cookies = channel.cookies
                user_agent = channel.user_agent
                impersonate = channel.impersonate
                used_cookies = bool(cookies)
                time.sleep(random.uniform(2.0, 5.0))

            result = self.http_client.get_response(
                url=url,
                proxy=proxy,
                cookies=cookies,
                user_agent=user_agent,
                impersonate=impersonate,
                referer="https://www.avito.ru/",
                retries=self.config.max_count_of_retry
            )
            self.good_request_count += 1
            self.last_failure_reason = None
            if channel:
                self.channel_manager.update_cookies(channel, result.cookies)
                self.channel_manager.mark_success(channel)
            elif self.proxy_obj:
                from mobile_proxy_manager import proxy_manager
                proxy_manager.mark_proxy_success(self.proxy_obj.proxy_string)
            return result.text
        except BlockError as e:
            self.bad_request_count += 1
            reason = str(e)
            self.last_failure_reason = reason
            logger.warning(f"Блокировка Avito: {reason}")

            if channel:
                if used_cookies:
                    self.channel_manager.clear_cookies(channel, reason)
                    clean_channel = self.channel_manager.get_channel(channel.id) or channel
                    if block_retries > 0:
                        no_cookie_html = self._try_fetch_without_cookies(clean_channel, url)
                        if no_cookie_html is not None:
                            logger.info("Stored cookies caused block, same channel works without cookies.")
                            self.channel_manager.mark_success(clean_channel)
                            return no_cookie_html
                    channel = clean_channel

                if block_retries > 0 and self.channel_manager.handle_block(channel, reason):
                    logger.info("Канал обработал блокировку. Повторяем запрос...")
                    return self.fetch_data(url, block_retries=block_retries - 1)

                self.channel_manager.cooldown_channel(channel, reason, minutes=5 if "429" in reason else 15)
                if block_retries > 0:
                    return self.fetch_data(url, block_retries=block_retries - 1)
                return None

            if self.proxy_obj:
                from mobile_proxy_manager import proxy_manager
                proxy_manager.mark_proxy_failed(self.proxy_obj.proxy_string, reason)
                self.proxy_obj = self.get_proxy_obj() # Сразу берем новый прокси
            
            # Пробуем получить новые куки через API spfa.ru
            if block_retries > 0 and self.cookies_manager.handle_block():
                logger.info("Сессия успешно обновлена через API. Повторяем запрос...")
                return self.fetch_data(url, block_retries=block_retries - 1)
            
            if self.cookies_manager.api_client:
                logger.warning("SPFA API настроен, ручной браузерный фолбэк пропущен.")
                return None

            # Фолбэк на ручное обновление через браузер только для локального режима без API.
            if self._refresh_manual_session(url):
                logger.info("Сессия успешно обновлена вручную. Повторяем запрос...")
                return self.fetch_data(url, block_retries=block_retries - 1)
                
            return None
        except ProxyError as e:
            self.bad_request_count += 1
            logger.warning(f"Ошибка прокси: {e}")
            self.last_failure_reason = str(e)
            if channel:
                self.channel_manager.cooldown_channel(channel, str(e), minutes=10)
            elif self.proxy_obj:
                from mobile_proxy_manager import proxy_manager
                proxy_manager.mark_proxy_failed(self.proxy_obj.proxy_string, str(e))
            return None
        except Exception as e:
            self.bad_request_count += 1
            logger.error(f"Ошибка fetch_data: {e}")
            return None

    def _try_fetch_without_cookies(self, channel: ParserChannel, url: str) -> str | None:
        try:
            result = self.http_client.get_response(
                url=url,
                proxy=channel.formatted_proxy,
                cookies=None,
                user_agent=None,
                impersonate=channel.impersonate,
                referer="https://www.avito.ru/",
                retries=1,
                timeout=20,
            )
            return result.text
        except (BlockError, ProxyError, FetchError) as err:
            logger.warning(f"No-cookie retry for channel #{channel.id} failed: {err}")
            return None

    @staticmethod
    def _is_challenge_page(html_code: str) -> bool:
        text = BeautifulSoup(html_code or "", "html.parser").get_text(" ", strip=True).lower()
        return (
            ("проблем" in text and "ip" in text)
            or "captcha" in text
            or "докажите" in text
            or "проверка" in text and "безопас" in text
        )

    def _refresh_manual_session(self, url: str) -> bool:
        try:
            from avito_session import refresh_avito_session

            html_code = refresh_avito_session(url=url, timeout_seconds=900, return_html=True)
            if not html_code:
                return False
            self.cookies_manager.load_local_session()
            return True
        except Exception as err:
            logger.warning(f"Не удалось обновить Avito-сессию вручную: {err}")
            return False

    def _get_manual_rendered_html(self, url: str) -> str | None:
        try:
            from avito_session import refresh_avito_session

            html_code = refresh_avito_session(url=url, timeout_seconds=900, return_html=True)
            if html_code:
                self.cookies_manager.load_local_session()
            return html_code
        except Exception as err:
            logger.warning(f"Не удалось получить отрендеренную страницу Avito: {err}")
            return None

    def get_ads_from_url(self, url: str, parse_retries: int = 1) -> list[Item]:
        html_code = self.fetch_data(url=url)
        if not html_code:
            logger.warning(f"Не удалось получить HTML для {url}")
            return []

        data_from_page = self.find_json_on_page(html_code=html_code)
        catalog = data_from_page.get("catalog") or data_from_page.get("data", {}).get("catalog") or {}
        try:
            ads_models = ItemsResponse(**catalog)
            ads = self._clean_null_ads(ads=ads_models.items)
        except ValidationError as err:
            ads = self._parse_ads_from_dom(html_code=html_code)
            if not ads:
                if self.channel_manager.api_client:
                    if "catalog" in html_code:
                        logger.error(f"HTML содержит catalog, но парсер не смог извлечь объявления: {err}")
                        return []
                    if parse_retries > 0 and self.current_channel:
                        self.channel_manager.refresh_cookies(self.current_channel)
                        logger.info("Пустой ответ Avito. Cookies канала обновлены, повторяем парсинг...")
                        return self.get_ads_from_url(url, parse_retries=parse_retries - 1)
                    logger.error(f"Не удалось извлечь объявления без браузерного фолбэка: {err}")
                    return []
                rendered_html = self._get_manual_rendered_html(url)
                ads = self._parse_ads_from_dom(html_code=rendered_html or "")
                if not ads:
                    logger.error(f"При валидации объявлений произошла ошибка: {err}")
                    return []

        ads = self._add_seller_to_ads(ads=ads)
        return ads

    def parse(self):
        while not (self.stop_event and self.stop_event.is_set()):
            for url in self.config.urls:
                if self.stop_event and self.stop_event.is_set():
                    return
                    
                if DEBUG_MODE:
                    html_code = open("response.txt", "r", encoding="utf-8").read()
                else:
                    html_code = self.fetch_data(url=url)

                if not html_code:
                    logger.warning(
                        f"Не удалось получить HTML для {url}, пробую заново через {self.config.pause_between_links} сек.")
                    time.sleep(self.config.pause_between_links)
                    continue

                data_from_page = self.find_json_on_page(html_code=html_code)
                catalog = data_from_page.get("catalog") or data_from_page.get("data", {}).get("catalog") or {}
                try:
                    ads_models = ItemsResponse(**catalog)
                    ads = self._clean_null_ads(ads=ads_models.items)
                except ValidationError as err:
                    ads = self._parse_ads_from_dom(html_code=html_code)
                    if not ads:
                        rendered_html = self._get_manual_rendered_html(url)
                        ads = self._parse_ads_from_dom(html_code=rendered_html or "")
                        if not ads:
                            logger.error(f"При валидации объявлений произошла ошибка: {err}")
                            continue

                ads = self._add_seller_to_ads(ads=ads)

                if not ads:
                    logger.info("Объявления закончились, заканчиваю работу с данной ссылкой")
                    continue

                filter_ads = self.filter_ads(ads=ads)

                if self.tg_handler:
                    self._send_to_tg(ads=filter_ads)

                filter_ads = self.parse_views(ads=filter_ads)

                if filter_ads:
                    self.__save_viewed(ads=filter_ads)

                logger.info(f"Пауза {self.config.pause_between_links} сек. перед следующим обходом")
                time.sleep(self.config.pause_between_links)

            # Если one_time_start=True, выходим из цикла
            if self.config.one_time_start:
                break

        logger.info(f"Хорошие запросы: {self.good_request_count}шт, плохие: {self.bad_request_count}шт")

    @staticmethod
    def _clean_null_ads(ads: list[Item]) -> list[Item]:
        return [ad for ad in ads if ad.id]

    @staticmethod
    def find_json_on_page(html_code, data_type: str = "mime") -> dict:
        soup = BeautifulSoup(html_code, "html.parser")
        fallback = {}
        for _script in soup.select('script'):
            script_type = _script.get('type')
            script_text = _script.text or ""
            if data_type == 'mime' and script_type != 'mime/invalid' and 'catalog' not in script_text:
                continue

            try:
                script_content = html.unescape(script_text)
                parsed_data = json.loads(script_content)
            except Exception:
                continue

            if 'state' in parsed_data:
                state = parsed_data['state']
                state_data = state.get("data", {})
                if state_data.get("catalog"):
                    return state_data
                fallback = state
            elif parsed_data.get("data", {}).get("catalog"):
                return parsed_data
            elif 'data' in parsed_data:
                fallback = parsed_data
            else:
                fallback = parsed_data
        return fallback

    @staticmethod
    def _parse_ads_from_dom(html_code: str) -> list[Item]:
        soup = BeautifulSoup(html_code, "html.parser")
        cards = soup.select('[data-marker="item"], .iva-item-root')
        ads = []
        for index, card in enumerate(cards):
            title_el = card.select_one('[data-marker="item-title"], h3, [itemprop="name"]')
            link_el = card.select_one('a[href]')
            if not title_el or not link_el:
                continue

            title = title_el.get_text(" ", strip=True)
            href = link_el.get("href") or ""
            url_path = href.split("?", 1)[0].lstrip("/")
            match = re.search(r"_(\d+)$", url_path)
            ad_id = int(match.group(1)) if match else abs(hash(url_path or title)) % 10_000_000_000

            price = 0
            price_el = card.select_one('[data-marker="item-price"], [itemprop="price"]')
            if price_el:
                price_text = price_el.get("content") or price_el.get_text(" ", strip=True)
                digits = re.sub(r"\D", "", price_text)
                price = int(digits) if digits else 0

            price_string = str(price) if price else ""
            ads.append(Item(
                id=ad_id,
                title=title,
                urlPath=url_path,
                priceDetailed={
                    "enabled": True,
                    "fullString": price_string,
                    "hasValue": bool(price),
                    "postfix": "₽",
                    "string": price_string,
                    "stringWithoutDiscount": None,
                    "title": {},
                    "titleDative": "",
                    "value": price,
                    "wasLowered": False,
                    "exponent": "",
                },
            ))
        return ads

    def filter_ads(self, ads: list[Item]) -> list[Item]:
        """Сортирует объявления"""
        filters = [
            self._filter_viewed,
            self._filter_by_price_range,
            self._filter_by_black_keywords,
            self._filter_by_white_keyword,
            self._filter_by_address,
            self._filter_by_seller,
            self._filter_by_recent_time,
            self._filter_by_reserve,
            self._filter_by_promotion,
        ]

        for filter_fn in filters:
            ads = filter_fn(ads)
            logger.info(f"После фильтрации {filter_fn.__name__} осталось {len(ads)}")
            if not len(ads):
                return ads
        return ads

    def _filter_by_price_range(self, ads: list[Item]) -> list[Item]:
        try:
            return [ad for ad in ads if self.config.min_price <= ad.priceDetailed.value <= self.config.max_price]
        except Exception as err:
            logger.debug(f"Ошибка при фильтрации по цене: {err}")
            return ads

    def _filter_by_black_keywords(self, ads: list[Item]) -> list[Item]:
        if not self.config.keys_word_black_list:
            return ads
        try:
            return [ad for ad in ads if not self._is_phrase_in_ads(ad=ad, phrases=self.config.keys_word_black_list)]
        except Exception as err:
            logger.debug(f"Ошибка при проверке объявлений по списку стоп-слов: {err}")
            return ads

    def _filter_by_white_keyword(self, ads: list[Item]) -> list[Item]:
        if not self.config.keys_word_white_list:
            return ads
        try:
            return [ad for ad in ads if self._is_phrase_in_ads(ad=ad, phrases=self.config.keys_word_white_list)]
        except Exception as err:
            logger.debug(f"Ошибка при проверке объявлений по списку обязательных слов: {err}")
            return ads

    def _filter_by_address(self, ads: list[Item]) -> list[Item]:
        if not self.config.geo:
            return ads
        try:
            return [ad for ad in ads if self.config.geo in ad.geo.formattedAddress]
        except Exception as err:
            logger.debug(f"Ошибка при проверке объявлений по адресу: {err}")
            return ads

    def _filter_viewed(self, ads: list[Item]) -> list[Item]:
        try:
            return [ad for ad in ads if not self.is_viewed(ad=ad)]
        except Exception as err:
            logger.debug(f"Ошибка при проверке объявления по признаку смотрели или не смотрели: {err}")
            return ads

    def _add_seller_to_ads(self, ads: list[Item]) -> list[Item]:
        for ad in ads:
            if seller_id := self._extract_seller_slug(data=ad):
                ad.sellerId = seller_id
        return ads

    @staticmethod
    def _add_promotion_to_ads(ads: list[Item]) -> list[Item]:
        for ad in ads:
            ad.isPromotion = any(
                v.get("title") == "Продвинуто"
                for step in (ad.iva or {}).get("DateInfoStep", [])
                for v in step.payload.get("vas", [])
            )
        return ads

    def _filter_by_seller(self, ads: list[Item]) -> list[Item]:
        if not self.config.seller_black_list:
            return ads
        try:
            return [ad for ad in ads if not ad.sellerId or ad.sellerId not in self.config.seller_black_list]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании объявления с продавцами из черного списка : {err}")
            return ads

    def _filter_by_recent_time(self, ads: list[Item]) -> list[Item]:
        if not self.config.max_age:
            return ads
        try:
            return [ad for ad in ads if
                    ad.sortTimeStamp and self._is_recent(timestamp_ms=ad.sortTimeStamp, max_age_seconds=self.config.max_age)]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании слишком старых объявлений: {err}")
            return ads

    def _filter_by_reserve(self, ads: list[Item]) -> list[Item]:
        if not self.config.ignore_reserv:
            return ads
        try:
            return [ad for ad in ads if not ad.isReserved]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании объявлений в резерве: {err}")
            return ads

    def _filter_by_promotion(self, ads: list[Item]) -> list[Item]:
        ads = self._add_promotion_to_ads(ads=ads)
        if not self.config.ignore_promotion:
            return ads
        try:
            return [ad for ad in ads if not ad.isPromotion]
        except Exception as err:
            logger.debug(f"Ошибка при отсеивании продвинутых объявлений: {err}")
            return ads

    def parse_views(self, ads: list[Item]) -> list[Item]:
        if not self.config.parse_views:
            return ads

        logger.info("Начинаю парсинг просмотров")

        for ad in ads:
            try:
                html_code_full_page = self.fetch_data(url=f"https://www.avito.ru{ad.urlPath}")
                if html_code_full_page:
                    ad.total_views, ad.today_views = self._extract_views(html=html_code_full_page)
                delay = random.uniform(0.1, 0.9)
                time.sleep(delay)
            except Exception as err:
                logger.warning(f"Ошибка при парсинге {ad.urlPath}: {err}")
                continue

        return ads

    @staticmethod
    def _extract_views(html: str) -> tuple:
        soup = BeautifulSoup(html, "html.parser")

        def extract_digits(element):
            return int(''.join(filter(str.isdigit, element.get_text()))) if element else None

        total = extract_digits(soup.select_one('[data-marker="item-view/total-views"]'))
        today = extract_digits(soup.select_one('[data-marker="item-view/today-views"]'))

        return total, today

    def _refresh_manual_session(self, url: str) -> bool:
        try:
            from avito_session import refresh_avito_session

            html_code = refresh_avito_session(url=url, timeout_seconds=900, return_html=True)
            if not html_code:
                return False
            self.cookies_manager.load_local_session()
            return True
        except Exception as err:
            logger.warning(f"Не удалось обновить Avito-сессию вручную: {err}")
            return False

    def _get_manual_rendered_html(self, url: str) -> str | None:
        try:
            from avito_session import refresh_avito_session

            html_code = refresh_avito_session(url=url, timeout_seconds=900, return_html=True)
            if html_code:
                self.cookies_manager.load_local_session()
            return html_code
        except Exception as err:
            logger.warning(f"Не удалось получить отрендеренную страницу Avito: {err}")
            return None

    @staticmethod
    def _extract_seller_slug(data):
        match = re.search(r"/brands/([^/?#]+)", str(data))
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _is_phrase_in_ads(ad: Item, phrases: list) -> bool:
        full_text_from_ad = (ad.title + ad.description).lower()
        return any(phrase.lower() in full_text_from_ad for phrase in phrases)

    def is_viewed(self, ad: Item) -> bool:
        """Проверяет, смотрели мы это или нет"""
        return self.db_handler.record_exists(record_id=ad.id, price=ad.priceDetailed.value)

    @staticmethod
    def _is_recent(timestamp_ms: int, max_age_seconds: int) -> bool:
        now = datetime.utcnow()
        published_time = datetime.utcfromtimestamp(timestamp_ms / 1000)
        return (now - published_time) <= timedelta(seconds=max_age_seconds)


    def __save_viewed(self, ads: list[Item]) -> None:
        """Сохраняет просмотренные объявления"""
        try:
            self.db_handler.add_record_from_page(ads=ads)
        except Exception as err:
            logger.info(f"При сохранении в БД ошибка {err}")

    def get_next_page_url(self, url: str):
        """Получает следующую страницу"""
        try:
            url_parts = urlparse(url)
            query_params = parse_qs(url_parts.query)
            current_page = int(query_params.get('p', [1])[0])
            query_params['p'] = current_page + 1
            logger.debug(f"Страница {current_page} -> {current_page + 1}")

            new_query = urlencode(query_params, doseq=True)
            next_url = urlunparse((url_parts.scheme, url_parts.netloc, url_parts.path, url_parts.params, new_query,
                                   url_parts.fragment))
            return next_url
        except Exception as err:
            logger.error(f"Не смог сформировать ссылку на следующую страницу для {url}. Ошибка: {err}")
            return url


if __name__ == "__main__":
    try:
        config = load_avito_config("config.toml")
    except Exception as err:
        logger.error(f"Ошибка загрузки конфига: {err}")
        exit(1)

    while True:
        try:
            parser = AvitoParse(config)
            parser.parse()
            if config.one_time_start:
                logger.info("Парсинг завершен т.к. включён one_time_start в настройках")
                break
            logger.info(f"Парсинг завершен. Пауза {config.pause_general} сек")
            time.sleep(config.pause_general)
        except Exception as err:
            logger.error(f"Произошла ошибка {err}. Будет повторный запуск через 30 сек.")
            time.sleep(30)
