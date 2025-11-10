import threading
import time
import json
from datetime import datetime
from database import Database
from dto import AvitoConfig
from parser_cls import AvitoParse
from bot import bot
import logging

logger = logging.getLogger(__name__)

class ParserService:
    def __init__(self):
        self.db = Database()
        self.is_running = False
        self.stop_event = threading.Event()
        self.thread = None

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
        with self.db.conn:
            cursor = self.db.conn.cursor()
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
            'tg_notifications': True
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
            one_time_start=True,
            count=1,
            pause_between_links=2,
            max_count_of_retry=3,
            save_xlsx=False
        )

    def _run_parser_for_user(self, user_id, config):
        """Запускает парсер для пользователя"""
        try:
            parser = AvitoParse(config, stop_event=self.stop_event)
            
            # Переопределяем отправку в Telegram для отправки пользователю
            if config.tg_notifications:
                parser.tg_handler = UserTgHandler(user_id)
            
            parser.parse()
            
        except Exception as e:
            logger.error(f"Ошибка парсинга для пользователя {user_id}: {e}")

class UserTgHandler:
    """Обработчик для отправки уведомлений пользователю через бота"""
    
    def __init__(self, user_id):
        self.user_id = user_id
        self.db = Database()

    def send_to_tg(self, ad=None, msg=None):
        """Отправляет сообщение пользователю через бота"""
        try:
            if ad and not self.db.is_ad_found(self.user_id, ad.id):
                # Сохраняем объявление
                self.db.add_found_ad(self.user_id, ad.id, json.dumps(ad.dict()))
                
                # Форматируем сообщение
                message = self.format_ad(ad)
                bot.send_message(self.user_id, message, parse_mode='Markdown')
                
            elif msg:
                bot.send_message(self.user_id, msg)
                
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения пользователю {self.user_id}: {e}")

    @staticmethod
    def format_ad(ad):
        """Форматирует объявление для отправки"""
        full_url = f"https://avito.ru/{ad.urlPath}"
        price = ad.priceDetailed.value if ad.priceDetailed else "Цена не указана"
        
        message = (
            f"*🏠 Новое объявление!*\n\n"
            f"*{price}* руб." + (" 🔥" if getattr(ad, 'isPromotion', False) else "") + "\n"
            f"*{ad.title}*\n\n"
            f"📍 {ad.geo.formattedAddress if ad.geo else 'Адрес не указан'}\n"
            f"🔗 [Ссылка на объявление]({full_url})\n"
        )
        
        if hasattr(ad, 'total_views') and ad.total_views:
            message += f"👁️ Просмотры: {ad.total_views}\n"
            
        return message

# Глобальный экземпляр сервиса парсера
parser_service = ParserService()
