import logging
import telebot
import sqlite3
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_IDS
from database import Database
from payment_service import payment_service
from dto import AvitoConfig
from parser_cls import AvitoParse
from models import Item
from parser_service import UserTgHandler
import threading
import time

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем экземпляр бота и базы данных
bot = telebot.TeleBot(BOT_TOKEN)
db = Database()

# Тарифы
SUBSCRIPTION_PLANS = {
    "basic": {"name": "Базовый", "price": 10, "days": 30, "links_limit": 5},
    "premium": {"name": "Премиум", "price": 599, "days": 30, "links_limit": 20},
    "vip": {"name": "VIP", "price": 999, "days": 30, "links_limit": 100}
}

# Словарь для отслеживания ожидающих платежей
pending_payments = {}

# Импортируем сервис парсера
from parser_service import ParserService

# Создаем экземпляр сервиса парсера
parser_service = ParserService()

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    # Добавляем пользователя в базу
    db.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    if user_id in ADMIN_IDS:
        # Создаем клавиатуру выбора режима для администратора
        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('Админ', 'Пользователь')
        bot.send_message(
            message.chat.id,
            "Привет, администратор! Выберите режим работы:",
            reply_markup=markup
        )
    else:
        # Проверяем подписку пользователя
        subscription = db.get_user_subscription(user_id)
        if subscription:
            # Пользователь с активной подпиской
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add('Добавить ссылку', 'Мои ссылки', 'Тест парсера', 'Настройки парсера', 'Моя подписка')
            bot.send_message(
                message.chat.id,
                f"Привет! Твоя подписка активна до {subscription['end_date'][:10]}\n"
                "Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
                reply_markup=markup
            )
        else:
            # Пользователь без подписки
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add('Купить подписку', 'Тест парсера', 'Информация')
            bot.send_message(
                message.chat.id,
                "Привет! Я парсер Авито. Для использования бота нужна подписка.\n"
                "Но ты можешь протестировать парсер прямо сейчас!\n"
                "Выбери тариф и начни получать новые объявления первым!",
                reply_markup=markup
            )

# Обработчик команды /get_id
@bot.message_handler(commands=['get_id'])
def get_user_id(message):
    user_id = message.from_user.id
    bot.reply_to(message, f"Ваш ID: {user_id}")

# Обработчик команды /admin
@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        bot.reply_to(message, "Это команда только для администраторов!")
    else:
        bot.reply_to(message, "У вас нет прав для выполнения этой команды.")

# Обработчик команды /help
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message, "Это помощь для всех пользователей!")

# Обработчик текстовых сообщений (кнопки)
@bot.message_handler(commands=['add_proxy'])
def add_proxy_command(message):
    """Обработчик команды для добавления мобильного прокси (только для админов)"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Эта команда только для администраторов!")
        return
    
    # Получаем текст после команды
    command_parts = message.text.split(' ', 1)
    if len(command_parts) < 2:
        bot.reply_to(message, 
                    "❌ Использование: /add_proxy [прокси]\n\n"
                    "Формат: login:password@host:port\n"
                    "Для SOCKS можно указать схему: socks5://login:password@host:port\n\n"
                    "Пример:\n"
                    "/add_proxy login:password@proxy.example.com:12345")
        return
    
    proxy_string = command_parts[1].strip()
    
    # Валидация формата прокси
    if '@' not in proxy_string or proxy_string.count(':') < 2:
        bot.reply_to(message, 
                    "❌ Неверный формат прокси!\n\n"
                    "Правильный формат:\n"
                    "login:password@host:port\n"
                    "или socks5://login:password@host:port\n\n"
                    "Пример:\n"
                    "login:password@proxy.example.com:12345")
        return
    
    try:
        from mobile_proxy_manager import proxy_manager
        proxy_manager.add_proxy(proxy_string)
        bot.reply_to(message, f"✅ Мобильный прокси успешно добавлен!")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при добавлении прокси: {str(e)}")

@bot.message_handler(commands=['proxy_status'])
def proxy_status_command(message):
    """Показывает статус мобильных прокси (только для админов)"""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Эта команда только для администраторов!")
        return
    
    try:
        from mobile_proxy_manager import proxy_manager
        proxies = proxy_manager.get_proxy_status()
        
        if not proxies:
            bot.reply_to(message, "📊 Нет мобильных прокси в базе")
            return
        
        status_text = "📊 *Статус мобильных прокси:*\n\n"
        
        for proxy in proxies:
            proxy_string, is_active, success_count, fail_count, last_fail_reason = proxy
            proxy_masked = _mask_proxy_for_display(proxy_string)
            status = "✅ Активен" if is_active else "❌ Отключен"
            status_text += (
                f"• `{proxy_masked}`\n"
                f"  Статус: {status}\n"
                f"  Успешно: {success_count}, Ошибок: {fail_count}\n"
            )
            if last_fail_reason:
                status_text += f"  Последняя ошибка: {last_fail_reason}\n"
            status_text += "\n"
        
        bot.reply_to(message, status_text, parse_mode='Markdown')
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при получении статуса прокси: {str(e)}")

@bot.message_handler(commands=['channels_status'])
def channels_status_command(message):
    """Показывает состояние parser channels (только для админов)."""
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Эта команда только для администраторов!")
        return

    try:
        from parser.channels.manager import ChannelManager

        # Ensure channels exist for active proxies before showing status.
        ChannelManager()
        channels = db.get_all_parser_channels()
        if not channels:
            bot.reply_to(message, "📊 Parser channels отсутствуют. Добавьте прокси через /add_proxy.")
            return

        status_text = "📊 *Parser channels:*\n\n"
        for channel in channels:
            channel_id, proxy_string, spfa_id, impersonate, status, cooldown_until, success_count, fail_count, last_error, updated_date = channel
            proxy_masked = _mask_proxy_for_display(proxy_string)
            status_text += (
                f"#{channel_id} `{proxy_masked}`\n"
                f"Статус: `{status}` | SPFA ID: `{spfa_id or '-'}` | TLS: `{impersonate or '-'}`\n"
                f"Успешно: `{success_count}` | Ошибок: `{fail_count}`\n"
            )
            if cooldown_until:
                status_text += f"Cooldown до: `{cooldown_until}`\n"
            if last_error:
                status_text += f"Ошибка: `{last_error[:120]}`\n"
            status_text += f"Обновлен: `{updated_date}`\n\n"

        bot.reply_to(message, status_text, parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при получении статуса каналов: {str(e)}")

def _mask_proxy_for_display(proxy_string: str) -> str:
    if '@' not in proxy_string:
        return proxy_string
    credentials, host = proxy_string.split('@', 1)
    if ':' not in credentials:
        return f"***@{host}"
    login, _password = credentials.split(':', 1)
    return f"{login}:***@{host}"

@bot.message_handler(commands=['reset_channel'])
def reset_channel_command(message):
    """Сбрасывает cooldown канала по ID (только для админов)."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Эта команда только для администраторов!")
        return

    try:
        channel_id = int(message.text.split(maxsplit=1)[1])
        db.reset_parser_channel(channel_id)
        bot.reply_to(message, f"✅ Channel #{channel_id} сброшен и активирован.")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Использование: /reset_channel <id>")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка сброса channel: {str(e)}")

@bot.message_handler(commands=['disable_channel'])
def disable_channel_command(message):
    """Отключает канал по ID (только для админов)."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Эта команда только для администраторов!")
        return

    try:
        parts = message.text.split(maxsplit=2)
        channel_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "Disabled by admin"
        db.disable_parser_channel(channel_id, reason)
        bot.reply_to(message, f"✅ Channel #{channel_id} отключен.")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Использование: /disable_channel <id> [причина]")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка отключения channel: {str(e)}")

@bot.message_handler(commands=['test_channel'])
def test_channel_command(message):
    """Диагностика канала без изменения cooldown/status (только для админов)."""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Эта команда только для администраторов!")
        return

    try:
        channel_id = int(message.text.split(maxsplit=1)[1])
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Использование: /test_channel <id>")
        return

    try:
        report = _run_channel_diagnostic(channel_id)
        bot.reply_to(message, report)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка диагностики channel: {str(e)}")

def _run_channel_diagnostic(channel_id: int) -> str:
    from parser.channels.manager import ChannelManager
    from parser.http.client import AvitoHttpClient
    from parser.http.exceptions import BlockError, ProxyError, FetchError

    manager = ChannelManager()
    channel = manager.get_channel(channel_id)
    if not channel:
        return f"Channel #{channel_id} не найден."
    if not channel.impersonate:
        manager.assign_impersonate(channel)
        channel = manager.get_channel(channel_id)

    client = AvitoHttpClient(use_random_impersonate=False)
    checks = [
        ("ipinfo", "https://ipinfo.io/json", None),
        ("avito_home_no_cookies", "https://www.avito.ru", None),
        ("avito_category_no_cookies", "https://www.avito.ru/moskva/telefony/apple-ASgBAgICAUTkAwQ", None),
    ]
    if channel.cookies:
        checks.append(("avito_category_with_cookies", "https://www.avito.ru/moskva/telefony/apple-ASgBAgICAUTkAwQ", channel.cookies))

    lines = [
        f"Channel #{channel.id}: {_mask_proxy_for_display(channel.proxy_string)}",
        f"TLS: {channel.impersonate or '-'} | SPFA: {channel.spfa_id or '-'}",
    ]

    for name, url, cookies in checks:
        try:
            result = client.get_response(
                url=url,
                proxy=channel.formatted_proxy,
                cookies=cookies,
                user_agent=channel.user_agent,
                impersonate=channel.impersonate or "chrome136",
                retries=1,
                timeout=20,
            )
            marker = "catalog" if "catalog" in result.text else "no_catalog"
            lines.append(f"{name}: OK {result.status_code}, len={len(result.text)}, {marker}")
        except BlockError as err:
            lines.append(f"{name}: BLOCK {err.status_code or '-'} {str(err)[:120]}")
        except (ProxyError, FetchError) as err:
            lines.append(f"{name}: ERROR {str(err)[:120]}")

    return "\n".join(lines)

def _get_or_create_parser_settings(user_id: int) -> dict:
    settings = db.get_parser_settings(user_id)
    if settings:
        return settings

    settings = {
        'min_price': 0,
        'max_price': 999999999,
        'keys_word_white_list': [],
        'keys_word_black_list': [],
        'seller_black_list': [],
        'geo': '',
        'max_age': 86400,
        'ignore_reserv': True,
        'ignore_promotion': False,
        'parse_views': False,
        'tg_notifications': True,
    }
    db.update_parser_settings(user_id, settings)
    return settings

def _update_parser_setting(message, key: str, value):
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS and not db.is_user_active(user_id):
        bot.reply_to(message, "Для настройки парсера нужна активная подписка!")
        return

    settings = _get_or_create_parser_settings(user_id)
    settings[key] = value
    db.update_parser_settings(user_id, settings)
    bot.reply_to(message, "Настройка сохранена.")

def _get_command_argument(message, command: str) -> str:
    return message.text.replace(command, "", 1).strip()

@bot.message_handler(commands=['set_min_price'])
def set_min_price_command(message):
    try:
        value = int(_get_command_argument(message, '/set_min_price'))
        _update_parser_setting(message, 'min_price', value)
    except ValueError:
        bot.reply_to(message, "Использование: /set_min_price 1000")

@bot.message_handler(commands=['set_max_price'])
def set_max_price_command(message):
    try:
        value = int(_get_command_argument(message, '/set_max_price'))
        _update_parser_setting(message, 'max_price', value)
    except ValueError:
        bot.reply_to(message, "Использование: /set_max_price 50000")

@bot.message_handler(commands=['set_geo'])
def set_geo_command(message):
    value = _get_command_argument(message, '/set_geo')
    _update_parser_setting(message, 'geo', value)

@bot.message_handler(commands=['set_max_age'])
def set_max_age_command(message):
    try:
        value = int(_get_command_argument(message, '/set_max_age'))
        _update_parser_setting(message, 'max_age', value)
    except ValueError:
        bot.reply_to(message, "Использование: /set_max_age 86400")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text
    
    if user_id in ADMIN_IDS:
        # Обработка выбора режима администратором
        if text == 'Админ':
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
            markup.add('Статистика', 'Пользователи', 'Тест парсера', 'Вернуться к выбору режима')
            bot.send_message(
                message.chat.id,
                "Вы вошли в режим администратора",
                reply_markup=markup
            )
        elif text == 'Пользователь':
            # Админ в режиме пользователя
            subscription = db.get_user_subscription(user_id)
            if subscription:
                # Пользователь с активной подпиской
                markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                markup.add('Добавить ссылку', 'Мои ссылки', 'Тест парсера', 'Настройки парсера', 'Моя подписка', 'Вернуться к выбору режима')
                bot.send_message(
                    message.chat.id,
                    f"Привет! Твоя подписка активна до {subscription['end_date'][:10]}\n"
                    "Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
                    reply_markup=markup
                )
            else:
                # Пользователь без подписки
                markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                markup.add('Купить подписку', 'Тест парсера', 'Информация', 'Вернуться к выбору режима')
                bot.send_message(
                    message.chat.id,
                    "Привет! Я парсер Авито. Для использования бота нужна подписка.\n"
                    "Но ты можешь протестировать парсер прямо сейчас!\n"
                    "Выбери тариф и начни получать новые объявления первым!",
                    reply_markup=markup
                )
        elif text == 'Вернуться к выбору режима':
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add('Админ', 'Пользователь')
            bot.send_message(
                message.chat.id,
                "Выберите режим работы:",
                reply_markup=markup
            )
        # Обработка кнопок в режиме администратора
        elif text == 'Статистика':
            # TODO: Реализовать статистику
            bot.reply_to(message, "Статистика будет доступна позже.")
        elif text == 'Пользователи':
            show_users_list(message)
        elif text == 'Тест парсера':
            # Запускаем тестовый парсинг для администратора
            start_test_parsing(message)
        
        # Обработка кнопок в режиме пользователя для администратора
        elif text == 'Купить подписку':
            show_subscription_plans(message)
        elif text == 'Информация':
            bot.reply_to(message, "Я парсер Авито. С моей помощью ты сможешь:\n"
                                  "• Получать уведомления о новых объявлениях\n"
                                  "• Мониторить до 100 ссылок одновременно\n"
                                  "• Быть первым на самых выгодных предложениях!")
        elif text == 'Моя подписка':
            subscription = db.get_user_subscription(user_id)
            if subscription:
                # Всегда показываем тип подписки и дату окончания, независимо от статуса
                status = "✅ Активна" if subscription['is_active'] else "❌ Неактивна"
                bot.reply_to(message, f"📋 *Информация о подписке:*\n\n"
                                     f"💎 Тип: {subscription['type']}\n"
                                     f"📅 Действует до: {subscription['end_date'][:10]}\n"
                                     f"🔸 Статус: {status}")
            else:
                bot.reply_to(message, "📋 У тебя ещё не было подписки. Нажми 'Купить подписку'")
        elif text == 'Добавить ссылку':
            subscription = db.get_user_subscription(user_id)
            if subscription:
                # Проверяем лимит ссылок
                links = db.get_user_links(user_id)
                plan_limit = SUBSCRIPTION_PLANS.get(subscription['type'], {}).get('links_limit', 0)
                if len(links) >= plan_limit:
                    bot.reply_to(message, f"Достигнут лимит ссылок ({plan_limit}). Увеличьте тариф.")
                else:
                    msg = bot.reply_to(message, "Пришли мне ссылку на Авито для мониторинга:")
                    bot.register_next_step_handler(msg, process_avito_link)
            else:
                bot.reply_to(message, "Для добавления ссылки нужна активная подписка!")
        elif text == 'Мои ссылки':
            subscription = db.get_user_subscription(user_id)
            if subscription:
                links = db.get_user_links(user_id)
                if links:
                    links_text = "Твои ссылки:\n\n" + "\n".join([f"• {link[0]}" for link in links])
                    bot.reply_to(message, links_text)
                else:
                    bot.reply_to(message, "У тебя пока нет добавленных ссылок.")
            else:
                bot.reply_to(message, "Для просмотра ссылок нужна активная подписка!")
        else:
            bot.reply_to(message, "Неизвестная команда")
    else:
        # Обработка для обычных пользователей
        subscription = db.get_user_subscription(user_id)
        
        if text == 'Купить подписку':
            show_subscription_plans(message)
        elif text == 'Информация':
            bot.reply_to(message, "Я парсер Авито. С моей помощью ты сможешь:\n"
                                  "• Получать уведомления о новых объявлениях\n"
                                  "• Мониторить до 100 ссылок одновременно\n"
                                  "• Быть первым на самых выгодных предложениях!")
        elif text == 'Моя подписка':
            subscription = db.get_user_subscription(user_id)
            if subscription:
                status = "✅ Активна" if subscription['is_active'] else "❌ Неактивна"
                bot.reply_to(message, f"📋 *Информация о подписке:*\n\n"
                                     f"💎 Тип: {subscription['type']}\n"
                                     f"📅 Действует до: {subscription['end_date'][:10]}\n"
                                     f"🔸 Статус: {status}")
            else:
                bot.reply_to(message, "📋 У тебя ещё не было подписки. Нажми 'Купить подписку'")
        elif text == 'Добавить ссылку':
            if subscription:
                # Проверяем лимит ссылок
                links = db.get_user_links(user_id)
                plan_limit = SUBSCRIPTION_PLANS.get(subscription['type'], {}).get('links_limit', 0)
                if len(links) >= plan_limit:
                    bot.reply_to(message, f"Достигнут лимит ссылок ({plan_limit}). Увеличьте тариф.")
                else:
                    msg = bot.reply_to(message, "Пришли мне ссылку на Авито для мониторинга:")
                    bot.register_next_step_handler(msg, process_avito_link)
            else:
                bot.reply_to(message, "Для добавления ссылки нужна активная подписка!")
        elif text == 'Мои ссылки':
            if subscription:
                links = db.get_user_links(user_id)
                if links:
                    links_text = "Твои ссылки:\n\n" + "\n".join([f"• {link[0]}" for link in links])
                    # Добавляем кнопку тестового парсинга
                    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                    markup.add('Добавить ссылку', 'Мои ссылки', 'Тест парсера', 'Настройки парсера', 'Моя подписка')
                    bot.reply_to(message, links_text, reply_markup=markup)
                else:
                    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                    markup.add('Добавить ссылку', 'Мои ссылки', 'Настройки парсера', 'Моя подписка')
                    bot.reply_to(message, "У тебя пока нет добавленных ссылок.", reply_markup=markup)
            else:
                bot.reply_to(message, "Для просмотра ссылок нужна активная подписка!")
        
        elif text == 'Настройки парсера':
            if subscription:
                show_parser_settings(message)
            else:
                bot.reply_to(message, "Для настройки парсера нужна активная подписка!")
        # Убрана кнопка "Настройки прокси" для пользователей
        elif text == 'Тест парсера':
            start_simple_user_test_parsing(message)
        else:
            bot.reply_to(message, "Неизвестная команда")

def show_subscription_plans(message):
    markup = InlineKeyboardMarkup()
    for plan_id, plan in SUBSCRIPTION_PLANS.items():
        markup.add(InlineKeyboardButton(
            f"{plan['name']} - {plan['price']}₽/мес",
            callback_data=f"subscribe_{plan_id}"
        ))
    bot.send_message(
        message.chat.id,
        "Выбери тариф подписки:",
        reply_markup=markup
    )

def process_avito_link(message):
    user_id = message.from_user.id
    link = message.text.strip()
    
    # Простая валидация ссылки
    if link.startswith('https://www.avito.ru/'):
        db.add_user_link(user_id, link)
        bot.reply_to(message, "Ссылка успешно добавлена! Начинаю мониторинг...")
        # TODO: Запустить парсинг для этой ссылки
    else:
        bot.reply_to(message, "Это не похоже на ссылку Авито. Попробуй еще раз.")

# Обработчик callback-кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith('subscribe_'):
        plan_id = call.data.split('_')[1]
        plan = SUBSCRIPTION_PLANS.get(plan_id)
        if plan:
            try:
                # Создаем платеж
                payment = payment_service.create_payment(
                    amount=plan['price'],
                    description=f"Подписка {plan['name']} на парсер Авито",
                    user_id=call.from_user.id,
                    plan_id=plan_id
                )
                
                if payment and hasattr(payment, 'confirmation') and hasattr(payment.confirmation, 'confirmation_url'):
                    # Сохраняем информацию о платеже
                    pending_payments[payment.id] = {
                        'user_id': call.from_user.id,
                        'plan_id': plan_id,
                        'message_id': call.message.message_id,
                        'pending_message_sent': False  # Флаг для отслеживания отправки сообщения о pending статусе
                    }
                    
                    # Добавляем запись о платеже в БД
                    db.add_payment(
                        user_id=call.from_user.id,
                        amount=plan['price'],
                        payment_system='yookassa',
                        payment_id=payment.id,
                        status='pending'
                    )
                    
                    # Отправляем ссылку для оплаты
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("💳 Оплатить", url=payment.confirmation.confirmation_url))
                    markup.add(InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment.id}"))
                    
                    message_text = (
                        f"💎 *Подписка {plan['name']}*\n\n"
                        f"💰 Сумма: *{plan['price']}₽*\n"
                        f"📅 Срок: *{plan['days']}* дней\n"
                        f"🔗 Лимит ссылок: *{plan['links_limit']}*\n\n"
                        f"Для активации подписки нажмите кнопку '💳 Оплатить'.\n"
                        f"После оплаты нажмите '✅ Проверить оплату'."
                    )
                    
                    # Если тестовый режим, добавляем информацию
                    if payment_service.test_mode:
                        message_text += "\n\n⚠️ *Тестовый режим оплаты*\nПлатеж будет автоматически подтвержден при проверке"
                    
                    bot.send_message(
                        call.message.chat.id,
                        message_text,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )
                else:
                    bot.answer_callback_query(call.id, "❌ Ошибка создания платежа. Попробуйте позже.", show_alert=True)
            except Exception as e:
                logger.error(f"Ошибка при создании платежа: {e}")
                bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа. Попробуйте позже.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Тариф не найден.", show_alert=True)
    
    elif call.data.startswith('check_payment_'):
        payment_id = call.data.split('_')[2]
        check_payment_status(call.from_user.id, payment_id, call.message.chat.id)
    elif call.data == 'show_subscription_plans':
        show_subscription_plans(call.message)

def check_payment_status(user_id: int, payment_id: str, chat_id: int):
    """Проверяет статус платежа и активирует подписку при успешной оплате"""
    try:
        status = payment_service.check_payment_status(payment_id)
        
        if status == 'succeeded':
            payment_info = pending_payments.get(payment_id)
            if payment_info and payment_info['user_id'] == user_id:
                plan_id = payment_info['plan_id']
                plan = SUBSCRIPTION_PLANS.get(plan_id)
                
                if plan:
                    # Активируем подписку
                    db.add_subscription(user_id, plan_id, plan['days'])
                    
                    # Обновляем статус платежа в БД
                    db.add_payment(
                        user_id=user_id,
                        amount=plan['price'],
                        payment_system='yookassa',
                        payment_id=payment_id,
                        status='succeeded'
                    )
                    
                    # Удаляем из ожидающих
                    del pending_payments[payment_id]
                    
                    # Обновляем клавиатуру пользователя
                    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                    markup.add('Добавить ссылку', 'Мои ссылки', 'Тест парсера', 'Настройки парсера', 'Моя подписка')
                    
                    bot.send_message(
                        chat_id,
                        f"✅ *Платеж подтвержден!*\n\n"
                        f"💎 Подписка *{plan['name']}* активирована на *{plan['days']}* дней!\n"
                        f"🔗 Лимит ссылок: *{plan['links_limit']}*\n\n"
                        f"Теперь ты можешь добавить ссылки для мониторинга через меню 'Добавить ссылку'.",
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
                else:
                    bot.send_message(chat_id, "❌ Информация о тарифе не найдена.")
            else:
                bot.send_message(chat_id, "❌ Информация о платеже не найдена.")
        elif status == 'pending':
            payment_info = pending_payments.get(payment_id)
            # Отправляем сообщение только если оно еще не отправлялось
            if payment_info and not payment_info.get('pending_message_sent'):
                bot.send_message(chat_id, "⏳ Платеж еще обрабатывается. Попробуйте проверить позже.")
                # Помечаем, что сообщение отправлено
                payment_info['pending_message_sent'] = True
        elif status == 'canceled':
            bot.send_message(chat_id, "❌ Платеж отменен.")
            # Обновляем статус платежа в БД
            db.add_payment(
                user_id=user_id,
                amount=0,
                payment_system='yookassa',
                payment_id=payment_id,
                status='canceled'
            )
            # Удаляем из ожидающих при отмене
            if payment_id in pending_payments:
                del pending_payments[payment_id]
        else:
            bot.send_message(chat_id, f"❌ Статус платежа: {status}")
    except Exception as e:
        logger.error(f"Ошибка при проверке платежа {payment_id}: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при проверке платежа. Попробуйте позже.")

# Убрана функция show_proxy_settings, так как пользователи больше не могут настраивать прокси

# Фоновая проверка платежей
def check_pending_payments():
    while True:
        try:
            for payment_id, payment_info in list(pending_payments.items()):
                # В фоновой проверке не отправляем сообщения о pending статусе
                status = payment_service.check_payment_status(payment_id)
                if status == 'succeeded':
                    # Если платеж успешен, активируем подписку
                    user_id = payment_info['user_id']
                    plan_id = payment_info['plan_id']
                    plan = SUBSCRIPTION_PLANS.get(plan_id)
                    
                    if plan:
                        # Активируем подписку
                        db.add_subscription(user_id, plan_id, plan['days'])
                        
                        # Обновляем статус платежа в БД
                        db.add_payment(
                            user_id=user_id,
                            amount=plan['price'],
                            payment_system='yookassa',
                            payment_id=payment_id,
                            status='succeeded'
                        )
                        
                        # Отправляем сообщение пользователю
                        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                        markup.add('Добавить ссылку', 'Мои ссылки', 'Тест парсера', 'Настройки парсера', 'Моя подписка')
                        
                        try:
                            bot.send_message(
                                user_id,
                                f"✅ *Платеж подтвержден!*\n\n"
                                f"💎 Подписка *{plan['name']}* активирована на *{plan['days']}* дней!\n"
                                f"🔗 Лимит ссылок: *{plan['links_limit']}*\n\n"
                                f"Теперь ты можешь добавить ссылки для мониторинга через меню 'Добавить ссылку'.",
                                parse_mode='Markdown',
                                reply_markup=markup
                            )
                        except Exception as e:
                            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
                        
                        # Удаляем из ожидающих
                        del pending_payments[payment_id]
                elif status == 'canceled':
                    # Обновляем статус платежа в БД
                    try:
                        db.add_payment(
                            user_id=payment_info['user_id'],
                            amount=0,
                            payment_system='yookassa',
                            payment_id=payment_id,
                            status='canceled'
                        )
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении отмененного платежа {payment_id}: {e}")
                    # Удаляем отмененные платежи
                    if payment_id in pending_payments:
                        del pending_payments[payment_id]
            time.sleep(60)  # Проверяем каждую минуту
        except Exception as e:
            logger.error(f"Ошибка в фоновой проверке платежей: {e}")
            time.sleep(60)

def show_users_list(message):
    """Показывает список пользователей администратору в виде файла"""
    user_id = message.from_user.id
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "У вас нет прав для выполнения этой команды.")
        return
    
    try:
        with sqlite3.connect(db.db_name) as conn:
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
            
            users = cursor.fetchall()
            
            if not users:
                bot.reply_to(message, "В базе данных нет пользователей.")
                return
            
            # Создаем содержимое файла
            file_content = "📊 Список пользователей\n\n"
            file_content += f"Всего пользователей: {len(users)}\n"
            file_content += f"Дата выгрузки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            file_content += "=" * 80 + "\n\n"
            
            for i, user in enumerate(users, 1):
                user_id, username, first_name, last_name, reg_date, is_active, sub_type, sub_end, links_count = user
                
                user_info = f"{i}. ID: {user_id}\n"
                user_info += f"   Имя: {first_name or ''} {last_name or ''}\n"
                user_info += f"   Username: @{username or 'нет'}\n"
                user_info += f"   Дата регистрации: {reg_date[:10] if reg_date else 'нет данных'}\n"
                user_info += f"   Количество ссылок: {links_count}\n"
                
                # Информация о подписке
                if sub_type and sub_end:
                    try:
                        days_left = (datetime.strptime(sub_end[:10], '%Y-%m-%d') - datetime.now()).days
                        user_info += f"   Подписка: {sub_type} (до {sub_end[:10]}, осталось {days_left} дн.)\n"
                    except:
                        user_info += f"   Подписка: {sub_type} (до {sub_end[:10]})\n"
                else:
                    user_info += f"   Подписка: нет\n"
                
                user_info += f"   Активен: {'да' if is_active else 'нет'}\n"
                user_info += "-" * 40 + "\n\n"
                
                file_content += user_info
            
            # Создаем временный файл
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.txt', delete=False) as f:
                f.write(file_content)
                temp_file_path = f.name
            
            # Отправляем файл
            with open(temp_file_path, 'rb') as file_to_send:
                bot.send_document(
                    message.chat.id,
                    file_to_send,
                    caption=f"📊 Список пользователей ({len(users)} чел.)",
                    visible_file_name=f"users_list_{datetime.now().strftime('%Y-%m-%d')}.txt"
                )
            
            # Удаляем временный файл
            os.unlink(temp_file_path)
            
            # Добавляем краткую статистику в сообщение
            active_subscriptions = sum(1 for user in users if user[6] and user[7])  # sub_type and sub_end
            total_links = sum(user[8] for user in users)  # links_count
            
            stats_message = (
                f"📈 Краткая статистика:\n"
                f"• Всего пользователей: {len(users)}\n"
                f"• С активной подпиской: {active_subscriptions}\n"
                f"• Всего ссылок для мониторинга: {total_links}"
            )
            
            bot.send_message(message.chat.id, stats_message)
                
            # Добавляем кнопки для управления
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add('Статистика', 'Пользователи', 'Тест парсера', 'Вернуться к выбору режима')
            
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        bot.reply_to(message, f"Произошла ошибка при получении списка пользователей: {str(e)}")

def show_parser_settings(message):
    """Показывает настройки парсера"""
    user_id = message.from_user.id
    settings = db.get_parser_settings(user_id)
    
    if not settings:
        settings = {
            'min_price': 0,
            'max_price': 999999999,
            'keys_word_white_list': [],
            'keys_word_black_list': [],
            'seller_black_list': [],
            'geo': '',
            'max_age': 86400,
            'ignore_reserv': True,
            'ignore_promotion': False,
            'parse_views': False,
            'tg_notifications': True,
            'proxy_string': '',
            'proxy_change_url': ''
        }
        db.update_parser_settings(user_id, settings)
    
    settings_text = (
        f"⚙️ *Текущие настройки парсера:*\n\n"
        f"• Минимальная цена: {settings['min_price']} руб.\n"
        f"• Максимальная цена: {settings['max_price']} руб.\n"
        f"• Город: {settings['geo'] or 'Не указан'}\n"
        f"• Макс. возраст: {settings['max_age']} сек.\n"
        f"• Игнорировать резервы: {'Да' if settings['ignore_reserv'] else 'Нет'}\n"
        f"• Игнорировать продвинутые: {'Да' if settings['ignore_promotion'] else 'Нет'}\n"
        f"• Парсить просмотры: {'Да' if settings['parse_views'] else 'Нет'}\n"
        f"• Уведомления в Telegram: {'Да' if settings['tg_notifications'] else 'Нет'}\n\n"
        f"Используйте команды для изменения настроек:\n"
        f"/set_min_price [цена] - установить мин. цену\n"
        f"/set_max_price [цена] - установить макс. цену\n"
        f"/set_geo [город] - установить город\n"
        f"/set_max_age [секунды] - установить макс. возраст"
    )
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('Изменить настройки', 'Вернуться в меню')
    
    bot.send_message(
        message.chat.id,
        settings_text,
        reply_markup=markup,
        parse_mode='Markdown'
    )

def start_test_parsing(message):
    """Запускает тестовый парсинг для администратора"""
    user_id = message.from_user.id
    
    # Получаем текущие настройки (включая прокси)
    current_settings = db.get_parser_settings(user_id)
    if not current_settings:
        current_settings = {}
    
    # Создаем тестовую ссылку для проверки
    test_url = "https://www.avito.ru/moskva/telefony/mobilnye_telefony/apple-ASgBAgICAUSSyA3OqzmwwQ2I_Dc?cd=1"
    
    # Создаем тестовые настройки парсера (убираем все фильтры)
    test_config = {
        'min_price': 0,
        'max_price': 999999999,
        'keys_word_white_list': [],
        'keys_word_black_list': [],
        'seller_black_list': [],
        'geo': '',  # Пустая строка - без фильтра по городу
        'max_age': 0,  # Без ограничения по времени
        'ignore_reserv': False,
        'ignore_promotion': False,
        'parse_views': False,
        'tg_notifications': True,
        'proxy_string': current_settings.get('proxy_string', ''),
        'proxy_change_url': current_settings.get('proxy_change_url', '')
    }
    
    # Сохраняем тестовые настройки
    db.update_parser_settings(user_id, test_config)
    
    # Добавляем тестовую ссылку
    db.add_user_link(user_id, test_url)
    
    # Создаем конфиг для парсера
    config = AvitoConfig(
        urls=[test_url],
        min_price=test_config['min_price'],
        max_price=test_config['max_price'],
        keys_word_white_list=test_config['keys_word_white_list'],
        keys_word_black_list=test_config['keys_word_black_list'],
        seller_black_list=test_config['seller_black_list'],
        geo=test_config['geo'],
        max_age=test_config['max_age'],
        ignore_reserv=test_config['ignore_reserv'],
        ignore_promotion=test_config['ignore_promotion'],
        parse_views=test_config['parse_views'],
        proxy_string=test_config['proxy_string'],
        proxy_change_url=test_config['proxy_change_url'],
        one_time_start=True,
        count=1,
        pause_between_links=2,
        max_count_of_retry=3,
        save_xlsx=False
    )
    
    # Запускаем парсинг в отдельном потоке
    threading.Thread(target=run_test_parser, args=(user_id, config, message.chat.id), daemon=True).start()
    
    bot.send_message(
        message.chat.id,
        "🔍 *Запускаю тестовый парсинг...*\n\n"
        "Тестовые параметры:\n"
        f"• Ссылка: {test_url}\n"
        f"• Цена: {test_config['min_price']} - {test_config['max_price']} руб.\n"
        f"• Ключевые слова: {', '.join(test_config['keys_word_white_list'])}\n"
        f"• Город: {'Любой (фильтр отключен)' if not test_config['geo'] else test_config['geo']}\n\n"
        "Результаты придут в этом чате в течение 1-2 минут.",
        parse_mode='Markdown'
    )

def start_user_test_parsing(message):
    """Запускает тестовый парсинг для обычного пользователя"""
    user_id = message.from_user.id
    
    # Получаем текущие настройки пользователя
    current_settings = db.get_parser_settings(user_id)
    if not current_settings:
        current_settings = {}
    
    # Получаем ссылки пользователя
    user_links = db.get_user_links(user_id)
    if not user_links:
        bot.send_message(
            message.chat.id,
            "❌ *У тебя нет добавленных ссылок для тестирования!*\n\n"
            "Сначала добавь ссылки через меню 'Добавить ссылку'.",
            parse_mode='Markdown'
        )
        return
    
    # Берем первую ссылку пользователя
    test_url = user_links[0][0]
    
    # Используем настройки пользователя
    test_config = {
        'min_price': current_settings.get('min_price', 0),
        'max_price': current_settings.get('max_price', 999999999),
        'keys_word_white_list': current_settings.get('keys_word_white_list', []),
        'keys_word_black_list': current_settings.get('keys_word_black_list', []),
        'seller_black_list': current_settings.get('seller_black_list', []),
        'geo': current_settings.get('geo', ''),
        'max_age': current_settings.get('max_age', 86400),
        'ignore_reserv': current_settings.get('ignore_reserv', True),
        'ignore_promotion': current_settings.get('ignore_promotion', False),
        'parse_views': current_settings.get('parse_views', False),
        'tg_notifications': True,
        'proxy_string': current_settings.get('proxy_string', ''),
        'proxy_change_url': current_settings.get('proxy_change_url', '')
    }
    
    # Создаем конфиг для парсера
    config = AvitoConfig(
        urls=[test_url],
        min_price=test_config['min_price'],
        max_price=test_config['max_price'],
        keys_word_white_list=test_config['keys_word_white_list'],
        keys_word_black_list=test_config['keys_word_black_list'],
        seller_black_list=test_config['seller_black_list'],
        geo=test_config['geo'],
        max_age=test_config['max_age'],
        ignore_reserv=test_config['ignore_reserv'],
        ignore_promotion=test_config['ignore_promotion'],
        parse_views=test_config['parse_views'],
        proxy_string=test_config['proxy_string'],
        proxy_change_url=test_config['proxy_change_url'],
        one_time_start=True,
        count=1,
        pause_between_links=2,
        max_count_of_retry=3,
        save_xlsx=False
    )
    
    # Запускаем парсинг в отдельном потоке
    threading.Thread(target=run_user_test_parser, args=(user_id, config, message.chat.id), daemon=True).start()
    
    bot.send_message(
        message.chat.id,
        "🔍 *Запускаю тестовый парсинг...*\n\n"
        "Использую твои настройки и первую ссылку из списка.\n\n"
        f"• Ссылка: {test_url}\n"
        f"• Цена: {test_config['min_price']} - {test_config['max_price']} руб.\n"
        f"• Ключевые слова: {', '.join(test_config['keys_word_white_list']) if test_config['keys_word_white_list'] else 'любые'}\n"
        f"• Город: {'Любой' if not test_config['geo'] else test_config['geo']}\n\n"
        "Результаты придут в этом чате в течение 1-2 минут.",
        parse_mode='Markdown'
    )

def run_user_test_parser(user_id, config, chat_id):
    """Запускает тестовый парсер для пользователя"""
    try:
        # Создаем обработчик для отправки уведомлений пользователю
        tg_handler = UserTgHandler(user_id, bot)
        
        # Создаем список для отслеживания найденных объявлений
        found_ads = []
        original_send_to_tg = tg_handler.send_to_tg
        
        def track_send_to_tg(ad=None, msg=None):
            if ad:
                found_ads.append(ad)
                logger.info(f"Найдено объявление для пользователя {user_id}: {ad.title} - {ad.priceDetailed.value} руб.")
            if msg:
                logger.info(f"Получено сообщение для пользователя {user_id}: {msg}")
            original_send_to_tg(ad=ad, msg=msg)
        
        tg_handler.send_to_tg = track_send_to_tg
        
        # Создаем событие остановки
        stop_event = threading.Event()
        
        # Запускаем парсер
        parser = AvitoParse(config, stop_event=stop_event)
        parser.tg_handler = tg_handler
        
        # Запускаем парсинг в отдельном потоке
        def parse_with_stop():
            parser.parse()
            # После завершения парсинга устанавливаем событие остановки
            stop_event.set()
        
        parse_thread = threading.Thread(target=parse_with_stop)
        parse_thread.start()
        
        # Ждем завершения парсинга или таймаут
        parse_thread.join(timeout=120)  # 2 минуты таймаут
        
        # Если поток еще жив, останавливаем
        if parse_thread.is_alive():
            stop_event.set()
            parse_thread.join(timeout=10)
        
        # Формируем сообщение о результатах
        if found_ads:
            result_message = (
                f"✅ *Тестовый парсинг завершен успешно!*\n\n"
                f"Найдено и отправлено *{len(found_ads)}* новых объявлений.\n"
                f"Парсер работает корректно.\n\n"
                f"Примеры найденных объявлений:\n"
            )
            # Добавляем информацию о первых 3 объявлениях
            for i, ad in enumerate(found_ads[:3]):
                result_message += f"\n{i+1}. {ad.title} - {ad.priceDetailed.value} руб."
        else:
            result_message = (
                "⚠️ *Тестовый парсинг завершен, но объявления не найдены.*\n\n"
                "Возможные причины:\n"
                "• Нет новых объявлений по заданным критериям\n"
                "• Все объявления уже были просмотрены ранее\n"
                "• Слишком строгие фильтры поиска\n\n"
                "Попробуйте изменить параметры поиска."
            )
        
        # Отправляем сообщение о завершении
        bot.send_message(
            chat_id,
            result_message,
            parse_mode='Markdown'
        )
            
    except Exception as e:
        logger.error(f"Ошибка при тестовом парсинге для пользователя {user_id}: {e}")
        bot.send_message(
            chat_id,
            f"❌ *Ошибка при тестовом парсинге:*\n\n{str(e)}",
            parse_mode='Markdown'
        )

def run_test_parser(user_id, config, chat_id):
    """Запускает парсер в отдельном потоке"""
    try:
        # Создаем обработчик для отправки уведомлений администратору
        tg_handler = UserTgHandler(user_id, bot)
        
        # Создаем событие остановки
        stop_event = threading.Event()
        
        # Запускаем парсер
        parser = AvitoParse(config, stop_event=stop_event)
        parser.tg_handler = tg_handler
        
        # Запускаем парсинг в отдельном потоке
        def parse_with_stop():
            parser.parse()
            # После завершения парсинга устанавливаем событие остановки
            stop_event.set()
        
        parse_thread = threading.Thread(target=parse_with_stop)
        parse_thread.start()
        
        # Ждем завершения парсинга или таймаут
        parse_thread.join(timeout=120)  # 2 минуты таймаут
        
        # Если поток еще жив, останавливаем
        if parse_thread.is_alive():
            stop_event.set()
            parse_thread.join(timeout=10)
        
        # Отправляем сообщение о завершении
        bot.send_message(
            chat_id,
            "✅ *Тестовый парсинг завершен!*\n\n"
            "Если вы получили уведомления о новых объявлениях - парсер работает корректно.\n"
            "Тестовые данные были автоматически удалены.",
            parse_mode='Markdown'
        )
        
        # Удаляем тестовую ссылку
        with sqlite3.connect(db.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM user_links WHERE user_id = ? AND avito_link = ?', 
                          (user_id, config.urls[0]))
            conn.commit()
            
    except Exception as e:
        logger.error(f"Ошибка при тестовом парсинге: {e}")
        bot.send_message(
            chat_id,
            f"❌ *Ошибка при тестовом парсинге:*\n\n{str(e)}",
            parse_mode='Markdown'
        )

def start_simple_user_test_parsing(message):
    """Запускает упрощенный тестовый парсинг для всех пользователей"""
    user_id = message.from_user.id
    
    # Создаем тестовую ссылку для проверки (iPhone в Москве)
    test_url = "https://www.avito.ru/moskva/telefony/mobilnye_telefony/apple-ASgBAgICAUSSyA3OqzmwwQ2I_Dc?cd=1"
    
    # Создаем тестовые настройки парсера (убираем все фильтры)
    test_config = {
        'min_price': 0,
        'max_price': 999999999,
        'keys_word_white_list': [],
        'keys_word_black_list': [],
        'seller_black_list': [],
        'geo': '',  # Пустая строка - без фильтра по городу
        'max_age': 0,  # Без ограничения по времени
        'ignore_reserv': False,
        'ignore_promotion': False,
        'parse_views': False,
        'tg_notifications': True,
        'proxy_string': '',
        'proxy_change_url': ''
    }
    
    # Создаем конфиг для парсера
    config = AvitoConfig(
        urls=[test_url],
        min_price=test_config['min_price'],
        max_price=test_config['max_price'],
        keys_word_white_list=test_config['keys_word_white_list'],
        keys_word_black_list=test_config['keys_word_black_list'],
        seller_black_list=test_config['seller_black_list'],
        geo=test_config['geo'],
        max_age=test_config['max_age'],
        ignore_reserv=test_config['ignore_reserv'],
        ignore_promotion=test_config['ignore_promotion'],
        parse_views=test_config['parse_views'],
        proxy_string=test_config['proxy_string'],
        proxy_change_url=test_config['proxy_change_url'],
        one_time_start=True,
        count=1,
        pause_between_links=2,
        max_count_of_retry=3,
        save_xlsx=False
    )
    
    # Запускаем парсинг в отдельном потоке
    threading.Thread(target=run_simple_user_test_parser, args=(user_id, config, message.chat.id), daemon=True).start()
    
    bot.send_message(
        message.chat.id,
        "🔍 *Запускаю тестовый парсинг...*\n\n"
        "Тестовые параметры:\n"
        f"• Ссылка: {test_url}\n"
        f"• Цена: {test_config['min_price']} - {test_config['max_price']} руб.\n"
        f"• Ключевые слова: {'любые'}\n"
        f"• Город: {'Любой'}\n\n"
        "*Это демо-версия парсера!*\n"
        "Для полноценного использования с твоими ссылками и настройками - приобрети подписку.\n\n"
        "Результаты придут в этом чате в течение 1-2 минут.",
        parse_mode='Markdown'
    )

def run_simple_user_test_parser(user_id, config, chat_id):
    """Запускает упрощенный тестовый парсер для всех пользователей"""
    try:
        # Создаем обработчик для отправки уведомлений пользователю
        tg_handler = UserTgHandler(user_id, bot)
        
        # Создаем список для отслеживания найденных объявлений
        found_ads = []
        original_send_to_tg = tg_handler.send_to_tg
        
        def track_send_to_tg(ad=None, msg=None):
            if ad:
                found_ads.append(ad)
                logger.info(f"Найдено объявление для пользователя {user_id}: {ad.title} - {ad.priceDetailed.value} руб.")
            if msg:
                logger.info(f"Получено сообщение для пользователя {user_id}: {msg}")
            original_send_to_tg(ad=ad, msg=msg)
        
        tg_handler.send_to_tg = track_send_to_tg
        
        # Создаем событие остановки
        stop_event = threading.Event()
        
        # Запускаем парсер
        parser = AvitoParse(config, stop_event=stop_event)
        parser.tg_handler = tg_handler
        
        # Запускаем парсинг в отдельном потоке
        def parse_with_stop():
            parser.parse()
            # После завершения парсинга устанавливаем событие остановки
            stop_event.set()
        
        parse_thread = threading.Thread(target=parse_with_stop)
        parse_thread.start()
        
        # Ждем завершения парсинга или таймаут
        parse_thread.join(timeout=120)  # 2 минуты таймаут
        
        # Если поток еще жив, останавливаем
        if parse_thread.is_alive():
            stop_event.set()
            parse_thread.join(timeout=10)
        
        # Формируем сообщение о результатах
        if found_ads:
            result_message = (
                f"✅ *Тестовый парсинг завершен успешно!*\n\n"
                f"Найдено и отправлено *{len(found_ads)}* новых объявлений.\n"
                f"Парсер работает корректно.\n\n"
                f"*Примеры найденных объявлений:*\n"
            )
            # Добавляем информацию о первых 3 объявлениях
            for i, ad in enumerate(found_ads[:3]):
                result_message += f"\n{i+1}. {ad.title} - {ad.priceDetailed.value} руб."
            
            result_message += "\n\n💎 *Хочешь больше?*\nПриобрети подписку и настрой парсер под свои нужды!"
        else:
            result_message = (
                "⚠️ *Тестовый парсинг завершен, но объявления не найдены.*\n\n"
                "Возможные причины:\n"
                "• Нет новых объявлений по заданным критериям\n"
                "• Все объявления уже были просмотрены ранее\n"
                "• Проблемы с подключением\n\n"
                "💎 *Попробуй полноценную версию с подпиской!*\n"
                "Ты сможешь настроить фильтры под себя и мониторить свои ссылки."
            )
        
        # Добавляем кнопку для покупки подписки
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💎 Купить подписку", callback_data="show_subscription_plans"))
        
        # Отправляем сообщение о завершении
        bot.send_message(
            chat_id,
            result_message,
            parse_mode='Markdown',
            reply_markup=markup
        )
            
    except Exception as e:
        logger.error(f"Ошибка при тестовом парсинге для пользователя {user_id}: {e}")
        bot.send_message(
            chat_id,
            f"❌ *Ошибка при тестовом парсинге:*\n\n{str(e)}\n\n"
            "💎 *Попробуй полноценную версию с подпиской!*",
            parse_mode='Markdown'
        )

# Запуск бота
if __name__ == '__main__':
    payment_checker_thread = threading.Thread(target=check_pending_payments, daemon=True)
    payment_checker_thread.start()

    # Устанавливаем бот в сервис парсера
    parser_service.set_bot(bot)
    
    # Запускаем сервис парсера при старте бота
    parser_service.start_monitoring()
    
    print("Бот запущен...")
    try:
        bot.infinity_polling(skip_pending=True)
    except KeyboardInterrupt:
        print("Бот остановлен пользователем")
        parser_service.stop_monitoring()
    except Exception as e:
        print(f"Ошибка при работе бота: {e}")
        parser_service.stop_monitoring()
