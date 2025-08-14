# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/14 22:15
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from typing import Dict, Any, Optional

from loguru import logger
from telegram import InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from settings import settings


async def _handle_answer_parts_geolocation_identification(
    context: ContextTypes.DEFAULT_TYPE, chat: Any, extras: Dict[str, Any], reply_to_message_id
):
    photo_links = extras.get("photo_links", [])
    place_name = extras.get("place_name", "")

    if photo_links:
        await _send_street_view_images(
            context, chat.id, photo_links, place_name, reply_to_message_id=reply_to_message_id
        )


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
            media=media_group[:9],
            reply_to_message_id=reply_to_message_id,
            parse_mode=ParseMode.HTML,
        )
        return True
    except Exception as err:
        logger.exception(f"Failed to send media group: {err}")
        return False
