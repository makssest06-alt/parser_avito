import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


AVITO_URL = "https://www.avito.ru/moskva/telefony/mobilnye_telefony/apple-ASgBAgICAUSSyA3OqzmwwQ2I_Dc?cd=1"
PROFILE_DIR = Path("browser_profile") / "avito"
SESSION_FILE = Path("avito_session.json")
COOKIES_FILE = Path("cookies.json")
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def has_listings(page) -> bool:
    selectors = [
        '[data-marker="item-title"]',
        '[data-marker="item"]',
        '.iva-item-root',
        '[itemtype*="schema.org/Product"]',
    ]
    return any(page.locator(selector).count() > 0 for selector in selectors)


def has_ip_problem(page) -> bool:
    text = page.locator("body").inner_text(timeout=10_000).lower()
    return "проблем" in text and "ip" in text


def save_session(context, page):
    user_agent = page.evaluate("() => navigator.userAgent")
    cookies = {cookie["name"]: cookie["value"] for cookie in context.cookies()}

    SESSION_FILE.write_text(
        json.dumps({"cookies": cookies, "user_agent": user_agent}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")


def wait_for_listings(page, timeout_seconds: int = 900) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            if has_listings(page) and not has_ip_problem(page):
                return True
        except Exception:
            pass
        page.wait_for_timeout(2_000)
    return False


def refresh_avito_session(url: str = AVITO_URL, timeout_seconds: int = 900, return_html: bool = False) -> str | None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        launch_kwargs = {}
        if EDGE_PATH.exists():
            launch_kwargs["executable_path"] = str(EDGE_PATH)

        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            **launch_kwargs,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        print("Открылся браузер Avito.")
        print("Если появилась капча или 'проблема с IP', реши ее вручную.")
        print("Программа продолжит сама, когда увидит объявления на странице.")

        if not wait_for_listings(page, timeout_seconds=timeout_seconds):
            print("Сессия не сохранена: за отведенное время объявления не появились.")
            context.close()
            return None

        save_session(context, page)
        html = page.content() if return_html else None
        print(f"Сессия сохранена в {SESSION_FILE}")
        context.close()
        return html


def main():
    refresh_avito_session()


if __name__ == "__main__":
    main()
