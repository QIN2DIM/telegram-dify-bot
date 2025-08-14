# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/21 21:07
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 搜索命令处理器，使用 Dify 大模型服务提供智能搜索功能
"""

from loguru import logger
from telegram import ReactionTypeEmoji, Chat, Message
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from dify.models import ForcedCommand
from models import Interaction, TaskType
from mybot.common import add_message_to_media_group_cache, download_media_group_files
from mybot.services import dify_service, response_service
from mybot.task_manager import non_blocking_handler

EMOJI_REACTION = [ReactionTypeEmoji(emoji="🤔")]


def _extract_search_query(args: list) -> str:
    """从用户输入中提取真正的检索词，过滤掉 mention entity"""
    if not args:
        return ""

    # 过滤掉 mention entity（以 @ 开头的词）
    filtered_args = [arg for arg in args if not arg.startswith("@")]

    return " ".join(filtered_args).strip()


async def _match_context(update: Update):
    """Match and extract message and chat context from update"""
    message = None
    chat = None

    if update.message:
        message = update.message
        chat = update.message.chat
    elif update.callback_query:
        message = update.callback_query.message
        chat = update.callback_query.message.chat if update.callback_query.message else None

    # Fallback to effective_* methods
    if not message or not chat:
        message = update.effective_message
        chat = update.effective_chat

    return message, chat


async def _reply_emoji_reaction(context: ContextTypes.DEFAULT_TYPE, chat: Chat, message: Message):
    """Send emoji reaction to indicate processing"""
    try:
        await context.bot.set_message_reaction(
            chat_id=chat.id, message_id=message.message_id, reaction=EMOJI_REACTION
        )
    except Exception as reaction_error:
        logger.debug(f"无法设置消息反应: {reaction_error}")


async def _process_media_files(message: Message, context: ContextTypes.DEFAULT_TYPE):
    """Process and download media files from message"""
    # Add message to media group cache and download all media files
    add_message_to_media_group_cache(message)
    media_files = await download_media_group_files(message, context.bot)

    # Check if any media was downloaded
    has_media = False
    if media_files:
        for media_type, paths in media_files.items():
            if paths:
                has_media = True
                logger.info(f"Downloaded {len(paths)} {media_type} for search")
                break

    # For backward compatibility
    photo_paths = media_files.get("photos", []) if media_files else []

    return media_files, has_media, photo_paths


async def _reply_help(
    context: ContextTypes.DEFAULT_TYPE, chat: Chat, message: Message, query: str, has_media: bool
) -> bool:
    """Reply with help message if no query or media provided"""
    if query or has_media:
        return False

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text="请提供搜索关键词或上传文件\n\n使用方法: \n• <code>/search 你的搜索内容</code>\n• <code>/search</code> + 发送图片/文档/音频/视频\n• <code>/search 描述文字</code> + 发送文件",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
    except Exception as send_error:
        logger.error(f"发送搜索提示失败: {send_error}")

    return True


@non_blocking_handler("search_command")
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """智能搜索命令，使用 Dify 大模型服务提供搜索结果"""
    # Skip inline queries
    if update.inline_query:
        logger.info(f"search 命令收到内联查询: {update.inline_query.query}")
        return

    # Extract search query
    query = _extract_search_query(context.args)
    logger.debug(f"Invoke Search: {query}")

    # Match message and chat context
    message, chat = await _match_context(update)
    if not message or not chat:
        logger.warning("search 命令：无法找到有效的消息或聊天信息进行回复")
        return

    # Process media files
    media_files, has_media, photo_paths = await _process_media_files(message, context)

    # Show help if no query or media provided
    if await _reply_help(context, chat, message, query, has_media):
        return

    # Use default prompt for media-only searches
    if not query and has_media:
        query = "请分析这个文件"

    # Add reaction to indicate processing
    await _reply_emoji_reaction(context, chat, message)

    # Create Interaction object
    interaction = Interaction(
        task_type=TaskType.MENTION,
        from_user_fmt=str(message.from_user.id if message.from_user else "unknown"),
        photo_paths=photo_paths,
        media_files=media_files,
    )

    # Get bot username
    bot_username = f"{context.bot.username.rstrip('@')}"

    # Invoke Dify service with streaming
    try:
        logger.info(f"开始调用 Dify 搜索服务 (流式): {query[:100]}... (媒体文件: {has_media})")

        streaming_generator = dify_service.invoke_model_streaming(
            bot_username=bot_username,
            message_context=query,
            from_user=interaction.from_user_fmt,
            photo_paths=photo_paths,
            media_files=media_files,
            forced_command=ForcedCommand.GOOGLE_GROUNDING,
        )

        await response_service.send_streaming_response(update, context, streaming_generator)

    except Exception as search_error:
        logger.error(f"调用 Dify 搜索服务失败: {search_error}")

        # Send error message
        await context.bot.send_message(
            chat_id=chat.id,
            text="❌ 搜索过程中发生错误，请稍后再试",
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.message_id,
        )
