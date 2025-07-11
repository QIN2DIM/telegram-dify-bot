# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for building message contexts for LLM.
"""
from typing import Dict, List, Any

from telegram import Update, Message
from telegram.ext import ContextTypes

from models import TaskType, Interaction
from mybot.prompts import (
    MESSAGE_FORMAT_TEMPLATE,
    MENTION_PROMPT_TEMPLATE,
    MENTION_WITH_REPLY_PROMPT_TEMPLATE,
    REPLY_SINGLE_PROMPT_TEMPLATE,
    USER_PREFERENCES_TPL,
    HTML_STYLE_TPL,
    CONTEXT_PART,
    MESSAGE_SEPARATOR,
)
from settings import settings


def _format_entities_info(entities_info: Dict[str, List[Dict]]) -> str:
    """
    格式化实体信息为可读文本
    """
    if not entities_info:
        return ""

    formatted_entities = []

    # 处理文本实体
    for entity in entities_info.get("text_entities", []):
        if entity["type"] == "url":
            formatted_entities.append(f"链接: {entity['text']}")
        elif entity["type"] == "text_link":
            formatted_entities.append(f"链接: {entity['text']} -> {entity.get('url', '')}")
        elif entity["type"] == "mention":
            formatted_entities.append(f"提及: {entity['text']}")
        elif entity["type"] == "hashtag":
            formatted_entities.append(f"话题: {entity['text']}")
        elif entity["type"] == "cashtag":
            formatted_entities.append(f"股票: {entity['text']}")
        elif entity["type"] == "phone_number":
            formatted_entities.append(f"电话: {entity['text']}")
        elif entity["type"] == "email":
            formatted_entities.append(f"邮箱: {entity['text']}")
        elif entity["type"] == "bold":
            formatted_entities.append(f"粗体: {entity['text']}")
        elif entity["type"] == "italic":
            formatted_entities.append(f"斜体: {entity['text']}")
        elif entity["type"] == "code":
            formatted_entities.append(f"代码: {entity['text']}")
        elif entity["type"] == "pre":
            formatted_entities.append(f"代码块: {entity['text']}")

    # 处理caption实体
    for entity in entities_info.get("caption_entities", []):
        if entity["type"] == "url":
            formatted_entities.append(f"图片说明中的链接: {entity['text']}")
        elif entity["type"] == "text_link":
            formatted_entities.append(
                f"图片说明中的链接: {entity['text']} -> {entity.get('url', '')}"
            )
        elif entity["type"] == "mention":
            formatted_entities.append(f"图片说明中的提及: {entity['text']}")
        elif entity["type"] == "hashtag":
            formatted_entities.append(f"图片说明中的话题: {entity['text']}")

    return "\n".join(formatted_entities) if formatted_entities else ""


def _format_forward_info(forward_info: Dict[str, Any]) -> str:
    """
    格式化转发信息为可读文本
    """
    if not forward_info:
        return ""

    forward_text = f"转发消息类型: {forward_info.get('type', 'unknown')}\n"
    forward_text += f"转发时间: {forward_info.get('date', '')}\n"

    if "sender_user" in forward_info:
        user = forward_info["sender_user"]
        forward_text += f"原始发送者: {user.get('username', '')} ({user.get('first_name', '')} {user.get('last_name', '')}, ID: {user.get('id', '')})\n"
    elif "sender_chat" in forward_info:
        chat = forward_info["sender_chat"]
        forward_text += f"原始发送频道/群组: {chat.get('title', '')} (@{chat.get('username', '')}, ID: {chat.get('id', '')})\n"
    elif "chat" in forward_info:
        chat = forward_info["chat"]
        forward_text += f"转发来源: {chat.get('title', '')} (@{chat.get('username', '')}, ID: {chat.get('id', '')})\n"

    if "sender_user_name" in forward_info:
        forward_text += f"签名: {forward_info['sender_user_name']}\n"

    if "author_signature" in forward_info:
        forward_text += f"作者签名: {forward_info['author_signature']}\n"

    return forward_text.strip()


def _format_reply_info(reply_info: Dict[str, Any]) -> str:
    """
    格式化回复信息为可读文本
    """
    if not reply_info:
        return ""

    reply_text = ""
    # reply_text = f"回复消息ID: {reply_info.get('message_id', '')}\n"
    # reply_text += f"回复时间: {reply_info.get('date', '')}\n"

    # 用户信息
    # if reply_info.get("user_info"):
    #     user = reply_info["user_info"]
    #     reply_text += f"被回复用户: {user.get('username', '')} ({user.get('display_name', '')}, ID: {user.get('id', '')})\n"

    # 消息内容
    # if reply_info.get("text"):
    #     reply_text += f"被回复消息内容: {reply_info['text']}\n"
    # elif reply_info.get("caption"):
    #     reply_text += f"被回复消息说明: {reply_info['caption']}\n"

    # 媒体类型
    if reply_info.get("has_media"):
        reply_text += f"媒体类型: {reply_info.get('media_type', 'unknown')}\n"

    # 实体信息
    if reply_info.get("entities"):
        entities_text = _format_entities_info(reply_info["entities"])
        if entities_text:
            reply_text += f"被回复消息中的链接和格式:\n{entities_text}\n"

    # 转发信息
    if reply_info.get("is_forwarded") and reply_info.get("forward_info"):
        forward_text = _format_forward_info(reply_info["forward_info"])
        if forward_text:
            reply_text += f"被回复消息的转发信息:\n{forward_text}\n"

    return reply_text.strip()


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
    history_messages = ""
    if bot_message:
        history_messages = await _format_message(bot_message)
    user_preferences = ""
    return history_messages, user_preferences


async def build_message_context(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    task_type: TaskType,
    interaction: Interaction = None,
) -> str:
    """
    构建用于 LLM 的消息上下文
    增强版本，包含富文本信息、转发信息、回复信息等
    """
    trigger_message = update.effective_message
    message_text = trigger_message.text or trigger_message.caption or ""
    message_context = message_text or "请分析这张图片"

    # 基础上下文信息
    context_parts = []

    # 添加用户信息
    if interaction and interaction.user_info:
        user_info = interaction.user_info
        # context_parts.append(
        #     f"用户信息: {user_info.get('display_name', 'Unknown')} (@{user_info.get('username', 'N/A')}, ID: {user_info.get('id', 'N/A')})"
        # )
        if user_info.get('language_code'):
            context_parts.append(f"用户语言: {user_info['language_code']}")

    # 添加实体信息（富文本）
    if interaction and interaction.entities_info:
        entities_text = _format_entities_info(interaction.entities_info)
        if entities_text and entities_text != f"提及: @{context.bot.username}":
            context_parts.append(f"消息中的链接和格式信息:\n{entities_text}")

    # 添加转发信息
    if interaction and interaction.forward_info:
        forward_text = _format_forward_info(interaction.forward_info)
        if forward_text:
            context_parts.append(f"转发消息信息:\n{forward_text}")

    # 处理不同的任务类型
    if task_type == TaskType.MENTION:
        history_messages = await _get_chat_history_for_mention(
            update.effective_chat.id, trigger_message.message_id, context.bot
        )
        user_query = await _format_message(trigger_message)

        # 添加上下文信息
        if context_parts:
            part_ = CONTEXT_PART.format(context_part="\n".join(context_parts)).strip()
            user_query += "\n\n" + part_

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

        # 添加回复信息
        if interaction and interaction.reply_info:
            reply_context = _format_reply_info(interaction.reply_info)
            if reply_context:
                # reply_text += f"\n\n回复消息的详细信息:\n{reply_context}"
                reply_text += f"\n\n<metadata>\n{reply_context}\n</metadata>"

        message_context = MENTION_WITH_REPLY_PROMPT_TEMPLATE.format(
            message_text=message_text, reply_text=reply_text
        ).strip()

        # 添加当前消息的上下文信息
        if context_parts:
            part_ = CONTEXT_PART.format(context_part="\n".join(context_parts)).strip()
            message_context += f"\n\n{part_}"

    elif task_type == TaskType.REPLAY and trigger_message.reply_to_message:
        history_messages, user_preferences = await _get_reply_mode_context(
            update.effective_chat,
            trigger_message,
            trigger_message.reply_to_message,
            trigger_message.from_user.id if trigger_message.from_user else 0,
            context.bot,
        )

        # 添加回复信息
        if interaction and interaction.reply_info:
            reply_context = _format_reply_info(interaction.reply_info)
            if reply_context:
                history_messages += f"\n\n<metadata>\n{reply_context}\n</metadata>"

        if history_messages:
            message_context = REPLY_SINGLE_PROMPT_TEMPLATE.format(
                user_query=message_text, history_messages=history_messages
            ).strip()
            if user_preferences:
                message_context += USER_PREFERENCES_TPL.format(
                    user_preferences=user_preferences
                ).strip()

        # 添加当前消息的上下文信息
        if context_parts:
            part_ = CONTEXT_PART.format(context_part="\n".join(context_parts)).strip()
            message_context += f"\n\n{part_}"

    else:
        # 对于其他任务类型，直接添加上下文信息
        if context_parts:
            message_context += "\n\n" + "\n".join(context_parts)

    # Guidelines for Adding Telegram HTML Parse Mode
    if settings.BOT_ANSWER_PARSE_MODE == "HTML":
        message_context = f"{message_context}\n{MESSAGE_SEPARATOR}{HTML_STYLE_TPL.strip()}".strip()

    return message_context.strip()
