# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 02:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Parse social media links and automatically download media resources
"""

from pathlib import Path

from loguru import logger
from telegram import ReactionTypeEmoji, Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes

from plugins.social_parser import parser_registry
from utils.image_compressor import compress_image_for_telegram


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


async def _send_media_files(
    context, chat_id: int, download_results: list, post_content: str = ""
) -> None:
    """Send downloaded media files to chat with post content as caption"""
    if not download_results:
        return

    # Filter successful downloads
    successful_downloads = [r for r in download_results if r['success'] and r['local_path']]

    if not successful_downloads:
        logger.debug("No successful downloads to send")
        return

    # Group files by type for batch sending
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

        # Create caption for first media item only (include full post content)
        caption = ""
        if len(photos) == 0 and len(videos) == 0 and len(documents) == 0:
            caption = post_content if post_content else "📥 下载的媒体文件"

        if media_type == 'photo':
            # Try to compress image if needed
            try:
                compressed_path = compress_image_for_telegram(file_path)
                if compressed_path != file_path:
                    # Compression was performed, track for cleanup
                    compressed_files.append(compressed_path)
                    logger.info(
                        f"Image compressed: {Path(file_path).name} -> {Path(compressed_path).name}"
                    )
                photos.append({'file_path': compressed_path, 'caption': caption})
            except Exception as e:
                logger.warning(f"Image compression failed for {file_path}: {e}, using original")
                photos.append({'file_path': file_path, 'caption': caption})
        elif media_type == 'video':
            videos.append({'file_path': file_path, 'caption': caption})
        else:
            documents.append(file_path)  # Send documents individually

    try:
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

        # Send documents individually
        for i, doc_path in enumerate(documents):
            with open(doc_path, 'rb') as doc_file:
                # Use post content as caption for first document only
                doc_caption = (
                    post_content if i == 0 and not photos and not videos else "📄 其他格式文件"
                )
                await context.bot.send_document(
                    chat_id=chat_id, document=doc_file, caption=doc_caption, parse_mode="HTML"
                )
                logger.info(f"Sent document: {doc_path}")

    except Exception as e:
        logger.error(f"Failed to send media files: {e}")
        # Send fallback message
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ 媒体文件发送失败: {str(e)}\n\n但文件已成功下载到本地。",
            parse_mode='HTML',
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

        # Get appropriate parser from registry
        parser = parser_registry.get_parser(link)

        if parser:
            # Parse using the appropriate parser
            post = await parser.invoke(link, download=download)

            if post:
                # Format post content
                reply_text = _format_social_post_response(post)

                # Check if there are downloaded media files
                download_results = getattr(post, 'download_results', None)
                if download_results and any(r['success'] for r in download_results):
                    # Send media files with post content as caption
                    await _send_media_files(context, chat.id, download_results, reply_text)
                    logger.info(f"Sent media files with content for {parser.platform_id} post")
                else:
                    # No media files, send text only
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
            supported_platforms = parser_registry.get_supported_platforms()
            platforms_text = "\n".join([f"• {platform}" for platform in supported_platforms])

            reply_text = (
                "❌ 不支持的链接类型\n\n"
                "<b>目前支持的平台：</b>\n"
                f"{platforms_text}\n\n"
                "更多平台支持正在开发中..."
            )

        # Send error/unsupported reply message
        await context.bot.send_message(
            chat_id=chat.id,
            text=reply_text,
            parse_mode='HTML',
            reply_to_message_id=message.message_id,
        )

    except Exception as e:
        # Handle exceptions with default reply
        logger.error(f"解析链接失败: {e}")

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

        # Send error message
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=reply_text,
                parse_mode='HTML',
                reply_to_message_id=message.message_id,
            )
        except Exception as send_error:
            logger.error(f"发送错误回复失败: {send_error}")
