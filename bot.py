import logging
import telebot
from telebot.types import ReplyKeyboardMarkup
from config import BOT_TOKEN, ADMIN_IDS

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем экземпляр бота
bot = telebot.TeleBot(BOT_TOKEN)

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
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
        # Создаем клавиатуру для обычного пользователя
        markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('Посмотреть свою подписку', 'Посмотреть свою ссылку')
        bot.send_message(
            message.chat.id,
            "Привет! Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
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
            markup.add('Добавить прокси', 'Вернуться к выбору режима')
            bot.send_message(
                message.chat.id,
                "Вы вошли в режим администратора",
                reply_markup=markup
            )
        elif text == 'Пользователь':
            markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add('Посмотреть свою подписку', 'Посмотреть свою ссылку', 'Вернуться к выбору режима')
            bot.send_message(
                message.chat.id,
                "Привет! Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
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
        elif text == 'Добавить прокси':
            bot.reply_to(message, "Функция добавления прокси будет реализована позже.")
        # Обработка кнопок в режиме пользователя
        elif text == 'Посмотреть свою подписку':
            bot.reply_to(message, "Информация о подписке будет доступна позже.")
        elif text == 'Посмотреть свою ссылку':
            bot.reply_to(message, "Ваша ссылка будет отображена позже.")
        else:
            bot.reply_to(message, "Неизвестная команда")
    else:
        if text == 'Посмотреть свою подписку':
            bot.reply_to(message, "Информация о подписке будет доступна позже.")
        elif text == 'Посмотреть свою ссылку':
            bot.reply_to(message, "Ваша ссылка будет отображена позже.")
        else:
            bot.reply_to(message, "Неизвестная команда")

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
