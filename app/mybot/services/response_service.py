# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/12 10:00
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : Service for sending responses to Telegram.
"""
import json
import time
from contextlib import suppress
from typing import AsyncGenerator, Dict, Any

from loguru import logger
from telegram import Update, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from dify.models import AnswerType
from models import Interaction, TaskType, AGENT_STRATEGY_TYPE, AgentStrategy
from plugins.instant_view_generator.node import create_instant_view
from settings import settings


async def _send_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    reply_to_message_id: int | None = None,
) -> bool:
    """发送消息的辅助函数，优雅降级处理 Markdown 格式错误"""
    for parse_mode in settings.pending_parse_mode:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode,
            )
            return True
        except Exception as err:
            logger.error(f"Failed to send final message({parse_mode}): {err}")

    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id
        )
        return True
    except Exception as e2:
        logger.error(f"Failed to send message: {e2}")
        return False


async def _send_photo_with_caption(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    photo_url: str,
    caption: str,
    reply_to_message_id: int | None = None,
) -> bool:
    """发送带标题的图片消息"""
    for parse_mode in settings.pending_parse_mode:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=photo_url,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
                parse_mode=parse_mode,
            )
            return True
        except Exception as err:
            logger.error(f"Failed to send photo with caption({parse_mode}): {err}")

    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo_url,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
        )
        return True
    except Exception as e2:
        logger.error(f"Failed to send photo: {e2}")
        return False


async def _send_media_group_with_caption(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    photo_urls: list[str],
    caption: str,
    reply_to_message_id: int | None = None,
) -> bool:
    """发送多张图片+文字的媒体组消息"""
    if not photo_urls:
        return False

    parse_mode = ParseMode.HTML

    # 构造媒体组：第一张图片包含文字，其他图片不包含文字
    media_group = []

    try:

        for i, photo_url in enumerate(photo_urls):
            if i == 0:
                # 第一张图片包含完整的文字说明
                media_group.append(
                    InputMediaPhoto(media=photo_url, caption=caption, parse_mode=parse_mode)
                )
            else:
                # 其他图片不包含文字
                media_group.append(InputMediaPhoto(media=photo_url))

        await context.bot.send_media_group(
            chat_id=chat_id, media=media_group[:9], reply_to_message_id=reply_to_message_id
        )
        return True
    except Exception as err:
        logger.exception(f"Failed to send media group({parse_mode}): {err}")

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
            context, chat_id, result_text, reply_to_message_id=trigger_message.message_id
        )
        if sent:
            return

        # 失败则尝试 @用户
        user_mention = "User"
        if trigger_message.from_user:
            user_mention = trigger_message.from_user.mention_html()
        final_text = f"{user_mention}\n\n{result_text}"
        await _send_message(context, chat_id, final_text)

    elif interaction.task_type == TaskType.AUTO:
        await _send_message(context, chat_id, result_text)


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
        initial_text = "🤔 Planning..."
        initial_message = await context.bot.send_message(
            chat_id=chat.id,
            text=initial_text,
            reply_to_message_id=(
                trigger_message.message_id if interaction.task_type != TaskType.AUTO else None
            ),
        )

        final_result: dict | None = None
        agent_strategy_name: AGENT_STRATEGY_TYPE = ""
        last_edit_time = time.time()

        async for chunk in streaming_generator:
            if not chunk or not isinstance(chunk, dict) or not (event := chunk.get("event")):
                continue

            chunk_data = chunk.get("data", {})
            node_type = chunk_data.get("node_type", "")
            node_title = chunk_data.get("title", "")
            node_index = chunk_data.get("index", 0)

            # logger.debug(json.dumps(chunk, indent=2, ensure_ascii=False))

            if event == "workflow_finished":
                final_result = chunk_data.get('outputs', {})
                break
            elif event in ["node_started"]:
                key_progress_text = ""
                if agent_strategy := chunk_data.get("agent_strategy", {}):
                    agent_strategy_name = agent_strategy.get("name", "")
                if node_type in ["llm", "agent"] and node_title:
                    key_progress_text = f"<blockquote>{node_title}</blockquote>"
                elif node_type in ["tool"] and node_title:
                    # bypass flood
                    if node_index > 3:
                        key_progress_text = f"<blockquote>✨ 工具使用：{node_title}</blockquote>"
                if key_progress_text:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat.id,
                            message_id=initial_message.message_id,
                            text=key_progress_text,
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception as err:
                        logger.error(f"Failed to edit node's title: {err}")
            elif event == "agent_log":
                _agent_log = ""
                agent_log_parts = []

                # ReAct 结构化日志
                thought = ""
                action = ""

                # function_calling 结构化日志
                output_text = ""
                tool_input = []
                tool_call_name = ""
                tool_response = ""
                tool_call_input = {}

                # == 填充模板 == #
                if agent_data := chunk_data.get("data", {}):
                    # 适配的 Agent(ReAct) Node 的 agent_log 协议规范
                    if agent_strategy_name == AgentStrategy.REACT:
                        action = agent_data.get("action", agent_data.get("action_name", ""))
                        agent_data_json = json.dumps(agent_data, indent=2, ensure_ascii=False)
                        thought = f'<pre><code class="language-json">{agent_data_json}</code></pre>'

                    # 适配 function_calling agent_strategy 协议规范
                    elif agent_strategy_name == AgentStrategy.FUNCTION_CALLING:
                        if output_pending := agent_data.get("output"):
                            if isinstance(output_pending, str):
                                output_text = output_pending
                            if isinstance(output_pending, dict):
                                output_text = output_pending.get("llm_response", "")
                        tool_input = agent_data.get("tool_input", [])
                        tool_call_input = agent_data.get("tool_call_input", {})
                        tool_call_name = agent_data.get("tool_call_name", "")
                        tool_response = agent_data.get("tool_response", "")
                elif chunk_data.get("status", "") == "start":
                    if agent_strategy_name == AgentStrategy.FUNCTION_CALLING:
                        action = "🤔 Thinking..."

                # == 解析模板 == #
                if action:
                    agent_log_parts.append(f"<blockquote>Agent: {action}</blockquote>")
                if thought:
                    agent_log_parts.append(thought)
                if output_text:
                    agent_log_parts.append(output_text)
                if tool_input:
                    for t in tool_input:
                        if isinstance(t, dict) and "args" in t and "name" in t:
                            block_language = t.get("args", {}).get("language", "json")
                            tool_args_content = json.dumps(t["args"], indent=2, ensure_ascii=False)
                            agent_log_parts.append(f"<blockquote>ToolUse: {t['name']}</blockquote>")
                            agent_log_parts.append(
                                f'<pre><code class="language-{block_language}">{tool_args_content}</code></pre>'
                            )
                if tool_call_name:
                    agent_log_parts.append(f"<blockquote>ToolUse: {tool_call_name}</blockquote>")
                if tool_call_input:
                    block_language = tool_call_input.get("language", "json")
                    tool_args = json.dumps(tool_call_input, indent=2, ensure_ascii=False)
                    agent_log_parts.append(
                        f'<pre><code class="language-{block_language}">{tool_args}</code></pre>'
                    )
                if tool_response:
                    agent_log_parts.append(
                        f'<pre><code class="language-json">{tool_response}</code></pre>'
                    )

                _agent_log = "\n\n".join(agent_log_parts)

                if _agent_log:
                    try:
                        now = time.time()
                        if now - last_edit_time > 1.5:
                            await context.bot.edit_message_text(
                                chat_id=chat.id,
                                message_id=initial_message.message_id,
                                text=_agent_log,
                                parse_mode=ParseMode.HTML,
                            )
                            last_edit_time = now
                    except Exception as err:
                        logger.error(f"Failed to edit agent log: {err}")

        # 输出响应日志
        with suppress(Exception):
            if final_result:
                outputs_json = json.dumps(final_result, indent=2, ensure_ascii=False)
                logger.debug(f"LLM Result: \n{outputs_json}")
            else:
                logger.warning("No final result")

        # 更新为最终结果
        final_answer_message_id = None
        if final_result and (final_answer := final_result.get(settings.BOT_OUTPUTS_ANSWER_KEY, '')):
            final_type = final_result.get(settings.BOT_OUTPUTS_TYPE_KEY, "")
            extras = final_result.get(settings.BOT_OUTPUTS_EXTRAS_KEY, {})

            # == RENDER 1: Instant View == #
            # 期望 instant_view 都使用标准的 Markdown 语法表达，而非 HTML
            if extras.get("is_instant_view"):
                try:
                    instant_view_content = final_answer

                    # 如果是地理位置识别任务且有图片，将图片整合到 Instant View 内容中
                    photo_links = extras.get("photo_links", [])
                    place_name = extras.get("place_name", "")
                    if final_type == AnswerType.GEOLOCATION_IDENTIFICATION and photo_links:
                        # 将图片链接添加到 Markdown 内容中
                        instant_view_content += "\n\n"
                        if place_name:
                            instant_view_content += f"## {place_name}\n\n"

                        # 添加图片到 Markdown 中
                        for i, photo_url in enumerate(photo_links):
                            if i == 0:
                                instant_view_content += f"![Street View]({photo_url})\n\n"
                            else:
                                instant_view_content += f"![Street View {i+1}]({photo_url})\n\n"
                    response = await create_instant_view(
                        content=instant_view_content,
                        input_format="Markdown",
                        title=extras.get("title"),
                    )
                    if response.success:
                        await context.bot.edit_message_text(
                            chat_id=chat.id,
                            message_id=initial_message.message_id,
                            parse_mode=ParseMode.HTML,
                            text=response.instant_view_content.strip(),
                        )
                        return
                except Exception as send_error:
                    logger.error(f"发送错误回复失败: {send_error}")
                    # Instant View 渲染失败，将继续执行后续的通用渲染和街景图片发送逻辑作为兜底

            # == RENDER 2: General RichText == #
            # 更新初始消息为最终答案
            for parse_mode in settings.pending_parse_mode:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat.id,
                        message_id=initial_message.message_id,
                        text=final_answer,
                        parse_mode=parse_mode,
                    )
                    # 记录最终答案消息的 ID，用于后续街景图片引用
                    final_answer_message_id = initial_message.message_id
                    break
                except Exception as err:
                    logger.exception(f"Failed to send final message({parse_mode}): {err}")

            # == RENDER 3: Street View Images == #
            # 如果是地理位置识别任务且有图片，发送额外的街景图片作为补充
            photo_links = extras.get("photo_links", [])
            place_name = extras.get("place_name", "")
            caption = f"<code>{place_name.strip()}</code>" if place_name else "Street View"
            if final_type == AnswerType.GEOLOCATION_IDENTIFICATION and photo_links:
                # 确定街景图片引用的消息 ID：优先引用机器人自己的最终答案消息，没有的话再引用用户消息
                street_view_reply_id = None
                if interaction.task_type != TaskType.AUTO:
                    # 优先引用机器人自己发送的最终答案消息
                    street_view_reply_id = final_answer_message_id or trigger_message.message_id

                # 发送街景图片作为补充信息
                if len(photo_links) > 1:
                    # 多张图片：使用 send_media_group
                    await _send_media_group_with_caption(
                        context,
                        chat.id,
                        photo_links,
                        caption,
                        reply_to_message_id=street_view_reply_id,
                    )
                else:
                    # 单张图片：使用 send_photo
                    await _send_photo_with_caption(
                        context,
                        chat.id,
                        photo_links[0],
                        caption,
                        reply_to_message_id=street_view_reply_id,
                    )

        else:
            await context.bot.edit_message_text(
                chat_id=chat.id, message_id=initial_message.message_id, text="抱歉，处理失败。"
            )

    except Exception as e:
        logger.exception(f"Streaming response error: {e}")
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
