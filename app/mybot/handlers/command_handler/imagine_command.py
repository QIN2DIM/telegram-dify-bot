# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/13 20:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Imagine command handler for generating images using Dify workflow
"""
import asyncio

import telegram
from loguru import logger
from telegram import ReactionTypeEmoji, Chat, Message
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from dify.models import ForcedCommand
from models import Interaction, TaskType
from mybot.services import dify_service, response_service
from mybot.task_manager import non_blocking_handler
from mybot.common import (
    should_ignore_command_in_group,
    add_message_to_media_group_cache,
    download_media_group_files,
)

EMOJI_REACTION = [ReactionTypeEmoji(emoji=telegram.constants.ReactionEmoji.FIRE)]


async def _match_context(update: Update):
    # Get message and chat info
    message = None
    chat = None

    if update.message:
        message = update.message
        chat = update.message.chat
    elif update.callback_query:
        message = update.callback_query.message
        chat = update.callback_query.message.chat if update.callback_query.message else None

    # Fallback to effective_* methods
    if not message or not chat:
        message = update.effective_message
        chat = update.effective_chat

    return message, chat


async def _reply_emoji_reaction(context: ContextTypes.DEFAULT_TYPE, chat: Chat, message: Message):
    try:
        await context.bot.set_message_reaction(
            chat_id=chat.id, message_id=message.message_id, reaction=EMOJI_REACTION
        )
    except Exception as reaction_error:
        logger.debug(f"无法设置消息反应: {reaction_error}")


async def _reply_help(
    context: ContextTypes.DEFAULT_TYPE, chat: Chat, message: Message, prompt: str, has_media: bool
) -> bool | None:
    # Check if prompt or media is provided
    if prompt or has_media:
        return False

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="请提供图片生成提示词或上传参考图片\n\n使用方法:\n• <code>/imagine 你想生成的图片描述</code>\n• <code>/imagine</code> + 发送参考图片\n• <code>/imagine 描述文字</code> + 发送参考图片\n",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
    except Exception as send_error:
        logger.error(f"发送提示失败: {send_error}")

    return True


async def _collect_media_group_files(message: Message, bot) -> tuple[dict, bool, list]:
    """
    Collect all media files from a message, handling media groups properly.

    When multiple photos are sent with a command, Telegram creates a media group
    where each photo is a separate message with the same media_group_id.
    We need to wait for all messages to arrive before processing.

    Smart wait logic:
    - If message is part of a media group, check if other messages are already cached
    - If cache already has multiple messages, skip waiting (message_handler already waited)
    - If cache only has this message, wait for others to arrive

    Args:
        message: The trigger message (with the command)
        bot: Bot instance

    Returns:
        Tuple of (media_files dict, has_media bool, photo_paths list)
    """
    from mybot.common import get_media_group_messages

    # Add current message to cache first
    add_message_to_media_group_cache(message)

    # If this message is part of a media group, check if we need to wait
    if message.media_group_id:
        # Check current cache state
        cached_messages = get_media_group_messages(message)
        initial_count = len(cached_messages)

        # If only this message is in cache, we need to wait for others
        # This happens when imagine_command is called directly from CommandHandler
        if initial_count <= 1:
            logger.debug(
                f"Media group {message.media_group_id}: only {initial_count} message(s) in cache, "
                "waiting for more..."
            )
            # Wait for other messages to be received and cached
            await asyncio.sleep(0.8)
            # Re-fetch after waiting
            cached_messages = get_media_group_messages(message)

        logger.info(
            f"Processing media group {message.media_group_id} with {len(cached_messages)} messages"
        )
        for idx, msg in enumerate(cached_messages):
            logger.debug(
                f"  Message {idx + 1}: id={msg.message_id}, "
                f"has_photo={bool(msg.photo)}, has_caption={bool(msg.caption)}"
            )

    # Now download all media from the group (or single message)
    media_files = await download_media_group_files(message, bot)

    # Check if any media was downloaded and log details
    has_media = False
    total_files = 0
    if media_files:
        for media_type, paths in media_files.items():
            if paths:
                has_media = True
                total_files += len(paths)
                logger.info(f"Downloaded {len(paths)} {media_type} for /imagine processing")

    if not has_media:
        logger.warning(f"No media files downloaded for message {message.message_id}")

    # For backward compatibility
    photo_paths = media_files.get("photos", []) if media_files else []

    return media_files, has_media, photo_paths


@non_blocking_handler("imagine_command")
async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate images using Dify workflow based on user prompts"""
    if update.inline_query:
        return

    # In group chats, only respond to commands with bot mention
    if should_ignore_command_in_group(update, context):
        logger.debug("Ignoring /imagine command in group without bot mention")
        return

    # Extract prompt from arguments
    prompt = " ".join(context.args) if context.args else ""
    logger.debug(f"Invoke Imagine: {prompt}")

    message, chat = await _match_context(update)
    if not message or not chat:
        logger.warning("imagine 命令：无法找到有效的消息或聊天信息进行回复")
        return

    # Process media files from current message (with media group support)
    media_files, has_media, photo_paths = await _collect_media_group_files(
        message, context.bot
    )

    # Also check for media in replied message (if user replied to a message with media)
    if message.reply_to_message:
        # Handle replied message's media group
        reply_media_files, reply_has_media, _ = await _collect_media_group_files(
            message.reply_to_message, context.bot
        )

        if reply_has_media and reply_media_files:
            # Merge media files from reply
            if not media_files:
                media_files = reply_media_files
                has_media = True
            else:
                for media_type, paths in reply_media_files.items():
                    if paths:
                        if media_type not in media_files:
                            media_files[media_type] = []
                        media_files[media_type].extend(paths)
                        has_media = True

            # Update photo_paths for backward compatibility
            if reply_media_files.get("photos"):
                photo_paths = (photo_paths or []) + reply_media_files["photos"]

    # Check if prompt or media is provided
    if await _reply_help(context, chat, message, prompt, has_media):
        return

    # Use default prompt for media-only generation
    if not prompt and has_media:
        prompt = "请参考附件信息"

    # Add reaction to indicate processing
    await _reply_emoji_reaction(context, chat, message)

    # Create Interaction object
    interaction = Interaction(
        task_type=TaskType.MENTION,
        from_user_fmt=str(message.from_user.id if message.from_user else "unknown"),
        photo_paths=photo_paths,
        media_files=media_files,
    )

    # Get bot username
    bot_username = f"{context.bot.username.rstrip('@')}"

    # Invoke Dify service with streaming
    try:
        logger.info(
            f"Starting call to Dify image generation service: {prompt[:100]}... (媒体文件: {has_media})"
        )

        forced_command = ForcedCommand.IMAGINE
        streaming_generator = dify_service.invoke_model_streaming(
            bot_username=bot_username,
            message_context=prompt,
            from_user=interaction.from_user_fmt,
            photo_paths=photo_paths,
            media_files=media_files,
            forced_command=forced_command,
        )

        await response_service.send_streaming_response(
            update, context, streaming_generator, forced_command=forced_command
        )

    except Exception as imagine_error:
        logger.error(f"Call to Dify image generation service failed: {imagine_error}")

        # Send error message
        await context.bot.send_message(
            chat_id=chat.id,
            text="❌ 图片生成过程中发生错误，请稍后再试",
            parse_mode='HTML',
            reply_to_message_id=message.message_id,
        )
