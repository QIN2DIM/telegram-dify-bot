# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:55
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import asyncio
import json
import time

from dify import DifyWorkflowClient
from dify.models import WorkflowRunPayload, WorkflowInputs
from loguru import logger

user = "abc-123"
bot_username = "qin2dimbot"

user_prompt = """
@qin2dimbot 根据这篇百科，介绍高超音速武器的发展史，列出核心的timeline和突破
https://zh.wikipedia.org/wiki/%E9%AB%98%E8%B6%85%E9%9F%B3%E9%80%9F%E6%AD%A6%E5%99%A8
"""


async def main():
    dify_client = DifyWorkflowClient()

    inputs = WorkflowInputs(bot_username=bot_username, message_context=user_prompt)

    payload = WorkflowRunPayload(inputs=inputs, user=user, response_mode="streaming")

    final_result: dict | None = None

    # 异步迭代 streaming 方法返回的生成器
    time_0 = time.time()
    chunk_count = 0
    async for chunk in dify_client.streaming(payload=payload):
        if not chunk or not isinstance(chunk, dict) or not (event := chunk.get("event")):
            continue

        chunk_data = chunk.get("data", {})
        node_type = chunk_data.get("node_type", "")
        node_title = chunk_data.get("title")

        logger.debug(chunk)

        if event == "workflow_finished":
            final_result = chunk_data.get('outputs', {})
            break
        elif event in ["node_started"]:
            if node_type in ["llm", "agent"] and node_title:
                progress_text = f"<blockquote>{node_title}</blockquote>"
                print(f"✨ {progress_text}")
            elif node_type in ["tool"] and node_title:
                progress_text = f"<blockquote>工具使用：{node_title}</blockquote>"
                print(f"✨ {progress_text}")
        elif event == "agent_log":
            if agent_data := chunk_data.get("data", {}):
                action = agent_data.get("action", "")
                thought = agent_data.get("thought", "")
                if action and thought:
                    progress_text = f"<blockquote>ReAct: {action}</blockquote>\n\n{thought}"
                    print(progress_text)
        elif event == "text_chunk":
            chunk_count += 1
            now_ = time.time()
            if chunk_count >= 10 and now_ - time_0 > 10.0:
                time_0 = now_
                logger.debug("✨ <blockquote>更新进度状态[x]</blockquote>")

    if final_result:
        outputs = json.dumps(final_result, ensure_ascii=False, indent=2)
        print(outputs)


if __name__ == '__main__':
    asyncio.run(main())
