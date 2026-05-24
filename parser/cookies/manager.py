import json
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class CookiesManager:
    """
    Менеджер сессий (куки).
    Пока работает с локальным файлом, но готов к подключению API (например, spfa.ru).
    """
    def __init__(self, session_file: str = "avito_session.json"):
        self.session_file = session_file
        self.current_cookies: Optional[Dict[str, str]] = None
        self.user_agent: Optional[str] = None
        
        self.load_local_session()

    def load_local_session(self) -> bool:
        """Загружает куки из локального JSON файла (созданного Edge-скриптом)."""
        if not os.path.exists(self.session_file):
            logger.warning(f"Файл сессии {self.session_file} не найден.")
            return False
            
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            raw_cookies = data.get("cookies", [])
            
            # Конвертируем список словарей (формат Playwright/Selenium) или читаем как словарь
            formatted_cookies = {}
            if isinstance(raw_cookies, dict):
                formatted_cookies = raw_cookies
            elif isinstance(raw_cookies, list):
                for c in raw_cookies:
                    formatted_cookies[c['name']] = c['value']
                
            self.current_cookies = formatted_cookies
            self.user_agent = data.get("user_agent")
            
            logger.info("Локальная сессия успешно загружена.")
            return True
        except Exception as e:
            logger.error(f"Ошибка загрузки локальной сессии: {e}")
            return False

    def get_cookies(self) -> Optional[Dict[str, str]]:
        """Возвращает текущие активные куки."""
        # В будущем здесь может быть логика: если куки протухли, идем на API за новыми
        return self.current_cookies

    def get_user_agent(self) -> Optional[str]:
        return self.user_agent

    def handle_block(self):
        """Вызывается, когда текущие куки привели к бану."""
        logger.warning("Текущие куки заблокированы! Требуется ротация (пока не реализовано через API).")
        # Тут в будущем будет вызов API для покупки новых кук
        # и сброс self.current_cookies
