import json
import logging
import os
import random
import sqlite3
import time
import urllib.error
import urllib.request
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
    impersonate: str | None
    spfa_id: int | None
    fail_count: int
    success_count: int
    last_unblock_time: float
    last_error: str | None
    status_history: list[int]
    unblock_started_at: float | None
    last_purchase_at: float | None
    proxy_type: str
    change_ip_url: str
    last_ip_change: float


class ChannelManager:
    """Manages Avito parsing channels: proxy + cookies + user-agent."""

    MAX_STATUS_HISTORY = 20
    PURCHASE_COOLDOWN = 600
    UNBLOCK_TIMEOUT = 300
    WAIT_FIRST_FOR_UNBLOCK = 5
    WAIT_FOR_UNBLOCK = 10
    MIN_CHANNEL_REUSE_SECONDS = int(os.getenv("MIN_CHANNEL_REUSE_SECONDS", "60"))
    MOBILE_IP_CHANGE_COOLDOWN_SECONDS = int(os.getenv("MOBILE_IP_CHANGE_COOLDOWN_SECONDS", "120"))
    MOBILE_IP_CHANGE_WAIT_SECONDS = int(os.getenv("MOBILE_IP_CHANGE_WAIT_SECONDS", "20"))
    IMPERSONATE_LIST = ["chrome136", "chrome131", "chrome124", "chrome120", "edge"]

    def __init__(self, db_name: str = "users.db"):
        self.db = Database(db_name)
        self.db_name = self.db.db_name
        self._ensure_schema()
        token = os.getenv("SPFA_TOKEN", "").strip()
        self.api_client = SpfaApiClient(token) if token else None
        self._add_env_proxy()
        self._ensure_channels_for_active_proxies()
        self._sync_channel_status_for_proxy_activity()

    def acquire_channel(self) -> Optional[ParserChannel]:
        """Returns the least recently used channel that is not cooling down."""
        self._ensure_channels_for_active_proxies()
        min_reuse_time = (datetime.now() - timedelta(seconds=self.MIN_CHANNEL_REUSE_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pc.id, pc.proxy_string, pc.spfa_id, pc.cookies_json, pc.user_agent,
                       pc.fail_count, pc.success_count, pc.last_unblock_time, pc.last_error,
                       pc.status_history_json, pc.unblock_started_at, pc.last_purchase_at,
                       pc.impersonate, COALESCE(mp.proxy_type, 'server'), COALESCE(mp.change_ip_url, ''),
                       COALESCE(mp.last_ip_change, 0)
                FROM parser_channels pc
                JOIN mobile_proxies mp ON mp.proxy_string = pc.proxy_string
                WHERE mp.is_active = TRUE
                  AND pc.status != 'disabled'
                  AND (pc.cooldown_until IS NULL OR pc.cooldown_until <= ?)
                  AND (pc.last_used IS NULL OR pc.last_used <= ?)
                ORDER BY pc.fail_count ASC, pc.success_count DESC, pc.last_used IS NOT NULL, pc.last_used ASC
                LIMIT 1
            ''', (datetime.now().isoformat(), min_reuse_time))
            row = cursor.fetchone()

        if not row:
            logger.warning("Нет доступных каналов: все прокси в cooldown или пул пуст.")
            return None

        channel = self._row_to_channel(row)
        if not channel.impersonate:
            self.assign_impersonate(channel)
            channel = self.get_channel(channel.id)

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
                SELECT pc.id, pc.proxy_string, pc.spfa_id, pc.cookies_json, pc.user_agent,
                       pc.fail_count, pc.success_count, pc.last_unblock_time, pc.last_error,
                       pc.status_history_json, pc.unblock_started_at, pc.last_purchase_at,
                       pc.impersonate, COALESCE(mp.proxy_type, 'server'), COALESCE(mp.change_ip_url, ''),
                       COALESCE(mp.last_ip_change, 0)
                FROM parser_channels pc
                LEFT JOIN mobile_proxies mp ON mp.proxy_string = pc.proxy_string
                WHERE pc.id = ?
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
                    status_history_json = ?,
                    unblock_started_at = NULL,
                    cooldown_until = NULL,
                    last_used = CURRENT_TIMESTAMP,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (self._status_history_json(channel, 200), channel.id))
            conn.commit()

    def update_cookies(self, channel: ParserChannel, response_cookies: dict):
        if not response_cookies:
            return

        merged = dict(channel.cookies or {})
        merged.update(response_cookies)
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET cookies_json = ?, updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (json.dumps(merged, ensure_ascii=False), channel.id))
            conn.commit()

    def assign_impersonate(self, channel: ParserChannel):
        impersonate = random.choice(self.IMPERSONATE_LIST)
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET impersonate = ?, updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (impersonate, channel.id))
            conn.commit()

    def cooldown_channel(self, channel: ParserChannel, reason: str, minutes: int = 15):
        status_code = self._status_code_from_reason(reason)
        minutes = self._cooldown_minutes(reason, channel.fail_count + 1, default_minutes=minutes)
        cooldown_until = datetime.now() + timedelta(minutes=minutes)
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET status = 'cooldown',
                    cooldown_until = ?,
                    fail_count = fail_count + 1,
                    last_error = ?,
                    status_history_json = ?,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (cooldown_until.isoformat(), reason, self._status_history_json(channel, status_code), channel.id))
            conn.commit()
        logger.warning(f"Канал #{channel.id} поставлен в cooldown до {cooldown_until:%H:%M:%S}: {reason}")

    def handle_rate_limit(self, channel: ParserChannel) -> bool:
        """Handles repeated 429 without changing IP first."""
        if not self.api_client or not channel.spfa_id:
            return False

        if self._start_unblock(channel):
            return True

        return self.refresh_cookies(channel)

    def handle_block(self, channel: ParserChannel, reason: str) -> bool:
        """Tries cheap recovery for a blocked channel before cooldown."""
        if channel.proxy_type == "mobile" and channel.change_ip_url:
            if self._change_mobile_ip(channel, reason):
                if self.api_client and channel.spfa_id:
                    self._start_unblock(channel)
                return True

        if "429" in reason:
            return self.handle_rate_limit(channel)

        return False

    def refresh_cookies(self, channel: ParserChannel) -> bool:
        if not self.api_client:
            return False

        if channel.spfa_id and channel.last_purchase_at and time.time() - channel.last_purchase_at < self.PURCHASE_COOLDOWN:
            logger.info(
                f"Канал #{channel.id}: cookies куплены менее 10 минут назад, не покупаем новые, пробуем unblock."
            )
            return self._start_unblock(channel)

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
                    unblock_started_at = NULL,
                    last_purchase_at = ?,
                    status_history_json = '[]',
                    status = 'ready',
                    cooldown_until = NULL,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (cookie_id, json.dumps(cookies, ensure_ascii=False), user_agent or "", time.time(), channel.id))
            conn.commit()
        logger.info(f"Канал #{channel.id}: получены новые cookies #{cookie_id}.")
        return True

    def _ensure_schema(self):
        columns = {
            "impersonate": "TEXT",
            "status_history_json": "TEXT",
            "unblock_started_at": "REAL",
            "last_purchase_at": "REAL",
        }
        with sqlite3.connect(self.db_name) as conn:
            existing = {row[1] for row in conn.execute("PRAGMA table_info(parser_channels)").fetchall()}
            for name, column_type in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE parser_channels ADD COLUMN {name} {column_type}")
            conn.commit()

    def _ensure_channels_for_active_proxies(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO parser_channels (proxy_string)
                SELECT proxy_string FROM mobile_proxies WHERE is_active = TRUE
            ''')
            conn.commit()

    def _sync_channel_status_for_proxy_activity(self):
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET status = 'disabled', updated_date = CURRENT_TIMESTAMP
                WHERE proxy_string IN (
                    SELECT proxy_string FROM mobile_proxies WHERE is_active = FALSE
                )
            ''')
            conn.execute('''
                UPDATE parser_channels
                SET status = 'ready', updated_date = CURRENT_TIMESTAMP
                WHERE status = 'disabled'
                  AND proxy_string IN (
                    SELECT proxy_string FROM mobile_proxies WHERE is_active = TRUE
                  )
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

        status_history = []
        if row[9]:
            try:
                status_history = json.loads(row[9])
            except json.JSONDecodeError:
                status_history = []

        return ParserChannel(
            id=row[0],
            proxy_string=row[1],
            formatted_proxy=self._format_proxy(row[1]),
            spfa_id=row[2],
            cookies=cookies,
            user_agent=row[4],
            impersonate=row[12],
            fail_count=row[5] or 0,
            success_count=row[6] or 0,
            last_unblock_time=row[7] or 0,
            last_error=row[8],
            status_history=status_history,
            unblock_started_at=row[10],
            last_purchase_at=row[11],
            proxy_type=row[13] or "server",
            change_ip_url=row[14] or "",
            last_ip_change=row[15] or 0,
        )

    def _change_mobile_ip(self, channel: ParserChannel, reason: str) -> bool:
        now = time.time()
        elapsed = now - (channel.last_ip_change or 0)
        if elapsed < self.MOBILE_IP_CHANGE_COOLDOWN_SECONDS:
            logger.info(
                f"Канал #{channel.id}: смена IP запускалась недавно, прошло {int(elapsed)}с."
            )
            time.sleep(self.MOBILE_IP_CHANGE_WAIT_SECONDS)
            return True

        logger.warning(f"Канал #{channel.id}: mobile proxy получил блок ({reason}), меняем IP.")
        try:
            request = urllib.request.Request(channel.change_ip_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                status_code = response.getcode()
                if status_code >= 400:
                    logger.warning(f"Канал #{channel.id}: change_ip_url вернул HTTP {status_code}.")
                    return False
        except (urllib.error.URLError, TimeoutError, ValueError) as err:
            logger.warning(f"Канал #{channel.id}: не удалось сменить IP mobile proxy: {err}")
            return False

        self.db.mark_mobile_ip_changed(channel.proxy_string, now)
        time.sleep(self.MOBILE_IP_CHANGE_WAIT_SECONDS)
        return True

    def _unblock_before_reuse(self, channel: ParserChannel) -> bool:
        """Runs free SPFA unblock before retrying a channel that previously hit 403."""
        if not self.api_client or not channel.spfa_id or not channel.last_error:
            return False
        if "403" not in channel.last_error:
            return False
        if time.time() - channel.last_unblock_time <= 60:
            return False

        return self._start_unblock(channel)

    def _start_unblock(self, channel: ParserChannel) -> bool:
        if not self.api_client or not channel.spfa_id:
            return False

        now = time.time()
        if channel.unblock_started_at:
            elapsed = now - channel.unblock_started_at
            if elapsed < self.UNBLOCK_TIMEOUT:
                logger.info(f"Канал #{channel.id}: unblock уже выполняется, прошло {int(elapsed)}с.")
                time.sleep(self.WAIT_FOR_UNBLOCK)
                return True

        if now - channel.last_unblock_time <= 60:
            logger.info(f"Канал #{channel.id}: unblock запускался недавно, ждём.")
            time.sleep(self.WAIT_FOR_UNBLOCK)
            return True

        logger.info(f"Канал #{channel.id}: запускаем free unblock cookies #{channel.spfa_id}.")
        if not self.api_client.unblock_session(channel.spfa_id):
            return False

        time.sleep(self.WAIT_FIRST_FOR_UNBLOCK)
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE parser_channels
                SET last_unblock_time = ?,
                    unblock_started_at = ?,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (now, now, channel.id))
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

    def _status_history_json(self, channel: ParserChannel, status_code: int | None) -> str:
        history = list(channel.status_history or [])
        if status_code:
            history.append(status_code)
        return json.dumps(history[-self.MAX_STATUS_HISTORY:])

    @staticmethod
    def _status_code_from_reason(reason: str) -> int | None:
        if "403" in reason:
            return 403
        if "429" in reason:
            return 429
        if "401" in reason:
            return 401
        return None

    @staticmethod
    def _format_proxy(proxy_string: str) -> str:
        if proxy_string.startswith(("http://", "https://", "socks4://", "socks5://", "socks5h://")):
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
