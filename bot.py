import logging
import telebot
from telebot.types import ReplyKeyboardMarkup
from config import BOT_TOKEN, ADMIN_IDS

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем экземпляр бота
bot = telebot.TeleBot(BOT_TOKEN)

# Команда старт для всех пользователей
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        # Клавиатура для администратора
        admin_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        admin_keyboard.add('Добавить прокси')
        bot.send_message(
            message.chat.id,
            "Привет, администратор!",
            reply_markup=admin_keyboard
        )
    else:
        # Клавиатура для обычного пользователя
        user_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
        user_keyboard.add('Посмотреть свою подписку', 'Посмотреть свою ссылку')
        bot.send_message(
            message.chat.id,
            "Привет! Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
            reply_markup=user_keyboard
        )

# Команда для получения ID пользователя
@bot.message_handler(commands=['get_id'])
def get_id(message):
    user_id = message.from_user.id
    bot.send_message(message.chat.id, f"Ваш ID: {user_id}")

# Команда только для администраторов
@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        bot.send_message(message.chat.id, "Это команда только для администраторов!")
    else:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")

# Обычная команда для всех пользователей
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.send_message(message.chat.id, "Это помощь для всех пользователей!")

# Обработчик текстовых сообщений (для кнопок)
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    user_id = message.from_user.id
    text = message.text
    
    if user_id in ADMIN_IDS:
        # Обработка кнопок администратора
        if text == 'Добавить прокси':
            bot.send_message(message.chat.id, "Функция добавления прокси будет реализована позже.")
    else:
        # Обработка кнопок пользователя
        if text == 'Посмотреть свою подписку':
            bot.send_message(message.chat.id, "Информация о подписке будет доступна позже.")
        elif text == 'Посмотреть свою ссылку':
            bot.send_message(message.chat.id, "Ваша ссылка будет отображена позже.")

def main():
    # Запускаем бота
    bot.infinity_polling()

if __name__ == '__main__':
    main()
