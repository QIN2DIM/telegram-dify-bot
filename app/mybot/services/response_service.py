# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for sending responses to Telegram.
"""
import json
from contextlib import suppress
from typing import AsyncGenerator, Dict, Any

from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from models import Interaction, TaskType


async def _send_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
    log_prefix: str = "",
) -> bool:
    """发送消息的辅助函数，优雅降级处理 Markdown 格式错误"""
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=reply_to_message_id,
        )
        return True
    except Exception as err:
        logger.debug(f"Failed to send with HTML: {err}")
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id
            )
            logger.debug(f"{log_prefix} sent without parse_mode - {err}")
            return True
        except Exception as e2:
            logger.error(f"Failed to send message: {e2}")
            return False


async def send_standard_response(
    update: Update, context: ContextTypes.DEFAULT_TYPE, interaction: Interaction, result_text: str
):
    """为 blocking 模式发送标准回复"""
    chat_id = update.effective_chat.id
    trigger_message = update.effective_message

    if interaction.task_type in [TaskType.MENTION, TaskType.MENTION_WITH_REPLY, TaskType.REPLAY]:
        # 优先直接回复
        sent = await _send_message(
            context,
            chat_id,
            result_text,
            reply_to_message_id=trigger_message.message_id,
            log_prefix="Direct reply",
        )
        if sent:
            return

        # 失败则尝试 @用户
        user_mention = "User"
        if trigger_message.from_user:
            user_mention = trigger_message.from_user.mention_html()
        final_text = f"{user_mention}\n\n{result_text}"
        await _send_message(context, chat_id, final_text, log_prefix="Mention reply")

    elif interaction.task_type == TaskType.AUTO:
        await _send_message(context, chat_id, result_text, log_prefix="Auto reply")


async def send_streaming_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    interaction: Interaction,
    streaming_generator: AsyncGenerator[Dict[str, Any], None],
):
    """处理流式响应，发送并编辑消息"""
    chat = update.effective_chat
    trigger_message = update.effective_message
    initial_message = None

    try:
        # 创建初始消息
        initial_text = "🤔 思考中..."
        initial_message = await context.bot.send_message(
            chat_id=chat.id,
            text=initial_text,
            reply_to_message_id=(
                trigger_message.message_id if interaction.task_type != TaskType.AUTO else None
            ),
        )

        final_result: dict | None = None
        answer_key = "answer"

        async for chunk in streaming_generator:
            if not chunk or not isinstance(chunk, dict) or not (event := chunk.get("event")):
                continue

            chunk_data = chunk.get("data", {})
            if event == "workflow_finished":
                final_result = chunk_data.get('outputs', {})
                break
            elif event == "node_started":
                if node_title := chunk_data.get("title"):
                    progress_text = f"> {node_title}"
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat.id,
                            message_id=initial_message.message_id,
                            text=progress_text,
                        )
                    except Exception:
                        pass

        with suppress(Exception):
            outputs_json = json.dumps(final_result, indent=2, ensure_ascii=False)
            logger.debug(f"LLM Result: \n{outputs_json}")

        # 更新为最终结果
        if final_result and (final_answer := final_result.get(answer_key, '')):
            try:
                await context.bot.edit_message_text(
                    chat_id=chat.id,
                    message_id=initial_message.message_id,
                    text=final_answer,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                await context.bot.edit_message_text(
                    chat_id=chat.id, message_id=initial_message.message_id, text=final_answer
                )
        else:
            await context.bot.edit_message_text(
                chat_id=chat.id, message_id=initial_message.message_id, text="抱歉，处理失败。"
            )

    except Exception as e:
        logger.error(f"Streaming response error: {e}")
        error_message = "抱歉，处理过程中遇到问题，请稍后再试。"
        if initial_message:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat.id, message_id=initial_message.message_id, text=error_message
                )
            except Exception as e2:
                logger.error(f"Failed to edit message to error: {e2}")
        else:
            await _send_message(
                context, chat.id, error_message, reply_to_message_id=trigger_message.message_id
            )
