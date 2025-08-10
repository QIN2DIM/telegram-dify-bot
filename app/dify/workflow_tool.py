# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 19:51
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from pathlib import Path
from typing import List, Dict

from dify import DifyWorkflowClient
from dify.models import (
    WorkflowRunPayload,
    WorkflowInputs,
    WorkflowCompletionResponse,
    FORCED_COMMAND_TYPE,
    ForcedCommand,
)
from settings import settings


async def run_blocking_dify_workflow(
    message_context: str,
    from_user: str,
    bot_username: str = "",
    with_files: Path | List[Path] | Dict[str, List[Path]] | None = None,
    forced_command: FORCED_COMMAND_TYPE | None = None,
    **kwargs,
) -> WorkflowCompletionResponse:

    # 测试模式：
    # 1. 将所有来自机器人的请求强制切换到 阻塞模式 + TEST BRANCH
    # 2. 但是放行 `commit`，这是一个仅从开发者端流入的指令
    if settings.ENABLE_TEST_MODE and forced_command not in [
        ForcedCommand.COMMIT_MESSAGE_GENERATION
    ]:
        forced_command = ForcedCommand.TEST

    client = DifyWorkflowClient()

    inputs = WorkflowInputs(
        message_context=message_context,
        bot_username=bot_username,
        parse_mode=settings.BOT_ANSWER_PARSE_MODE,
        forced_command=forced_command,
    )
    payload = WorkflowRunPayload(inputs=inputs, user=from_user, response_mode="blocking")

    return await client.run(payload=payload, with_files=with_files)


async def run_streaming_dify_workflow(
    bot_username: str,
    message_context: str,
    from_user: str,
    with_files: Path | List[Path] | Dict[str, List[Path]] | None = None,
    forced_command: FORCED_COMMAND_TYPE | None = None,
    **kwargs,
):
    if settings.ENABLE_TEST_MODE and forced_command not in [
        ForcedCommand.COMMIT_MESSAGE_GENERATION
    ]:
        forced_command = ForcedCommand.TEST

    client = DifyWorkflowClient()
    inputs = WorkflowInputs(
        bot_username=bot_username,
        message_context=message_context,
        parse_mode=settings.BOT_ANSWER_PARSE_MODE,
        forced_command=forced_command,
    )
    payload = WorkflowRunPayload(inputs=inputs, user=from_user, response_mode="streaming")

    return client.streaming(payload=payload, with_files=with_files)


async def invoke_commit_message_generation(user_prompt: str):
    return await run_blocking_dify_workflow(
        message_context=user_prompt,
        from_user=str(ForcedCommand.COMMIT_MESSAGE_GENERATION),
        forced_command=ForcedCommand.COMMIT_MESSAGE_GENERATION,
    )
