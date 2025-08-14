# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/15 00:12
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from typing import Dict, Any

from dify.models import ForcedCommand
from mybot.services.response_service.event_handler import EventHandler

SUCCEED_HTML_TPL = """
<b>Prompt</b>: 
<code>{prompt}</code>

<b>Negative Prompt</b>: 
<code>{negative_prompt}</code>
"""

DEFAULT_TOOL_CALLING_TITLE = "<blockquote>✨ 工具使用：{node_title}</blockquote>"


def _extract_progress_text_image_qwen_master(structured_output: Dict[str, Any]) -> str | None:
    if structured_output and isinstance(structured_output, dict):
        prompt = structured_output.get("prompt", "")
        negative_prompt = structured_output.get("negative_prompt", "")
        return SUCCEED_HTML_TPL.format(prompt=prompt, negative_prompt=negative_prompt)


async def node_started(
    chunk_data: Dict[str, Any],
    event_handler: EventHandler,
    *,
    forced_command: ForcedCommand | None = None,
    is_update_progress: bool = True,
) -> None:
    """Handle node_started event"""
    node_type = chunk_data.get("node_type", "")
    node_title = chunk_data.get("title", "")
    node_index = chunk_data.get("index", 0)

    if agent_strategy := chunk_data.get("agent_strategy", {}):
        event_handler.lazy_data.agent_strategy_name = agent_strategy.get("name", "")

    key_progress_text = ""

    if node_type in ["llm", "agent"] and node_title:
        key_progress_text = f"<blockquote>{node_title}</blockquote>"
    elif node_type == "tool" and node_title and node_index > 3:
        key_progress_text = DEFAULT_TOOL_CALLING_TITLE.format(node_title=node_title)
        if forced_command == ForcedCommand.IMAGINE:
            structured_output = event_handler.lazy_data.imagine_optimized_output
            if res := _extract_progress_text_image_qwen_master(structured_output):
                key_progress_text += res

    if is_update_progress:
        await event_handler.update_progress_message(key_progress_text)
