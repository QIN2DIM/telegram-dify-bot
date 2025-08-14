# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 00:44
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
import mimetypes
import random
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import List, Optional, Dict
from collections import defaultdict

from loguru import logger
from telegram import Message, Bot, Document, Audio, Video, Voice, VideoNote, File

from settings import DATA_DIR

# Media Group cache to handle grouped messages
_media_group_cache: Dict[str, List[Message]] = defaultdict(list)
_cache_cleanup_time = time.time()


def should_ignore_command_in_group(update, context) -> bool:
    """
    Check if a command should be ignored in group chats.
    Returns True if the command should be ignored (not processed).

    In groups, only respond to commands with bot mention (/command@botname).
    In private chats, respond to all commands.
    """
    # Only check for group chats
    if not update.message or update.message.chat.type == "private":
        return False

    # In groups, check if command contains bot mention
    bot_username = context.bot.username
    if bot_username and update.message.text:
        # If command doesn't contain @botname, ignore it
        command_part = update.message.text.split()[0] if update.message.text else ""
        if command_part.startswith("/") and f"@{bot_username}" not in command_part:
            return True

    return False


def storage_messages_dataset(chat_type: str, effective_message: Message) -> None:
    """仅用于开发测试，程序运行稳定后移除"""

    preview_text = json.dumps(effective_message.to_dict(), indent=2, ensure_ascii=False)

    fp = DATA_DIR.joinpath(f"{chat_type}_messages/{int(time.time())}.json")
    fp.parent.mkdir(parents=True, exist_ok=True)

    fp.write_text(preview_text, encoding="utf-8")
    # logger.debug(f"echo message - {preview_text}")


def _cleanup_media_group_cache():
    """Clean up old entries from media group cache"""
    global _cache_cleanup_time, _media_group_cache

    current_time = time.time()
    # Clean up every 5 minutes
    if current_time - _cache_cleanup_time > 300:
        # Remove entries older than 2 minutes
        cutoff_time = current_time - 120

        groups_to_remove = []
        for group_id, messages in _media_group_cache.items():
            # Check if all messages in the group are old
            if all(msg.date.timestamp() < cutoff_time for msg in messages):
                groups_to_remove.append(group_id)

        for group_id in groups_to_remove:
            del _media_group_cache[group_id]

        _cache_cleanup_time = current_time

        if groups_to_remove:
            logger.debug(f"Cleaned up {len(groups_to_remove)} old media groups from cache")


def add_message_to_media_group_cache(message: Message):
    """Add a message to the media group cache if it belongs to a group"""
    if not message.media_group_id:
        return

    _cleanup_media_group_cache()

    group_id = message.media_group_id

    # Check if this message is already in the cache (by message_id)
    existing_ids = [msg.message_id for msg in _media_group_cache[group_id]]
    if message.message_id not in existing_ids:
        _media_group_cache[group_id].append(message)
        logger.debug(
            f"Added message_id={message.message_id} to media group {group_id}, total messages: {len(_media_group_cache[group_id])}"
        )
    else:
        logger.debug(
            f"Message_id={message.message_id} already in media group {group_id} cache, skipping"
        )


def get_media_group_messages(message: Message) -> List[Message]:
    """
    Get all messages from the same media group

    Args:
        message: The trigger message

    Returns:
        List of messages from the same media group (including the trigger message)
    """
    if not message.media_group_id:
        return [message]  # Single message, not part of a group

    group_id = message.media_group_id
    group_messages = list(_media_group_cache.get(group_id, []))

    # Check if trigger message is already in the cache (by message_id)
    message_ids = [msg.message_id for msg in group_messages]
    if message.message_id not in message_ids:
        group_messages.append(message)

    # Remove duplicates by message_id (keep first occurrence)
    seen = set()
    unique_messages = []
    for msg in group_messages:
        if msg.message_id not in seen:
            seen.add(msg.message_id)
            unique_messages.append(msg)

    # Sort by message_id to ensure consistent order
    unique_messages.sort(key=lambda msg: msg.message_id)

    # logger.debug(f"Found {len(unique_messages)} unique messages in media group {group_id}")
    return unique_messages


async def download_telegram_file(
    bot: Bot, file_obj: File, download_dir: Path, file_extension: Optional[str] = None
) -> Optional[Path]:
    """
    Download a single Telegram file to local storage

    Args:
        bot: Telegram bot instance
        file_obj: Telegram File object
        download_dir: Directory to save the file
        file_extension: Optional file extension override

    Returns:
        Path to downloaded file or None if failed
    """
    try:
        # Create download directory if needed
        download_dir.mkdir(parents=True, exist_ok=True)

        # Determine file extension
        if not file_extension and file_obj.file_path:
            file_extension = Path(file_obj.file_path).suffix
        if not file_extension:
            file_extension = '.bin'  # Default binary extension

        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        local_path = download_dir / unique_filename

        # Download file
        await file_obj.download_to_drive(local_path)
        logger.info(f"Downloaded file: {local_path} (size: {file_obj.file_size} bytes)")

        return local_path

    except Exception as e:
        logger.exception(f"Failed to download file {file_obj.file_id} - {e}")
        return None


async def _download_photos_from_message(message: Message, bot: Bot) -> List[Path] | None:
    """
    从Telegram消息中下载照片到本地

    特性：
    - 自动选择最高质量的图片版本（最大file_size）
    - 生成唯一文件名避免冲突
    - 保持原始文件扩展名
    - 错误处理和日志记录

    Args:
        message: Telegram消息对象
        bot: 机器人对象

    Returns:
        List[Path]: 下载的图片文件路径列表，如果没有图片则返回None
    """
    if not message.photo:
        return None

    # 创建下载目录
    download_dir = DATA_DIR / "downloads" / "photos"
    download_dir.mkdir(parents=True, exist_ok=True)

    downloaded_files = []

    # Telegram的photo字段是PhotoSize列表，包含不同尺寸的同一张图片
    # 我们选择最大尺寸的版本（file_size最大的）
    largest_photo = max(message.photo, key=lambda x: x.file_size or 0)

    logger.debug(
        f"Downloading photo from message_id={message.message_id}, file_id={largest_photo.file_id}, size={largest_photo.file_size}"
    )

    try:
        file_obj = await bot.get_file(largest_photo.file_id)
        local_path = await download_telegram_file(bot, file_obj, download_dir)
        if local_path:
            downloaded_files.append(local_path)
            logger.debug(f"Successfully downloaded photo to {local_path}")
    except Exception as e:
        logger.error(f"Failed to download photo {largest_photo.file_id}: {e}")

    return downloaded_files if downloaded_files else None


async def _download_multiple_photos_from_message(message: Message, bot: Bot) -> List[Path] | None:
    """
    处理包含多张图片的消息（如果消息包含多个媒体组）
    注意：单个消息的photo字段只包含一张图片的多个尺寸版本
    如果要处理真正的多张图片，需要处理media_group_id相同的多条消息

    Args:
        message: Telegram消息对象
        bot: 机器人对象

    Returns:
        List[Path]: 下载的图片文件路径列表
    """
    # 对于单条消息，直接调用单张图片下载函数
    return await _download_photos_from_message(message, bot)


async def download_document_from_message(message: Message, bot: Bot) -> Optional[Path]:
    """
    Download document from a message

    Args:
        message: Telegram message containing document
        bot: Bot instance

    Returns:
        Path to downloaded document or None
    """
    if not message.document:
        return None

    download_dir = DATA_DIR / "downloads" / "documents"
    document: Document = message.document

    try:
        file_obj = await bot.get_file(document.file_id)

        # Try to determine extension from mime_type or file_name
        file_extension = None
        if document.file_name:
            file_extension = Path(document.file_name).suffix
        elif document.mime_type:
            ext = mimetypes.guess_extension(document.mime_type)
            if ext:
                file_extension = ext

        return await download_telegram_file(bot, file_obj, download_dir, file_extension)
    except Exception:
        logger.exception(f"Failed to download document {document.file_id}")
        return None


async def download_audio_from_message(message: Message, bot: Bot) -> Optional[Path]:
    """
    Download audio from a message

    Args:
        message: Telegram message containing audio
        bot: Bot instance

    Returns:
        Path to downloaded audio or None
    """
    if not message.audio:
        return None

    download_dir = DATA_DIR / "downloads" / "audio"
    audio: Audio = message.audio

    try:
        file_obj = await bot.get_file(audio.file_id)

        # Determine extension from mime_type
        file_extension = None
        if audio.file_name:
            file_extension = Path(audio.file_name).suffix
        elif audio.mime_type:
            ext = mimetypes.guess_extension(audio.mime_type)
            if ext:
                file_extension = ext

        return await download_telegram_file(bot, file_obj, download_dir, file_extension)
    except Exception:
        logger.exception(f"Failed to download audio {audio.file_id}")
        return None


async def download_video_from_message(message: Message, bot: Bot) -> Optional[Path]:
    """
    Download video from a message

    Args:
        message: Telegram message containing video
        bot: Bot instance

    Returns:
        Path to downloaded video or None
    """
    if not message.video:
        return None

    download_dir = DATA_DIR / "downloads" / "videos"
    video: Video = message.video

    try:
        file_obj = await bot.get_file(video.file_id)

        # Determine extension from mime_type
        file_extension = None
        if video.file_name:
            file_extension = Path(video.file_name).suffix
        elif video.mime_type:
            ext = mimetypes.guess_extension(video.mime_type)
            if ext:
                file_extension = ext

        return await download_telegram_file(bot, file_obj, download_dir, file_extension)
    except Exception:
        logger.exception(f"Failed to download video {video.file_id}")
        return None


async def download_voice_from_message(message: Message, bot: Bot) -> Optional[Path]:
    """
    Download voice message

    Args:
        message: Telegram message containing voice
        bot: Bot instance

    Returns:
        Path to downloaded voice or None
    """
    if not message.voice:
        return None

    download_dir = DATA_DIR / "downloads" / "voice"
    voice: Voice = message.voice

    try:
        file_obj = await bot.get_file(voice.file_id)

        # Voice messages are typically .ogg files
        file_extension = '.ogg'
        if voice.mime_type:
            ext = mimetypes.guess_extension(voice.mime_type)
            if ext:
                file_extension = ext

        return await download_telegram_file(bot, file_obj, download_dir, file_extension)
    except Exception:
        logger.exception(f"Failed to download voice {voice.file_id}")
        return None


async def download_video_note_from_message(message: Message, bot: Bot) -> Optional[Path]:
    """
    Download video note (round video message)

    Args:
        message: Telegram message containing video note
        bot: Bot instance

    Returns:
        Path to downloaded video note or None
    """
    if not message.video_note:
        return None

    download_dir = DATA_DIR / "downloads" / "video_notes"
    video_note: VideoNote = message.video_note

    try:
        file_obj = await bot.get_file(video_note.file_id)

        # Video notes are typically .mp4 files
        file_extension = '.mp4'

        return await download_telegram_file(bot, file_obj, download_dir, file_extension)
    except Exception:
        logger.exception(f"Failed to download video note {video_note.file_id}")
        return None


def _classify_file_by_extension(file_path: Path) -> str:
    """
    Classify file type based on extension for proper categorization

    Args:
        file_path: Path to the file

    Returns:
        Classified media type string
    """
    if not file_path:
        return "documents"

    file_extension = file_path.suffix.upper().lstrip(".")

    # Video files (including those sent as documents)
    if file_extension in [
        "MP4",
        "AVI",
        "MOV",
        "WMV",
        "FLV",
        "MKV",
        "WEBM",
        "MPEG",
        "M4V",
        "3GP",
        "OGV",
    ]:
        return "videos"

    # Audio files (including those sent as documents)
    if file_extension in ["MP3", "WAV", "OGG", "M4A", "AAC", "FLAC", "WMA", "AMR", "MPGA", "OPUS"]:
        return "audio"

    # Image files (rare but possible as documents)
    if file_extension in ["JPG", "JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF", "SVG"]:
        return "photos"

    # Everything else remains as document
    return "documents"


async def download_all_media_from_message(message: Message, bot: Bot) -> Dict[str, List[Path]]:
    """
    Download all media from a message with smart file type classification

    Args:
        message: Telegram message
        bot: Bot instance

    Returns:
        Dictionary with media type as key and list of paths as value
    """
    media_files = {
        "photos": [],
        "documents": [],
        "audio": [],
        "videos": [],
        "voice": [],
        "video_notes": [],
    }

    # Download photo
    if message.photo:
        photo_paths = await _download_photos_from_message(message, bot)
        if photo_paths:
            media_files["photos"].extend(photo_paths)

    # Download document (with smart reclassification)
    if message.document:
        doc_path = await download_document_from_message(message, bot)
        if doc_path:
            # Classify based on file extension to handle videos/audio sent as documents
            classified_type = _classify_file_by_extension(doc_path)
            media_files[classified_type].append(doc_path)
            logger.debug(f"Document {doc_path.name} reclassified as {classified_type}")

    # Download audio
    if message.audio:
        audio_path = await download_audio_from_message(message, bot)
        if audio_path:
            media_files["audio"].append(audio_path)

    # Download video
    if message.video:
        video_path = await download_video_from_message(message, bot)
        if video_path:
            media_files["videos"].append(video_path)

    # Download voice
    if message.voice:
        voice_path = await download_voice_from_message(message, bot)
        if voice_path:
            media_files["voice"].append(voice_path)

    # Download video note
    if message.video_note:
        video_note_path = await download_video_note_from_message(message, bot)
        if video_note_path:
            media_files["video_notes"].append(video_note_path)

    return media_files


async def download_media_group_files(trigger_message: Message, bot: Bot) -> Dict[str, List[Path]]:
    """
    Download all media files from a media group or single message

    Args:
        trigger_message: The message that triggered the interaction
        bot: Bot instance

    Returns:
        Dictionary with media type as key and list of paths as value
    """
    # Get all messages in the media group (or just the single message)
    group_messages = get_media_group_messages(trigger_message)

    # Log media group info for debugging
    if len(group_messages) > 1:
        logger.info(f"Processing media group with {len(group_messages)} messages")
        for idx, msg in enumerate(group_messages):
            if msg.photo:
                largest_photo = msg.photo[-1]
                logger.debug(
                    f"Message {idx+1}: message_id={msg.message_id}, "
                    f"photo_file_id={largest_photo.file_id[:20]}..., "
                    f"file_unique_id={largest_photo.file_unique_id}, "
                    f"file_size={largest_photo.file_size}"
                )

    # Aggregate all media files
    aggregated_media_files = {
        "photos": [],
        "documents": [],
        "audio": [],
        "videos": [],
        "voice": [],
        "video_notes": [],
    }

    for message in group_messages:
        message_media = await download_all_media_from_message(message, bot)

        # Merge media files from each message
        for media_type, paths in message_media.items():
            if paths:
                aggregated_media_files[media_type].extend(paths)

    # Log the results
    total_files = sum(len(paths) for paths in aggregated_media_files.values())
    if total_files > 0:
        logger.info(f"Downloaded {total_files} files from media group/message")
        for media_type, paths in aggregated_media_files.items():
            if paths:
                logger.debug(f"  {media_type}: {len(paths)} files")

    return aggregated_media_files


def cleanup_old_photos(max_age_hours: int = 24) -> None:
    """
    清理超过指定时间的下载图片文件

    Args:
        max_age_hours: 文件最大保留时间（小时）
    """
    download_dir = DATA_DIR / "downloads" / "photos"
    if not download_dir.exists():
        return

    current_time = time.time()
    max_age_seconds = max_age_hours * 3600

    cleaned_count = 0
    try:
        for photo_file in download_dir.iterdir():
            if photo_file.is_file():
                file_age = current_time - photo_file.stat().st_mtime
                if file_age > max_age_seconds:
                    photo_file.unlink()
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old photo files")

    except Exception as e:
        logger.error(f"Failed to cleanup old photos: {e}")


def cleanup_old_media(max_age_hours: int = 24) -> None:
    """
    Clean up old downloaded media files (all types)

    Args:
        max_age_hours: Maximum age in hours before deletion
    """
    download_dir = DATA_DIR / "downloads"
    if not download_dir.exists():
        return

    current_time = time.time()
    max_age_seconds = max_age_hours * 3600

    total_cleaned = 0
    total_size = 0

    try:
        # Clean all subdirectories
        for subdir in download_dir.iterdir():
            if not subdir.is_dir():
                continue

            cleaned_count = 0
            cleaned_size = 0

            for file_path in subdir.rglob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_size = file_path.stat().st_size
                        with suppress(Exception):
                            file_path.unlink()
                            cleaned_count += 1
                            cleaned_size += file_size

            if cleaned_count > 0:
                logger.info(
                    f"Cleaned {cleaned_count} old {subdir.name} files "
                    f"({cleaned_size / (1024*1024):.2f} MB)"
                )
                total_cleaned += cleaned_count
                total_size += cleaned_size

        if total_cleaned > 0:
            logger.info(
                f"Total cleanup: {total_cleaned} files " f"({total_size / (1024*1024):.2f} MB)"
            )

    except Exception:
        logger.exception("Failed to cleanup old media files")


def cleanup_old_social_downloads(max_age_hours: int = 48) -> None:
    """
    清理超过指定时间的社交媒体下载文件

    Args:
        max_age_hours: 文件最大保留时间（小时）
    """
    social_downloads_dir = DATA_DIR / "downloads"
    if not social_downloads_dir.exists():
        return

    current_time = time.time()
    max_age_seconds = max_age_hours * 3600

    total_cleaned_count = 0
    total_cleaned_size = 0

    try:
        # 遍历所有平台目录（除了 photos）
        for platform_dir in social_downloads_dir.iterdir():
            if not platform_dir.is_dir() or platform_dir.name == "photos":
                continue

            platform_cleaned_count = 0
            platform_cleaned_size = 0

            # 遍历平台下的所有内容目录
            for content_dir in platform_dir.iterdir():
                if not content_dir.is_dir():
                    continue

                # 检查目录中的文件
                files_to_clean = []
                for file_path in content_dir.iterdir():
                    if file_path.is_file():
                        file_age = current_time - file_path.stat().st_mtime
                        if file_age > max_age_seconds:
                            files_to_clean.append(file_path)

                # 删除过期文件
                for file_path in files_to_clean:
                    try:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        platform_cleaned_count += 1
                        platform_cleaned_size += file_size
                    except Exception as file_error:
                        logger.warning(f"Failed to delete file {file_path}: {file_error}")

                # 如果目录为空，删除目录
                try:
                    if not any(content_dir.iterdir()):
                        content_dir.rmdir()
                        logger.debug(f"Removed empty directory: {content_dir}")
                except Exception as dir_error:
                    logger.debug(f"Failed to remove directory {content_dir}: {dir_error}")

            # 记录平台清理统计
            if platform_cleaned_count > 0:
                platform_cleaned_size_mb = platform_cleaned_size / (1024 * 1024)
                logger.info(
                    f"Cleaned up {platform_cleaned_count} old {platform_dir.name} files "
                    f"({platform_cleaned_size_mb:.2f}MB)"
                )

            total_cleaned_count += platform_cleaned_count
            total_cleaned_size += platform_cleaned_size

        # 总体统计
        if total_cleaned_count > 0:
            total_cleaned_size_mb = total_cleaned_size / (1024 * 1024)
            logger.info(
                f"Total cleanup: {total_cleaned_count} files "
                f"({total_cleaned_size_mb:.2f}MB) from all platforms"
            )

    except Exception as e:
        logger.error(f"Failed to cleanup old social media downloads: {e}")


hello_replies: List[str] = [
    "Hey! 👋 Welcome—I'm here to help. 😊\nWhat can I do for you today? Whether it’s a question, an idea, or you just want to chat, I’m all ears! 💬❤️‍🔥",
    "Hi there!",
    "Hey! 👋",
    "Hi! 😊",
    "What's up?",
    "Good to see you!",
    "Hey there!",
    "Howdy!",
    "Hi! 👀",
    "Hello hello!",
    "Yo! (^_^)",
    "你好！",
    "嗨！✨",
    "Hello! 🌟",
    "Hey hey!",
    "Hi friend!",
    "Greetings!",
    "Hiya!",
    "Well hello!",
    "Hey you! 😄",
    "Hi hi!",
    "Hello world!",
    "嗨呀！",
    "Sup!",
    "Oh hi!",
    "Hello beautiful!",
    "Hey buddy!",
    "Hi stranger!",
    "Hello sunshine! ☀️",
    "Hellow~ 🎵",
    "Hey! Nice to meet you! 🤝",
]


image_mention_prompts: List[str] = [
    "我看到你发了张图片并提到了我！🖼️ 请告诉我你想要我做什么：\n✨ 翻译图片中的文字？\n🔍 分析图片内容？\n💬 或者其他什么？",
    "嗨！👋 我看到你的图片了！请告诉我你的具体需求：\n📝 需要翻译图片中的文字吗？\n🤔 还是想了解图片的内容？\n请明确说明你的问题！",
    "你好！我注意到你发了张图片 📸\n请告诉我你希望我帮你做什么：\n🌐 翻译图片中的文字？\n📋 描述图片内容？\n💡 或者其他什么需求？",
    "看到你的图片了！🎨 不过我需要知道你的具体需求：\n📖 翻译图片中的文字？\n🔍 分析图片内容？\n💬 请明确告诉我你想要什么帮助！",
    "嗨！我看到你提到了我并发了张图片 📷\n请告诉我你的需求：\n🈯 翻译图片中的文字？\n📊 分析图片内容？\n✨ 或者其他什么？",
    "你好！👋 我看到你的图片了！请明确你的需求：\n🔤 需要翻译图片中的文字吗？\n🎯 还是想了解图片的具体内容？\n请告诉我你想要什么帮助！",
    "Hi there! 我看到你发了张图片！📸\n请告诉我你的具体需求：\n📝 翻译图片中的文字？\n🔍 分析图片内容？\n💬 或者其他什么？",
    "嗨！我注意到你的图片了 🖼️\n请明确告诉我你想要：\n🌐 翻译图片中的文字？\n📋 描述图片内容？\n💡 或者其他什么帮助？",
    "你好！看到你提到了我并发了张图片 📷\n请告诉我你的需求：\n🈯 翻译图片中的文字？\n🔍 分析图片内容？\n✨ 请明确说明你的问题！",
    "Hi! 我看到你的图片了！🎨\n请告诉我你想要什么帮助：\n📖 翻译图片中的文字？\n📊 分析图片内容？\n💬 或者其他什么需求？",
]


def get_hello_reply():
    return random.choice(hello_replies)


def get_image_mention_prompt():
    return random.choice(image_mention_prompts)


async def process_message_media(
    message: Message, bot: Bot
) -> tuple[Dict[str, List[Path]], bool, List[Path]]:
    """
    Process and download media files from a message

    This is a shared utility function used by command handlers that need to process media files.

    Args:
        message: Telegram message that may contain media
        bot: Bot instance for downloading files

    Returns:
        tuple containing:
        - media_files: Dictionary with media type as key and list of paths as value
        - has_media: Boolean indicating if any media was downloaded
        - photo_paths: List of photo paths for backward compatibility
    """
    # Add message to media group cache and download all media files
    add_message_to_media_group_cache(message)
    media_files = await download_media_group_files(message, bot)

    # Check if any media was downloaded
    has_media = False
    if media_files:
        for media_type, paths in media_files.items():
            if paths:
                has_media = True
                logger.info(f"Downloaded {len(paths)} {media_type} for processing")
                break

    # For backward compatibility
    photo_paths = media_files.get("photos", []) if media_files else []

    return media_files, has_media, photo_paths
