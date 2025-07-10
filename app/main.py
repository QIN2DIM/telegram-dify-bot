# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:40
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
from contextlib import suppress

from loguru import logger
from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters

from mybot import cli
from mybot import task_handler
from mybot.common import cleanup_old_photos
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

    # 定期清理旧的下载图片（每次重启时都尝试清理）
    with suppress(Exception):
        cleanup_old_photos(max_age_hours=24)

    # Create the Application and pass it your bot's token.
    application = settings.get_default_application()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", cli.start))
    application.add_handler(CommandHandler("help", cli.help_command))
    application.add_handler(CommandHandler("auto", cli.auto))
    application.add_handler(CommandHandler("pause", cli.pause))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, task_handler))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
