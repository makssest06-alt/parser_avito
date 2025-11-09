import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import ReplyKeyboardMarkup
from config import BOT_TOKEN, ADMIN_IDS

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Команда старт для всех пользователей
def start(update, context):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        # Клавиатура для администратора
        admin_keyboard = [['Добавить прокси']]
        reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True)
        update.message.reply_text(
            "Привет, администратор!",
            reply_markup=reply_markup
        )
    else:
        # Клавиатура для обычного пользователя
        user_keyboard = [
            ['Посмотреть свою подписку', 'Посмотреть свою ссылку']
        ]
        reply_markup = ReplyKeyboardMarkup(user_keyboard, resize_keyboard=True)
        update.message.reply_text(
            "Привет! Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
            reply_markup=reply_markup
        )

# Команда для получения ID пользователя
def get_id(update, context):
    user_id = update.effective_user.id
    update.message.reply_text(f"Ваш ID: {user_id}")

# Команда только для администраторов
def admin_command(update, context):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        update.message.reply_text("Это команда только для администраторов!")
    else:
        update.message.reply_text("У вас нет прав для выполнения этой команды.")

# Обычная команда для всех пользователей
def help_command(update, context):
    update.message.reply_text("Это помощь для всех пользователей!")

# Обработчик текстовых сообщений (для кнопок)
def handle_buttons(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in ADMIN_IDS:
        # Обработка кнопок администратора
        if text == 'Добавить прокси':
            update.message.reply_text("Функция добавления прокси будет реализована позже.")
    else:
        # Обработка кнопок пользователя
        if text == 'Посмотреть свою подписку':
            update.message.reply_text("Информация о подписке будет доступна позже.")
        elif text == 'Посмотреть свою ссылку':
            update.message.reply_text("Ваша ссылка будет отображена позже.")

def main():
    # Создаем Updater и передаем ему токен бота
    updater = Updater(BOT_TOKEN, use_context=True)
    
    # Получаем диспетчер для регистрации обработчиков
    dp = updater.dispatcher

    # Добавляем обработчики команд
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("admin", admin_command))
    dp.add_handler(CommandHandler("get_id", get_id))
    
    # Обработчик текстовых сообщений (включая нажатия кнопок)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_buttons))

    # Запускаем бота
    updater.start_polling()
    
    # Запускаем бота до тех пор, пока пользователь не остановит его
    updater.idle()

if __name__ == '__main__':
    main()
