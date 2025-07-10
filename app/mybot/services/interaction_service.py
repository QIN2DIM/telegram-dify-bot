# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for handling pre-interaction logic.
"""
from contextlib import suppress

from loguru import logger
from telegram import Update, Message, Chat, Bot
from telegram.ext import ContextTypes

from models import TaskType, Interaction
from mybot.common import (
    storage_messages_dataset,
    _download_photos_from_message,
    get_hello_reply,
    get_image_mention_prompt,
)
from mybot.handlers.command_handler import auto_translation_enabled_chats
from settings import settings


def _is_mention_bot(message: Message, bot_username: str) -> bool:
    """
    检查消息是否提及了指定的机器人
    """
    if message.text:
        for entity in message.entities:
            if entity.type == "mention":
                mentioned_username = message.text[entity.offset + 1 : entity.offset + entity.length]
                if mentioned_username == bot_username:
                    return True

    if message.caption:
        for entity in message.caption_entities:
            if entity.type == "mention":
                mentioned_username = message.caption[
                    entity.offset + 1 : entity.offset + entity.length
                ]
                if mentioned_username == bot_username:
                    return True

    return False


def _determine_task_type(
    chat: Chat, message: Message, bot: Bot, is_auto_trigger: bool = False
) -> TaskType | None:
    """
    判断是否需要进行直接翻译及翻译类型
    """
    if chat.id not in settings.whitelist:
        return None

    if message.from_user.is_bot:
        pass

    if message.reply_to_message:
        reply_user = message.reply_to_message.from_user
        if reply_user.is_bot and reply_user.username == bot.username:
            return TaskType.REPLAY
        if _is_mention_bot(message, bot.username):
            return TaskType.MENTION_WITH_REPLY

    if not is_auto_trigger and not message.entities and not message.caption_entities:
        return None

    if _is_mention_bot(message, bot.username):
        return TaskType.MENTION

    if is_auto_trigger and (message.text or message.photo or message.caption):
        return TaskType.AUTO

    return None


async def pre_interactivity(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Interaction | None:
    """
    Handles pre-interaction logic like task identification, reacting to messages, and downloading media.
    """
    chat = update.effective_chat
    trigger_message = update.effective_message

    with suppress(Exception):
        storage_messages_dataset(chat.type, trigger_message)

    is_auto_mode = chat.id in auto_translation_enabled_chats

    task_type = _determine_task_type(
        chat, trigger_message, context.bot, is_auto_trigger=is_auto_mode
    )

    if not task_type or not isinstance(task_type, TaskType):
        return None

    logger.debug(f"{task_type=}")

    # React to the message to show it's being processed
    reaction = "🤔"
    if task_type == TaskType.AUTO:
        reaction = "🤖"

    try:
        await context.bot.set_message_reaction(
            chat_id=chat.id, message_id=trigger_message.message_id, reaction=reaction
        )
    except Exception as e:
        logger.debug(f"Failed to set reaction: {e}")

    # Handle special cases for MENTION task
    if task_type == TaskType.MENTION:
        real_text = (trigger_message.text or trigger_message.caption or "").replace(
            f"@{context.bot.username}", ""
        )
        if not real_text.strip() and not trigger_message.photo:
            await trigger_message.reply_text(get_hello_reply())
            return None
        if trigger_message.photo and not real_text.strip():
            await trigger_message.reply_text(get_image_mention_prompt())
            return None

    # Prepare user info
    from_user_fmt = "Anonymous"
    if trigger_message.sender_chat:
        _user = trigger_message.sender_chat
        from_user_fmt = f"{_user.username or _user.title}({_user.id})"
    elif trigger_message.from_user:
        _user = trigger_message.from_user
        from_user_fmt = f"{_user.username or _user.first_name}({_user.id})"

    # Download photos
    photo_paths = None
    if trigger_message.photo:
        photo_paths = await _download_photos_from_message(trigger_message, context.bot)

    if (
        task_type == TaskType.MENTION_WITH_REPLY
        and trigger_message.reply_to_message
        and trigger_message.reply_to_message.photo
    ):
        reply_photo_paths = await _download_photos_from_message(
            trigger_message.reply_to_message, context.bot
        )
        if reply_photo_paths:
            photo_paths = (photo_paths or []) + reply_photo_paths

    return Interaction(task_type=task_type, from_user_fmt=from_user_fmt, photo_paths=photo_paths)
