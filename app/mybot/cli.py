# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 00:44
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from telegram import Update, ForceReply
from telegram.ext import ContextTypes

# 自动翻译模式状态管理（简单实现，生产环境应使用数据库）
auto_translation_enabled_chats = set()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!", reply_markup=ForceReply(selective=True)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Help!")


async def auto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """开启自动翻译模式"""
    chat_id = update.effective_chat.id
    auto_translation_enabled_chats.add(chat_id)
    await update.message.reply_text("已开启自动翻译模式")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """暂停自动翻译模式"""
    chat_id = update.effective_chat.id
    auto_translation_enabled_chats.discard(chat_id)
    await update.message.reply_text("已暂停自动翻译模式")
