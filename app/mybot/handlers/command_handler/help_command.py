# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/13 13:58
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from mybot.task_manager import non_blocking_handler

templates_dir = Path(__file__).parent.joinpath("templates")
pending_template_path = templates_dir.joinpath("help.txt")

help_template = "help!"
if pending_template_path.is_file():
    help_template = pending_template_path.read_text(encoding="utf-8")


@non_blocking_handler("help_command")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_markdown(help_template)
