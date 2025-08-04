# -*- coding: utf-8 -*-
"""
Telegram media handling service for sending photos, videos, and documents
"""
from contextlib import suppress
from pathlib import Path
from typing import List, Dict, Literal, Optional

from loguru import logger
from telegram import Bot, InputMediaPhoto, InputMediaVideo, InputMediaDocument

from utils.file_utils import get_media_type, format_file_size
from utils.image_compressor import compress_image_for_telegram

# Telegram file size limits (in bytes) for local API mode
URL_LIMIT = 20 * 1024 * 1024  # 20MB - Direct URL upload limit
PREVIEW_LIMIT = 50 * 1024 * 1024  # 50MB - Photo preview limit
VIDEO_LIMIT = 2 * 1024 * 1024 * 1024  # 2GB - Video limit (local API mode)
DOCUMENT_LIMIT = 2 * 1024 * 1024 * 1024  # 2GB - Document limit (local API mode)

# Text limits
MAX_CAPTION_LENGTH = 1024

SendMethod = Literal['photo', 'video', 'document', 'compress_photo']


class TelegramMediaService:
    """Service for handling Telegram media uploads"""

    @staticmethod
    def determine_send_method(file_path: str) -> SendMethod:
        """Determine how to send a file based on size and type"""
        file_size = Path(file_path).stat().st_size
        media_type = get_media_type(file_path)

        if file_size > DOCUMENT_LIMIT:
            logger.warning(f"File {file_path} exceeds 2GB limit: {format_file_size(file_size)}")
            return 'document'

        if media_type == 'photo':
            if file_size <= URL_LIMIT:
                return 'photo'
            elif file_size <= PREVIEW_LIMIT:
                return 'compress_photo'
            else:
                return 'document'

        elif media_type == 'video':
            file_extension = Path(file_path).suffix.lower()
            if file_extension == '.webm':
                logger.info(f"WebM file detected: {file_path}")

            if file_size <= VIDEO_LIMIT:
                return 'video'
            else:
                return 'document'

        return 'document'

    @staticmethod
    def create_video_media(file_path: str, file_obj, caption: str = "") -> InputMediaVideo:
        """Create InputMediaVideo with appropriate streaming support"""
        supports_streaming = Path(file_path).suffix.lower() != '.webm'
        return InputMediaVideo(
            media=file_obj,
            caption=caption,
            parse_mode="HTML",
            supports_streaming=supports_streaming,
        )

    @classmethod
    async def send_media_batch(
        cls,
        bot: Bot,
        chat_id: int,
        media_files: List[Dict[str, str]],
        reply_to_message_id: Optional[int] = None,
        progress_callback=None,
    ) -> Optional[int]:
        """Send media files in batches

        Args:
            bot: Telegram bot instance
            chat_id: Chat ID to send to
            media_files: List of dicts with 'file_path' and 'caption' keys
            reply_to_message_id: Message ID to reply to
            progress_callback: Optional callback for progress updates

        Returns:
            First message ID of sent messages, or None if failed
        """
        if not media_files:
            return None

        # Group files by send method
        photos = []
        videos = []
        documents = []
        compressed_files = []

        # Process each file
        for i, file_info in enumerate(media_files):
            file_path = file_info['file_path']
            if not Path(file_path).exists():
                continue

            send_method = cls.determine_send_method(file_path)
            caption = file_info.get('caption', '') if i == 0 else ""

            if send_method == 'photo':
                photos.append({'file_path': file_path, 'caption': caption})
            elif send_method == 'compress_photo':
                try:
                    compressed_path = compress_image_for_telegram(file_path)
                    if compressed_path != file_path:
                        compressed_files.append(compressed_path)

                    if Path(compressed_path).stat().st_size <= PREVIEW_LIMIT:
                        photos.append({'file_path': compressed_path, 'caption': caption})
                    else:
                        documents.append({'file_path': compressed_path, 'caption': caption})
                except Exception as e:
                    logger.warning(f"Image compression failed: {e}")
                    documents.append({'file_path': file_path, 'caption': caption})
            elif send_method == 'video':
                videos.append({'file_path': file_path, 'caption': caption})
            else:
                documents.append({'file_path': file_path, 'caption': caption})

        # Update progress if callback provided
        if progress_callback:
            total_files = len(photos) + len(videos) + len(documents)
            await progress_callback(total_files, photos, videos, documents)

        # Send media in batches
        first_msg_id = None

        try:
            if photos:
                msg_id = await cls._send_media_group(
                    bot, chat_id, photos, InputMediaPhoto, reply_to_message_id
                )
                first_msg_id = first_msg_id or msg_id

            if videos:
                msg_id = await cls._send_media_group(
                    bot, chat_id, videos, InputMediaVideo, reply_to_message_id or first_msg_id
                )
                first_msg_id = first_msg_id or msg_id

            if documents:
                msg_id = await cls._send_media_group(
                    bot, chat_id, documents, InputMediaDocument, reply_to_message_id or first_msg_id
                )
                first_msg_id = first_msg_id or msg_id

            # Cleanup compressed files
            for file_path in compressed_files:
                with suppress(Exception):
                    Path(file_path).unlink()

            return first_msg_id

        except Exception as e:
            logger.error(f"Failed to send media: {e}")
            # Cleanup compressed files on error
            for file_path in compressed_files:
                with suppress(Exception):
                    Path(file_path).unlink()
            raise

    @classmethod
    async def _send_media_group(
        cls,
        bot: Bot,
        chat_id: int,
        media_list: List[Dict[str, str]],
        media_class: type,
        reply_to_message_id: Optional[int] = None,
    ) -> Optional[int]:
        """Send a group of media files"""
        if not media_list:
            return None

        first_msg_id = None

        # Send in batches of 10 (Telegram limit)
        for i in range(0, len(media_list), 10):
            batch = media_list[i : i + 10]
            media_batch = []

            for item in batch:
                with open(item['file_path'], 'rb') as file_obj:
                    caption = item.get('caption', '')

                    # Truncate caption if too long
                    if len(caption) > MAX_CAPTION_LENGTH:
                        caption = ""

                    if media_class == InputMediaVideo:
                        media_batch.append(
                            cls.create_video_media(item['file_path'], file_obj, caption)
                        )
                    else:
                        media_batch.append(
                            media_class(media=file_obj, caption=caption, parse_mode="HTML")
                        )

            try:
                # Send batch
                sent_messages = await bot.send_media_group(
                    chat_id=chat_id,
                    media=media_batch,
                    parse_mode="HTML",
                    reply_to_message_id=reply_to_message_id if i == 0 else first_msg_id,
                )

                if sent_messages and not first_msg_id:
                    first_msg_id = sent_messages[0].message_id

            finally:
                # Close file handles
                for media in media_batch:
                    with suppress(Exception):
                        media.media.close()

        return first_msg_id
