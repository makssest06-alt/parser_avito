import os
import requests
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class SpfaApiClient:
    """Клиент для работы с API spfa.ru для получения сессий Авито."""
    
    # URL может отличаться, если в документации spfa.ru указан другой
    BASE_URL = "https://spfa.ru/api/v1" 
    
    def __init__(self, token: str):
        self.token = token
        
    def get_new_session(self) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        Покупает/получает новую сессию.
        Возвращает кортеж (cookies_dict, user_agent).
        """
        try:
            # TODO: Уточнить точный эндпоинт API spfa.ru в документации сервиса
            # Обычно это GET запрос с передачей токена
            response = requests.get(
                f"{self.BASE_URL}/get_cookies", 
                params={"token": self.token, "service": "avito"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" or "cookies" in data:
                    raw_cookies = data.get("cookies", [])
                    user_agent = data.get("user_agent", "")
                    
                    # Форматируем куки
                    formatted_cookies = {}
                    if isinstance(raw_cookies, dict):
                        formatted_cookies = raw_cookies
                    elif isinstance(raw_cookies, list):
                        for c in raw_cookies:
                            if 'name' in c and 'value' in c:
                                formatted_cookies[c['name']] = c['value']
                            else:
                                # fallback for simple k-v lists if any
                                pass
                                
                    logger.info("Успешно получена новая сессия от spfa.ru")
                    return formatted_cookies, user_agent
                else:
                    logger.error(f"Ошибка API spfa.ru: {data}")
            else:
                logger.error(f"Сбой запроса к spfa.ru: {response.status_code} {response.text}")
                
        except Exception as e:
            logger.error(f"Ошибка соединения с spfa.ru: {e}")
            
        return None, None
