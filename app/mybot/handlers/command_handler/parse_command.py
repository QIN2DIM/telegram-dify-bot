# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 02:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Parse social media links and automatically download media resources
"""
import asyncio
from contextlib import suppress
from pathlib import Path

from loguru import logger
from telegram import ReactionTypeEmoji, Update, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from telegram.ext import ContextTypes

from mybot.task_manager import non_blocking_handler
from mybot.services.instant_view_service import try_send_as_instant_view
from plugins.social_parser import parser_registry
from utils.image_compressor import compress_image_for_telegram

# Constants for Telegram limits (in bytes)
URL_LIMIT = 20 * 1024 * 1024  # 20MB
PREVIEW_LIMIT = 50 * 1024 * 1024  # 50MB
VIDEO_LIMIT = 2 * 1024 * 1024 * 1024  # 2GB for local mode
DOCUMENT_LIMIT = 2 * 1024 * 1024 * 1024  # 2GB

# Telegram message limit is 4096 characters, use 90% as safe limit
MAX_MESSAGE_LENGTH = int(4096 * 0.9)  # 3686 characters
# Telegram caption limit is 1024 characters
MAX_CAPTION_LENGTH = 1024

# Track active parse tasks to prevent garbage collection
_active_parse_tasks = set()


async def _send_or_edit_message(
    context, chat_id: int, text: str, progress_msg=None, reply_to_id=None
):
    """Send new message or edit existing progress message"""
    if progress_msg:
        with suppress(Exception):
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text=(
                    f"<blockquote>{text}</blockquote>"
                    if "❌" not in text and "📄" not in text
                    else text
                ),
                parse_mode='HTML',
            )
            return

    await context.bot.send_message(
        chat_id=chat_id, text=text, parse_mode='HTML', reply_to_message_id=reply_to_id
    )


def _extract_link_from_args(args: list) -> str:
    """Extract link from user input"""
    if not args:
        return ""

    link = ""

    for arg in args:
        if "http" in arg.lower() or "www." in arg.lower():
            link = arg.strip()
            break
        elif not link:  # If no URL found yet, use the first argument
            link = arg.strip()

    return link


def _get_media_type(file_path: str) -> str:
    """Determine media type from file extension"""
    file_extension = Path(file_path).suffix.lower()

    # Image extensions
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
    # Video extensions
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v', '.3gp', '.flv'}

    if file_extension in image_extensions:
        return 'photo'
    elif file_extension in video_extensions:
        return 'video'
    else:
        return 'document'


def _get_file_size(file_path: str) -> int:
    """Get file size in bytes"""
    return Path(file_path).stat().st_size


def _format_download_summary(download_results: list) -> str:
    """Format download summary with file information for progress message"""
    successful_downloads = [r for r in download_results if r.get('success') and r.get('local_path')]
    if not successful_downloads:
        return "📥 没有成功下载的文件"

    lines = ["📥 已下载的文件：\n"]

    for i, result in enumerate(successful_downloads, 1):
        file_path = Path(result['local_path'])
        if not file_path.exists():
            continue

        # Get file info
        file_size = file_path.stat().st_size
        extension = file_path.suffix.upper().lstrip('.') or 'FILE'

        # Format size
        if file_size >= 1024 * 1024 * 1024:  # >= 1GB
            size_str = f"{file_size / (1024 * 1024 * 1024):.2f} GiB"
        elif file_size >= 1024 * 1024:  # >= 1MB
            size_str = f"{file_size / (1024 * 1024):.2f} MiB"
        elif file_size >= 1024:  # >= 1KB
            size_str = f"{file_size / 1024:.2f} KiB"
        else:
            size_str = f"{file_size} B"

        # Format: 1. JPG - 2.45 MiB
        lines.append(f"{i}. {extension} - {size_str}")

    # Add total summary
    total_size = sum(
        Path(r['local_path']).stat().st_size
        for r in successful_downloads
        if r.get('local_path') and Path(r['local_path']).exists()
    )

    if total_size >= 1024 * 1024 * 1024:
        total_size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GiB"
    elif total_size >= 1024 * 1024:
        total_size_str = f"{total_size / (1024 * 1024):.2f} MiB"
    else:
        total_size_str = f"{total_size / 1024:.2f} KiB"

    lines.append(f"\n📊 总计: {len(successful_downloads)} 个文件, {total_size_str}")

    return "\n".join(lines)


def _determine_send_method(file_path: str, media_type: str) -> str:
    """Determine how to send a file based on Telegram limits and file type

    Telegram limits (local mode):
    - URL upload: 20MB
    - Preview (photo): 50MB
    - Video: 2GB (local mode)
    - Document: 2GB

    Returns: 'photo', 'video', 'document', or 'compress_photo'
    """
    file_size = _get_file_size(file_path)

    if file_size > DOCUMENT_LIMIT:
        file_size_gib = file_size / (1024 * 1024 * 1024)
        logger.warning(f"File {file_path} exceeds 2GB limit: {file_size_gib:.2f} GiB")
        return 'document'  # Still try as document, but will likely fail

    if media_type == 'photo':
        if file_size <= URL_LIMIT:
            return 'photo'
        elif file_size <= PREVIEW_LIMIT:
            # For images >20MB but <=50MB, try compression first
            return 'compress_photo'
        else:
            # For images >50MB, send as document
            return 'document'

    elif media_type == 'video':
        file_extension = Path(file_path).suffix.lower()
        # WebM format doesn't support streaming in Telegram, suggest conversion
        if file_extension == '.webm':
            logger.info(
                f"WebM file detected: {file_path} - WebM doesn't support streaming in Telegram"
            )
            # Still send as video but user should know about the limitation
            if file_size <= VIDEO_LIMIT:
                return 'video'
            else:
                return 'document'
        else:
            # MP4 and other formats with streaming support
            if file_size <= VIDEO_LIMIT:
                return 'video'
            else:
                # For videos >2GB, send as document (though likely to fail)
                return 'document'

    else:
        return 'document'


async def _cleanup_files(download_results: list, compressed_files: list) -> None:
    """Clean up downloaded files and compressed files after successful sending"""
    # Clean up compressed files first
    for file_path in compressed_files:
        try:
            if Path(file_path).exists():
                Path(file_path).unlink()
                logger.debug(f"Cleaned up compressed file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up compressed file {file_path}: {e}")

    # Clean up downloaded files
    cleaned_dirs = set()
    for result in download_results:
        if result.get('success') and result.get('local_path'):
            file_path = Path(result['local_path'])
            try:
                if file_path.exists():
                    # Get parent directory
                    parent_dir = file_path.parent

                    # Delete the file
                    file_path.unlink()
                    logger.debug(f"Cleaned up downloaded file: {file_path}")

                    # Track parent directories for cleanup
                    cleaned_dirs.add(parent_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up file {file_path}: {e}")

    # Clean up empty directories
    for dir_path in cleaned_dirs:
        try:
            # Only remove if directory is empty
            if dir_path.exists() and not any(dir_path.iterdir()):
                dir_path.rmdir()
                logger.debug(f"Removed empty directory: {dir_path}")

                # Try to clean up parent directories if empty
                parent = dir_path.parent
                while parent.name not in ['downloads', 'data'] and parent.exists():
                    if not any(parent.iterdir()):
                        parent.rmdir()
                        logger.debug(f"Removed empty parent directory: {parent}")
                        parent = parent.parent
                    else:
                        break
        except Exception as e:
            logger.warning(f"Failed to clean up directory {dir_path}: {e}")


async def _send_media_files(
    context,
    chat_id: int,
    download_results: list,
    post_content: str = "",
    progress_msg=None,
    original_message_id=None,
):
    """Send downloaded media files to chat with post content as caption"""
    successful_downloads = [r for r in download_results if r.get('success') and r.get('local_path')]
    if not successful_downloads:
        return

    photos, videos, documents, compressed_files = [], [], [], []
    first_caption = post_content or "📥 下载的媒体文件"

    for i, result in enumerate(successful_downloads):
        file_path = result['local_path']
        if not Path(file_path).exists():
            continue

        media_type = _get_media_type(file_path)
        send_method = _determine_send_method(file_path, media_type)
        caption = first_caption if i == 0 else ""

        if send_method == 'photo':
            photos.append({'file_path': file_path, 'caption': caption})
        elif send_method == 'compress_photo':
            try:
                compressed_path = compress_image_for_telegram(file_path)
                if compressed_path != file_path:
                    compressed_files.append(compressed_path)
                    if _get_file_size(compressed_path) <= 50 * 1024 * 1024:
                        photos.append({'file_path': compressed_path, 'caption': caption})
                    else:
                        documents.append({'file_path': compressed_path, 'caption': caption})
                else:
                    documents.append({'file_path': file_path, 'caption': caption})
            except Exception as e:
                logger.warning(f"Image compression failed: {e}")
                documents.append({'file_path': file_path, 'caption': caption})
        elif send_method == 'video':
            videos.append({'file_path': file_path, 'caption': caption})
        else:
            documents.append({'file_path': file_path, 'caption': caption})

    async def _send_batch(media_list, media_class, first_group_msg_id=None):
        """Send media in batches, with subsequent batches replying to first batch"""
        current_first_msg_id = first_group_msg_id
        long_caption_msg_id = None

        for i in range(0, len(media_list), 10):
            batch = media_list[i : i + 10]
            media_batch = []
            long_caption_item = None

            for item in batch:
                file_obj = open(item['file_path'], 'rb')
                caption = item['caption']

                # Check if caption is too long
                if caption and len(caption) > MAX_CAPTION_LENGTH:
                    # Store the long caption item for instant view handling
                    if not long_caption_item:
                        long_caption_item = item
                    # Send without caption first
                    if media_class == InputMediaVideo:
                        # Check if it's WebM format (doesn't support streaming)
                        is_webm = Path(item['file_path']).suffix.lower() == '.webm'
                        if is_webm:
                            media_batch.append(
                                media_class(media=file_obj, caption="", parse_mode="HTML")
                            )
                        else:
                            media_batch.append(
                                media_class(
                                    media=file_obj,
                                    caption="",
                                    parse_mode="HTML",
                                    supports_streaming=True,
                                )
                            )
                    else:
                        media_batch.append(
                            media_class(media=file_obj, caption="", parse_mode="HTML")
                        )
                else:
                    if media_class == InputMediaVideo:
                        # Check if it's WebM format (doesn't support streaming)
                        is_webm = Path(item['file_path']).suffix.lower() == '.webm'
                        if is_webm:
                            media_batch.append(
                                media_class(media=file_obj, caption=caption, parse_mode="HTML")
                            )
                        else:
                            media_batch.append(
                                media_class(
                                    media=file_obj,
                                    caption=caption,
                                    parse_mode="HTML",
                                    supports_streaming=True,
                                )
                            )
                    else:
                        media_batch.append(
                            media_class(media=file_obj, caption=caption, parse_mode="HTML")
                        )

            try:
                # For the first batch, reply to original message. For later batches, reply to the first batch
                if i == 0 and not current_first_msg_id:
                    # First batch of all media types - reply to original user message
                    reply_to_message_id = original_message_id
                else:
                    # Subsequent batches - reply to first batch
                    reply_to_message_id = current_first_msg_id if current_first_msg_id else None

                sent_messages = await context.bot.send_media_group(
                    chat_id=chat_id,
                    media=media_batch,
                    parse_mode="HTML",
                    reply_to_message_id=reply_to_message_id,
                )

                # Track first message ID for subsequent batches to reply to
                if i == 0 and sent_messages and not current_first_msg_id:
                    current_first_msg_id = sent_messages[0].message_id

                # Handle long caption using instant view
                if long_caption_item and sent_messages:
                    try:
                        success = await try_send_as_instant_view(
                            bot=context.bot,
                            chat_id=chat_id,
                            message_id=sent_messages[0].message_id,
                            content=long_caption_item['caption'],
                            title="媒体文件详情",
                        )
                        if success:
                            long_caption_msg_id = sent_messages[0].message_id
                        else:
                            # Fallback: send as separate message
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=f"📄 媒体文件详情：\n\n{long_caption_item['caption']}",
                                parse_mode="HTML",
                                reply_to_message_id=sent_messages[0].message_id,
                            )
                    except Exception as e:
                        logger.warning(f"Failed to handle long caption: {e}")

            finally:
                for media in media_batch:
                    with suppress(Exception):
                        media.media.close()

        return current_first_msg_id

    try:
        total_files = len(photos) + len(videos) + len(documents)
        if progress_msg and total_files > 0:
            # Build detailed sending info
            sending_info = ["📤 正在发送媒体文件：\n"]

            if photos:
                sending_info.append(f"🇿️ 图片: {len(photos)} 个")
            if videos:
                sending_info.append(f"🎥 视频: {len(videos)} 个")
            if documents:
                sending_info.append(f"📄 文档: {len(documents)} 个")

            sending_info.append(f"\n📊 总计: {total_files} 个文件")

            await _send_or_edit_message(context, chat_id, "\n".join(sending_info), progress_msg)

        first_group_msg_id = None

        if photos:
            first_group_msg_id = await _send_batch(photos, InputMediaPhoto, first_group_msg_id)
        if videos:
            first_group_msg_id = await _send_batch(videos, InputMediaVideo, first_group_msg_id)
        if documents:
            first_group_msg_id = await _send_batch(
                documents, InputMediaDocument, first_group_msg_id
            )

        # Delete a progress message after all media files are sent successfully
        if progress_msg:
            with suppress(Exception):
                await context.bot.delete_message(
                    chat_id=chat_id, message_id=progress_msg.message_id
                )
            # Message might already be deleted or not deletable

        # Clean up downloaded files and compressed files after successful sending
        await _cleanup_files(successful_downloads, compressed_files)

    except Exception as e:
        error_text = f"❌ 媒体文件发送失败: {str(e)}\n\n但文件已成功下载到本地。"
        # Try to edit a progress message with error, or send a new message if that fails
        if progress_msg:
            with suppress(Exception):
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text=error_text,
                    parse_mode='HTML',
                )
                return
            # Fall through to send a new message

        await context.bot.send_message(
            chat_id=chat_id,
            text=error_text,
            parse_mode='HTML',
            reply_to_message_id=original_message_id,
        )


def _format_social_post_response(post) -> str:
    """Format social media post data into a readable telegram message (basic info only)"""
    if not post:
        return "无法解析链接内容"

    # Build the response message with basic info
    response_parts = []

    # Title and author line
    title = getattr(post, 'title', '')
    author = getattr(post, 'user_nickname', '')

    if title and author:
        response_parts.append(f"<b>{title}</b> - {author}")
    elif title:
        response_parts.append(f"<b>{title}</b>")
    elif author:
        response_parts.append(f"{author}")

    # Published time
    if hasattr(post, 'published_time') and post.published_time:
        response_parts.append(f"{post.published_time}")

    # Description
    if hasattr(post, 'desc') and post.desc:
        desc = post.desc.replace("[话题]", "")
        desc = f"<blockquote>{desc}</blockquote>"
        response_parts.append(desc)

    final_message = "\n\n".join(response_parts)

    if len(final_message) > MAX_MESSAGE_LENGTH:
        # Find the description part to truncate
        for i, part in enumerate(response_parts):
            if part.startswith("<blockquote>") and part.endswith("</blockquote>"):
                # Calculate available space for description
                other_parts_length = sum(
                    len(p) + 2 for j, p in enumerate(response_parts) if j != i
                )  # +2 for "\n\n"
                available_length = MAX_MESSAGE_LENGTH - other_parts_length

                # Keep some space for the blockquote tags and ellipsis
                blockquote_overhead = len("<blockquote></blockquote>") + 3  # +3 for "..."
                max_desc_length = available_length - blockquote_overhead

                if max_desc_length > 50:  # Only truncate if we have reasonable space
                    original_desc = part[12:-13]  # Remove <blockquote> tags
                    truncated_desc = original_desc[:max_desc_length] + "..."
                    response_parts[i] = f"<blockquote>{truncated_desc}</blockquote>"
                    final_message = "\n\n".join(response_parts)
                break

    return final_message


async def _cleanup_completed_tasks():
    """Clean up completed tasks from the active tasks set"""
    completed_tasks = [task for task in _active_parse_tasks if task.done()]
    for task in completed_tasks:
        _active_parse_tasks.discard(task)
        # Log any exceptions that occurred in background tasks
        if not task.cancelled() and task.exception():
            logger.error(f"Background parse task failed: {task.exception()}")


def get_active_parse_tasks_count() -> int:
    """Get the number of currently active parse tasks"""
    return len(_active_parse_tasks)


async def _parse_task(context, chat_id: int, link: str, message_id: int, progress_msg=None) -> None:
    """Background task for parsing and downloading - runs independently"""
    current_task = asyncio.current_task()
    try:
        # Get parser
        parser = parser_registry.get_parser(link)

        if parser:
            # Parse content
            await _send_or_edit_message(
                context, chat_id, f"📥 正在解析 {parser.platform_id} 内容...", progress_msg
            )
            post = await parser.invoke(link, download=True)

            if post:
                reply_text = _format_social_post_response(post)
                download_results = getattr(post, 'download_results', None)

                if download_results and any(r.get('success') for r in download_results):
                    # Show download summary with file details
                    download_summary = _format_download_summary(download_results)
                    await _send_or_edit_message(context, chat_id, download_summary, progress_msg)
                    # Brief pause to let user see the summary
                    await asyncio.sleep(1.5)

                    await _send_or_edit_message(
                        context, chat_id, "📤 正在发送媒体文件...", progress_msg
                    )
                    await _send_media_files(
                        context, chat_id, download_results, reply_text, progress_msg, message_id
                    )
                else:
                    await _send_or_edit_message(
                        context, chat_id, reply_text, progress_msg, message_id
                    )
                return
            else:
                reply_text = f"❌ 无法解析 {parser.platform_id} 链接，请检查链接是否有效"
        else:
            # Unsupported platform
            platforms_text = "\n".join(
                [f"• {p}" for p in parser_registry.get_supported_platforms()]
            )
            reply_text = (
                "❌ 不支持的链接类型\n\n"
                f"<b>目前支持的平台：</b>\n{platforms_text}\n\n"
                "更多平台支持正在开发中..."
            )

        await _send_or_edit_message(context, chat_id, reply_text, progress_msg, message_id)

    except Exception as e:
        logger.exception(f"解析链接失败: {e}")
        error_text = (
            "❌ 解析失败，请稍后重试\n\n"
            "<b>可能的原因：</b>\n• 链接格式不正确\n• 网络连接问题\n• 服务暂时不可用"
        )
        await _send_or_edit_message(context, chat_id, error_text, progress_msg, message_id)
    finally:
        # Ensure task is removed from active set when done
        if current_task:
            _active_parse_tasks.discard(current_task)


@non_blocking_handler("parse_command")
async def parse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parse social media links and automatically download media resources"""
    link = _extract_link_from_args(context.args)
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        logger.warning("parse 命令：无法找到有效的消息或聊天信息")
        return

    if not link:
        platforms_text = "\n".join([f"• {p}" for p in parser_registry.get_supported_platforms()])
        reply_text = (
            "❌ 请提供一个有效的链接\n\n"
            "<b>使用方法：</b> <code>/parse &lt;链接&gt;</code>\n\n"
            f"<b>支持的平台：</b>\n{platforms_text}"
        )
        await _send_or_edit_message(context, chat.id, reply_text, reply_to_id=message.message_id)
        return

    # Add emoji reaction
    with suppress(Exception):
        await context.bot.set_message_reaction(
            chat_id=chat.id, message_id=message.message_id, reaction=[ReactionTypeEmoji(emoji="🎉")]
        )

    # Send an initial progress message
    progress_msg = None
    with suppress(Exception):
        progress_msg = await context.bot.send_message(
            chat_id=chat.id,
            text="<blockquote>🔍 正在解析链接...</blockquote>",
            parse_mode='HTML',
            reply_to_message_id=message.message_id,
        )

    # Clean up completed tasks periodically
    await _cleanup_completed_tasks()

    # Create background task for parsing - this won't block the bot
    task = asyncio.create_task(
        _parse_task(context, chat.id, link, message.message_id, progress_msg)
    )

    # Add task to set to prevent garbage collection and track active tasks
    _active_parse_tasks.add(task)

    # The task runs independently without blocking other bot operations
    logger.info(
        f"Started non-blocking parse task for link: {link[:50]}... (Active tasks: {len(_active_parse_tasks)})"
    )
