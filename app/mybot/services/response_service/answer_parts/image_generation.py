# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/14 22:16
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from loguru import logger
from telegram import InputMediaPhoto, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from settings import DATA_DIR


async def _handle_answer_parts_image_generation(
    context: ContextTypes.DEFAULT_TYPE,
    chat: Any,
    trigger_message: Message,
    initial_message: Message,
    final_answer: str,
    extras: Dict[str, Any],
):
    # Send the generated images with caption, using the initial message for visual streaming effect
    await _send_imagine_result(
        context=context,
        chat_id=chat.id,
        image_urls=extras.get("all_image_urls", []),
        params=extras.get("params", {}),
        reply_to_message_id=trigger_message.message_id,
        initial_message=initial_message,
        final_answer=final_answer,
    )


async def _download_image_from_url(url: str) -> Optional[Path]:
    """Download image from URL and save to temporary directory"""
    try:
        # Create temp directory for generated images
        temp_dir = DATA_DIR / "generated_images"
        temp_dir.mkdir(exist_ok=True)

        # Extract filename from URL or generate a unique one
        import uuid
        from urllib.parse import urlparse

        parsed_url = urlparse(url)
        filename = Path(parsed_url.path).name
        if not filename or not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            filename = f"generated_{uuid.uuid4().hex[:8]}.jpg"

        # Download the image
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Save to file
            file_path = temp_dir / filename
            file_path.write_bytes(response.content)
            logger.info(f"Downloaded image from {url} to {file_path}")
            return file_path

    except Exception as e:
        logger.error(f"Failed to download image from {url}: {e}")
        return None


async def _send_single_photo_with_caption(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    caption: str,
    reply_to_message_id: int,
    parse_mode: str,
    delete_message_id: int,
    photo: bytes,
):
    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            parse_mode=parse_mode,
        )
        await context.bot.delete_message(chat_id=chat_id, message_id=delete_message_id)
    except Exception as e:
        if "Message caption is too long" in str(e):
            logger.warning(f"Caption too long, sending photo without caption: {e}")
            await context.bot.send_photo(
                chat_id=chat_id, photo=photo, reply_to_message_id=reply_to_message_id
            )
        else:
            raise


async def _send_photo_group_with_caption(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    caption: str,
    reply_to_message_id: int,
    parse_mode: str,
    delete_message_id: int,
    downloaded_files: list,
):
    # Send as media group
    media_group = []
    for i, file_path in enumerate(downloaded_files):
        photo = Path(file_path).read_bytes()
        if i == 0:
            media_group.append(InputMediaPhoto(media=photo, caption=caption, parse_mode=parse_mode))
        else:
            media_group.append(InputMediaPhoto(media=photo))

    try:
        await context.bot.send_media_group(
            chat_id=chat_id, media=media_group, reply_to_message_id=reply_to_message_id
        )
        await context.bot.delete_message(chat_id=chat_id, message_id=delete_message_id)
    except Exception as e:
        if "Message caption is too long" in str(e):
            logger.warning(f"Caption too long, sending media group without caption: {e}")
            # Rebuild media group without caption
            media_group = []
            for file_path in downloaded_files:
                photo = Path(file_path).read_bytes()
                media_group.append(InputMediaPhoto(media=photo))
            await context.bot.send_media_group(
                chat_id=chat_id, media=media_group, reply_to_message_id=reply_to_message_id
            )
        else:
            raise


async def _send_imagine_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    image_urls: list[str],
    params: Dict[str, Any],
    reply_to_message_id: Optional[int] = None,
    initial_message: Optional[Message] = None,
    final_answer: Optional[str] = None,
):
    """Send generated image with parameters as caption, optionally editing an existing message"""
    if not image_urls:
        return False

    # Download images
    downloaded_files: list[Any] = []

    # Limit to telegram's max
    for url in image_urls[:9]:
        file_path = await _download_image_from_url(url)
        if file_path:
            downloaded_files.append(file_path)

    if not downloaded_files:
        logger.error("Failed to download any images")
        return False

    # Use final_answer as caption if provided, otherwise use params
    if final_answer:
        caption_markdown = final_answer
        caption_html = final_answer
    else:
        caption_markdown = params.get("caption_markdown", "")
        caption_html = params.get("caption_html", caption_markdown)

    # Try to send with HTML first (since final_answer is usually HTML formatted)
    parse_modes = [ParseMode.HTML, ParseMode.MARKDOWN_V2, None]

    for parse_mode in parse_modes:
        caption = caption_html if parse_mode == ParseMode.HTML else caption_markdown
        try:
            # Send single photo with caption
            if len(downloaded_files) == 1:
                photo = Path(downloaded_files[0]).read_bytes()
                await _send_single_photo_with_caption(
                    context=context,
                    chat_id=chat_id,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                    parse_mode=str(parse_mode),
                    delete_message_id=initial_message.message_id,
                    photo=photo,
                )
            else:
                await _send_photo_group_with_caption(
                    context=context,
                    chat_id=chat_id,
                    caption=caption,
                    reply_to_message_id=reply_to_message_id,
                    parse_mode=str(parse_mode),
                    delete_message_id=initial_message.message_id,
                    downloaded_files=downloaded_files,
                )
            logger.info(f"Successfully sent {len(downloaded_files)} generated images")
            return
        except Exception as e:
            if "Message caption is too long" not in str(e):
                logger.exception(f"Failed to send with parse_mode={parse_mode}: {e}")
                continue
            else:
                # For caption too long error, it's already handled in the sub-functions
                # Just log and exit successfully
                logger.info(
                    f"Successfully sent {len(downloaded_files)} generated images (without caption due to length)"
                )
                return
