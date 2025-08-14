# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/14 21:45
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

import json
import time
from contextlib import suppress
from typing import AsyncGenerator
from typing import Dict, Any, Optional

import telegram.error
from loguru import logger
from telegram import Message
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from dify.models import AnswerType, ForcedCommand, WorkflowEvent
from mybot.services.instant_view_service import try_send_as_instant_view
from mybot.services.response_service import answer_parts
from mybot.services.response_service import streaming_parts
from mybot.services.response_service.event_handler import AGENT_LOG_UPDATE_INTERVAL, EventHandler
from settings import settings

# Constants
INITIAL_PLANNING_TEXT = "🤔 Planning..."
ERROR_MESSAGE = "抱歉，处理过程中遇到问题，请稍后再试。"
FAILURE_MESSAGE = "抱歉，处理失败。"
LOADING_PLACEHOLDER = "🔄 Loading..."


async def _process_streaming_chunks(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    initial_message: Message,
    streaming_generator: AsyncGenerator[Dict[str, Any], None],
    *,
    forced_command: ForcedCommand | None = None,
) -> Optional[Dict[str, Any]]:
    """Process streaming chunks and update progress"""
    final_result = None
    last_edit_time = time.time()

    event_handler = EventHandler(context, chat_id, initial_message.message_id)

    async for chunk in streaming_generator:
        if not chunk or not isinstance(chunk, dict) or not (event := chunk.get("event")):
            continue

        chunk_data = chunk.get("data", {})

        # print(f"{json.dumps(chunk, indent=2, ensure_ascii=False)}\n")

        if event == WorkflowEvent.WORKFLOW_FINISHED:
            final_result = chunk_data.get('outputs', {})
            break
        elif event == WorkflowEvent.NODE_STARTED:
            await streaming_parts.node_started(
                chunk_data, event_handler, forced_command=forced_command
            )
        elif event == WorkflowEvent.NODE_FINISHED:
            await streaming_parts.node_finished(
                chunk_data, event_handler, forced_command=forced_command
            )
        elif event == WorkflowEvent.AGENT_LOG:
            is_update_progress = time.time() - last_edit_time > AGENT_LOG_UPDATE_INTERVAL
            await streaming_parts.agent_log(
                context, event_handler, is_update_progress=is_update_progress
            )
            last_edit_time = time.time()

    return final_result


async def _handle_final_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat: Any,
    initial_message: Message,
    final_result: Optional[Dict[str, Any]],
    trigger_message: Message,
) -> None:
    """Handle final result rendering and supplementary content"""
    # Log the result
    with suppress(Exception):
        if final_result:
            outputs_json = json.dumps(final_result, indent=2, ensure_ascii=False)
            logger.debug(f"LLM Result: \n{outputs_json}")
        else:
            logger.warning("No final result")

    final_answer = final_result.get(settings.BOT_OUTPUTS_ANSWER_KEY, '')
    if not final_result or not final_answer:
        await context.bot.edit_message_text(
            chat_id=chat.id, message_id=initial_message.message_id, text=FAILURE_MESSAGE
        )
        return

    final_type = final_result.get(settings.BOT_OUTPUTS_TYPE_KEY, "")
    extras = final_result.get(settings.BOT_OUTPUTS_EXTRAS_KEY, {})

    # For IMAGE_GENERATION type, skip normal rendering as we'll handle it specially
    final_answer_message_id = None
    if final_type != AnswerType.IMAGE_GENERATION:
        # Render final answer normally for non-image generation types
        final_answer_message_id = await answer_parts.final_answer(
            context, chat.id, initial_message, final_answer, extras, final_type
        )

    # Handle Imagine type - send generated images with parameters
    if final_type == AnswerType.IMAGE_GENERATION:
        await answer_parts.image_generation(
            context, chat, trigger_message, initial_message, final_answer, extras
        )

    # Send supplementary street view images if applicable
    elif final_type == AnswerType.GEOLOCATION_IDENTIFICATION:
        reply_to_message_id = final_answer_message_id or trigger_message.message_id
        await answer_parts.geolocation_identification(context, chat, extras, reply_to_message_id)


async def _handle_streaming_error(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    initial_message: Optional[Message],
    trigger_message: Message,
) -> None:
    """Handle streaming errors gracefully"""
    if initial_message:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=initial_message.message_id, text=ERROR_MESSAGE
            )
        except Exception as e2:
            logger.error(f"Failed to edit message to error: {e2}")
    else:
        await _send_message(
            context, chat_id, ERROR_MESSAGE, reply_to_message_id=trigger_message.message_id
        )


async def _send_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
) -> bool:
    """Send message with graceful fallback for formatting errors and long messages"""

    # Try with different parse modes
    for parse_mode in settings.pending_parse_mode:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode,
            )
            return True
        except telegram.error.BadRequest as err:
            if "Message_too_long" in str(err).lower():
                logger.info(f"Message too long ({parse_mode}), switching to Instant View")
                return await _handle_message_too_long_fallback(
                    context, chat_id, text, reply_to_message_id, parse_mode=parse_mode
                )
            else:
                logger.error(f"Failed to send message({parse_mode}): {err}")
        except Exception as err:
            logger.error(f"Failed to send message({parse_mode}): {err}")

    # Final fallback without parse mode
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id
        )
        return True
    except telegram.error.BadRequest as err:
        if "Message_too_long" in str(err).lower():
            logger.info("Message too long (no parse mode), trying Instant View as final fallback")
            return await _handle_message_too_long_fallback(
                context, chat_id, text, reply_to_message_id
            )
        else:
            logger.error(f"Failed to send message: {err}")
    except Exception as e2:
        logger.error(f"Failed to send message: {e2}")

    return False


async def _handle_message_too_long_fallback(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    content: str,
    reply_to_message_id: Optional[int] = None,
    extras: Optional[Dict[str, Any]] = None,
    final_type: str = "",
    title: Optional[str] = None,
    parse_mode: Optional[ParseMode] = None,
) -> bool:
    """Handle message too long error by creating placeholder and using Instant View"""
    try:
        # Create placeholder message
        placeholder_message = await context.bot.send_message(
            chat_id=chat_id, text=LOADING_PLACEHOLDER, reply_to_message_id=reply_to_message_id
        )

        # Use Instant View to edit placeholder
        return await try_send_as_instant_view(
            bot=context.bot,
            chat_id=chat_id,
            message_id=placeholder_message.message_id,
            content=content,
            extras=extras or {},
            final_type=final_type,
            title=title,
            parse_mode=parse_mode,
        )
    except Exception as e:
        logger.error(f"Failed to handle message too long fallback: {e}")
        return False


async def send_standard_response(
    update: Update, context: ContextTypes.DEFAULT_TYPE, result_text: str
):
    """Send standard response for blocking mode"""
    chat_id = update.effective_chat.id
    trigger_message = update.effective_message

    # Try direct reply first
    if await _send_message(context, chat_id, result_text, trigger_message.message_id):
        return

    # Fallback to mention user
    user_mention = "User"
    if trigger_message.from_user:
        user_mention = trigger_message.from_user.mention_html()

    final_text = f"{user_mention}\n\n{result_text}"

    await _send_message(context, chat_id, final_text)


async def send_streaming_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    streaming_generator: AsyncGenerator[Dict[str, Any], None],
    *,
    forced_command: ForcedCommand | None = None,
):
    """Handle streaming response with live updates"""
    chat = update.effective_chat
    trigger_message = update.effective_message
    initial_message = None

    try:
        # Create an initial message
        initial_message = await context.bot.send_message(
            chat_id=chat.id,
            text=INITIAL_PLANNING_TEXT,
            reply_to_message_id=trigger_message.message_id,
        )

        final_result = await _process_streaming_chunks(
            context, chat.id, initial_message, streaming_generator, forced_command=forced_command
        )

        await _handle_final_result(context, chat, initial_message, final_result, trigger_message)

    except Exception as e:
        logger.exception(f"Streaming response error: {e}")
        await _handle_streaming_error(context, chat.id, initial_message, trigger_message)
