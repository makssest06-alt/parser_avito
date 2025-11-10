import sqlite3
from datetime import datetime, timedelta
from typing import Optional

class Database:
    def __init__(self, db_name="users.db"):
        self.db_name = db_name
        self._create_tables()

    def _create_tables(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
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
            
            # Таблица подписок
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
            
            # Таблица платежей
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
            
            # Таблица ссылок пользователей
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
            
            # Таблица настроек парсера для пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS parser_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
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
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица найденных объявлений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS found_ads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    ad_id INTEGER,
                    ad_data TEXT,
                    found_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            conn.commit()

    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()

    def get_user_subscription(self, user_id: int) -> Optional[dict]:
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT subscription_type, start_date, end_date, is_active
                FROM subscriptions 
                WHERE user_id = ? AND is_active = TRUE AND end_date > ?
                ORDER BY end_date DESC LIMIT 1
            ''', (user_id, datetime.now()))
            
            result = cursor.fetchone()
            if result:
                return {
                    'type': result[0],
                    'start_date': result[1],
                    'end_date': result[2],
                    'is_active': result[3]
                }
            return None

    def add_subscription(self, user_id: int, subscription_type: str, duration_days: int):
        start_date = datetime.now()
        end_date = start_date + timedelta(days=duration_days)
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # Деактивируем старые подписки
            cursor.execute('''
                UPDATE subscriptions SET is_active = FALSE WHERE user_id = ?
            ''', (user_id,))
            
            # Добавляем новую подписку
            cursor.execute('''
                INSERT INTO subscriptions (user_id, subscription_type, start_date, end_date)
                VALUES (?, ?, ?, ?)
            ''', (user_id, subscription_type, start_date, end_date))
            conn.commit()

    def add_payment(self, user_id: int, amount: float, payment_system: str, payment_id: str, status: str = 'pending'):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payments (user_id, amount, payment_system, payment_id, status)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, amount, payment_system, payment_id, status))
            conn.commit()

    def add_user_link(self, user_id: int, avito_link: str):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_links (user_id, avito_link)
                VALUES (?, ?)
            ''', (user_id, avito_link))
            conn.commit()

    def get_user_links(self, user_id: int) -> list:
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
        subscription = self.get_user_subscription(user_id)
        return subscription is not None

    def get_parser_settings(self, user_id: int) -> Optional[dict]:
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
            if result:
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
                    'tg_notifications': bool(result[10])
                }
            return None

    def update_parser_settings(self, user_id: int, settings: dict):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            # Удаляем старые настройки
            cursor.execute('DELETE FROM parser_settings WHERE user_id = ?', (user_id,))
            
            # Добавляем новые настройки
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
                settings.get('tg_notifications', True)
            ))
            conn.commit()

    def add_found_ad(self, user_id: int, ad_id: int, ad_data: str):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO found_ads (user_id, ad_id, ad_data)
                VALUES (?, ?, ?)
            ''', (user_id, ad_id, ad_data))
            conn.commit()

    def is_ad_found(self, user_id: int, ad_id: int) -> bool:
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 1 FROM found_ads WHERE user_id = ? AND ad_id = ?
            ''', (user_id, ad_id))
            return cursor.fetchone() is not None
