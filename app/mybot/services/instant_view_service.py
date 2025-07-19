# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for handling Instant View rendering.
"""
from typing import Dict, Any, Optional

from loguru import logger
from telegram import Bot
from telegram.constants import ParseMode

from dify.models import AnswerType
from plugins.instant_view_generator.node import create_instant_view


async def render_instant_view(
    bot: Bot,
    chat_id: int,
    message_id: int,
    content: str,
    extras: Dict[str, Any],
    final_type: str,
    title: Optional[str] = None,
    input_format: ParseMode = ParseMode.MARKDOWN,
) -> bool:
    """
    Render content as Instant View

    Args:
        input_format:
        bot: Telegram bot instance
        chat_id: Chat ID
        message_id: Message ID to edit
        content: Content to render
        extras: Extra data containing photo_links, place_name, etc.
        final_type: Answer type
        title: Optional title for instant view

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        instant_view_content = content

        # If it's geolocation identification task with photos, integrate them into Instant View content
        photo_links = extras.get("photo_links", [])
        place_name = extras.get("place_name", "")
        if final_type == AnswerType.GEOLOCATION_IDENTIFICATION and photo_links:
            # Add photo links to Markdown content
            instant_view_content += "\n\n"
            if place_name:
                instant_view_content += f"## {place_name}\n\n"

            # Add images to Markdown
            for i, photo_url in enumerate(photo_links):
                if i == 0:
                    instant_view_content += f"![Street View]({photo_url})\n\n"
                else:
                    instant_view_content += f"![Street View {i+1}]({photo_url})\n\n"

        response = await create_instant_view(
            content=instant_view_content,
            input_format="HTML" if input_format in [ParseMode.HTML] else "Markdown",
            title=title or extras.get("title"),
        )

        if response.success:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                parse_mode=ParseMode.HTML,
                text=response.instant_view_content.strip(),
            )
            return True
        else:
            logger.warning(f"Failed to create instant view: {response}")
            return False

    except Exception as e:
        logger.error(f"Failed to render instant view: {e}")
        return False


async def try_send_as_instant_view(
    bot: Bot,
    chat_id: int,
    message_id: int,
    content: str,
    extras: Dict[str, Any] = None,
    final_type: str = "",
    title: Optional[str] = None,
    parse_mode: ParseMode = ParseMode.HTML,
) -> bool:
    """
    Try to send content as Instant View when a regular message fails

    Args:
        parse_mode:
        bot: Telegram bot instance
        chat_id: Chat ID
        message_id: Message ID to edit
        content: Content to send
        extras: Extra data, defaults to empty dict
        final_type: Answer type
        title: Optional title for instant view

    Returns:
        bool: True if successful, False otherwise
    """
    extras = extras or {}

    logger.info("Attempting to send content as Instant View due to message length limit")
    return await render_instant_view(
        bot=bot,
        chat_id=chat_id,
        message_id=message_id,
        content=content,
        extras=extras,
        final_type=final_type,
        title=title,
        input_format=parse_mode,
    )
