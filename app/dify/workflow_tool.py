# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 19:51
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from pathlib import Path
from typing import List

from dify.dify_client import DifyWorkflowClient
from models import WorkflowRunPayload, WorkflowInputs, WorkflowRunResponse


async def direct_translation_tool(
    bot_username: str,
    message_context: str,
    from_user: str,
    with_files: Path | List[Path] | None = None,
) -> WorkflowRunResponse:
    client = DifyWorkflowClient()

    inputs = WorkflowInputs(bot_username=bot_username, message_context=message_context)
    payload = WorkflowRunPayload(inputs=inputs, user=from_user, response_mode="blocking")

    return await client.run(payload=payload, with_files=with_files)
