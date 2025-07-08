# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 00:47
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from contextlib import suppress

from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

from dify.workflow_tool import direct_translation_tool
from models import TaskType
from mybot.cli import auto_translation_enabled_chats
from mybot.common import (
    _cleanup_old_photos,
    storage_messages_dataset,
    _is_available_direct_translation,
    _download_photos_from_message,
)
from utils import get_hello_reply


async def translation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理翻译请求，支持文本和图片

    功能特性：
    - 支持四种任务类型：MENTION, MENTION_WITH_REPLY, REPLAY, AUTO
    - 自动下载并处理图片（选择最高质量版本）
    - 处理引用消息中的文本和图片内容
    - 根据任务类型采用不同的回复策略
    - 自动清理过期的临时图片文件
    - 完整的错误处理和日志记录
    """
    chat = update.effective_chat
    trigger_message = update.effective_message

    # 定期清理旧的下载图片（每次处理时都尝试清理）
    with suppress(Exception):
        await _cleanup_old_photos(max_age_hours=24)

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

    placeholder_message = None

    if task_type == TaskType.MENTION:
        # 提及我，但没有输入任何内容且没有图片
        real_text = (trigger_message.text or "").replace(f"@{context.bot.username}", "")
        if not real_text.strip() and not trigger_message.photo and not trigger_message.caption:
            await trigger_message.reply_text(get_hello_reply())
            return
        # MENTION: 回复被@的消息
        placeholder_message = await trigger_message.reply_text("⏳")
    elif task_type == TaskType.MENTION_WITH_REPLY:
        # MENTION_WITH_REPLY: 回复被@的消息（用户引用材料并@机器人）
        placeholder_message = await trigger_message.reply_text("🔄")
    elif task_type == TaskType.REPLAY:
        # REPLAY: 不回复消息，而是mention用户
        placeholder_message = await context.bot.send_message(
            chat_id=chat.id,
            text=f"@{trigger_message.from_user.username or trigger_message.from_user.first_name} ⚡",
        )
    elif task_type == TaskType.AUTO:
        # AUTO: 直接发在群里，不打扰任何人，不使用placeholder
        pass

    logger.debug(f"{task_type=}")
    # AUTO模式下不需要placeholder，直接处理
    if task_type != TaskType.AUTO and not placeholder_message:
        return

    # 准备用户信息
    from_user_fmt = "Anonymous"
    if trigger_message.sender_chat:
        _user = trigger_message.sender_chat
        from_user_fmt = f"{_user.username}({_user.id})"
    elif trigger_message.from_user:
        _user = trigger_message.from_user
        from_user_fmt = f"{_user.username}({_user.id})"

    # 处理消息内容和图片
    message_text = trigger_message.text or trigger_message.caption or ""

    # 处理引用消息的内容（MENTION_WITH_REPLY情况）
    if task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        reply_text = (
            trigger_message.reply_to_message.text or trigger_message.reply_to_message.caption or ""
        )
        if reply_text:
            # 将引用消息的内容添加到上下文中
            message_text = (
                f"<query>\n{message_text}\n</query>\n\n<quote_content>\n{reply_text}\n</quote_content>"
                if message_text
                else f"<quote_content>\n{reply_text}\n</quote_content>"
            )

    # 下载图片（如果有的话）
    photo_paths = None
    if trigger_message.photo:
        try:
            photo_paths = await _download_photos_from_message(trigger_message, context.bot)
            if photo_paths:
                logger.info(f"Downloaded {len(photo_paths)} photos for translation")
        except Exception as e:
            logger.error(f"Failed to download photos: {e}")

    # 处理引用消息中的图片（MENTION_WITH_REPLY情况）
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

    result = await direct_translation_tool(
        message_context=message_text or "请分析这张图片",
        from_user=from_user_fmt,
        with_files=photo_paths,
    )
    result_text = result.data.outputs.answer

    # 根据不同的task_type采用不同的回复方式
    if task_type == TaskType.MENTION or task_type == TaskType.MENTION_WITH_REPLY:
        # MENTION 和 MENTION_WITH_REPLY: 删除placeholder并回复原消息
        if placeholder_message:
            await placeholder_message.delete()
        await trigger_message.reply_text(result_text, parse_mode="Markdown")

    elif task_type == TaskType.REPLAY:
        # REPLAY: 删除placeholder并mention用户回复
        if placeholder_message:
            await placeholder_message.delete()
        user_mention = (
            f"@{trigger_message.from_user.username}"
            if trigger_message.from_user.username
            else trigger_message.from_user.mention_markdown_v2()
        )
        final_text = f"{user_mention}\n\n{result_text}"
        await context.bot.send_message(chat_id=chat.id, text=final_text, parse_mode="Markdown")

    elif task_type == TaskType.AUTO:
        # AUTO: 直接发在群里，不打扰任何人
        await context.bot.send_message(chat_id=chat.id, text=result_text, parse_mode="Markdown")
