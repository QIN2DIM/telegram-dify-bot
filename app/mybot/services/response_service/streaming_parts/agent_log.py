# -*- coding: utf-8 -*-
"""
@Time    : 2025/8/15 00:13
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import json
from typing import Dict, Any

from models import AGENT_STRATEGY_TYPE, AgentStrategy
from mybot.services.response_service.event_handler import EventHandler


async def agent_log(
    chunk_data: Dict[str, Any],
    event_handler: EventHandler,
    *,
    is_update_progress: bool | None = False,
) -> None:
    """Handle agent_log event"""

    agent_strategy_name = event_handler.lazy_data.agent_strategy_name

    if agent_data := chunk_data.get("data", {}):
        parsed_data = _parse_agent_log_data(agent_data, agent_strategy_name)
    elif (
        chunk_data.get("status") == "start"
        and agent_strategy_name == AgentStrategy.FUNCTION_CALLING
    ):
        parsed_data = {"action": "🤔 Thinking..."}
    else:
        return agent_strategy_name

    agent_log_text = _format_agent_log(parsed_data)

    if is_update_progress:
        await event_handler.update_progress_message(agent_log_text)


def _parse_agent_log_data(
    agent_data: Dict[str, Any], agent_strategy_name: AGENT_STRATEGY_TYPE
) -> Dict[str, Any]:
    """Parse agent log data based on strategy type"""
    parsed_data = {
        "action": "",
        "thought": "",
        "output_text": "",
        "tool_input": [],
        "tool_call_name": "",
        "tool_response": "",
        "tool_call_input": {},
    }

    if agent_strategy_name == AgentStrategy.REACT:
        parsed_data["action"] = agent_data.get("action", agent_data.get("action_name", ""))
        agent_data_json = json.dumps(agent_data, indent=2, ensure_ascii=False)
        parsed_data["thought"] = f'<pre><code class="language-json">{agent_data_json}</code></pre>'

    elif agent_strategy_name == AgentStrategy.FUNCTION_CALLING:
        if output_pending := agent_data.get("output"):
            if isinstance(output_pending, str):
                parsed_data["output_text"] = output_pending
            elif isinstance(output_pending, dict):
                parsed_data["output_text"] = output_pending.get("llm_response", "")

        parsed_data["tool_input"] = agent_data.get("tool_input", [])
        parsed_data["tool_call_input"] = agent_data.get("tool_call_input", {})
        parsed_data["tool_call_name"] = agent_data.get("tool_call_name", "")
        parsed_data["tool_response"] = agent_data.get("tool_response", "")

    return parsed_data


def _format_agent_log(parsed_data: Dict[str, Any]) -> str:
    """Format parsed agent log data into display text"""
    agent_log_parts = []

    if action := parsed_data["action"]:
        agent_log_parts.append(f"<blockquote>Agent: {action}</blockquote>")

    if thought := parsed_data["thought"]:
        agent_log_parts.append(thought)

    if output_text := parsed_data["output_text"]:
        agent_log_parts.append(output_text)

    if tool_input := parsed_data["tool_input"]:
        for t in tool_input:
            if isinstance(t, dict) and "args" in t and "name" in t:
                block_language = t.get("args", {}).get("language", "json")
                tool_args_content = json.dumps(t["args"], indent=2, ensure_ascii=False)
                agent_log_parts.append(f"<blockquote>ToolUse: {t['name']}</blockquote>")
                agent_log_parts.append(
                    f'<pre><code class="language-{block_language}">{tool_args_content}</code></pre>'
                )

    if tool_call_name := parsed_data["tool_call_name"]:
        agent_log_parts.append(f"<blockquote>ToolUse: {tool_call_name}</blockquote>")

    if tool_call_input := parsed_data["tool_call_input"]:
        block_language = tool_call_input.get("language", "json")
        tool_args = json.dumps(tool_call_input, indent=2, ensure_ascii=False)
        agent_log_parts.append(
            f'<pre><code class="language-{block_language}">{tool_args}</code></pre>'
        )

    if tool_response := parsed_data["tool_response"]:
        agent_log_parts.append(f'<pre><code class="language-json">{tool_response}</code></pre>')

    return "\n\n".join(agent_log_parts)
