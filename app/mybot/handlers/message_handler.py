# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : The main message handler orchestrating services.
"""
from loguru import logger
from telegram import Update
from telegram.ext import ContextTypes

import asyncio
from mybot.task_manager import non_blocking_handler
from mybot.services import interaction_service, context_service, dify_service, response_service
from mybot.handlers.command_handler.search_command import search_command
from mybot.handlers.command_handler.imagine_command import imagine_command
from mybot.common import add_message_to_media_group_cache
from settings import settings


def _extract_command_from_message(message_text: str, bot_username: str) -> tuple[str, list[str]]:
    """
    从消息文本中提取命令和参数
    返回: (command_name, args_list)
    """
    if not message_text.startswith("/"):
        return "", []

    # Remove leading "/"
    text = message_text[1:].strip()

    # Split into parts
    parts = text.split()
    if not parts:
        return "", []

    command_part = parts[0]
    remaining_parts = parts[1:]

    # Handle @bot_mention in command
    if "@" in command_part:
        command_name = command_part.split("@")[0]
    else:
        command_name = command_part

    # Remove bot mention from arguments if present
    if remaining_parts and remaining_parts[0] == f"@{bot_username}":
        remaining_parts = remaining_parts[1:]

    return command_name, remaining_parts


async def _handle_media_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, command_name: str, args: list[str]
) -> bool:
    """
    处理包含媒体文件的命令
    返回: True 如果命令被处理，False 如果不是支持的媒体命令
    """
    if command_name == "search":
        context.args = args
        logger.debug(f"Detected /{command_name} command in message_handler with args: {args}")
        await search_command(update, context)
        return True
    elif command_name == "imagine":
        context.args = args
        logger.debug(f"Detected /{command_name} command in message_handler with args: {args}")
        await imagine_command(update, context)
        return True

    # 未来可以在这里添加其他支持媒体的命令
    # elif command_name == "other_media_command":
    #     context.args = args
    #     await other_media_command(update, context)
    #     return True

    return False


@non_blocking_handler("handle_message")
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Orchestrates the bot's response to a new message.
    """
    # Add message to media group cache first (for potential media group handling)
    message = update.effective_message
    if message:
        add_message_to_media_group_cache(message)

        # For media groups, wait a bit to collect all messages
        if message.media_group_id:
            # Small delay to allow other messages in the group to arrive
            await asyncio.sleep(0.5)

            # Check if we should process this group
            # Only the message with caption (or the last message if no caption) should trigger processing
            from mybot.common import get_media_group_messages

            group_messages = get_media_group_messages(message)

            # Find the message that should trigger processing (prefer one with caption)
            trigger_msg = None
            for msg in group_messages:
                if msg.caption or msg.text:
                    trigger_msg = msg
                    break

            # If no message has caption, use the last one
            if not trigger_msg and group_messages:
                trigger_msg = group_messages[-1]

            # Only proceed if this is the trigger message
            if trigger_msg and trigger_msg.message_id != message.message_id:
                # logger.debug(f"Skipping non-trigger message {message.message_id} in media group")
                return

    # Check if this is a command with media (photos/documents/etc)
    # When users send commands with media, Telegram doesn't recognize them as commands
    # so they get routed to message_handler instead of CommandHandler
    if message and (message.text or message.caption):
        message_text = (message.text or message.caption or "").strip()

        if message_text.startswith("/"):
            # In groups, only handle commands that mention this bot
            # In private chats, handle all commands
            bot_username = context.bot.username
            is_private_chat = message.chat.type == "private"
            is_for_this_bot = f"@{bot_username}" in message_text if bot_username else False

            if is_private_chat or is_for_this_bot:
                command_name, args = _extract_command_from_message(message_text, bot_username)

                # Try to handle as media command
                if await _handle_media_command(update, context, command_name, args):
                    return

    # 1. Determine task and perform pre-interaction
    interaction = await interaction_service.pre_interactivity(update, context)
    if not interaction:
        return

    # 2. Build context for the LLM
    message_context = await context_service.build_message_context(
        update, context, interaction.task_type, interaction
    )
    logger.debug(f"Message context:\n{message_context}")

    # 3. Invoke LLM and send response
    response_mode = settings.RESPONSE_MODE.lower()
    bot_username = f"{context.bot.username.rstrip('@')}"

    if response_mode == "streaming":
        try:
            streaming_generator = dify_service.invoke_model_streaming(
                bot_username=bot_username,
                message_context=message_context,
                from_user=interaction.from_user_fmt,
                photo_paths=interaction.photo_paths,
                media_files=interaction.media_files,
            )
            await response_service.send_streaming_response(update, context, streaming_generator)
        except Exception as e:
            logger.error(f"Streaming invocation failed: {e}")
    else:  # Blocking mode
        try:
            result_text = await dify_service.invoke_model_blocking(
                bot_username=bot_username,
                message_context=message_context,
                from_user=interaction.from_user_fmt,
                photo_paths=interaction.photo_paths,
                media_files=interaction.media_files,
            )
            if result_text:
                await response_service.send_standard_response(update, context, result_text)
        except Exception as e:
            logger.error(f"Blocking invocation failed: {e}")
