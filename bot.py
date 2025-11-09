import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from config import BOT_TOKEN, ADMIN_IDS

# Включим логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Команда старт для всех пользователей
async def start(update, context):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        # Клавиатура для администратора
        admin_keyboard = [['Добавить прокси']]
        reply_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Привет, администратор!",
            reply_markup=reply_markup
        )
    else:
        # Клавиатура для обычного пользователя
        user_keyboard = [
            ['Посмотреть свою подписку', 'Посмотреть свою ссылку']
        ]
        reply_markup = ReplyKeyboardMarkup(user_keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Привет! Я парсер Авито. Выведу тебе новые объявления быстрее всего!",
            reply_markup=reply_markup
        )

# Команда для получения ID пользователя
async def get_id(update, context):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Ваш ID: {user_id}")

# Команда только для администраторов
async def admin_command(update, context):
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        await update.message.reply_text("Это команда только для администраторов!")
    else:
        await update.message.reply_text("У вас нет прав для выполнения этой команды.")

# Обычная команда для всех пользователей
async def help_command(update, context):
    await update.message.reply_text("Это помощь для всех пользователей!")

# Обработчик текстовых сообщений (для кнопок)
async def handle_buttons(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id in ADMIN_IDS:
        # Обработка кнопок администратора
        if text == 'Добавить прокси':
            await update.message.reply_text("Функция добавления прокси будет реализована позже.")
    else:
        # Обработка кнопок пользователя
        if text == 'Посмотреть свою подписку':
            await update.message.reply_text("Информация о подписке будет доступна позже.")
        elif text == 'Посмотреть свою ссылку':
            await update.message.reply_text("Ваша ссылка будет отображена позже.")

async def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("get_id", get_id))
    
    # Обработчик текстовых сообщений (включая нажатия кнопок)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    # Запускаем бота
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
