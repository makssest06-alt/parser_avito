import threading
import time
import json
import sqlite3
from datetime import datetime
from Database import Database
from dto import AvitoConfig
from parser_cls import AvitoParse
from models import Item
import logging

logger = logging.getLogger(__name__)

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
        """Основной цикл мониторинга"""
        while self.is_running and not self.stop_event.is_set():
            try:
                # Получаем всех активных пользователей
                active_users = self._get_active_users()
                
                for user_id in active_users:
                    if self.stop_event.is_set():
                        break
                    
                    # Получаем ссылки пользователя
                    links = self.db.get_user_links(user_id)
                    if not links:
                        continue
                    
                    # Получаем настройки парсера
                    settings = self.db.get_parser_settings(user_id)
                    if not settings:
                        settings = self._get_default_settings()
                    
                    # Создаем конфиг для парсера
                    config = self._create_config(links, settings, user_id)
                    
                    # Запускаем парсинг
                    self._run_parser_for_user(user_id, config)
                
                # Пауза между циклами мониторинга
                time.sleep(300)  # 5 минут
                
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(60)

    def _get_active_users(self):
        """Получает список активных пользователей"""
        with sqlite3.connect(self.db.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT u.user_id 
                FROM users u
                JOIN subscriptions s ON u.user_id = s.user_id
                WHERE s.is_active = TRUE AND s.end_date > ?
            ''', (datetime.now(),))
            return [row[0] for row in cursor.fetchall()]

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
        return AvitoConfig(
            urls=[link[0] for link in links],
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
            proxy_string=settings.get('proxy_string', ''),
            proxy_change_url=settings.get('proxy_change_url', ''),
            tg_notifications=settings.get('tg_notifications', True),
            one_time_start=False,  # Изменено на False для непрерывного парсинга
            count=3,  # Увеличиваем количество страниц для парсинга
            pause_between_links=10,  # Увеличиваем паузу между запросами
            max_count_of_retry=5,
            save_xlsx=False
        )

    def set_bot(self, bot_instance):
        """Устанавливает экземпляр бота для отправки сообщений"""
        self.bot = bot_instance

    def _run_parser_for_user(self, user_id, config):
        """Запускает парсер для пользователя"""
        try:
            parser = AvitoParse(config, stop_event=self.stop_event)
            
            # Переопределяем отправку в Telegram для отправки пользователю
            if config.tg_notifications and self.bot:
                parser.tg_handler = UserTgHandler(user_id, self.bot)
            
            # Запускаем парсинг с ограничением по времени
            def run_parse():
                parser.parse()
            
            # Запускаем в отдельном потоке с таймаутом
            parse_thread = threading.Thread(target=run_parse)
            parse_thread.start()
            parse_thread.join(timeout=300)  # 5 минут на парсинг всех страниц
            
            # Если поток еще жив, останавливаем
            if parse_thread.is_alive():
                logger.warning(f"Парсинг для пользователя {user_id} превысил время выполнения")
                
        except Exception as e:
            logger.error(f"Ошибка парсинга для пользователя {user_id}: {e}")

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
            logger.error(f"Ошибка отправки сообщения пользователю {self.user_id}: {e}")

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
