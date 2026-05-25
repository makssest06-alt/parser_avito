import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional, Tuple


logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name: str = "users.db"):
        self.db_name = db_name
        self._create_tables()

    def _create_tables(self):
        """Создает все необходимые таблицы в базе данных."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    subscription_type TEXT,
                    start_date TIMESTAMP,
                    end_date TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    currency TEXT DEFAULT 'RUB',
                    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    payment_system TEXT,
                    payment_id TEXT UNIQUE,
                    status TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    avito_link TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS parser_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    min_price INTEGER DEFAULT 0,
                    max_price INTEGER DEFAULT 999999999,
                    keys_word_white_list TEXT,
                    keys_word_black_list TEXT,
                    seller_black_list TEXT,
                    geo TEXT,
                    max_age INTEGER DEFAULT 86400,
                    ignore_reserv BOOLEAN DEFAULT TRUE,
                    ignore_promotion BOOLEAN DEFAULT FALSE,
                    parse_views BOOLEAN DEFAULT FALSE,
                    tg_notifications BOOLEAN DEFAULT TRUE,
                    proxy_string TEXT DEFAULT '',
                    proxy_change_url TEXT DEFAULT '',
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS found_ads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    ad_id INTEGER,
                    ad_data TEXT,
                    found_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    UNIQUE(user_id, ad_id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS viewed (
                    id INTEGER,
                    price INTEGER,
                    PRIMARY KEY (id, price)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mobile_proxies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proxy_string TEXT UNIQUE,
                    proxy_type TEXT DEFAULT 'server',
                    change_ip_url TEXT DEFAULT '',
                    is_active BOOLEAN DEFAULT TRUE,
                    last_used TIMESTAMP,
                    last_ip_change REAL DEFAULT 0,
                    ip_change_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    last_fail_reason TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self._ensure_columns(cursor, 'mobile_proxies', {
                'proxy_type': "TEXT DEFAULT 'server'",
                'change_ip_url': "TEXT DEFAULT ''",
                'last_ip_change': 'REAL DEFAULT 0',
                'ip_change_count': 'INTEGER DEFAULT 0',
            })
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS parser_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proxy_string TEXT UNIQUE,
                    spfa_id INTEGER,
                    cookies_json TEXT,
                    cookie_status TEXT DEFAULT 'unknown',
                    cookie_error TEXT,
                    user_agent TEXT,
                    impersonate TEXT,
                    status TEXT DEFAULT 'ready',
                    cooldown_until TIMESTAMP,
                    fail_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    last_error TEXT,
                    status_history_json TEXT,
                    last_unblock_time REAL DEFAULT 0,
                    unblock_started_at REAL,
                    last_purchase_at REAL,
                    last_cookie_clear_at REAL,
                    last_warmup_at REAL DEFAULT 0,
                    next_available_at TIMESTAMP,
                    last_used TIMESTAMP,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self._ensure_columns(cursor, 'parser_channels', {
                'impersonate': 'TEXT',
                'cookie_status': "TEXT DEFAULT 'unknown'",
                'cookie_error': 'TEXT',
                'status_history_json': 'TEXT',
                'unblock_started_at': 'REAL',
                'last_purchase_at': 'REAL',
                'last_cookie_clear_at': 'REAL',
                'last_warmup_at': 'REAL DEFAULT 0',
                'next_available_at': 'TIMESTAMP',
            })
            conn.commit()

    @staticmethod
    def _ensure_columns(cursor, table_name: str, columns: dict):
        existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
        for column_name, column_type in columns.items():
            if column_name not in existing:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Добавляет или обновляет пользователя."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()

    def get_user_subscription(self, user_id: int) -> Optional[dict]:
        """Получает последнюю подписку пользователя и вычисляет ее текущий статус."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT subscription_type, start_date, end_date, is_active
                FROM subscriptions
                WHERE user_id = ?
                ORDER BY end_date DESC LIMIT 1
            ''', (user_id,))
            result = cursor.fetchone()

        if not result:
            return None

        subscription_type, start_date, end_date, is_active = result
        if isinstance(end_date, str):
            end_datetime = datetime.fromisoformat(end_date)
        else:
            end_datetime = datetime.fromtimestamp(end_date)

        return {
            'type': subscription_type,
            'start_date': start_date,
            'end_date': end_date,
            'is_active': bool(is_active) and datetime.now() < end_datetime,
        }

    def add_subscription(self, user_id: int, subscription_type: str, duration_days: int):
        """Добавляет новую подписку и деактивирует предыдущие."""
        start_date = datetime.now()
        end_date = start_date + timedelta(days=duration_days)

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE subscriptions SET is_active = FALSE WHERE user_id = ?', (user_id,))
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subscription_type, start_date, end_date, is_active)
                VALUES (?, ?, ?, ?, TRUE)
            ''', (user_id, subscription_type, start_date.isoformat(), end_date.isoformat()))
            conn.commit()

    def add_payment(self, user_id: int, amount: float, payment_system: str, payment_id: str, status: str = 'pending'):
        """Добавляет или обновляет запись о платеже."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO payments (user_id, amount, payment_system, payment_id, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, amount, payment_system, payment_id, status))
            conn.commit()

    def add_user_link(self, user_id: int, avito_link: str):
        """Добавляет ссылку для мониторинга."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_links (user_id, avito_link)
                VALUES (?, ?)
            ''', (user_id, avito_link))
            conn.commit()

    def get_user_links(self, user_id: int) -> List[Tuple[str, str]]:
        """Получает все активные ссылки пользователя."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT avito_link, created_date
                FROM user_links
                WHERE user_id = ? AND is_active = TRUE
                ORDER BY created_date DESC
            ''', (user_id,))
            return cursor.fetchall()

    def is_user_active(self, user_id: int) -> bool:
        """Проверяет наличие активной подписки."""
        subscription = self.get_user_subscription(user_id)
        return bool(subscription and subscription['is_active'])

    def get_parser_settings(self, user_id: int) -> Optional[dict]:
        """Получает настройки парсера пользователя."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT min_price, max_price, keys_word_white_list, keys_word_black_list,
                       seller_black_list, geo, max_age, ignore_reserv, ignore_promotion,
                       parse_views, tg_notifications
                FROM parser_settings
                WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()

        if not result:
            return None

        return {
            'min_price': result[0],
            'max_price': result[1],
            'keys_word_white_list': result[2].split('\n') if result[2] else [],
            'keys_word_black_list': result[3].split('\n') if result[3] else [],
            'seller_black_list': result[4].split('\n') if result[4] else [],
            'geo': result[5],
            'max_age': result[6],
            'ignore_reserv': bool(result[7]),
            'ignore_promotion': bool(result[8]),
            'parse_views': bool(result[9]),
            'tg_notifications': bool(result[10]),
            'proxy_string': '',
            'proxy_change_url': '',
        }

    def update_parser_settings(self, user_id: int, settings: dict):
        """Обновляет настройки парсера пользователя."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM parser_settings WHERE user_id = ?', (user_id,))
            cursor.execute('''
                INSERT INTO parser_settings
                (user_id, min_price, max_price, keys_word_white_list, keys_word_black_list,
                 seller_black_list, geo, max_age, ignore_reserv, ignore_promotion, parse_views, tg_notifications)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                settings.get('min_price', 0),
                settings.get('max_price', 999999999),
                '\n'.join(settings.get('keys_word_white_list', [])),
                '\n'.join(settings.get('keys_word_black_list', [])),
                '\n'.join(settings.get('seller_black_list', [])),
                settings.get('geo', ''),
                settings.get('max_age', 86400),
                settings.get('ignore_reserv', True),
                settings.get('ignore_promotion', False),
                settings.get('parse_views', False),
                settings.get('tg_notifications', True),
            ))
            conn.commit()

    def add_found_ad(self, user_id: int, ad_id: int, ad_data: str):
        """Добавляет найденное объявление."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO found_ads (user_id, ad_id, ad_data)
                VALUES (?, ?, ?)
            ''', (user_id, ad_id, ad_data))
            conn.commit()

    def is_ad_found(self, user_id: int, ad_id: int) -> bool:
        """Проверяет, было ли объявление уже найдено."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM found_ads WHERE user_id = ? AND ad_id = ?', (user_id, ad_id))
            return cursor.fetchone() is not None

    def add_record(self, ad):
        """Добавляет запись в таблицу просмотренных объявлений."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO viewed (id, price) VALUES (?, ?)",
                (ad.id, ad.priceDetailed.value),
            )
            conn.commit()

    def add_record_from_page(self, ads: list):
        """Добавляет несколько просмотренных объявлений."""
        records = [(ad.id, ad.priceDetailed.value) for ad in ads]
        if not records:
            return

        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.executemany("INSERT OR IGNORE INTO viewed (id, price) VALUES (?, ?)", records)
            conn.commit()

    def record_exists(self, record_id: int, price: int) -> bool:
        """Проверяет существование просмотренного объявления."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM viewed WHERE id = ? AND price = ?", (record_id, price))
            return cursor.fetchone() is not None

    def add_mobile_proxy(self, proxy_string: str, proxy_type: str = 'server', change_ip_url: str = ''):
        """Добавляет proxy в пул."""
        proxy_type = proxy_type if proxy_type in {'server', 'mobile'} else 'server'
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mobile_proxies (proxy_string, proxy_type, change_ip_url, is_active)
                VALUES (?, ?, ?, TRUE)
                ON CONFLICT(proxy_string) DO UPDATE SET
                    proxy_type = excluded.proxy_type,
                    change_ip_url = excluded.change_ip_url,
                    is_active = TRUE,
                    last_fail_reason = NULL
            ''', (proxy_string, proxy_type, change_ip_url))
            conn.commit()

    def get_random_active_proxy(self) -> Optional[str]:
        """Получает случайный активный прокси."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT proxy_string FROM mobile_proxies
                WHERE is_active = TRUE
                ORDER BY RANDOM()
                LIMIT 1
            ''')
            result = cursor.fetchone()
            return result[0] if result else None

    def update_proxy_stats(self, proxy_string: str, success: bool, fail_reason: str = None):
        """Обновляет статистику использования прокси."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            if success:
                cursor.execute('''
                    UPDATE mobile_proxies
                    SET success_count = success_count + 1,
                        last_used = CURRENT_TIMESTAMP
                    WHERE proxy_string = ?
                ''', (proxy_string,))
            else:
                cursor.execute('''
                    UPDATE mobile_proxies
                    SET fail_count = fail_count + 1,
                        last_fail_reason = ?,
                        last_used = CURRENT_TIMESTAMP
                    WHERE proxy_string = ?
                ''', (fail_reason, proxy_string))
            conn.commit()

    def disable_proxy(self, proxy_string: str, reason: str):
        """Отключает прокси."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE mobile_proxies
                SET is_active = FALSE,
                    last_fail_reason = ?
                WHERE proxy_string = ?
            ''', (reason, proxy_string))
            conn.commit()

    def get_all_proxies(self) -> List[Tuple]:
        """Получает все прокси."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, proxy_string, is_active, success_count, fail_count, last_fail_reason,
                       proxy_type, change_ip_url, last_ip_change, ip_change_count
                FROM mobile_proxies
                ORDER BY created_date
            ''')
            return cursor.fetchall()

    def enable_proxy(self, proxy_identifier: str):
        """Активирует proxy по ID или полной строке и сбрасывает статус channel."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            proxy_string = self._get_proxy_string(cursor, proxy_identifier)
            if not proxy_string:
                raise ValueError(f"Proxy `{proxy_identifier}` не найден")

            cursor.execute('''
                UPDATE mobile_proxies
                SET is_active = TRUE,
                    last_fail_reason = NULL
                WHERE proxy_string = ?
            ''', (proxy_string,))
            cursor.execute('''
                UPDATE parser_channels
                SET status = 'ready',
                    cooldown_until = NULL,
                    next_available_at = NULL,
                    last_error = NULL,
                    updated_date = CURRENT_TIMESTAMP
                WHERE proxy_string = ?
            ''', (proxy_string,))
            conn.commit()

    def delete_proxy(self, proxy_identifier: str):
        """Удаляет proxy по ID или полной строке вместе с parser channel."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            proxy_string = self._get_proxy_string(cursor, proxy_identifier)
            if not proxy_string:
                raise ValueError(f"Proxy `{proxy_identifier}` не найден")

            cursor.execute('DELETE FROM parser_channels WHERE proxy_string = ?', (proxy_string,))
            cursor.execute('DELETE FROM mobile_proxies WHERE proxy_string = ?', (proxy_string,))
            conn.commit()

    @staticmethod
    def _get_proxy_string(cursor, proxy_identifier: str) -> str | None:
        identifier = str(proxy_identifier).strip()
        if identifier.isdigit():
            cursor.execute('SELECT proxy_string FROM mobile_proxies WHERE id = ?', (int(identifier),))
        else:
            cursor.execute('SELECT proxy_string FROM mobile_proxies WHERE proxy_string = ?', (identifier,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_all_parser_channels(self) -> List[Tuple]:
        """Получает все parser channels для диагностики."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pc.id, pc.proxy_string, pc.spfa_id, pc.impersonate, pc.status, pc.cooldown_until,
                       pc.success_count, pc.fail_count, pc.last_error, pc.updated_date,
                       COALESCE(mp.proxy_type, 'server'), COALESCE(mp.change_ip_url, ''),
                       COALESCE(mp.last_ip_change, 0), COALESCE(mp.ip_change_count, 0),
                       COALESCE(pc.cookie_status, 'unknown'), pc.last_purchase_at, pc.last_warmup_at,
                       pc.next_available_at, pc.status_history_json
                FROM parser_channels pc
                LEFT JOIN mobile_proxies mp ON mp.proxy_string = pc.proxy_string
                ORDER BY pc.id
            ''')
            return cursor.fetchall()

    def clear_parser_channel_cookies(self, channel_id: int, reason: str = 'Cookies cleared'):
        """Очищает cookies/SPFA привязку channel без отключения proxy."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM parser_channels WHERE id = ?', (channel_id,))
            if not cursor.fetchone():
                raise ValueError(f"Parser channel #{channel_id} не найден")

            cursor.execute('''
                UPDATE parser_channels
                SET spfa_id = NULL,
                    cookies_json = NULL,
                    user_agent = NULL,
                    cookie_status = 'cleared',
                    cookie_error = ?,
                    last_purchase_at = NULL,
                    last_cookie_clear_at = strftime('%s','now'),
                    last_warmup_at = 0,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (reason, channel_id))
            conn.commit()

    def mark_mobile_ip_changed(self, proxy_string: str, changed_at: float):
        """Фиксирует успешную смену IP для mobile proxy."""
        with sqlite3.connect(self.db_name) as conn:
            conn.execute('''
                UPDATE mobile_proxies
                SET last_ip_change = ?,
                    ip_change_count = ip_change_count + 1,
                    last_used = CURRENT_TIMESTAMP
                WHERE proxy_string = ?
            ''', (changed_at, proxy_string))
            conn.commit()

    def reset_parser_channel(self, channel_id: int):
        """Сбрасывает cooldown и ошибки parser channel, а связанный proxy делает активным."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT proxy_string FROM parser_channels WHERE id = ?', (channel_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Parser channel #{channel_id} не найден")

            proxy_string = row[0]
            cursor.execute('''
                UPDATE mobile_proxies
                SET is_active = TRUE, last_fail_reason = NULL
                WHERE proxy_string = ?
            ''', (proxy_string,))
            cursor.execute('''
                UPDATE parser_channels
                SET status = 'ready',
                    cooldown_until = NULL,
                    next_available_at = NULL,
                    fail_count = 0,
                    last_error = NULL,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (channel_id,))
            conn.commit()

    def disable_parser_channel(self, channel_id: int, reason: str = 'Disabled by admin'):
        """Отключает parser channel и связанный proxy."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT proxy_string FROM parser_channels WHERE id = ?', (channel_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Parser channel #{channel_id} не найден")

            proxy_string = row[0]
            cursor.execute('''
                UPDATE mobile_proxies
                SET is_active = FALSE, last_fail_reason = ?
                WHERE proxy_string = ?
            ''', (reason, proxy_string))
            cursor.execute('''
                UPDATE parser_channels
                SET status = 'disabled',
                    last_error = ?,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (reason, channel_id))
            conn.commit()

    def enable_parser_channel(self, channel_id: int):
        """Включает parser channel и связанный proxy без удаления статистики."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT proxy_string FROM parser_channels WHERE id = ?', (channel_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Parser channel #{channel_id} не найден")

            proxy_string = row[0]
            cursor.execute('''
                UPDATE mobile_proxies
                SET is_active = TRUE,
                    last_fail_reason = NULL
                WHERE proxy_string = ?
            ''', (proxy_string,))
            cursor.execute('''
                UPDATE parser_channels
                SET status = 'ready',
                    cooldown_until = NULL,
                    next_available_at = NULL,
                    last_error = NULL,
                    updated_date = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (channel_id,))
            conn.commit()

    def delete_parser_channel(self, channel_id: int, delete_proxy: bool = True):
        """Удаляет parser channel; по умолчанию удаляет и связанный proxy."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT proxy_string FROM parser_channels WHERE id = ?', (channel_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Parser channel #{channel_id} не найден")

            proxy_string = row[0]
            cursor.execute('DELETE FROM parser_channels WHERE id = ?', (channel_id,))
            if delete_proxy:
                cursor.execute('DELETE FROM mobile_proxies WHERE proxy_string = ?', (proxy_string,))
            conn.commit()

    def get_all_users(self) -> List[Tuple]:
        """Получает всех пользователей для администратора."""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.user_id, u.username, u.first_name, u.last_name,
                       u.registration_date, u.is_active,
                       s.subscription_type, s.end_date,
                       COUNT(ul.avito_link) as links_count
                FROM users u
                LEFT JOIN subscriptions s ON u.user_id = s.user_id AND s.is_active = TRUE
                LEFT JOIN user_links ul ON u.user_id = ul.user_id AND ul.is_active = TRUE
                GROUP BY u.user_id
                ORDER BY u.registration_date DESC
            ''')
            return cursor.fetchall()

    def get_all_active_links_with_users(self) -> dict:
        """Возвращает словарь {url: [user_id_1, user_id_2]}"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ul.avito_link, ul.user_id 
                FROM user_links ul
                JOIN subscriptions s ON ul.user_id = s.user_id
                WHERE ul.is_active = TRUE 
                AND s.is_active = TRUE 
                AND s.end_date > ?
            ''', (datetime.now(),))
            
            result = {}
            for link, user_id in cursor.fetchall():
                if link not in result:
                    result[link] = []
                if user_id not in result[link]:
                    result[link].append(user_id)
            return result
