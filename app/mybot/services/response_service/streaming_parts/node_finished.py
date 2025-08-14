# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/15 01:48
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from typing import Dict, Any

from dify.models import ForcedCommand
from mybot.services.response_service.event_handler import EventHandler


async def node_finished(
    chunk_data: Dict[str, Any],
    event_handler: EventHandler,
    *,
    forced_command: ForcedCommand | None = None,
    **kwargs,
) -> None:
    """Handle node_started event"""
    node_output = chunk_data.get("outputs", {})
    node_type = chunk_data.get("node_type", "")
    node_title = chunk_data.get("title", "")

    if (
        forced_command == ForcedCommand.IMAGINE
        and node_type == "llm"
        and node_title == "优化提示词"
        and node_output
        and isinstance(node_output, dict)
    ):
        structured_output = node_output.get("structured_output", {})
        event_handler.lazy_data.imagine_optimized_output = structured_output
