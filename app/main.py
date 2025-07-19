# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:40
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
import signal
import sys
from contextlib import suppress

from loguru import logger
from telegram import Update, BotCommand
from telegram.ext import CommandHandler, MessageHandler, filters

from mybot.common import cleanup_old_photos
from mybot.handlers.command_handler import start_command, help_command, zlib_command
from mybot.handlers.message_handler import handle_message
from plugins import zlib_access_points
from settings import settings, LOG_DIR
from utils import init_log

init_log(
    runtime=LOG_DIR.joinpath("runtime.log"),
    error=LOG_DIR.joinpath("error.log"),
    serialize=LOG_DIR.joinpath("serialize.log"),
)


def init_plugin_storage():
    drivers = [zlib_access_points]
    for driver in drivers:
        with suppress(Exception):
            driver.init_database()


async def setup_bot_commands(application):
    """设置机器人的命令菜单"""
    commands = [
        # BotCommand("start", "开始使用机器人"),
        # BotCommand("help", "获取帮助信息"),
        BotCommand("zlib", "获取 Z-Library 搜索链接")
    ]

    try:
        await application.bot.set_my_commands(commands)
        logger.success(f"已设置机器人命令菜单: {[f'/{cmd.command}' for cmd in commands]}")
    except Exception as e:
        logger.error(f"设置机器人命令菜单失败: {e}")


def main() -> None:
    """Start the bot."""
    sp = settings.model_dump(mode='json')

    s = json.dumps(sp, indent=2, ensure_ascii=False)
    logger.success(f"Loading settings: {s}")

    if settings.ENABLE_DEV_MODE:
        logger.warning("🪄 开发模式已启动")

    if settings.ENABLE_TEST_MODE:
        logger.warning("🪄 测试模式已启动")

    # 定期清理旧的下载图片（每次重启时都尝试清理）
    with suppress(Exception):
        cleanup_old_photos(max_age_hours=24)

    # Create the Application and pass it your bot's token.
    application = settings.get_default_application()

    # 初始化数据库状态
    init_plugin_storage()

    # 设置机器人命令菜单
    application.post_init = setup_bot_commands

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("zlib", zlib_command))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    # Setting up a graceful shutdown
    def shutdown_handler(signum, frame):
        logger.info("Receiving a shutdown signal that is stopping the scheduler...")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
