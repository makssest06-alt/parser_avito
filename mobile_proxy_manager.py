import logging
import os
from pathlib import Path
from database import Database
from dto import Proxy
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)

class MobileProxyManager:
    def __init__(self):
        self.db = Database()
        # Добавляем начальный прокси при инициализации
        self._add_initial_proxy()

    def _add_initial_proxy(self):
        """Добавляет начальный прокси в базу"""
        initial_proxy = os.getenv("DEFAULT_MOBILE_PROXY", "").strip()
        if not initial_proxy:
            return
        try:
            self.db.add_mobile_proxy(initial_proxy)
            logger.info("Добавлен начальный мобильный прокси из .env")
        except Exception as e:
            logger.debug(f"Начальный прокси уже существует: {e}")

    def get_random_proxy(self) -> Optional[Proxy]:
        """Получает случайный активный прокси"""
        proxy_string = self.db.get_random_active_proxy()
        if proxy_string:
            # Для мобильных прокси используем пустую строку для смены IP
            # так как смена IP обычно происходит автоматически
            return Proxy(
                proxy_string=proxy_string,
                change_ip_link=""  # У мобильных прокси IP меняется автоматически
            )
        return None

    def mark_proxy_success(self, proxy_string: str):
        """Отмечает успешное использование прокси"""
        self.db.update_proxy_stats(proxy_string, success=True)

    def mark_proxy_failed(self, proxy_string: str, reason: str):
        """Отмечает неудачное использование прокси без постоянного отключения."""
        logger.warning(f"Прокси {proxy_string} получил ошибку: {reason}")
        self.db.update_proxy_stats(proxy_string, success=False, fail_reason=reason)

    def add_proxy(self, proxy_string: str, proxy_type: str = "server", change_ip_url: str = ""):
        """Добавляет новый proxy в базу"""
        self.db.add_mobile_proxy(proxy_string, proxy_type=proxy_type, change_ip_url=change_ip_url)
        logger.info(f"Добавлен новый прокси: {proxy_string}")

    def get_proxy_status(self):
        """Возвращает статус всех прокси"""
        return self.db.get_all_proxies()

    def is_proxy_available(self) -> bool:
        """Проверяет, есть ли доступные прокси"""
        return self.db.get_random_active_proxy() is not None

# Глобальный экземпляр менеджера прокси
proxy_manager = MobileProxyManager()
