# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/2 02:42
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Parse social media links and automatically download media resources
"""
from contextlib import suppress
from pathlib import Path

from loguru import logger
from telegram import ReactionTypeEmoji, Update, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from telegram.ext import ContextTypes

from plugins.social_parser import parser_registry
from utils.image_compressor import compress_image_for_telegram


async def _send_or_edit_message(
    context, chat_id: int, text: str, progress_msg=None, reply_to_id=None
):
    """Send new message or edit existing progress message"""
    if progress_msg:
        try:
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
        except Exception:
            pass  # Fall through to send new message

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

        for i in range(0, len(media_list), 10):
            batch = media_list[i : i + 10]
            media_batch = []
            for item in batch:
                file_obj = open(item['file_path'], 'rb')
                media_batch.append(
                    media_class(media=file_obj, caption=item['caption'], parse_mode="HTML")
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

            finally:
                for media in media_batch:
                    with suppress(Exception):
                        media.media.close()

        return current_first_msg_id

    try:
        total_files = len(photos) + len(videos) + len(documents)
        if progress_msg and total_files > 0:
            await _send_or_edit_message(
                context, chat_id, f"📤 正在发送 {total_files} 个媒体文件...", progress_msg
            )

        first_group_msg_id = None

        if photos:
            first_group_msg_id = await _send_batch(photos, InputMediaPhoto, first_group_msg_id)
        if videos:
            first_group_msg_id = await _send_batch(videos, InputMediaVideo, first_group_msg_id)
        if documents:
            first_group_msg_id = await _send_batch(
                documents, InputMediaDocument, first_group_msg_id
            )

        # Delete progress message after all media files are sent successfully
        if progress_msg:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id, message_id=progress_msg.message_id
                )
            except Exception:
                pass  # Message might already be deleted or not deletable

    except Exception as e:
        error_text = f"❌ 媒体文件发送失败: {str(e)}\n\n但文件已成功下载到本地。"
        # Try to edit progress message with error, or send new message if that fails
        if progress_msg:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text=error_text,
                    parse_mode='HTML',
                )
                return
            except Exception:
                pass  # Fall through to send new message

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

    # Telegram message limit is 4096 characters, use 90% as safe limit
    MAX_MESSAGE_LENGTH = int(4096 * 0.9)  # 3686 characters

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

    try:
        # Get parser
        await _send_or_edit_message(context, chat.id, "🔍 识别平台类型...", progress_msg)
        parser = parser_registry.get_parser(link)

        if parser:
            # Parse content
            await _send_or_edit_message(
                context, chat.id, f"📄 正在解析 {parser.platform_id} 内容...", progress_msg
            )
            post = await parser.invoke(link, download=True)

            if post:
                reply_text = _format_social_post_response(post)
                download_results = getattr(post, 'download_results', None)

                if download_results and any(r.get('success') for r in download_results):
                    await _send_or_edit_message(
                        context, chat.id, "📥 正在处理媒体文件...", progress_msg
                    )
                    await _send_media_files(
                        context,
                        chat.id,
                        download_results,
                        reply_text,
                        progress_msg,
                        message.message_id,
                    )
                else:
                    await _send_or_edit_message(
                        context, chat.id, reply_text, progress_msg, message.message_id
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

        await _send_or_edit_message(context, chat.id, reply_text, progress_msg, message.message_id)

    except Exception as e:
        logger.exception(f"解析链接失败: {e}")
        error_text = (
            "❌ 解析失败，请稍后重试\n\n"
            "<b>可能的原因：</b>\n• 链接格式不正确\n• 网络连接问题\n• 服务暂时不可用"
        )
        await _send_or_edit_message(context, chat.id, error_text, progress_msg, message.message_id)
