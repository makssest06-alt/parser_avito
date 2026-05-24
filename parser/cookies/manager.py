import json
import os
import logging
from typing import Dict, Optional
from .spfa_client import SpfaApiClient

logger = logging.getLogger(__name__)

class CookiesManager:
    """
    Менеджер сессий (куки).
    Умеет читать локальный файл и запрашивать новые куки через API.
    """
    def __init__(self, session_file: str = "avito_session.json"):
        self.session_file = session_file
        self.current_cookies: Optional[Dict[str, str]] = None
        self.user_agent: Optional[str] = None
        
        self.spfa_token = os.getenv("SPFA_TOKEN")
        self.api_client = SpfaApiClient(self.spfa_token) if self.spfa_token else None
        
        self.load_local_session()

    def load_local_session(self) -> bool:
        """Загружает куки из локального JSON файла."""
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
        """Возвращает текущие активные куки. Если их нет, пробует получить из API."""
        if not self.current_cookies and self.api_client:
            self.handle_block()
        return self.current_cookies

    def get_user_agent(self) -> Optional[str]:
        return self.user_agent

    def handle_block(self) -> bool:
        """Вызывается, когда текущие куки привели к бану."""
        logger.warning("Текущие куки заблокированы! Запрашиваем новые...")
        
        if self.api_client:
            logger.info("Обращение к API spfa.ru за новой сессией...")
            new_cookies, new_ua = self.api_client.get_new_session()
            if new_cookies:
                self.current_cookies = new_cookies
                if new_ua:
                    self.user_agent = new_ua
                self._save_session_locally()
                return True
            else:
                logger.error("Не удалось получить новые куки через API.")
                return False
        else:
            logger.warning("SPFA_TOKEN не настроен. Ротация через API невозможна.")
            return False

    def _save_session_locally(self):
        """Сохраняет новую API сессию в файл, чтобы не перекачивать ее при перезапуске."""
        if self.current_cookies:
            data = {
                "cookies": self.current_cookies,
                "user_agent": self.user_agent or ""
            }
            try:
                with open(self.session_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
            except Exception as e:
                logger.error(f"Ошибка сохранения сессии: {e}")
