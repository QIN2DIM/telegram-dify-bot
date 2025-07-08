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
    inputs = WorkflowInputs(message_context="Hello, my friend!")
    # with_files = [Path(__file__).parent.joinpath("sticker.webp")]
    with_files = None

    result = await dify_client.run(
        payload=WorkflowRunPayload(inputs=inputs, user=user, response_mode="blocking"),
        with_files=with_files,
    )
    if result:
        print(json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
