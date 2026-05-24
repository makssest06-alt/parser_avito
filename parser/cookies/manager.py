import json
import os
import logging
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from .spfa_client import SpfaApiClient

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)

class CookiesManager:
    """
    Менеджер сессий (куки).
    Умеет читать локальный файл и запрашивать новые куки через API.
    """
    def __init__(self, session_file: str = "avito_session.json"):
        self.session_file = session_file
        self.current_cookies: Optional[Dict[str, str]] = None
        self.user_agent: Optional[str] = None
        self.cookie_id: Optional[int] = None
        self.last_unblock_time: float = 0
        
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
            
            formatted_cookies = {}
            if isinstance(raw_cookies, dict):
                formatted_cookies = raw_cookies
            elif isinstance(raw_cookies, list):
                for c in raw_cookies:
                    formatted_cookies[c['name']] = c['value']
                
            self.current_cookies = formatted_cookies
            self.user_agent = data.get("user_agent")
            self.cookie_id = data.get("spfa_id")
            self.last_unblock_time = data.get("last_unblock_time", 0)
            
            logger.info(f"Локальная сессия загружена (ID: {self.cookie_id}).")
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
        logger.warning("Текущие куки заблокированы! Запрашиваем новые или разблокируем...")
        
        if not self.api_client:
            logger.warning("SPFA_TOKEN не настроен. Ротация через API невозможна.")
            return False

        import time
        # Пытаемся разблокировать, если куки от spfa, и мы не делали этого за последние 60 сек
        if self.cookie_id and (time.time() - self.last_unblock_time > 60):
            logger.info(f"Пробуем бесплатно разблокировать текущую сессию (ID: {self.cookie_id})...")
            if self.api_client.unblock_session(self.cookie_id):
                logger.info("Разблокировка запущена. Ждем 5 секунд...")
                time.sleep(5)
                self.last_unblock_time = time.time()
                self._save_session_locally()
                return True
            else:
                logger.info("Не удалось разблокировать. Вероятно истекли 12 часов.")

        # Покупаем новые
        logger.info("Покупаем новую сессию Spfa...")
        cid, cookies, ua = self.api_client.get_new_session()
        
        if cookies:
            self.cookie_id = cid
            self.current_cookies = cookies
            if ua:
                self.user_agent = ua
            self.last_unblock_time = 0
            self._save_session_locally()
            
            balance = self.api_client.get_balance()
            logger.info(f"Новая сессия куплена (ID: {cid}). Остаток баланса: {balance} руб.")
            return True
            
        logger.error("Не удалось получить новые куки через API.")
        return False

    def _save_session_locally(self):
        """Сохраняет новую API сессию в файл, чтобы не перекачивать ее при перезапуске."""
        if self.current_cookies:
            data = {
                "spfa_id": self.cookie_id,
                "last_unblock_time": self.last_unblock_time,
                "cookies": self.current_cookies,
                "user_agent": self.user_agent or ""
            }
            try:
                with open(self.session_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f)
            except Exception as e:
                logger.error(f"Ошибка сохранения сессии: {e}")
