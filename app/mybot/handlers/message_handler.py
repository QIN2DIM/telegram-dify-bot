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

from mybot.services import interaction_service, context_service, dify_service, response_service
from settings import settings
from triggers.auto_translation import process_auto_translation


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Orchestrates the bot's response to a new message.
    """
    # 检查是否需要进行自动翻译
    if await process_auto_translation(update, context):
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
            )
            await response_service.send_streaming_response(
                update, context, interaction, streaming_generator
            )
        except Exception as e:
            logger.error(f"Streaming invocation failed: {e}")
    else:  # Blocking mode
        try:
            result_text = await dify_service.invoke_model_blocking(
                bot_username=bot_username,
                message_context=message_context,
                from_user=interaction.from_user_fmt,
                photo_paths=interaction.photo_paths,
            )
            if result_text:
                await response_service.send_standard_response(
                    update, context, interaction, result_text
                )
        except Exception as e:
            logger.error(f"Blocking invocation failed: {e}")
