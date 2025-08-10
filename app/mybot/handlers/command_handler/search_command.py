# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/21 21:07
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : 搜索命令处理器，使用 Dify 大模型服务提供智能搜索功能
"""

from loguru import logger
from telegram import ReactionTypeEmoji
from telegram import Update
from telegram.ext import ContextTypes

from dify.models import ForcedCommand
from models import Interaction, TaskType
from mybot.common import download_all_media_from_message
from mybot.task_manager import non_blocking_handler
from mybot.services import dify_service, response_service


def _extract_search_query(args: list) -> str:
    """从用户输入中提取真正的检索词，过滤掉 mention entity"""
    if not args:
        return ""

    # 过滤掉 mention entity（以 @ 开头的词）
    filtered_args = [arg for arg in args if not arg.startswith("@")]

    return " ".join(filtered_args).strip()


@non_blocking_handler("search_command")
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """智能搜索命令，使用 Dify 大模型服务提供搜索结果"""

    # 获取用户输入的查询参数，过滤掉 mention entity
    query = _extract_search_query(context.args)
    logger.debug(f"Invoke Search: {query}")

    # 尝试获取有效的消息和聊天信息
    message = None
    chat = None

    if update.message:
        message = update.message
        chat = update.message.chat
    elif update.callback_query:
        message = update.callback_query.message
        chat = update.callback_query.message.chat if update.callback_query.message else None
    elif update.inline_query:
        # 内联查询无法直接回复，记录并返回
        logger.info(f"search 命令收到内联查询: {update.inline_query.query}")
        return

    # 如果没有找到有效的消息或聊天信息，尝试从 effective_* 方法获取
    if not message or not chat:
        message = update.effective_message
        chat = update.effective_chat

    # 最后检查是否有有效的回复目标
    if not message or not chat:
        logger.warning("search 命令：无法找到有效的消息或聊天信息进行回复")
        return

    # Download all media files from message
    media_files = await download_all_media_from_message(message, context.bot)

    # Check if any media was downloaded
    has_media = False
    if media_files:
        for media_type, paths in media_files.items():
            if paths:
                has_media = True
                logger.info(f"Downloaded {len(paths)} {media_type} for search")
                break

    # For backward compatibility
    photo_paths = media_files.get("photos", []) if media_files else None

    # 检查是否提供了搜索查询或媒体文件
    if not query and not has_media:
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text="请提供搜索关键词或上传文件\n\n使用方法: \n• <code>/search 你的搜索内容</code>\n• <code>/search</code> + 发送图片/文档/音频/视频\n• <code>/search 描述文字</code> + 发送文件",
                parse_mode='HTML',
                reply_to_message_id=message.message_id,
            )
        except Exception as send_error:
            logger.error(f"发送搜索提示失败: {send_error}")
        return

    # 如果没有文本但有媒体，使用默认的分析提示
    if not query and has_media:
        query = "请分析这个文件"

    # 立即给消息添加 reaction 表示收到指令
    try:
        await context.bot.set_message_reaction(
            chat_id=chat.id, message_id=message.message_id, reaction=[ReactionTypeEmoji(emoji="🤔")]
        )
    except Exception as reaction_error:
        logger.debug(f"无法设置消息反应: {reaction_error}")

    # 创建 Interaction 对象以模仿 message_handler 的处理方式
    interaction = Interaction(
        task_type=TaskType.MENTION,  # 使用 MENTION 类型以确保回复到原消息
        from_user_fmt=str(message.from_user.id if message.from_user else "unknown"),
        photo_paths=photo_paths or [],
        media_files=media_files,
    )

    # 获取 bot username
    bot_username = f"{context.bot.username.rstrip('@')}"

    # 使用流式调用 Dify 服务
    try:
        logger.info(f"开始调用 Dify 搜索服务 (流式): {query} (媒体文件: {has_media})")

        streaming_generator = dify_service.invoke_model_streaming(
            bot_username=bot_username,
            message_context=query,
            from_user=interaction.from_user_fmt,
            photo_paths=photo_paths,
            media_files=media_files,
            forced_command=ForcedCommand.GOOGLE_GROUNDING,  # 前置传参 forced_command
        )

        # 使用 response_service 处理流式响应
        await response_service.send_streaming_response(
            update, context, interaction, streaming_generator
        )

    except Exception as search_error:
        logger.error(f"调用 Dify 搜索服务失败: {search_error}")

        # 发送错误提示
        await context.bot.send_message(
            chat_id=chat.id,
            text="❌ 搜索过程中发生错误，请稍后再试",
            parse_mode='HTML',
            reply_to_message_id=message.message_id,
        )
