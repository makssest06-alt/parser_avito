class BlockError(Exception):
    """Вызывается, когда Avito блокирует запрос (капча, IP бан, 429)."""
    pass

class ProxyError(Exception):
    """Вызывается при проблемах с подключением через прокси."""
    pass

class FetchError(Exception):
    """Вызывается при других ошибках загрузки страницы."""
    pass
