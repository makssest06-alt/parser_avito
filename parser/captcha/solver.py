import os
import logging

logger = logging.getLogger(__name__)

AVITO_CAPTCHA_ID = "2d9c743cf7d63dbc9db578a608196bcd"
AVITO_VERIFY_URL = "https://www.avito.ru/web/1/firewallCaptcha/verify"

SOLVER_BACKEND = os.getenv("CAPTCHA_SOLVER", "geeked")

class CaptchaSolver:
    def __init__(self, proxy: str | None = None):
        self.backend = SOLVER_BACKEND
        self.proxy = proxy
        self._solver = None

    def solve(self) -> dict | None:
        if self.backend == "geeked":
            return self._solve_geeked()
        if self.backend == "2captcha":
            return self._solve_2captcha()
        raise ValueError(f"Unknown captcha solver backend: {self.backend}")

    def _solve_geeked(self) -> dict | None:
        try:
            from parser.captcha.geeked import Geeked
            kwargs = {}
            if self.proxy:
                kwargs["proxy"] = self.proxy
                kwargs["verify"] = False
            g = Geeked(AVITO_CAPTCHA_ID, risk_type="slide", **kwargs)
            result = g.solve()
            logger.info(f"GeekedTest captcha solved: lot_number={result.get('lot_number','?')[:16]}...")
            return result
        except Exception as e:
            logger.error(f"GeekedTest captcha solve failed: {e}")
            return None

    def _solve_2captcha(self) -> dict | None:
        logger.error("2captcha backend not implemented yet - set CAPTCHA_SOLVER=geeked or add 2captcha key")
        return None

    @staticmethod
    def verify_with_avito(solution: dict, session_cookies: dict | None = None,
                          proxy: str | None = None, headers: dict | None = None) -> tuple[bool, dict]:
        try:
            from curl_cffi import requests
            verify_headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "Origin": "https://www.avito.ru",
                "Referer": "https://www.avito.ru/",
            }
            if headers:
                ua = headers.get("User-Agent") or headers.get("user-agent")
                if ua:
                    verify_headers["User-Agent"] = ua
            if "User-Agent" not in verify_headers:
                verify_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            verify_body = {
                "captcha_id": solution["captcha_id"],
                "lot_number": solution["lot_number"],
                "pass_token": solution["pass_token"],
                "gen_time": solution["gen_time"],
                "captcha_output": solution["captcha_output"],
            }
            proxies = {"http": proxy, "https": proxy} if proxy else None
            resp = requests.post(
                AVITO_VERIFY_URL,
                json=verify_body,
                headers=verify_headers,
                cookies=session_cookies,
                proxies=proxies,
                impersonate="chrome124",
                timeout=15,
            )
            response_cookies = {}
            try:
                if hasattr(resp.cookies, "get_dict"):
                    response_cookies = resp.cookies.get_dict()
                else:
                    response_cookies = dict(resp.cookies)
            except Exception:
                pass
            if resp.ok:
                try:
                    data = resp.json()
                    if data.get("verified"):
                        logger.info("Avito captcha verification: SUCCESS")
                        return True, response_cookies
                except (ValueError, KeyError):
                    pass
                if resp.status_code == 200:
                    logger.info("Avito captcha verify returned 200 (assumed success)")
                    return True, response_cookies
            logger.warning(f"Avito captcha verify failed: status={resp.status_code}")
            return False, {}
        except Exception as e:
            logger.error(f"Avito captcha verify request failed: {e}")
            return False, {}

    @staticmethod
    def is_configured() -> bool:
        backend = os.getenv("CAPTCHA_SOLVER", "geeked")
        if backend == "geeked":
            return True
        if backend == "2captcha":
            return bool(os.getenv("CAPTCHA_API_KEY"))
        return False
