# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 19:51
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from pathlib import Path
from typing import List

from dify import DifyWorkflowClient
from dify.models import WorkflowRunPayload, WorkflowInputs, WorkflowCompletionResponse


async def run_blocking_dify_workflow(
    bot_username: str,
    message_context: str,
    from_user: str,
    with_files: Path | List[Path] | None = None,
) -> WorkflowCompletionResponse:
    client = DifyWorkflowClient()

    inputs = WorkflowInputs(bot_username=bot_username, message_context=message_context)
    payload = WorkflowRunPayload(inputs=inputs, user=from_user, response_mode="blocking")

    return await client.run(payload=payload, with_files=with_files)


async def run_streaming_dify_workflow(
    bot_username: str,
    message_context: str,
    from_user: str,
    with_files: Path | List[Path] | None = None,
):
    client = DifyWorkflowClient()
    inputs = WorkflowInputs(bot_username=bot_username, message_context=message_context)
    payload = WorkflowRunPayload(inputs=inputs, user=from_user, response_mode="streaming")

    return client.streaming(payload=payload, with_files=with_files)
