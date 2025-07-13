# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/13 13:58
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from telegram import Update, ForceReply
from telegram.ext import ContextTypes

START_TPL = """
你好，我是 @{username}，一个部署在 Telegram 群聊中的 AI 助手。

我的主要任务是回答群组成员提出的通用知识问题。你可以通过 @{username} 提及我，或者直接回复我的消息来向我提问。我会尽力提供准确、简洁、中立的答案，并使用你提问的相同语言进行回复。
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    bot_username = context.bot.username
    answer_text = START_TPL.format(username=bot_username).strip()
    await update.message.reply_html(rf"{answer_text}", reply_markup=ForceReply(selective=True))
