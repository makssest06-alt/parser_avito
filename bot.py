import logging
import telebot
from telebot.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, ADMIN_IDS
from database import Database

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
    "basic": {"name": "Базовый", "price": 299, "days": 30, "links_limit": 5},
    "premium": {"name": "Премиум", "price": 599, "days": 30, "links_limit": 20},
    "vip": {"name": "VIP", "price": 999, "days": 30, "links_limit": 100}
}

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
            markup.add('Добавить ссылку', 'Мои ссылки', 'Моя подписка')
            bot.send_message(
                message.chat.id,
                f"Привет! Твоя подписка активна до {subscription['end_date'][:10]}\n"
                "Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
                reply_markup=markup
            )
        else:
            # Пользователь без подписки
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add('Купить подписку', 'Информация')
            bot.send_message(
                message.chat.id,
                "Привет! Я парсер Авито. Для использования бота нужна подписка.\n"
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
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text
    
    if user_id in ADMIN_IDS:
        # Обработка выбора режима администратором
        if text == 'Админ':
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
            markup.add('Статистика', 'Пользователи', 'Вернуться к выбору режима')
            bot.send_message(
                message.chat.id,
                "Вы вошли в режим администратора",
                reply_markup=markup
            )
        elif text == 'Пользователь':
            # Админ в режиме пользователя
            subscription = db.get_user_subscription(user_id)
            if subscription:
                markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                markup.add('Добавить ссылку', 'Мои ссылки', 'Моя подписка', 'Вернуться к выбору режима')
                bot.send_message(
                    message.chat.id,
                    "Режим пользователя",
                    reply_markup=markup
                )
            else:
                markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
                markup.add('Купить подписку', 'Информация', 'Вернуться к выбору режима')
                bot.send_message(
                    message.chat.id,
                    "Режим пользователя",
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
            # TODO: Реализовать управление пользователями
            bot.reply_to(message, "Управление пользователями будет доступно позже.")
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
            if subscription:
                bot.reply_to(message, f"Твоя подписка: {subscription['type']}\n"
                                     f"Активна до: {subscription['end_date'][:10]}\n"
                                     f"Статус: {'Активна' if subscription['is_active'] else 'Неактивна'}")
            else:
                bot.reply_to(message, "У тебя нет активной подписки. Нажми 'Купить подписку'")
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
                    bot.reply_to(message, links_text)
                else:
                    bot.reply_to(message, "У тебя пока нет добавленных ссылок.")
            else:
                bot.reply_to(message, "Для просмотра ссылок нужна активная подписка!")
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
            # TODO: Интеграция с платежной системой
            # Пока просто добавляем подписку
            db.add_subscription(call.from_user.id, plan_id, plan['days'])
            bot.answer_callback_query(call.id, f"Подписка {plan['name']} активирована!")
            bot.send_message(
                call.message.chat.id,
                f"Поздравляем! Ты активировал подписку {plan['name']} на {plan['days']} дней!\n"
                f"Теперь ты можешь добавить до {plan['links_limit']} ссылок для мониторинга."
            )

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
