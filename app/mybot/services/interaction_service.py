# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for handling pre-interaction logic.
"""
from contextlib import suppress
from typing import Dict, List, Optional

from loguru import logger
from telegram import Update, Message, Chat, Bot, User
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


def _extract_message_entities(message: Message) -> Dict[str, List[Dict]]:
    """
    提取消息中的所有实体信息（如链接、mention、hashtag等）
    """
    entities_info = {"text_entities": [], "caption_entities": []}

    # 处理消息文本中的实体
    if message.text and message.entities:
        for entity in message.entities:
            entity_text = message.text[entity.offset : entity.offset + entity.length]
            entities_info["text_entities"].append(
                {
                    "type": entity.type,
                    "offset": entity.offset,
                    "length": entity.length,
                    "text": entity_text,
                    "url": getattr(entity, 'url', None),
                    "user": getattr(entity, 'user', None),
                    "language": getattr(entity, 'language', None),
                }
            )

    # 处理caption中的实体
    if message.caption and message.caption_entities:
        for entity in message.caption_entities:
            entity_text = message.caption[entity.offset : entity.offset + entity.length]
            entities_info["caption_entities"].append(
                {
                    "type": entity.type,
                    "offset": entity.offset,
                    "length": entity.length,
                    "text": entity_text,
                    "url": getattr(entity, 'url', None),
                    "user": getattr(entity, 'user', None),
                    "language": getattr(entity, 'language', None),
                }
            )

    return entities_info


def _extract_forward_info(message: Message) -> Optional[Dict]:
    """
    提取转发消息的完整信息
    """
    if not message.forward_origin:
        return None

    forward_info = {"type": message.forward_origin.type, "date": message.forward_origin.date}

    # 根据不同的转发类型获取具体信息
    if hasattr(message.forward_origin, 'sender_user'):
        forward_info["sender_user"] = {
            "id": message.forward_origin.sender_user.id,
            "username": message.forward_origin.sender_user.username,
            "first_name": message.forward_origin.sender_user.first_name,
            "last_name": message.forward_origin.sender_user.last_name,
            "is_bot": message.forward_origin.sender_user.is_bot,
        }
    elif hasattr(message.forward_origin, 'sender_chat'):
        forward_info["sender_chat"] = {
            "id": message.forward_origin.sender_chat.id,
            "title": message.forward_origin.sender_chat.title,
            "username": message.forward_origin.sender_chat.username,
            "type": message.forward_origin.sender_chat.type,
        }
    elif hasattr(message.forward_origin, 'chat'):
        forward_info["chat"] = {
            "id": message.forward_origin.chat.id,
            "title": message.forward_origin.chat.title,
            "username": message.forward_origin.chat.username,
            "type": message.forward_origin.chat.type,
        }

    if hasattr(message.forward_origin, 'message_id'):
        forward_info["message_id"] = message.forward_origin.message_id

    if hasattr(message.forward_origin, 'sender_user_name'):
        forward_info["sender_user_name"] = message.forward_origin.sender_user_name

    if hasattr(message.forward_origin, 'author_signature'):
        forward_info["author_signature"] = message.forward_origin.author_signature

    return forward_info


def _extract_user_info(user: Optional[User]) -> Dict:
    """
    提取用户的完整信息
    """
    if not user:
        return {"id": 0, "username": "Anonymous", "display_name": "Anonymous"}

    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "display_name": user.full_name,
        "is_bot": user.is_bot,
        "is_premium": getattr(user, 'is_premium', None),
        "language_code": user.language_code,
        "link": user.link if hasattr(user, 'link') else None,
    }


def _extract_chat_info(chat: Optional[Chat]) -> Dict:
    """
    提取聊天的完整信息
    """
    if not chat:
        return {"id": 0, "title": "Unknown", "type": "unknown"}

    chat_info = {"id": chat.id, "title": chat.title, "username": chat.username, "type": chat.type}

    # 只有在属性存在时才添加
    if hasattr(chat, 'description') and chat.description:
        chat_info["description"] = chat.description

    if hasattr(chat, 'invite_link') and chat.invite_link:
        chat_info["invite_link"] = chat.invite_link

    if hasattr(chat, 'pinned_message') and chat.pinned_message:
        chat_info["pinned_message"] = chat.pinned_message.message_id

    if hasattr(chat, 'permissions') and chat.permissions:
        chat_info["permissions"] = chat.permissions.to_dict()

    if hasattr(chat, 'slow_mode_delay') and chat.slow_mode_delay:
        chat_info["slow_mode_delay"] = chat.slow_mode_delay

    if hasattr(chat, 'link') and chat.link:
        chat_info["link"] = chat.link

    return chat_info


def _extract_reply_info(message: Message) -> Optional[Dict]:
    """
    提取回复消息的完整信息
    """
    if not message.reply_to_message:
        return None

    reply_msg = message.reply_to_message

    reply_info = {
        "message_id": reply_msg.message_id,
        "date": reply_msg.date,
        "text": reply_msg.text,
        "caption": reply_msg.caption,
        "user_info": _extract_user_info(reply_msg.from_user),
        "chat_info": _extract_chat_info(reply_msg.sender_chat) if reply_msg.sender_chat else None,
        "entities": _extract_message_entities(reply_msg),
        "forward_info": _extract_forward_info(reply_msg),
        "has_media": bool(
            reply_msg.photo
            or reply_msg.video
            or reply_msg.document
            or reply_msg.audio
            or reply_msg.voice
            or reply_msg.video_note
            or reply_msg.sticker
            or reply_msg.animation
        ),
        "media_type": None,
    }

    # 确定媒体类型
    if reply_msg.photo:
        reply_info["media_type"] = "photo"
    elif reply_msg.video:
        reply_info["media_type"] = "video"
    elif reply_msg.document:
        reply_info["media_type"] = "document"
    elif reply_msg.audio:
        reply_info["media_type"] = "audio"
    elif reply_msg.voice:
        reply_info["media_type"] = "voice"
    elif reply_msg.video_note:
        reply_info["media_type"] = "video_note"
    elif reply_msg.sticker:
        reply_info["media_type"] = "sticker"
    elif reply_msg.animation:
        reply_info["media_type"] = "animation"

    # 如果回复的消息也是转发消息，获取其转发信息
    if reply_msg.forward_origin:
        reply_info["is_forwarded"] = True
        reply_info["forward_info"] = _extract_forward_info(reply_msg)
    else:
        reply_info["is_forwarded"] = False

    return reply_info


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

    # 避免处理机器人自己发送的消息，防止循环回复
    if message.from_user.is_bot and message.from_user.username == bot.username:
        return None

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
    Enhanced version that captures more complete message context.
    """
    # 使用 effective_* 方法获取有效的聊天和消息
    chat = update.effective_chat
    trigger_message = update.effective_message
    effective_user = update.effective_user

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

    # 提取完整的用户信息
    user_info = _extract_user_info(effective_user)
    if trigger_message.sender_chat:
        user_info.update(_extract_chat_info(trigger_message.sender_chat))
        from_user_fmt = (
            f"{user_info.get('username') or user_info.get('title', 'Unknown')}({user_info['id']})"
        )
    else:
        from_user_fmt = f"{user_info.get('username') or user_info.get('display_name', 'Unknown')}({user_info['id']})"

    # 提取消息实体（富文本信息）
    entities_info = _extract_message_entities(trigger_message)

    # 提取转发信息
    forward_info = _extract_forward_info(trigger_message)

    # 提取回复信息
    reply_info = _extract_reply_info(trigger_message)

    # Download photos
    photo_paths = None
    if trigger_message.photo:
        photo_paths = await _download_photos_from_message(trigger_message, context.bot)

    # 处理 MENTION_WITH_REPLY 模式下的回复消息图片
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

    # 创建增强的 Interaction 对象
    return Interaction(
        task_type=task_type,
        from_user_fmt=from_user_fmt,
        photo_paths=photo_paths,
        # 添加新的上下文信息
        user_info=user_info,
        entities_info=entities_info,
        forward_info=forward_info,
        reply_info=reply_info,
        chat_info=_extract_chat_info(chat),
    )
