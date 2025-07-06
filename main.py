from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from settings import settings


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Hello {update.effective_user.first_name}")


app = (
    ApplicationBuilder()
    .token(token=settings.TELEGRAM_BOT_API_TOKEN.get_secret_value())
    .build()
)

app.add_handler(CommandHandler("hello", hello))

if __name__ == "__main__":
    app.run_polling()
