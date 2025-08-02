# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for sending responses to Telegram.
"""
import json
import time
from contextlib import suppress
from typing import AsyncGenerator, Dict, Any, Optional

import telegram.error
from loguru import logger
from telegram import Update, InputMediaPhoto, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from dify.models import AnswerType
from models import Interaction, TaskType, AGENT_STRATEGY_TYPE, AgentStrategy
from mybot.services.instant_view_service import render_instant_view, try_send_as_instant_view
from settings import settings

# Constants
LOADING_PLACEHOLDER = "🔄 Loading..."
INITIAL_PLANNING_TEXT = "🤔 Planning..."
ERROR_MESSAGE = "抱歉，处理过程中遇到问题，请稍后再试。"
FAILURE_MESSAGE = "抱歉，处理失败。"
AGENT_LOG_UPDATE_INTERVAL = 1.5
MEDIA_GROUP_LIMIT = 9


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


async def _send_photo_with_caption(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    photo_url: str,
    caption: str,
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send photo with caption, trying multiple parse modes"""
    for parse_mode in settings.pending_parse_mode:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_url,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode,
            )
            return True
        except Exception as err:
            logger.error(f"Failed to send photo with caption({parse_mode}): {err}")

    # Final fallback without parse mode
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_url,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )
        return True
    except Exception as e2:
        logger.error(f"Failed to send photo: {e2}")
        return False


async def _send_media_group_with_caption(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    photo_urls: list[str],
    caption: str,
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send media group with caption on first photo"""
    if not photo_urls:
        return False

    try:
        media_group = []
        for i, photo_url in enumerate(photo_urls):
            if i == 0:
                # First photo includes caption
                media_group.append(
                    InputMediaPhoto(media=photo_url, caption=caption, parse_mode=ParseMode.HTML)
                )
            else:
                media_group.append(InputMediaPhoto(media=photo_url, parse_mode=ParseMode.HTML))

        await context.bot.send_media_group(
            chat_id=chat_id,
            media=media_group[:MEDIA_GROUP_LIMIT],
            reply_to_message_id=reply_to_message_id,
            parse_mode=ParseMode.HTML,
        )
        return True
    except Exception as err:
        logger.exception(f"Failed to send media group: {err}")
        return False


def _parse_agent_log_data(
    agent_data: Dict[str, Any], agent_strategy_name: AGENT_STRATEGY_TYPE
) -> Dict[str, Any]:
    """Parse agent log data based on strategy type"""
    parsed_data = {
        "action": "",
        "thought": "",
        "output_text": "",
        "tool_input": [],
        "tool_call_name": "",
        "tool_response": "",
        "tool_call_input": {},
    }

    if agent_strategy_name == AgentStrategy.REACT:
        parsed_data["action"] = agent_data.get("action", agent_data.get("action_name", ""))
        agent_data_json = json.dumps(agent_data, indent=2, ensure_ascii=False)
        parsed_data["thought"] = f'<pre><code class="language-json">{agent_data_json}</code></pre>'

    elif agent_strategy_name == AgentStrategy.FUNCTION_CALLING:
        if output_pending := agent_data.get("output"):
            if isinstance(output_pending, str):
                parsed_data["output_text"] = output_pending
            elif isinstance(output_pending, dict):
                parsed_data["output_text"] = output_pending.get("llm_response", "")

        parsed_data["tool_input"] = agent_data.get("tool_input", [])
        parsed_data["tool_call_input"] = agent_data.get("tool_call_input", {})
        parsed_data["tool_call_name"] = agent_data.get("tool_call_name", "")
        parsed_data["tool_response"] = agent_data.get("tool_response", "")

    return parsed_data


def _format_agent_log(parsed_data: Dict[str, Any]) -> str:
    """Format parsed agent log data into display text"""
    agent_log_parts = []

    if action := parsed_data["action"]:
        agent_log_parts.append(f"<blockquote>Agent: {action}</blockquote>")

    if thought := parsed_data["thought"]:
        agent_log_parts.append(thought)

    if output_text := parsed_data["output_text"]:
        agent_log_parts.append(output_text)

    if tool_input := parsed_data["tool_input"]:
        for t in tool_input:
            if isinstance(t, dict) and "args" in t and "name" in t:
                block_language = t.get("args", {}).get("language", "json")
                tool_args_content = json.dumps(t["args"], indent=2, ensure_ascii=False)
                agent_log_parts.append(f"<blockquote>ToolUse: {t['name']}</blockquote>")
                agent_log_parts.append(
                    f'<pre><code class="language-{block_language}">{tool_args_content}</code></pre>'
                )

    if tool_call_name := parsed_data["tool_call_name"]:
        agent_log_parts.append(f"<blockquote>ToolUse: {tool_call_name}</blockquote>")

    if tool_call_input := parsed_data["tool_call_input"]:
        block_language = tool_call_input.get("language", "json")
        tool_args = json.dumps(tool_call_input, indent=2, ensure_ascii=False)
        agent_log_parts.append(
            f'<pre><code class="language-{block_language}">{tool_args}</code></pre>'
        )

    if tool_response := parsed_data["tool_response"]:
        agent_log_parts.append(f'<pre><code class="language-json">{tool_response}</code></pre>')

    return "\n\n".join(agent_log_parts)


async def _update_progress_message(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, text: str
) -> None:
    """Update progress message with error handling"""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode=ParseMode.HTML
        )
    except Exception as err:
        logger.error(f"Failed to update progress message: {err}")


async def _handle_final_answer_rendering(
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


async def _send_street_view_images(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    photo_links: list[str],
    place_name: str,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """Send street view images as supplementary information"""
    if not photo_links:
        return

    caption = f"<code>{place_name.strip()}</code>" if place_name else "Street View"

    if len(photo_links) > 1:
        await _send_media_group_with_caption(
            context, chat_id, photo_links, caption, reply_to_message_id=reply_to_message_id
        )
    else:
        await _send_photo_with_caption(
            context, chat_id, photo_links[0], caption, reply_to_message_id=reply_to_message_id
        )


async def send_standard_response(
    update: Update, context: ContextTypes.DEFAULT_TYPE, interaction: Interaction, result_text: str
):
    """Send standard response for blocking mode"""
    chat_id = update.effective_chat.id
    trigger_message = update.effective_message

    if interaction.task_type in [TaskType.MENTION, TaskType.MENTION_WITH_REPLY, TaskType.REPLAY]:
        # Try direct reply first
        sent = await _send_message(
            context, chat_id, result_text, reply_to_message_id=trigger_message.message_id
        )
        if sent:
            return

        # Fallback to mention user
        user_mention = "User"
        if trigger_message.from_user:
            user_mention = trigger_message.from_user.mention_html()
        final_text = f"{user_mention}\n\n{result_text}"
        await _send_message(context, chat_id, final_text)

    elif interaction.task_type == TaskType.AUTO:
        await _send_message(context, chat_id, result_text)


async def send_streaming_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    interaction: Interaction,
    streaming_generator: AsyncGenerator[Dict[str, Any], None],
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
            reply_to_message_id=(
                trigger_message.message_id if interaction.task_type != TaskType.AUTO else None
            ),
        )

        final_result = await _process_streaming_chunks(
            context, chat.id, initial_message, streaming_generator
        )

        await _handle_final_result(
            context, chat, initial_message, final_result, interaction, trigger_message
        )

    except Exception as e:
        logger.exception(f"Streaming response error: {e}")
        await _handle_streaming_error(context, chat.id, initial_message, trigger_message)


async def _process_streaming_chunks(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    initial_message: Message,
    streaming_generator: AsyncGenerator[Dict[str, Any], None],
) -> Optional[Dict[str, Any]]:
    """Process streaming chunks and update progress"""
    final_result = None
    agent_strategy_name = ""
    last_edit_time = time.time()

    async for chunk in streaming_generator:
        if not chunk or not isinstance(chunk, dict) or not (event := chunk.get("event")):
            continue

        chunk_data = chunk.get("data", {})

        if event == "workflow_finished":
            final_result = chunk_data.get('outputs', {})
            break

        elif event == "node_started":
            await _handle_node_started(
                context, chat_id, initial_message, chunk_data, agent_strategy_name
            )

        elif event == "agent_log":
            agent_strategy_name = await _handle_agent_log(
                context, chat_id, initial_message, chunk_data, agent_strategy_name, last_edit_time
            )
            last_edit_time = time.time()

    return final_result


async def _handle_node_started(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    initial_message: Message,
    chunk_data: Dict[str, Any],
    agent_strategy_name: str,
) -> str:
    """Handle node_started event"""
    node_type = chunk_data.get("node_type", "")
    node_title = chunk_data.get("title", "")
    node_index = chunk_data.get("index", 0)

    if agent_strategy := chunk_data.get("agent_strategy", {}):
        agent_strategy_name = agent_strategy.get("name", "")

    key_progress_text = ""
    if node_type in ["llm", "agent"] and node_title:
        key_progress_text = f"<blockquote>{node_title}</blockquote>"
    elif node_type == "tool" and node_title and node_index > 3:
        key_progress_text = f"<blockquote>✨ 工具使用：{node_title}</blockquote>"

    if key_progress_text:
        await _update_progress_message(
            context, chat_id, initial_message.message_id, key_progress_text
        )

    return agent_strategy_name


async def _handle_agent_log(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    initial_message: Message,
    chunk_data: Dict[str, Any],
    agent_strategy_name: str,
    last_edit_time: float,
) -> str:
    """Handle agent_log event"""
    if agent_data := chunk_data.get("data", {}):
        parsed_data = _parse_agent_log_data(agent_data, agent_strategy_name)
    elif (
        chunk_data.get("status") == "start"
        and agent_strategy_name == AgentStrategy.FUNCTION_CALLING
    ):
        parsed_data = {"action": "🤔 Thinking..."}
    else:
        return agent_strategy_name

    agent_log_text = _format_agent_log(parsed_data)

    if agent_log_text:
        now = time.time()
        if now - last_edit_time > AGENT_LOG_UPDATE_INTERVAL:
            await _update_progress_message(
                context, chat_id, initial_message.message_id, agent_log_text
            )

    return agent_strategy_name


async def _handle_final_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat: Any,
    initial_message: Message,
    final_result: Optional[Dict[str, Any]],
    interaction: Interaction,
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

    if not final_result or not (
        final_answer := final_result.get(settings.BOT_OUTPUTS_ANSWER_KEY, '')
    ):
        await context.bot.edit_message_text(
            chat_id=chat.id, message_id=initial_message.message_id, text=FAILURE_MESSAGE
        )
        return

    final_type = final_result.get(settings.BOT_OUTPUTS_TYPE_KEY, "")
    extras = final_result.get(settings.BOT_OUTPUTS_EXTRAS_KEY, {})

    # Render final answer
    final_answer_message_id = await _handle_final_answer_rendering(
        context, chat.id, initial_message, final_answer, extras, final_type
    )

    # Send supplementary street view images if applicable
    if final_type == AnswerType.GEOLOCATION_IDENTIFICATION:
        photo_links = extras.get("photo_links", [])
        place_name = extras.get("place_name", "")

        if photo_links:
            # Determine reply target
            street_view_reply_id = None
            if interaction.task_type != TaskType.AUTO:
                street_view_reply_id = final_answer_message_id or trigger_message.message_id

            await _send_street_view_images(
                context, chat.id, photo_links, place_name, reply_to_message_id=street_view_reply_id
            )


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
