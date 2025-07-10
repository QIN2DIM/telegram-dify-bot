# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:55
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import asyncio
import json

from dify import DifyWorkflowClient
from dify.models import WorkflowRunPayload, WorkflowInputs


async def main():
    dify_client = DifyWorkflowClient()

    user = "abc-123"
    bot_username = "qin2dimbot"
    message_context = f"@{bot_username} Hello, my friend!"

    # with_files = None

    inputs = WorkflowInputs(bot_username=bot_username, message_context=message_context)

    payload = WorkflowRunPayload(inputs=inputs, user=user, response_mode="streaming")

    # 异步迭代 streaming 方法返回的生成器
    async for chunk in dify_client.streaming(payload=payload):
        if not chunk or not isinstance(chunk, dict):
            continue
        if not (event := chunk.get("event")):
            continue

        chunk_data = chunk["data"]

        if event == "workflow_finished":
            outputs = json.dumps(chunk_data['outputs'], ensure_ascii=False, indent=2)
            print(outputs)
        elif event in ["workflow_started", "node_started", "tts_message"]:
            if node_title := chunk_data.get("title"):
                print(f"✨ {node_title} {chunk_data}")


if __name__ == '__main__':
    asyncio.run(main())
