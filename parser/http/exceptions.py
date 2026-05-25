class BlockError(Exception):
    """Вызывается, когда Avito блокирует запрос (капча, IP бан, 429)."""

    def __init__(self, message: str, status_code: int | None = None, response_cookies: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_cookies = response_cookies or {}

class ProxyError(Exception):
    """Вызывается при проблемах с подключением через прокси."""
    pass

class FetchError(Exception):
    """Вызывается при других ошибках загрузки страницы."""
    pass
