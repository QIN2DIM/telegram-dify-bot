# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/14 22:31
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from typing import Dict, Any, Optional

import telegram.error
from loguru import logger
from telegram import Message
from telegram.ext import ContextTypes

from mybot.services.instant_view_service import render_instant_view, try_send_as_instant_view
from settings import settings


async def _handle_answer_parts_final_answer(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    initial_message: Message,
    final_answer: str,
    extras: Dict[str, Any],
    final_type: str,
) -> Optional[int]:
    """Handle final answer rendering with fallback strategies"""
    # Try Instant View if explicitly requested
    if extras.get("is_instant_view"):
        success = await render_instant_view(
            bot=context.bot,
            chat_id=chat_id,
            message_id=initial_message.message_id,
            content=final_answer,
            extras=extras,
            final_type=final_type,
            title=extras.get("title"),
        )
        if success:
            return initial_message.message_id

    # Try general rich text rendering
    for parse_mode in settings.pending_parse_mode:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=initial_message.message_id,
                text=final_answer,
                parse_mode=parse_mode,
            )
            return initial_message.message_id
        except telegram.error.BadRequest as err:
            if "Message_too_long" in str(err):
                logger.info("Message too long, switching to Instant View")
                success = await try_send_as_instant_view(
                    bot=context.bot,
                    chat_id=chat_id,
                    message_id=initial_message.message_id,
                    content=final_answer,
                    extras=extras,
                    final_type=final_type,
                    title=extras.get("title"),
                    parse_mode=parse_mode,
                )
                if success:
                    return initial_message.message_id
                break
        except Exception as err:
            logger.exception(f"Failed to send final message({parse_mode}): {err}")

    # Final fallback to Instant View
    logger.warning("All parse modes failed, trying Instant View as fallback")
    success = await try_send_as_instant_view(
        bot=context.bot,
        chat_id=chat_id,
        message_id=initial_message.message_id,
        content=final_answer,
        extras=extras,
        final_type=final_type,
        title=extras.get("title"),
    )
    return initial_message.message_id if success else None
