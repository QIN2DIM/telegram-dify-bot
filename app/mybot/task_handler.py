# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/9 00:47
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
from contextlib import suppress

from loguru import logger
from telegram import Update, Message
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from dify.workflow_tool import run_blocking_dify_workflow, run_streaming_dify_workflow
from models import TaskType, Interaction
from mybot.cli import auto_translation_enabled_chats
from mybot.common import (
    storage_messages_dataset,
    _is_available_direct_translation,
    _download_photos_from_message,
    get_hello_reply,
    get_image_mention_prompt,
)
from mybot.prompts import (
    MENTION_PROMPT_TEMPLATE,
    MENTION_WITH_REPLY_PROMPT_TEMPLATE,
    MESSAGE_FORMAT_TEMPLATE,
    USER_PREFERENCES_TPL,
    REPLY_SINGLE_PROMPT_TEMPLATE,
)
from settings import settings


async def _format_message(message: Message) -> str:
    """格式化单条消息"""
    username = "Anonymous"
    user_id = "unknown"

    if message.sender_chat:
        username = message.sender_chat.username or message.sender_chat.title or "Channel"
        user_id = str(message.sender_chat.id)
    elif message.from_user:
        username = message.from_user.username or message.from_user.first_name or "User"
        user_id = str(message.from_user.id)

    timestamp = message.date.strftime("%Y-%m-%d %H:%M:%S")
    text = message.text or message.caption or "[Media]"

    return MESSAGE_FORMAT_TEMPLATE.format(
        username=username, user_id=user_id, timestamp=timestamp, message=text
    )


async def _get_chat_history_for_mention(
    chat_id: int, trigger_message_id: int, bot, max_messages: int = 50, max_hours: int = 24
) -> str:
    """获取 MENTION 模式的历史消息

    注意：由于 Telegram Bot API 限制，无法直接获取历史消息。
    这里返回空字符串，实际项目中应该从数据库或缓存中获取。
    """
    # TODO: 从存储的消息数据集中获取历史消息
    # 可以使用 storage_messages_dataset 存储的数据

    # 临时返回空历史记录
    # 在实际实现中，应该从数据库查询历史消息
    return ""


async def _get_reply_mode_context(
    chat,
    user_message: Message,
    bot_message: Message,
    user_id: int,
    bot,
    context_range: int = 15,
    user_bot_history_limit: int = 20,
    days_limit: int = 7,
) -> tuple[str, str]:
    """获取 REPLY 模式的上下文消息和用户偏好消息

    返回格式化后的历史消息字符串和用户偏好字符串
    """
    logger.debug(f"Getting reply mode context for user {user_id} in chat {chat.id}")

    # 格式化被引用的机器人消息作为历史消息
    history_messages = ""
    if bot_message:
        # 使用现有的格式化函数来格式化机器人消息
        formatted_bot_message = await _format_message(bot_message)
        history_messages = formatted_bot_message

    # 暂时返回空的用户偏好，因为没有数据库功能
    # 在实际实现中，应该从数据库查询用户与机器人的历史交互记录
    user_preferences = ""

    return history_messages, user_preferences


async def _pre_interactivity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    trigger_message = update.effective_message

    # todo: remove
    with suppress(Exception):
        storage_messages_dataset(chat.type, trigger_message)

    # 检查当前聊天是否启用了自动翻译模式
    is_auto_mode = chat.id in auto_translation_enabled_chats

    task_type = _is_available_direct_translation(
        chat, trigger_message, context.bot, is_auto_trigger=is_auto_mode
    )
    if task_type:
        logger.debug(f"{task_type=}")

    if not task_type or not isinstance(task_type, TaskType):
        return

    if task_type == TaskType.MENTION:
        # 检查用户的真实输入内容（排除@机器人的部分）
        real_text = (trigger_message.text or trigger_message.caption or "").replace(
            f"@{context.bot.username}", ""
        )

        # 情况1: 没有图片也没有文本内容 - 返回普通打招呼
        if not real_text.strip() and not trigger_message.photo:
            await trigger_message.reply_text(get_hello_reply())
            return

        # 情况2: 仅有图片但没有明确的文本指示 - 返回图片相关的友善提醒
        if trigger_message.photo and not real_text.strip():
            await trigger_message.reply_text(get_image_mention_prompt())
            return

        # MENTION: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤔"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")
    elif task_type == TaskType.MENTION_WITH_REPLY:
        # MENTION_WITH_REPLY: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤔"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")
    elif task_type == TaskType.REPLAY:
        # REPLAY: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤔"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")
    elif task_type == TaskType.AUTO:
        # AUTO: 对用户消息添加表情回应表示已收到
        try:
            await context.bot.set_message_reaction(
                chat_id=chat.id, message_id=trigger_message.message_id, reaction="🤖"
            )
        except Exception as e:
            logger.debug(f"Failed to set reaction: {e}")

    # 准备用户信息
    from_user_fmt = "Anonymous"
    if trigger_message.sender_chat:
        _user = trigger_message.sender_chat
        from_user_fmt = f"{_user.username}({_user.id})"
    elif trigger_message.from_user:
        _user = trigger_message.from_user
        from_user_fmt = f"{_user.username}({_user.id})"

    # 下载图片（如果有的话）
    photo_paths = None
    if trigger_message.photo:
        try:
            photo_paths = await _download_photos_from_message(trigger_message, context.bot)
            if photo_paths:
                logger.info(f"Downloaded {len(photo_paths)} photos for translation")
        except Exception as e:
            logger.error(f"Failed to download photos: {e}")

    # 处理引用消息中的图片（MENTION_WITH_REPLY）
    if task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        if trigger_message.reply_to_message.photo:
            try:
                reply_photo_paths = await _download_photos_from_message(
                    trigger_message.reply_to_message, context.bot
                )
                if reply_photo_paths:
                    photo_paths = (photo_paths or []) + reply_photo_paths
                    logger.info(f"Downloaded {len(reply_photo_paths)} photos from replied message")
            except Exception as e:
                logger.error(f"Failed to download photos from replied message: {e}")

    return Interaction(task_type=task_type, from_user_fmt=from_user_fmt, photo_paths=photo_paths)


async def _build_message_context(
    update: Update, context: ContextTypes.DEFAULT_TYPE, task_type: TaskType
) -> str:
    """构建消息上下文，提取共同的上下文构建逻辑"""
    chat = update.effective_chat
    trigger_message = update.effective_message

    # 构建消息上下文
    message_text = trigger_message.text or trigger_message.caption or ""
    message_context = message_text or "请分析这张图片"

    # 根据不同的 task_type 构建不同的上下文
    if task_type == TaskType.MENTION:
        # 获取历史消息
        history_messages = await _get_chat_history_for_mention(
            chat.id, trigger_message.message_id, context.bot
        )

        # 格式化当前用户查询
        user_query = await _format_message(trigger_message)

        # 使用模板构建完整上下文
        if history_messages:
            message_context = MENTION_PROMPT_TEMPLATE.format(
                user_query=user_query, history_messages=history_messages
            )

    elif task_type == TaskType.MENTION_WITH_REPLY and trigger_message.reply_to_message:
        reply_text = (
            trigger_message.reply_to_message.text or trigger_message.reply_to_message.caption or ""
        )
        if reply_text:
            # 使用 MENTION_WITH_REPLY 模板
            message_context = MENTION_WITH_REPLY_PROMPT_TEMPLATE.format(
                message_text=message_text, reply_text=reply_text
            )

    elif task_type == TaskType.REPLAY:
        # 获取回复模式的上下文
        if trigger_message.reply_to_message:
            history_messages, user_preferences = await _get_reply_mode_context(
                chat,
                trigger_message,
                trigger_message.reply_to_message,
                trigger_message.from_user.id if trigger_message.from_user else 0,
                context.bot,
            )

            # 格式化当前用户查询
            user_query = message_text

            # 使用 REPLY 模板构建完整上下文
            if history_messages:
                message_context = REPLY_SINGLE_PROMPT_TEMPLATE.format(
                    user_query=user_query, history_messages=history_messages
                ).strip()
                # Add 用户偏好记录
                if user_preferences:
                    message_context += USER_PREFERENCES_TPL.format(
                        user_preferences=user_preferences
                    ).strip()

    return message_context


async def _invoke_model_blocking(
    update: Update, context: ContextTypes.DEFAULT_TYPE, interaction: Interaction
) -> str:
    """原先的 blocking 模式调用"""
    task_type = interaction.task_type
    from_user_fmt = interaction.from_user_fmt
    photo_paths = interaction.photo_paths

    message_context = await _build_message_context(update, context, task_type)

    print(message_context)

    # 调用 LLM 进行处理
    result = await run_blocking_dify_workflow(
        bot_username=f"{context.bot.username.rstrip('@')}",
        message_context=message_context,
        from_user=from_user_fmt,
        with_files=photo_paths,
    )
    result_text = result.data.outputs.answer

    with suppress(Exception):
        outputs_json = json.dumps(
            result.data.outputs.model_dump(mode="json"), indent=2, ensure_ascii=False
        )
        logger.debug(f"LLM Result: \n{outputs_json}")

    return result_text


async def _invoke_model_streaming(
    update: Update, context: ContextTypes.DEFAULT_TYPE, interaction: Interaction
) -> bool:
    """流式响应模式"""
    chat = update.effective_chat
    trigger_message = update.effective_message
    task_type = interaction.task_type
    from_user_fmt = interaction.from_user_fmt
    photo_paths = interaction.photo_paths

    message_context = await _build_message_context(update, context, task_type)

    print(message_context)

    # 先创建初始消息
    initial_message = None
    error_message = None

    try:
        # 根据不同的task_type创建初始消息
        if task_type in [TaskType.MENTION, TaskType.MENTION_WITH_REPLY, TaskType.REPLAY]:
            # 尝试直接回复触发消息
            try:
                initial_message = await context.bot.send_message(
                    chat_id=chat.id,
                    text="🤔 思考中...",
                    reply_to_message_id=trigger_message.message_id,
                )
            except Exception:
                # 如果直接回复失败，尝试mention用户
                try:
                    if trigger_message.from_user:
                        if trigger_message.from_user.username:
                            user_mention = f"@{trigger_message.from_user.username}"
                        else:
                            user_mention = trigger_message.from_user.first_name or "User"
                    else:
                        user_mention = "User"

                    initial_message = await context.bot.send_message(
                        chat_id=chat.id, text=f"{user_mention}\n\n🤔 思考中..."
                    )
                except Exception:
                    # 最后兜底方案
                    initial_message = await context.bot.send_message(
                        chat_id=chat.id, text="🤔 思考中..."
                    )
        elif task_type == TaskType.AUTO:
            # AUTO模式直接发送消息
            initial_message = await context.bot.send_message(
                chat_id=chat.id, text="> 🤔 思考中...", parse_mode=ParseMode.HTML
            )

        if not initial_message:
            logger.error("Failed to create initial message")
            return False

        # 流式调用模型
        final_result: dict | None = None
        answer_key = "answer"

        streaming_generator = await run_streaming_dify_workflow(
            bot_username=f"{context.bot.username.rstrip('@')}",
            message_context=message_context,
            from_user=from_user_fmt,
            with_files=photo_paths,
        )

        async for chunk in streaming_generator:
            if not chunk or not isinstance(chunk, dict):
                continue

            if not (event := chunk.get("event")):
                continue

            chunk_data = chunk["data"]

            if event == "workflow_finished":
                # 最终结果
                final_result = chunk_data.get('outputs', {})
                break
            elif event in ["workflow_started", "node_started"]:
                # 节点开始，显示标题
                if node_title := chunk_data.get("title"):
                    # 更新消息，显示当前进度
                    progress_text = f"> {node_title}"
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat.id,
                            message_id=initial_message.message_id,
                            text=progress_text,
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    except Exception as e:
                        logger.debug(f"Failed to update progress message: {e}")
            elif event == "tts_message":
                # 处理 TTS 消息（如果需要）
                logger.warning("不支持 tts message")

        with suppress(Exception):
            outputs_json = json.dumps(final_result, indent=2, ensure_ascii=False)
            logger.debug(f"LLM Result: \n{outputs_json}")

        # 更新为最终结果
        if final_result:
            final_answer = final_result.get(answer_key, '')
            try:
                await context.bot.edit_message_text(
                    chat_id=chat.id,
                    message_id=initial_message.message_id,
                    text=final_answer,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.debug(f"Failed to update with Markdown: {e}")
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat.id, message_id=initial_message.message_id, text=final_answer
                    )
                except Exception as e2:
                    logger.error(f"Failed to update final message: {e2}")
                    return False
        else:
            # 如果没有最终结果，显示错误
            error_message = "抱歉，处理过程中遇到问题，请稍后再试。"
            try:
                await context.bot.edit_message_text(
                    chat_id=chat.id, message_id=initial_message.message_id, text=error_message
                )
            except Exception as e:
                logger.error(f"Failed to update error message: {e}")
                return False

        return True

    except Exception as e:
        logger.error(f"Streaming response error: {e}")

        # 发送友好的错误消息
        error_message = "抱歉，处理过程中遇到问题，请稍后再试。"

        if initial_message:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat.id, message_id=initial_message.message_id, text=error_message
                )
            except Exception as err:
                logger.error(f"Failed to update error message: {err}")
        else:
            # 如果连初始消息都没有创建成功，尝试直接回复
            try:
                await _send_message(
                    context,
                    chat.id,
                    error_message,
                    reply_to_message_id=trigger_message.message_id,
                    log_prefix="Error message",
                )
            except Exception as err:
                logger.error(f"Failed to send error message: {err}")

        return False


async def _send_message(context, chat_id, text, reply_to_message_id=None, log_prefix=""):
    """
    发送消息的辅助函数，优雅降级处理 Markdown 格式错误

    Args:
        context: Telegram context
        chat_id: 聊天ID
        text: 消息文本
        reply_to_message_id: 可选，回复消息ID
        log_prefix: 日志前缀

    Returns:
        bool: 发送是否成功
    """
    try:
        # 先尝试 Markdown 格式
        if reply_to_message_id:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_to_message_id=reply_to_message_id,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2
            )
        return True
    except Exception as err:
        logger.debug(f"Failed to send with Markdown: {err}")
        try:
            # Markdown 失败，尝试纯文本
            if reply_to_message_id:
                await context.bot.send_message(
                    chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id
                )
            else:
                await context.bot.send_message(chat_id=chat_id, text=text)
            logger.debug(f"{log_prefix} sent without parse_mode - {err}")
            return True
        except Exception as e2:
            logger.error(f"Failed to send message: {e2}")
            return False


async def _response_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, interaction: Interaction, result_text: str
):
    """

    Args:
        update:
        context:
        interaction: 交互配置
        result_text: 模型最终的输出结果

    Returns:

    """
    chat = update.effective_chat
    trigger_message = update.effective_message
    task_type = interaction.task_type

    # 根据不同的task_type采用不同的回复方式
    if task_type in [TaskType.MENTION, TaskType.MENTION_WITH_REPLY, TaskType.REPLAY]:
        # 统一的回复逻辑：按优先级尝试不同的回复方式
        reply_sent = False

        # 方案1: 尝试直接回复触发消息
        reply_sent = await _send_message(
            context,
            chat.id,
            result_text,
            reply_to_message_id=trigger_message.message_id,
            log_prefix="Direct reply to trigger message",
        )

        # 方案2: 如果方案1失败，尝试mention用户
        if not reply_sent:
            try:
                # 构建mention文本
                if trigger_message.from_user:
                    if trigger_message.from_user.username:
                        user_mention = f"@{trigger_message.from_user.username}"
                    else:
                        # 使用用户的名字作为文本mention（不是真正的mention，但至少能标识用户）
                        user_mention = trigger_message.from_user.first_name or "User"
                else:
                    user_mention = "User"

                final_text = f"{user_mention}\n\n{result_text}"
                reply_sent = await _send_message(
                    context, chat.id, final_text, log_prefix="Reply via mention"
                )
            except Exception as e:
                logger.error(f"Failed to send message with mention: {e}")

        # 方案3: 最后的兜底方案 - 直接发送消息，不mention任何人
        if not reply_sent:
            reply_sent = await _send_message(
                context, chat.id, result_text, log_prefix="Reply directly"
            )

    elif task_type == TaskType.AUTO:
        # AUTO: 直接发在群里，不打扰任何人
        await _send_message(context, chat.id, result_text, log_prefix="Auto reply")


async def task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理翻译请求，支持文本和图片

    功能特性：
    - 支持四种任务类型：MENTION, MENTION_WITH_REPLY, REPLAY, AUTO
    - 支持两种响应模式：blocking 和 streaming
    - 通过对用户消息添加表情回应来确认收到请求
    - 自动下载并处理图片（选择最高质量版本）
    - 处理引用消息中的文本和图片内容
    - 根据不同模式构建上下文，携带历史消息和用户偏好
    - 统一的回复策略（按优先级）：
      1. 尝试直接回复触发消息
      2. 如果失败，尝试@mention用户
      3. 最后兜底：直接发送消息到群组
    - 完整的错误处理和日志记录
    """
    # ==================== Section 1: LLM触发前交互 ====================
    if not (interaction := await _pre_interactivity(update, context)):
        return

    # ==================== Section 2: LLM调用 ====================
    response_mode = settings.RESPONSE_MODE.lower()

    if response_mode == "streaming":
        # 流式响应模式 - 在流式函数中直接处理消息发送
        success = await _invoke_model_streaming(update, context, interaction)
        if not success:
            logger.error("Streaming response failed")
            return
    else:
        # 默认 blocking 模式
        if not (result_text := await _invoke_model_blocking(update, context, interaction)):
            return

        # ==================== Section 3: 任务交付 ====================
        await _response_message(update, context, interaction, result_text)
