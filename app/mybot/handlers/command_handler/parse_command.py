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
from telegram import ReactionTypeEmoji, Update
from telegram.ext import ContextTypes

from mybot.task_manager import non_blocking_handler
from mybot.services.telegram_media_service import TelegramMediaService
from mybot.services.message_formatter import MessageFormatter
from plugins.social_parser import parser_registry


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

    for arg in args:
        if "http" in arg.lower() or "www." in arg.lower():
            return arg.strip()

    # If no URL found, use the first argument
    return args[0].strip()


async def _cleanup_files(download_results: list) -> None:
    """Clean up downloaded files after successful sending"""
    cleaned_dirs = set()

    for result in download_results:
        if result.get('success') and result.get('local_path'):
            file_path = Path(result['local_path'])
            try:
                if file_path.exists():
                    parent_dir = file_path.parent
                    file_path.unlink()
                    logger.debug(f"Cleaned up downloaded file: {file_path}")
                    cleaned_dirs.add(parent_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up file {file_path}: {e}")

    # Clean up empty directories
    for dir_path in cleaned_dirs:
        try:
            if dir_path.exists() and not any(dir_path.iterdir()):
                dir_path.rmdir()
                logger.debug(f"Removed empty directory: {dir_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up directory {dir_path}: {e}")


async def _send_media_progress_callback(context, chat_id, progress_msg):
    """Callback for media sending progress"""

    async def callback(total_files, photos, videos, documents):
        if progress_msg and total_files > 0:
            info_text = MessageFormatter.format_media_sending_info(photos, videos, documents)
            await _send_or_edit_message(context, chat_id, info_text, progress_msg)

    return callback


async def _handle_long_caption(bot, chat_id, message_id, caption):
    """Handle caption that's too long for Telegram"""
    try:
        # Send as a separate message
        await bot.send_message(
            chat_id=chat_id, text=caption, parse_mode="HTML", reply_to_message_id=message_id
        )
    except Exception as e:
        logger.warning(f"Failed to handle long caption: {e}")


async def _parse_and_download(
    context, chat_id: int, link: str, message_id: int, progress_msg=None
) -> None:
    """Parse social media link and download media if available"""
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
                # Format post content
                reply_text = MessageFormatter.format_social_post(post)
                download_results = getattr(post, 'download_results', None)

                if download_results and any(r.get('success') for r in download_results):
                    # Show download summary
                    download_summary = MessageFormatter.format_download_summary(download_results)
                    await _send_or_edit_message(context, chat_id, download_summary, progress_msg)
                    await asyncio.sleep(1.5)

                    # Send media files
                    await _send_or_edit_message(
                        context, chat_id, "📤 正在发送媒体文件...", progress_msg
                    )

                    # Prepare media files
                    media_files = []
                    for i, result in enumerate(download_results):
                        if result.get('success') and result.get('local_path'):
                            caption = reply_text if i == 0 else ""
                            media_files.append(
                                {'file_path': result['local_path'], 'caption': caption}
                            )

                    # Send media using the service
                    try:
                        progress_callback = await _send_media_progress_callback(
                            context, chat_id, progress_msg
                        )

                        first_msg_id = await TelegramMediaService.send_media_batch(
                            bot=context.bot,
                            chat_id=chat_id,
                            media_files=media_files,
                            reply_to_message_id=message_id,
                            progress_callback=progress_callback,
                        )

                        # Delete progress message after success
                        if progress_msg:
                            with suppress(Exception):
                                await context.bot.delete_message(
                                    chat_id=chat_id, message_id=progress_msg.message_id
                                )

                        # Handle long caption if needed
                        if first_msg_id and len(reply_text) > 1024:
                            await _handle_long_caption(
                                context.bot, chat_id, first_msg_id, reply_text
                            )

                        # Clean up downloaded files
                        await _cleanup_files(download_results)

                    except Exception as e:
                        error_text = f"❌ 媒体文件发送失败: {str(e)}\n\n但文件已成功下载到本地。"
                        await _send_or_edit_message(
                            context, chat_id, error_text, progress_msg, message_id
                        )
                else:
                    # No media to download, just send the post content
                    await _send_or_edit_message(
                        context, chat_id, reply_text, progress_msg, message_id
                    )
            else:
                reply_text = f"❌ 无法解析 {parser.platform_id} 链接，请检查链接是否有效"
                await _send_or_edit_message(context, chat_id, reply_text, progress_msg, message_id)
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
            "✨ 请提供一个有效的链接\n\n"
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

    # Parse and download media
    await _parse_and_download(context, chat.id, link, message.message_id, progress_msg)
