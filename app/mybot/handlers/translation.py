# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 00:47
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
from contextlib import suppress

from loguru import logger
from telegram import Update, Message
from telegram.ext import ContextTypes

from dify.workflow_tool import direct_translation_tool
from models import TaskType
from mybot.cli import auto_translation_enabled_chats
from mybot.common import (
    storage_messages_dataset,
    _is_available_direct_translation,
    _download_photos_from_message,
)
from prompts import (
    MENTION_PROMPT_TEMPLATE,
    MENTION_WITH_REPLY_PROMPT_TEMPLATE,
    REPLY_PROMPT_TEMPLATE,
    MESSAGE_FORMAT_TEMPLATE,
    USER_PREFERENCES_TPL,
)
from utils import get_hello_reply


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
    """获取 MENTION 模式的历史消息

    注意：由于 Telegram Bot API 限制，无法直接获取历史消息。
    这里返回空字符串，实际项目中应该从数据库或缓存中获取。
    """
    # TODO: 从存储的消息数据集中获取历史消息
    # 可以使用 storage_messages_dataset 存储的数据
    logger.debug(f"Attempting to get chat history for chat {chat_id}, message {trigger_message_id}")

    # 临时返回空历史记录
    # 在实际实现中，应该从数据库查询历史消息
    return ""


async def _get_reply_mode_context(
    chat,
    user_message: Message,
    bot_message: Message,
    user_id: int,
    bot,
    context_range: int = 15,
    user_bot_history_limit: int = 20,
    days_limit: int = 7,
) -> tuple[str, str]:
    """获取 REPLY 模式的上下文消息和用户偏好消息

    返回格式化后的历史消息字符串和用户偏好字符串
    """
    logger.debug(f"Getting reply mode context for user {user_id} in chat {chat.id}")

    # 格式化被引用的机器人消息作为历史消息
    history_messages = ""
    if bot_message:
        # 使用现有的格式化函数来格式化机器人消息
        formatted_bot_message = await _format_message(bot_message)
        history_messages = formatted_bot_message

    # 暂时返回空的用户偏好，因为没有数据库功能
    # 在实际实现中，应该从数据库查询用户与机器人的历史交互记录
    user_preferences = ""

    return history_messages, user_preferences


async def translation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理翻译请求，支持文本和图片

    功能特性：
    - 支持四种任务类型：MENTION, MENTION_WITH_REPLY, REPLAY, AUTO
    - 通过对用户消息添加表情回应来确认收到请求
    - 自动下载并处理图片（选择最高质量版本）
    - 处理引用消息中的文本和图片内容
    - 根据不同模式构建上下文，携带历史消息和用户偏好
    - 统一的回复策略（按优先级）：
      1. 尝试直接回复触发消息
      2. 如果失败，尝试@mention用户
      3. 最后兜底：直接发送消息到群组
    - 自动清理过期的临时图片文件
    - 完整的错误处理和日志记录
    """
    chat = update.effective_chat
    trigger_message = update.effective_message

    # ==================== Section 1: LLM触发前交互 ====================

    # todo: remove
    with suppress(Exception):
        storage_messages_dataset(chat.type, trigger_message)

    # 检查当前聊天是否启用了自动翻译模式
    is_auto_mode = chat.id in auto_translation_enabled_chats

    task_type = _is_available_direct_translation(
        chat, trigger_message, context.bot, is_auto_trigger=is_auto_mode
    )
    if not task_type or not isinstance(task_type, TaskType):
        return

    if task_type == TaskType.MENTION:
        # 提及我，但没有输入任何内容且没有图片
        real_text = (trigger_message.text or "").replace(f"@{context.bot.username}", "")
        if not real_text.strip() and not trigger_message.photo and not trigger_message.caption:
            await trigger_message.reply_text(get_hello_reply())
            return
        # MENTION: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤔"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")
    elif task_type == TaskType.MENTION_WITH_REPLY:
        # MENTION_WITH_REPLY: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤔"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")
    elif task_type == TaskType.REPLAY:
        # REPLAY: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤔"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")
    elif task_type == TaskType.AUTO:
        # AUTO: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤖"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")

    logger.debug(f"{task_type=}")

    # 准备用户信息
    from_user_fmt = "Anonymous"
    if trigger_message.sender_chat:
        _user = trigger_message.sender_chat
        from_user_fmt = f"{_user.username}({_user.id})"
    elif trigger_message.from_user:
        _user = trigger_message.from_user
        from_user_fmt = f"{_user.username}({_user.id})"

    # 下载图片（如果有的话）
    photo_paths = None
    if trigger_message.photo:
        try:
            photo_paths = await _download_photos_from_message(trigger_message, context.bot)
            if photo_paths:
                logger.info(f"Downloaded {len(photo_paths)} photos for translation")
        except Exception as e:
            logger.error(f"Failed to download photos: {e}")

    # 处理引用消息中的图片（MENTION_WITH_REPLY）
    if task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        if trigger_message.reply_to_message.photo:
            try:
                reply_photo_paths = await _download_photos_from_message(
                    trigger_message.reply_to_message, context.bot
                )
                if reply_photo_paths:
                    photo_paths = (photo_paths or []) + reply_photo_paths
                    logger.info(f"Downloaded {len(reply_photo_paths)} photos from replied message")
            except Exception as e:
                logger.error(f"Failed to download photos from replied message: {e}")

    # ==================== Section 2: LLM调用 ====================

    # 构建消息上下文
    message_text = trigger_message.text or trigger_message.caption or ""
    message_context = message_text or "请分析这张图片"

    # 根据不同的 task_type 构建不同的上下文
    if task_type == TaskType.MENTION:
        # 获取历史消息
        history_messages = await _get_chat_history_for_mention(
            chat.id, trigger_message.message_id, context.bot
        )

        # 格式化当前用户查询
        user_query = await _format_message(trigger_message)

        # 使用模板构建完整上下文
        if history_messages:
            message_context = MENTION_PROMPT_TEMPLATE.format(
                user_query=user_query, history_messages=history_messages
            )

    elif task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        reply_text = (
            trigger_message.reply_to_message.text or trigger_message.reply_to_message.caption or ""
        )
        if reply_text:
            # 使用 MENTION_WITH_REPLY 模板
            message_context = MENTION_WITH_REPLY_PROMPT_TEMPLATE.format(
                message_text=message_text, reply_text=reply_text
            )

    elif task_type == TaskType.REPLAY:
        # 获取回复模式的上下文
        if trigger_message.reply_to_message:
            history_messages, user_preferences = await _get_reply_mode_context(
                chat,
                trigger_message,
                trigger_message.reply_to_message,
                trigger_message.from_user.id if trigger_message.from_user else 0,
                context.bot,
            )

            # 格式化当前用户查询
            user_query = message_text

            # 使用 REPLY 模板构建完整上下文
            if history_messages:
                message_context = REPLY_PROMPT_TEMPLATE.format(
                    user_query=user_query,
                    history_messages=history_messages or "无历史记录",
                )
                # Add 用户偏好记录
                if user_preferences:
                    message_context += USER_PREFERENCES_TPL.format(
                        user_preferences=user_preferences
                    )

    print(message_context)
    logger.debug(f"Built message context for {task_type}: {len(message_context)} chars")

    # 调用 LLM 进行处理
    result = await direct_translation_tool(
        bot_username=f"{context.bot.username.rstrip('@')}",
        message_context=message_context,
        from_user=from_user_fmt,
        with_files=photo_paths,
    )
    result_text = result.data.outputs.answer

    with suppress(Exception):
        outputs_json = json.dumps(
            result.data.outputs.model_dump(mode="json"), indent=2, ensure_ascii=False
        )
        logger.debug(f"LLM Result: \n{outputs_json}")

    # ==================== Section 3: 任务交付 ====================

    # 根据不同的task_type采用不同的回复方式
    if task_type in [TaskType.MENTION, TaskType.MENTION_WITH_REPLY, TaskType.REPLAY]:
        # 统一的回复逻辑：按优先级尝试不同的回复方式
        reply_sent = False

        # 方案1: 尝试直接回复触发消息
        try:
            await trigger_message.reply_text(result_text, parse_mode="Markdown")
            reply_sent = True
            logger.debug("Reply sent via direct reply to trigger message")
        except Exception as e:
            logger.debug(f"Failed to reply to trigger message: {e}")

        # 方案2: 如果方案1失败，尝试mention用户
        if not reply_sent:
            try:
                # 构建mention文本
                if trigger_message.from_user:
                    if trigger_message.from_user.username:
                        user_mention = f"@{trigger_message.from_user.username}"
                    else:
                        # 使用用户的名字作为文本mention（不是真正的mention，但至少能标识用户）
                        user_mention = trigger_message.from_user.first_name or "User"
                else:
                    user_mention = "User"

                final_text = f"{user_mention}\n\n{result_text}"
                await context.bot.send_message(
                    chat_id=chat.id, text=final_text, parse_mode="Markdown"
                )
                reply_sent = True
                logger.debug("Reply sent via mention")
            except Exception as e:
                logger.error(f"Failed to send message with mention: {e}")

        # 方案3: 最后的兜底方案 - 直接发送消息，不mention任何人
        if not reply_sent:
            try:
                await context.bot.send_message(
                    chat_id=chat.id, text=result_text, parse_mode="Markdown"
                )
                logger.debug("Reply sent directly without mention")
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    elif task_type == TaskType.AUTO:
        # AUTO: 直接发在群里，不打扰任何人
        await context.bot.send_message(chat_id=chat.id, text=result_text, parse_mode="Markdown")
