import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
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
        await update.message.reply_text("Привет, администратор!")
    else:
        await update.message.reply_text("Привет, пользователь!")

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

# Обработчик текстовых сообщений
async def echo(update, context):
    await update.message.reply_text("Я получил ваше сообщение: " + update.message.text)

def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("get_id", get_id))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
