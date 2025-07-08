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

from loguru import logger
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters

from mybot import cli
from mybot import handlers
from settings import settings, LOG_DIR
from utils import init_log

init_log(
    runtime=LOG_DIR.joinpath("runtime.log"),
    error=LOG_DIR.joinpath("error.log"),
    serialize=LOG_DIR.joinpath("serialize.log"),
)


def main() -> None:
    """Start the bot."""
    sp = settings.model_dump(mode='json')

    s = json.dumps(sp, indent=2, ensure_ascii=False)
    logger.success(f"Loading settings: {s}")

    # Create the Application and pass it your bot's token.
    application = settings.get_default_application()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", cli.start))
    application.add_handler(CommandHandler("help", cli.help_command))
    application.add_handler(CommandHandler("auto", cli.auto))
    application.add_handler(CommandHandler("pause", cli.pause))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handlers.translation))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
