# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for building message contexts for LLM.
"""

from loguru import logger
from telegram import Update, Message
from telegram.ext import ContextTypes

from models import TaskType
from mybot.prompts import (
    MESSAGE_FORMAT_TEMPLATE,
    MENTION_PROMPT_TEMPLATE,
    MENTION_WITH_REPLY_PROMPT_TEMPLATE,
    REPLY_SINGLE_PROMPT_TEMPLATE,
    USER_PREFERENCES_TPL,
)


async def _format_message(message: Message) -> str:
    """格式化单条消息"""
    username = "Anonymous"
    user_id = "unknown"

    if message.sender_chat:
        username = message.sender_chat.username or message.sender_chat.title or "Channel"
        user_id = str(message.sender_chat.id)
    elif message.from_user:
        username = message.from_user.username or message.from_user.first_name or "User"
        user_id = str(message.from_user.id)

    timestamp = message.date.strftime("%Y-%m-%d %H:%M:%S")
    text = message.text or message.caption or "[Media]"

    return MESSAGE_FORMAT_TEMPLATE.format(
        username=username, user_id=user_id, timestamp=timestamp, message=text
    )


async def _get_chat_history_for_mention(
    chat_id: int, trigger_message_id: int, bot, max_messages: int = 50, max_hours: int = 24
) -> str:
    """获取 MENTION 模式的历史消息 (stub)"""
    return ""


async def _get_reply_mode_context(
    chat, user_message: Message, bot_message: Message, user_id: int, bot
) -> tuple[str, str]:
    """获取 REPLY 模式的上下文消息和用户偏好消息"""
    logger.debug(f"Getting reply mode context for user {user_id} in chat {chat.id}")
    history_messages = ""
    if bot_message:
        history_messages = await _format_message(bot_message)
    user_preferences = ""
    return history_messages, user_preferences


async def build_message_context(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_type: TaskType
) -> str:
    """构建用于 LLM 的消息上下文"""
    trigger_message = update.effective_message
    message_text = trigger_message.text or trigger_message.caption or ""
    message_context = message_text or "请分析这张图片"

    if task_type == TaskType.MENTION:
        history_messages = await _get_chat_history_for_mention(
            update.effective_chat.id, trigger_message.message_id, context.bot
        )
        user_query = await _format_message(trigger_message)
        if history_messages:
            message_context = MENTION_PROMPT_TEMPLATE.format(
                user_query=user_query, history_messages=history_messages
            )
        else:
            message_context = user_query

    elif task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        reply_text = (
            trigger_message.reply_to_message.text or trigger_message.reply_to_message.caption or ""
        )
        if reply_text:
            message_context = MENTION_WITH_REPLY_PROMPT_TEMPLATE.format(
                message_text=message_text, reply_text=reply_text
            )

    elif task_type == TaskType.REPLAY and trigger_message.reply_to_message:
        history_messages, user_preferences = await _get_reply_mode_context(
            update.effective_chat,
            trigger_message,
            trigger_message.reply_to_message,
            trigger_message.from_user.id if trigger_message.from_user else 0,
            context.bot,
        )
        if history_messages:
            message_context = REPLY_SINGLE_PROMPT_TEMPLATE.format(
                user_query=message_text, history_messages=history_messages
            ).strip()
            if user_preferences:
                message_context += USER_PREFERENCES_TPL.format(
                    user_preferences=user_preferences
                ).strip()

    return message_context
