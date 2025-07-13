# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/14 00:11
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 自动翻译功能命令处理器（指令转发层）
"""

from telegram import Update
from telegram.ext import ContextTypes

from settings import settings
from triggers.auto_translation import (
    enable_auto_translation,
    disable_auto_translation,
    get_auto_translation_status,
)


async def auto_translation_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """自动翻译命令处理器（指令转发层）"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    args = context.args

    # 检查白名单权限
    if settings.whitelist and chat_id not in settings.whitelist:
        await update.message.reply_text(
            "⚠️ 您没有权限使用自动翻译功能。\n" "此功能仅限于授权的聊天群组使用。"
        )
        return

    # 准备用户信息
    username = user.username or user.first_name or "匿名用户"
    user_id = user.id

    if not args:
        # 显示当前状态和帮助信息
        result = await get_auto_translation_status(chat_id)
        await update.message.reply_text(result.message, parse_mode='Markdown')
        return

    command = args[0].lower()

    if command == "on" or command == "开启":
        result = await enable_auto_translation(chat_id, user_id, username)
        await update.message.reply_text(result.message)
    elif command == "off" or command == "关闭":
        result = await disable_auto_translation(chat_id, user_id, username)
        await update.message.reply_markdown_v2(result.message)
    elif command == "status" or command == "状态":
        result = await get_auto_translation_status(chat_id)
        await update.message.reply_text(result.message, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "❌ 无效的命令参数。\n\n"
            "使用方法：\n"
            "• `/auto_translation on` - 开启自动翻译\n"
            "• `/auto_translation off` - 关闭自动翻译\n"
            "• `/auto_translation status` - 查看状态\n"
            "• `/auto_translation` - 显示帮助信息"
        )
