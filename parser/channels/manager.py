import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from database import Database
from parser.cookies.spfa_client import SpfaApiClient

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)


@dataclass
class ParserChannel:
    id: int
    proxy_string: str
    formatted_proxy: str
    cookies: dict | None
    user_agent: str | None
    spfa_id: int | None
    fail_count: int
    success_count: int
    last_unblock_time: float
    last_error: str | None


class ChannelManager:
    """Manages Avito parsing channels: proxy + cookies + user-agent."""

    def __init__(self, db_name: str = "users.db"):
        self.db = Database(db_name)
        self.db_name = self.db.db_name
        token = os.getenv("SPFA_TOKEN", "").strip()
        self.api_client = SpfaApiClient(token) if token else None
        self._add_env_proxy()
        self._ensure_channels_for_active_proxies()

    def acquire_channel(self) -> Optional[ParserChannel]:
        """Returns the least recently used channel that is not cooling down."""
        self._ensure_channels_for_active_proxies()
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pc.id, pc.proxy_string, pc.spfa_id, pc.cookies_json, pc.user_agent,
                       pc.fail_count, pc.success_count, pc.last_unblock_time, pc.last_error
                FROM parser_channels pc
                JOIN mobile_proxies mp ON mp.proxy_string = pc.proxy_string
                WHERE mp.is_active = TRUE
                  AND (pc.cooldown_until IS NULL OR pc.cooldown_until <= ?)
                ORDER BY pc.last_used IS NOT NULL, pc.last_used ASC, pc.fail_count ASC
                LIMIT 1
            ''', (datetime.now().isoformat(),))
            row = cursor.fetchone()

        if not row:
            logger.warning("Нет доступных каналов: все прокси в cooldown или пул пуст.")
            return None

        channel = self._row_to_channel(row)
        if self._unblock_before_reuse(channel):
            channel = self.get_channel(channel.id)

        if not channel.cookies and self.api_client:
            if not self.refresh_cookies(channel):
                self.cooldown_channel(channel, "Не удалось получить cookies", minutes=10)
                return self.acquire_channel()
            channel = self.get_channel(channel.id)

        if channel:
            self._touch_channel(channel.id)
        return channel

    def get_channel(self, channel_id: int) -> Optional[ParserChannel]:
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, proxy_string, spfa_id, cookies_json, user_agent,
                       fail_count, success_count, last_unblock_time, last_error
                FROM parser_channels
                WHERE id = ?
            ''', (channel_id,))
            row = cursor.fetchone()
        return self._row_to_channel(row) if row else None

    def mark_success(self, channel: ParserChannel):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET success_count = success_count + 1,
                    fail_count = 0,
                    status = 'ready',
                    last_error = NULL,
                    cooldown_until = NULL,
                    last_used = CURRENT_TIMESTAMP,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (channel.id,))
            conn.commit()

    def cooldown_channel(self, channel: ParserChannel, reason: str, minutes: int = 15):
        minutes = self._cooldown_minutes(reason, channel.fail_count + 1, default_minutes=minutes)
        cooldown_until = datetime.now() + timedelta(minutes=minutes)
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET status = 'cooldown',
                    cooldown_until = ?,
                    fail_count = fail_count + 1,
                    last_error = ?,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (cooldown_until.isoformat(), reason, channel.id))
            conn.commit()
        logger.warning(f"Канал #{channel.id} поставлен в cooldown до {cooldown_until:%H:%M:%S}: {reason}")

    def handle_rate_limit(self, channel: ParserChannel) -> bool:
        """Handles repeated 429 without changing IP first."""
        if not self.api_client or not channel.spfa_id:
            return False

        if time.time() - channel.last_unblock_time <= 60:
            logger.info(f"Канал #{channel.id}: unblock недавно уже запускался, покупаем новые cookies.")
            return self.refresh_cookies(channel)

        logger.info(f"Канал #{channel.id}: отправляем cookies #{channel.spfa_id} на unblock.")
        if self.api_client.unblock_session(channel.spfa_id):
            time.sleep(5)
            with sqlite3.connect(self.db_name) as conn:
                conn.execute('''
                    UPDATE parser_channels
                    SET last_unblock_time = ?, updated_date = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (time.time(), channel.id))
                conn.commit()
            return True

        return self.refresh_cookies(channel)

    def refresh_cookies(self, channel: ParserChannel) -> bool:
        if not self.api_client:
            return False

        cookie_id, cookies, user_agent = self.api_client.get_new_session()
        if not cookies:
            return False

        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET spfa_id = ?,
                    cookies_json = ?,
                    user_agent = ?,
                    last_unblock_time = 0,
                    status = 'ready',
                    cooldown_until = NULL,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (cookie_id, json.dumps(cookies, ensure_ascii=False), user_agent or "", channel.id))
            conn.commit()
        logger.info(f"Канал #{channel.id}: получены новые cookies #{cookie_id}.")
        return True

    def _ensure_channels_for_active_proxies(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO parser_channels (proxy_string)
                SELECT proxy_string FROM mobile_proxies WHERE is_active = TRUE
            ''')
            conn.commit()

    def _add_env_proxy(self):
        proxy = os.getenv("DEFAULT_MOBILE_PROXY", "").strip()
        if proxy:
            self.db.add_mobile_proxy(proxy)

    def _row_to_channel(self, row) -> ParserChannel:
        cookies = None
        if row[3]:
            try:
                cookies = json.loads(row[3])
            except json.JSONDecodeError:
                logger.warning(f"Канал #{row[0]}: не удалось прочитать cookies_json.")

        return ParserChannel(
            id=row[0],
            proxy_string=row[1],
            formatted_proxy=self._format_proxy(row[1]),
            spfa_id=row[2],
            cookies=cookies,
            user_agent=row[4],
            fail_count=row[5] or 0,
            success_count=row[6] or 0,
            last_unblock_time=row[7] or 0,
            last_error=row[8],
        )

    def _unblock_before_reuse(self, channel: ParserChannel) -> bool:
        """Runs free SPFA unblock before retrying a channel that previously hit 403."""
        if not self.api_client or not channel.spfa_id or not channel.last_error:
            return False
        if "403" not in channel.last_error:
            return False
        if time.time() - channel.last_unblock_time <= 60:
            return False

        logger.info(f"Канал #{channel.id}: перед повторным использованием запускаем free unblock cookies #{channel.spfa_id}.")
        if not self.api_client.unblock_session(channel.spfa_id):
            return False

        time.sleep(5)
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET last_unblock_time = ?, updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (time.time(), channel.id))
            conn.commit()
        return True

    @staticmethod
    def _cooldown_minutes(reason: str, fail_count: int, default_minutes: int) -> int:
        if "403" not in reason:
            return default_minutes
        if fail_count <= 1:
            return max(default_minutes, 15)
        if fail_count == 2:
            return max(default_minutes, 30)
        if fail_count == 3:
            return max(default_minutes, 60)
        if fail_count == 4:
            return max(default_minutes, 180)
        return max(default_minutes, 360)

    @staticmethod
    def _format_proxy(proxy_string: str) -> str:
        if proxy_string.startswith("http://") or proxy_string.startswith("https://"):
            return proxy_string

        if "@" in proxy_string:
            part1, part2 = proxy_string.split("@", 1)
            if ":" in part1 and not part1.replace(":", "").isdigit():
                return f"http://{proxy_string}"
            return f"http://{part2}@{part1}"

        return f"http://{proxy_string}"

    def _touch_channel(self, channel_id: int):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET last_used = CURRENT_TIMESTAMP, updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (channel_id,))
            conn.commit()
