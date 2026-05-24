import requests
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class SpfaApiClient:
    """Клиент для работы с API spfa.ru для получения сессий Авито."""
    
    BASE_URL = "https://spfa.ru/api" 
    
    def __init__(self, token: str):
        self.token = token
        
    def get_balance(self) -> float:
        """Получает текущий баланс в рублях."""
        try:
            res = requests.post(
                f"{self.BASE_URL}/balance/", 
                json={"api_key": self.token},
                timeout=10
            )
            if res.status_code == 200:
                data = res.json()
                if data.get("success"):
                    return float(data.get("balance", 0.0))
        except Exception as e:
            logger.error(f"Ошибка запроса баланса: {e}")
        return -1.0

    def get_new_session(self) -> Tuple[Optional[int], Optional[Dict[str, str]], Optional[str]]:
        """
        Покупает новую сессию.
        Возвращает кортеж (id, cookies_dict, user_agent).
        """
        try:
            response = requests.post(
                f"{self.BASE_URL}/cookies/", 
                json={"api_key": self.token, "full_format": False},
                timeout=15
            )
            
            data = response.json() if response.status_code in [200, 403, 503] else {}
            
            if response.status_code == 200 and data.get("success"):
                results = data.get("results", {})
                cookie_id = results.get("id")
                cookies = results.get("cookies", {})
                user_agent = results.get("user_agent", "")
                
                logger.info(f"Успешно получена новая сессия от spfa.ru (ID: {cookie_id})")
                return cookie_id, cookies, user_agent
            else:
                logger.error(f"Ошибка API spfa.ru (Код {response.status_code}): {data.get('message', response.text)}")
                
        except Exception as e:
            logger.error(f"Ошибка соединения с spfa.ru: {e}")
            
        return None, None, None

    def unblock_session(self, cookie_id: int) -> bool:
        """Отправляет куки на бесплатную разблокировку."""
        try:
            response = requests.post(
                f"{self.BASE_URL}/unblock/", 
                json={"api_key": self.token, "id": cookie_id},
                timeout=10
            )
            
            data = response.json() if response.status_code in [202, 404, 410] else {}
            
            if response.status_code == 202 and data.get("success"):
                logger.info(f"Запрос на разблокировку (ID: {cookie_id}) успешно отправлен.")
                return True
            else:
                logger.warning(f"Не удалось разблокировать сессию (Код {response.status_code}): {data.get('message')}")
                
        except Exception as e:
            logger.error(f"Ошибка соединения с spfa.ru при разблокировке: {e}")
            
        return False
