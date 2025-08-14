# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/13 20:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Imagine command handler for generating images using Dify workflow
"""
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
    context: ContextTypes.DEFAULT_TYPE, chat: Chat, message: Message, prompt: str
) -> bool | None:
    # Check if prompt is provided
    if prompt:
        return False

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="请提供图片生成提示词\n\n使用方法:\n• <code>/imagine 你想生成的图片描述</code>\n",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
    except Exception as send_error:
        logger.error(f"发送提示失败: {send_error}")

    return True


@non_blocking_handler("imagine_command")
async def imagine_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate images using Dify workflow based on user prompts"""
    if update.inline_query:
        return

    # Extract prompt from arguments
    prompt = " ".join(context.args) if context.args else ""
    logger.debug(f"Invoke Imagine: {prompt}")

    message, chat = await _match_context(update)
    if not message or not chat:
        logger.warning("imagine 命令：无法找到有效的消息或聊天信息进行回复")
        return

    # Check if prompt is provided
    if await _reply_help(context, chat, message, prompt):
        return

    # Add reaction to indicate processing
    await _reply_emoji_reaction(context, chat, message)

    # Create Interaction object
    interaction = Interaction(
        task_type=TaskType.MENTION,
        from_user_fmt=str(message.from_user.id if message.from_user else "unknown"),
        photo_paths=[],
        media_files={},
    )

    # Get bot username
    bot_username = f"{context.bot.username.rstrip('@')}"

    # Invoke Dify service with streaming
    try:
        logger.info(f"Starting call to Dify image generation service: {prompt[:100]}...")

        forced_command = ForcedCommand.IMAGINE
        streaming_generator = dify_service.invoke_model_streaming(
            bot_username=bot_username,
            message_context=prompt,
            from_user=interaction.from_user_fmt,
            photo_paths=[],
            media_files={},
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
