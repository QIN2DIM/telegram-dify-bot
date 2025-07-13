# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/13 13:58
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from loguru import logger
from telegram import ReactionTypeEmoji
from telegram import Update
from telegram.ext import ContextTypes

from triggers.zlib_access_points import get_zlib_search_url, get_zlib_search_url_with_info

publication_tpl = """
<b>社交网络</b>
• Twitter: https://x.com/z_lib_official

<b>相关链接</b>
• Wikipedia: https://en.wikipedia.org/wiki/Z-Library
• Reddit: https://www.reddit.com/r/zlibrary
"""


def _extract_search_query(args: list) -> str:
    """从用户输入中提取真正的检索词，过滤掉 mention entity"""
    if not args:
        return ""

    # 过滤掉 mention entity（以 @ 开头的词）
    filtered_args = [arg for arg in args if not arg.startswith("@")]

    return " ".join(filtered_args).strip()


async def zlib_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """获取 zlib 访问链接"""

    # 获取用户输入的查询参数，过滤掉 mention entity
    query = _extract_search_query(context.args)
    logger.debug(f"Invoke Zlib: {query}")

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
        logger.info(f"zlib 命令收到内联查询: {update.inline_query.query}")
        return

    # 如果没有找到有效的消息或聊天信息，尝试从 effective_* 方法获取
    if not message or not chat:
        message = update.effective_message
        chat = update.effective_chat

    # 最后检查是否有有效的回复目标
    if not message or not chat:
        logger.warning("zlib 命令：无法找到有效的消息或聊天信息进行回复")
        return

    try:
        # 立即给消息添加 reaction 表示收到指令
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id,
                message_id=message.message_id,
                reaction=[ReactionTypeEmoji(emoji="👻")],
            )
        except Exception as reaction_error:
            logger.debug(f"无法设置消息反应: {reaction_error}")

        # 从数据库获取链接
        if query:
            # 有搜索查询时，使用原有方法
            search_url = get_zlib_search_url(query)
            if search_url:
                reply_text = f'<b>Z-Library</b> <a href="{search_url}">👉 {query}</a>'
            else:
                reply_text = (
                    f"❌ 无法获取 Z-Library 链接，请尝试以下方式：\n\n{publication_tpl.strip()}"
                )
        else:
            # 没有搜索查询时，获取带时间信息的链接
            url_info = get_zlib_search_url_with_info(query)
            if url_info:
                update_time = url_info["update_time"]
                # 格式化时间显示
                time_str = update_time.strftime("%Y-%m-%d %H:%M:%S UTC")
                reply_text = (
                    f"🕒 Last updated: <code>{time_str}</code>\n📚 Access point: {url_info['url']}"
                )
            else:
                reply_text = (
                    f"❌ 无法获取 Z-Library 链接，请尝试以下方式：\n\n{publication_tpl.strip()}"
                )

        # 发送回复消息，直接回复无需 mention 用户
        await context.bot.send_message(
            chat_id=chat.id,
            text=reply_text,
            parse_mode='HTML',
            reply_to_message_id=message.message_id,
        )

    except Exception as e:
        # 发生异常时使用默认回复
        logger.error(f"获取 zlib 链接失败: {e}")

        # 确保有有效的回复目标
        if not message or not chat:
            logger.warning("zlib 命令异常处理：无法找到有效的回复目标")
            return

        reply_text = f"❌ 服务暂时不可用，请尝试以下方式：\n\n{publication_tpl.strip()}"

        # 发送错误消息，直接回复无需 mention 用户
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=reply_text,
                parse_mode='HTML',
                reply_to_message_id=message.message_id,
            )
        except Exception as send_error:
            logger.error(f"发送错误回复失败: {send_error}")
