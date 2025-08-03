# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 02:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Parse social media links and automatically download media resources
"""

from pathlib import Path

from loguru import logger
from telegram import ReactionTypeEmoji, Update, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from telegram.ext import ContextTypes

from plugins.social_parser import parser_registry
from utils.image_compressor import compress_image_for_telegram


async def _update_progress_message(
    context, chat_id: int, message_id: int, progress_text: str
) -> bool:
    """Update progress message with new status"""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"<blockquote>{progress_text}</blockquote>",
            parse_mode='HTML',
        )
        return True
    except Exception as e:
        logger.debug(f"Failed to update progress message: {e}")
        return False


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


def _determine_send_method(file_path: str, media_type: str) -> str:
    """Determine how to send file based on Telegram limits and file type

    Telegram limits:
    - URL upload: 20MB
    - Preview (photo/video): 50MB
    - Document: 2GB

    Returns: 'photo', 'video', 'document', or 'compress_photo'
    """
    file_size = _get_file_size(file_path)

    # Constants for Telegram limits (in bytes)
    URL_LIMIT = 20 * 1024 * 1024  # 20MB
    PREVIEW_LIMIT = 50 * 1024 * 1024  # 50MB
    DOCUMENT_LIMIT = 2 * 1024 * 1024 * 1024  # 2GB

    if file_size > DOCUMENT_LIMIT:
        logger.warning(f"File {file_path} exceeds 2GB limit: {file_size} bytes")
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
        if file_size <= PREVIEW_LIMIT:
            return 'video'
        else:
            # For videos >50MB, send as document
            return 'document'

    else:
        return 'document'


async def _send_media_files(
    context, chat_id: int, download_results: list, post_content: str = "", progress_message=None
) -> bool:
    """Send downloaded media files to chat with post content as caption"""
    if not download_results:
        return False

    # Filter successful downloads
    successful_downloads = [r for r in download_results if r['success'] and r['local_path']]

    if not successful_downloads:
        logger.debug("No successful downloads to send")
        return False

    # Group files by send method for batch sending
    photos = []
    videos = []
    documents = []
    compressed_files = []  # Track compressed files for cleanup

    for result in successful_downloads:
        file_path = result['local_path']

        # Check if file exists
        if not Path(file_path).exists():
            logger.warning(f"Downloaded file not found: {file_path}")
            continue

        media_type = _get_media_type(file_path)
        send_method = _determine_send_method(file_path, media_type)
        file_size = _get_file_size(file_path)

        # Create caption for first media item only (include full post content)
        caption = ""
        if len(photos) == 0 and len(videos) == 0 and len(documents) == 0:
            caption = post_content if post_content else "📥 下载的媒体文件"

        logger.debug(
            f"File: {Path(file_path).name}, Size: {file_size/1024/1024:.1f}MB, Type: {media_type}, Send as: {send_method}"
        )

        if send_method == 'photo':
            photos.append({'file_path': file_path, 'caption': caption})
        elif send_method == 'compress_photo':
            # Try to compress image for large photos
            try:
                compressed_path = compress_image_for_telegram(file_path)
                if compressed_path != file_path:
                    # Compression was performed, track for cleanup
                    compressed_files.append(compressed_path)
                    logger.info(
                        f"Image compressed: {Path(file_path).name} -> {Path(compressed_path).name}"
                    )
                    # Check if compressed image is small enough for photo
                    compressed_size = _get_file_size(compressed_path)
                    if compressed_size <= 50 * 1024 * 1024:  # 50MB
                        photos.append({'file_path': compressed_path, 'caption': caption})
                    else:
                        # Still too large after compression, send as document
                        documents.append({'file_path': compressed_path, 'caption': caption})
                else:
                    # No compression needed or failed, send as document
                    documents.append({'file_path': file_path, 'caption': caption})
            except Exception as e:
                logger.warning(
                    f"Image compression failed for {file_path}: {e}, sending as document"
                )
                documents.append({'file_path': file_path, 'caption': caption})
        elif send_method == 'video':
            videos.append({'file_path': file_path, 'caption': caption})
        else:  # send_method == 'document'
            documents.append({'file_path': file_path, 'caption': caption})

    try:
        # Update progress for sending media
        total_files = len(photos) + len(videos) + len(documents)
        if progress_message and total_files > 0:
            await _update_progress_message(
                context,
                chat_id,
                progress_message.message_id,
                f"📤 正在发送 {total_files} 个媒体文件...",
            )

        # Flag to track if we successfully edited the progress message with final content
        progress_updated_with_content = False

        # Send photo albums (up to 10 at a time)
        if photos:
            for i in range(0, len(photos), 10):
                batch_info = photos[i : i + 10]
                media_batch = []

                # Open files for this batch
                for photo_info in batch_info:
                    file_obj = open(photo_info['file_path'], 'rb')
                    media_batch.append(
                        InputMediaPhoto(
                            media=file_obj, caption=photo_info['caption'], parse_mode="HTML"
                        )
                    )

                try:
                    await context.bot.send_media_group(
                        chat_id=chat_id, media=media_batch, parse_mode="HTML"
                    )
                    logger.info(f"Sent photo batch {i//10 + 1} with {len(batch_info)} photos")
                finally:
                    # Close files for this batch
                    for media in media_batch:
                        try:
                            media.media.close()
                        except:
                            pass

        # Send video albums (up to 10 at a time)
        if videos:
            for i in range(0, len(videos), 10):
                batch_info = videos[i : i + 10]
                media_batch = []

                # Open files for this batch
                for video_info in batch_info:
                    file_obj = open(video_info['file_path'], 'rb')
                    media_batch.append(
                        InputMediaVideo(
                            media=file_obj, caption=video_info['caption'], parse_mode="HTML"
                        )
                    )

                try:
                    await context.bot.send_media_group(
                        chat_id=chat_id, media=media_batch, parse_mode="HTML"
                    )
                    logger.info(f"Sent video batch {i//10 + 1} with {len(batch_info)} videos")
                finally:
                    # Close files for this batch
                    for media in media_batch:
                        try:
                            media.media.close()
                        except:
                            pass

        # Send documents as media group (up to 10 at a time)
        if documents:
            for i in range(0, len(documents), 10):
                batch_info = documents[i : i + 10]
                media_batch = []

                # Open files for this batch
                for j, doc_info in enumerate(batch_info):
                    # Handle both old format (string) and new format (dict)
                    if isinstance(doc_info, dict):
                        doc_path = doc_info['file_path']
                        doc_caption = doc_info['caption'] if doc_info['caption'] else ""
                    else:
                        doc_path = doc_info
                        doc_caption = ""

                    # Use post content as caption for first document in first batch only
                    if i == 0 and j == 0 and not photos and not videos:
                        if not doc_caption:
                            doc_caption = post_content if post_content else "📄 文档文件"
                    elif not doc_caption:
                        doc_caption = ""

                    file_obj = open(doc_path, 'rb')
                    media_batch.append(
                        InputMediaDocument(media=file_obj, caption=doc_caption, parse_mode="HTML")
                    )

                try:
                    await context.bot.send_media_group(
                        chat_id=chat_id, media=media_batch, parse_mode="HTML"
                    )
                    logger.info(f"Sent document batch {i//10 + 1} with {len(batch_info)} documents")
                finally:
                    # Close files for this batch
                    for media in media_batch:
                        try:
                            media.media.close()
                        except:
                            pass

        # Try to edit progress message with final content if we haven't done so yet
        if progress_message and not progress_updated_with_content and post_content:
            success = await _update_progress_message(
                context, chat_id, progress_message.message_id, post_content
            )
            if success:
                progress_updated_with_content = True

        return True

    except Exception as e:
        logger.error(f"Failed to send media files: {e}")

        # Try to edit progress message with error
        if progress_message:
            await _update_progress_message(
                context,
                chat_id,
                progress_message.message_id,
                f"❌ 媒体文件发送失败: {str(e)}\n\n但文件已成功下载到本地。",
            )
            return True
        else:
            # Send fallback message
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ 媒体文件发送失败: {str(e)}\n\n但文件已成功下载到本地。",
                parse_mode='HTML',
            )
            return False


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
        # Limit description length for readability
        desc = post.desc if len(post.desc) <= 200 else post.desc[:200] + "..."
        desc = desc.replace("[话题]", "")
        desc = f"<blockquote>{desc}</blockquote>"
        response_parts.append(desc)

    return "\n\n".join(response_parts)


async def parse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parse social media links and automatically download media resources"""

    # Extract link from user input (download is always enabled)
    link = _extract_link_from_args(context.args)
    download = True  # Always download resources
    logger.debug(f"Invoke Parse: {link}, download: {download}")

    # Try to get valid message and chat info
    message = None
    chat = None

    if update.message:
        message = update.message
        chat = update.message.chat
    elif update.callback_query:
        message = update.callback_query.message
        chat = update.callback_query.message.chat if update.callback_query.message else None
    elif update.inline_query:
        # Inline queries cannot be replied to directly, log and return
        logger.info(f"parse 命令收到内联查询: {update.inline_query.query}")
        return

    # If no valid message or chat info found, try to get from effective_* methods
    if not message or not chat:
        message = update.effective_message
        chat = update.effective_chat

    # Final check for valid reply target
    if not message or not chat:
        logger.warning("parse 命令：无法找到有效的消息或聊天信息进行回复")
        return

    # Validate link input
    if not link:
        supported_platforms = parser_registry.get_supported_platforms()
        platforms_text = "\n".join([f"• {platform}" for platform in supported_platforms])

        reply_text = (
            "❌ 请提供一个有效的链接\n\n"
            "<b>使用方法：</b>\n"
            "<code>/parse &lt;链接&gt;</code> - 解析内容并下载媒体资源\n\n"
            "<b>支持的平台：</b>\n"
            f"{platforms_text}"
        )
        await context.bot.send_message(
            chat_id=chat.id,
            text=reply_text,
            parse_mode='HTML',
            reply_to_message_id=message.message_id,
        )
        return

    try:
        # Add reaction to indicate command received
        try:
            reaction_emoji = "🎉"
            await context.bot.set_message_reaction(
                chat_id=chat.id,
                message_id=message.message_id,
                reaction=[ReactionTypeEmoji(emoji=reaction_emoji)],
            )
        except Exception as reaction_error:
            logger.debug(f"无法设置消息反应: {reaction_error}")

        # Send initial progress message
        progress_message = None
        try:
            progress_message = await context.bot.send_message(
                chat_id=chat.id,
                text="<blockquote>🔍 正在解析链接...</blockquote>",
                parse_mode='HTML',
                reply_to_message_id=message.message_id,
            )
        except Exception as progress_error:
            logger.debug(f"无法发送进度消息: {progress_error}")

        # Get appropriate parser from registry
        if progress_message:
            await _update_progress_message(
                context, chat.id, progress_message.message_id, "🔍 识别平台类型..."
            )
        parser = parser_registry.get_parser(link)

        if parser:
            # Update progress for parsing
            if progress_message:
                await _update_progress_message(
                    context,
                    chat.id,
                    progress_message.message_id,
                    f"📄 正在解析 {parser.platform_id} 内容...",
                )

            # Parse using the appropriate parser
            post = await parser.invoke(link, download=download)

            if post:
                # Format post content
                reply_text = _format_social_post_response(post)

                # Check if there are downloaded media files
                download_results = getattr(post, 'download_results', None)
                if download_results and any(r['success'] for r in download_results):
                    # Update progress for media processing
                    if progress_message:
                        await _update_progress_message(
                            context, chat.id, progress_message.message_id, "📥 正在处理媒体文件..."
                        )

                    # Send media files with post content as caption, try to edit progress message first
                    success = await _send_media_files(
                        context, chat.id, download_results, reply_text, progress_message
                    )
                    if success:
                        logger.info(f"Sent media files with content for {parser.platform_id} post")
                    else:
                        # Fallback to new message if edit failed
                        await _send_media_files(
                            context, chat.id, download_results, reply_text, None
                        )
                        logger.info(
                            f"Sent media files as new messages for {parser.platform_id} post"
                        )
                else:
                    # No media files, edit progress message or send new text message
                    if progress_message:
                        success = await _update_progress_message(
                            context, chat.id, progress_message.message_id, reply_text
                        )
                        if not success:
                            # Fallback to new message if edit failed
                            await context.bot.send_message(
                                chat_id=chat.id,
                                text=reply_text,
                                parse_mode='HTML',
                                reply_to_message_id=message.message_id,
                            )
                    else:
                        await context.bot.send_message(
                            chat_id=chat.id,
                            text=reply_text,
                            parse_mode='HTML',
                            reply_to_message_id=message.message_id,
                        )
                    logger.debug(f"No media files to send for {parser.platform_id} post")

                return  # Exit after successful processing
            else:
                platform_name = parser.platform_id
                reply_text = f"❌ 无法解析 {platform_name} 链接，请检查链接是否有效"
        else:
            # Unsupported platform
            if progress_message:
                await _update_progress_message(
                    context, chat.id, progress_message.message_id, "❌ 不支持的链接类型"
                )

            supported_platforms = parser_registry.get_supported_platforms()
            platforms_text = "\n".join([f"• {platform}" for platform in supported_platforms])

            reply_text = (
                "❌ 不支持的链接类型\n\n"
                "<b>目前支持的平台：</b>\n"
                f"{platforms_text}\n\n"
                "更多平台支持正在开发中..."
            )

        # Send error/unsupported reply message, try to edit progress message first
        if progress_message:
            success = await _update_progress_message(
                context, chat.id, progress_message.message_id, reply_text
            )
            if not success:
                # Fallback to new message if edit failed
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=reply_text,
                    parse_mode='HTML',
                    reply_to_message_id=message.message_id,
                )
        else:
            await context.bot.send_message(
                chat_id=chat.id,
                text=reply_text,
                parse_mode='HTML',
                reply_to_message_id=message.message_id,
            )

    except Exception as e:
        # Handle exceptions with default reply
        logger.exception(f"解析链接失败: {e}")

        # Ensure valid reply target
        if not message or not chat:
            logger.warning("parse 命令异常处理：无法找到有效的回复目标")
            return

        reply_text = (
            "❌ 解析失败，请稍后重试\n\n"
            "<b>可能的原因：</b>\n"
            "• 链接格式不正确\n"
            "• 网络连接问题\n"
            "• 服务暂时不可用"
        )

        # Send error message, try to edit progress message first
        try:
            if progress_message:
                success = await _update_progress_message(
                    context, chat.id, progress_message.message_id, reply_text
                )
                if not success:
                    # Fallback to new message if edit failed
                    await context.bot.send_message(
                        chat_id=chat.id,
                        text=reply_text,
                        parse_mode='HTML',
                        reply_to_message_id=message.message_id,
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=reply_text,
                    parse_mode='HTML',
                    reply_to_message_id=message.message_id,
                )
        except Exception as send_error:
            logger.error(f"发送错误回复失败: {send_error}")
