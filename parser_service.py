import threading
import time
import json
import sqlite3
from datetime import datetime
from database import Database
from dto import AvitoConfig
from parser_cls import AvitoParse
from models import Item
import logging
import re

logger = logging.getLogger(__name__)


def sanitize_error(error: Exception) -> str:
    text = str(error)
    text = re.sub(r"/bot[^/\s]+/", "/bot***/", text)
    text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***", text)
    return text

class ParserService:
    def __init__(self):
        self.db = Database()
        self.is_running = False
        self.stop_event = threading.Event()
        self.thread = None
        self.bot = None  # Будет установлен позже

    def start_monitoring(self):
        """Запускает мониторинг в фоновом режиме"""
        if self.is_running:
            logger.info("Мониторинг уже запущен")
            return
        
        self.is_running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.thread.start()
        logger.info("Мониторинг запущен")

    def stop_monitoring(self):
        """Останавливает мониторинг"""
        self.is_running = False
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Мониторинг остановлен")
        
    def __del__(self):
        """Деструктор для корректной остановки"""
        self.stop_monitoring()

    def _monitoring_loop(self):
        """Основной цикл мониторинга (Queue & Deduplication)"""
        while self.is_running and not self.stop_event.is_set():
            try:
                links_with_users = self.db.get_all_active_links_with_users()
                
                if not links_with_users:
                    time.sleep(60)
                    continue
                    
                # Создаем единый парсер для скачивания (с любыми дефолтными настройками)
                generic_config = self._create_config([], self._get_default_settings(), 0)
                parser = AvitoParse(generic_config, stop_event=self.stop_event)
                
                for url, user_ids in links_with_users.items():
                    if self.stop_event.is_set():
                        break
                        
                    logger.info(f"Парсинг ссылки для {len(user_ids)} пользователей: {url}")
                    ads = parser.get_ads_from_url(url)
                    
                    if not ads:
                        time.sleep(10)
                        continue
                        
                    for user_id in user_ids:
                        settings = self.db.get_parser_settings(user_id)
                        if not settings:
                            settings = self._get_default_settings()
                            
                        # Создаем конфиг с фильтрами этого пользователя
                        user_config = self._create_config([url], settings, user_id)
                        
                        # Фильтруем
                        from parser.filters import AdsFilter
                        filtered_ads = AdsFilter.filter_ads(ads, user_config)
                        
                        # Рассылаем
                        if user_config.tg_notifications and self.bot:
                            tg_handler = UserTgHandler(user_id, self.bot)
                            for ad in filtered_ads:
                                tg_handler.send_to_tg(ad=ad)
                                
                    time.sleep(10) # Пауза между ссылками
                
                time.sleep(120) # Пауза между полными циклами обхода всех ссылок
                
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(60)

    def _get_default_settings(self):
        """Возвращает настройки по умолчанию"""
        return {
            'min_price': 0,
            'max_price': 999999999,
            'keys_word_white_list': [],
            'keys_word_black_list': [],
            'seller_black_list': [],
            'geo': '',
            'max_age': 86400,
            'ignore_reserv': True,
            'ignore_promotion': False,
            'parse_views': False,
            'tg_notifications': True,
            'proxy_string': '',
            'proxy_change_url': ''
        }

    def _create_config(self, links, settings, user_id):
        """Создает конфиг для парсера"""
        # links может быть списком строк (URLs) или списком кортежей (старый формат из БД)
        urls = [link[0] if isinstance(link, tuple) else link for link in links]
        
        # Всегда используем мобильные прокси из базы данных
        # Настройки прокси пользователя игнорируются
        return AvitoConfig(
            urls=urls,
            min_price=settings['min_price'],
            max_price=settings['max_price'],
            keys_word_white_list=settings['keys_word_white_list'],
            keys_word_black_list=settings['keys_word_black_list'],
            seller_black_list=settings['seller_black_list'],
            geo=settings['geo'],
            max_age=settings['max_age'],
            ignore_reserv=settings['ignore_reserv'],
            ignore_promotion=settings['ignore_promotion'],
            parse_views=settings['parse_views'],
            proxy_string='',  # Пустая строка - прокси будет выбран из мобильных прокси
            proxy_change_url='',  # Пустая строка, так как смена IP недоступна
            tg_notifications=settings.get('tg_notifications', True),
            one_time_start=True,  # Один проход выполняется в общем цикле мониторинга
            count=1,  # Парсим только первую страницу
            pause_between_links=10,  # Пауза между запросами
            max_count_of_retry=5,
            save_xlsx=False
        )

    def set_bot(self, bot_instance):
        """Устанавливает экземпляр бота для отправки сообщений"""
        self.bot = bot_instance

class UserTgHandler:
    """Обработчик для отправки уведомлений пользователю через бота"""
    
    def __init__(self, user_id, bot_instance):
        self.user_id = user_id
        self.db = Database()
        self.bot = bot_instance

    def send_to_tg(self, ad=None, msg=None):
        """Отправляет сообщение пользователю через бота"""
        try:
            if ad and not self.db.is_ad_found(self.user_id, ad.id):
                # Сохраняем объявление, преобразуя объект в словарь и сериализуя в JSON
                # Используем model_dump() для Pydantic v2 или dict() для v1
                try:
                    ad_dict = ad.model_dump()
                except AttributeError:
                    ad_dict = ad.dict()
                # Преобразуем все HttpUrl и Url объекты в строки
                self._convert_urls_to_strings(ad_dict)
                self.db.add_found_ad(self.user_id, ad.id, json.dumps(ad_dict, ensure_ascii=False, default=str))
                
                # Форматируем сообщение
                message = self.format_ad(ad)
                self.bot.send_message(self.user_id, message, parse_mode='Markdown')
                
            elif msg:
                self.bot.send_message(self.user_id, msg)
                
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {self.user_id}: {sanitize_error(e)}")

    def _convert_urls_to_strings(self, obj):
        """Рекурсивно преобразует все HttpUrl объекты и другие несериализуемые типы в строки"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                # Проверяем, является ли объект HttpUrl или имеет метод __str__
                if hasattr(value, '__class__') and ('HttpUrl' in str(value.__class__) or 'Url' in str(value.__class__)):
                    obj[key] = str(value)
                # Обрабатываем вложенные словари и списки
                elif isinstance(value, dict):
                    self._convert_urls_to_strings(value)
                elif isinstance(value, list):
                    self._convert_urls_to_strings(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if hasattr(item, '__class__') and ('HttpUrl' in str(item.__class__) or 'Url' in str(item.__class__)):
                    obj[i] = str(item)
                elif isinstance(item, dict):
                    self._convert_urls_to_strings(item)
                elif isinstance(item, list):
                    self._convert_urls_to_strings(item)

    @staticmethod
    def format_ad(ad):
        """Форматирует объявление для отправки"""
        # Безопасное получение URL
        url_path = getattr(ad, 'urlPath', '')
        full_url = f"https://avito.ru/{url_path}" if url_path else "https://avito.ru/"
        
        # Безопасное получение цены
        price = "Цена не указана"
        if hasattr(ad, 'priceDetailed') and ad.priceDetailed:
            price_value = getattr(ad.priceDetailed, 'value', None)
            if price_value is not None:
                price = f"{price_value}"
        
        # Безопасное получение заголовка
        title = getattr(ad, 'title', 'Без названия')
        
        # Безопасное получение адреса
        address = 'Адрес не указан'
        if hasattr(ad, 'geo') and ad.geo:
            address = getattr(ad.geo, 'formattedAddress', 'Адрес не указан')
        
        message = (
            f"*🏠 Новое объявление!*\n\n"
            f"*{price}* руб." + (" 🔥" if getattr(ad, 'isPromotion', False) else "") + "\n"
            f"*{title}*\n\n"
            f"📍 {address}\n"
            f"🔗 [Ссылка на объявление]({full_url})\n"
        )
        
        if hasattr(ad, 'total_views') and ad.total_views:
            message += f"👁️ Просмотры: {ad.total_views}\n"
            
        return message

# Глобальный экземпляр сервиса парсера
parser_service = ParserService()
