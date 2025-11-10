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
