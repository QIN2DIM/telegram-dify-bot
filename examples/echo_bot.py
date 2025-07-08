#!/usr/bin/env python
# pylint: disable=unused-argument
# This program is dedicated to the public domain under the CC0 license.

"""
Simple Bot to reply to Telegram messages.

First, a few handler functions are defined. Then, those functions are passed to
the Application and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Basic Echobot example, repeats messages.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""
import json
import logging
import time
from contextlib import suppress
from pathlib import Path

from telegram import ForceReply, Update, Message, MessageEntity
from telegram.ext import CommandHandler, ContextTypes, MessageHandler, filters
from telegram import Chat
from settings import settings
from loguru import logger

data_dir = Path(__file__).parent / "data"
data_dir.mkdir(parents=True, exist_ok=True)


# Define a few command handlers. These usually take the two arguments update and
# context.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!", reply_markup=ForceReply(selective=True)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")


def storage_messages_dataset(chat_type: str, effective_message: Message) -> None:
    """仅用于开发测试，程序运行稳定后移除"""

    preview_text = json.dumps(effective_message.to_dict(), indent=2, ensure_ascii=False)

    fp = data_dir.joinpath(f"{chat_type}_messages/{int(time.time())}.json")
    fp.parent.mkdir(parents=True, exist_ok=True)

    fp.write_text(preview_text, encoding="utf-8")
    logger.debug(f"echo message - {preview_text}")


def _is_available_translation(chat: Chat, message: Message) -> bool | None:
    if chat.id not in settings.whitelist:
        return
    if not message.entities:
        return

    text = message.text

    is_mention_message = False

    for e in message.entities:
        if e.type == "mention":
            is_mention_message = True
            break
    if not is_mention_message:
        return


async def translation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo the user message."""
    chat = update.effective_chat
    message = update.effective_message

    logger.debug("正在翻译....")

    with suppress(Exception):
        storage_messages_dataset(chat.type, message)

    # AttributeError: 'NoneType' object has no attribute 'reply_text'
    await update.message.reply_sticker("sticker.webp")


def main() -> None:
    """Start the bot."""
    sp = settings.model_dump(mode='json')

    s = json.dumps(sp, indent=2, ensure_ascii=False)
    logger.success(f"Loading settings: {s}")

    # Create the Application and pass it your bot's token.
    application = settings.get_default_application()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, translation))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
