# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:40
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import mimetypes
from pathlib import Path
from typing import List

from httpx import AsyncClient
from loguru import logger

from models import (
    WorkflowRunPayload,
    FilesUploadResponse,
    WorkflowFileInputBody,
    FILE_TYPE,
    WorkflowRunResponse,
)
from settings import settings


class DifyWorkflowClient:
    def __init__(
        self,
        api_key: str = settings.DIFY_WORKFLOW_API_KEY.get_secret_value(),
        base_url: str = settings.DIFY_APP_BASE_URL,
    ):
        headers = {"Authorization": f"Bearer {api_key}"}
        self._client = AsyncClient(base_url=base_url, headers=headers, timeout=900)

    async def run(
        self,
        payload: WorkflowRunPayload,
        with_files: List[Path] | Path = None,
        _filter_type: FILE_TYPE = "image",
    ) -> WorkflowRunResponse | None:
        """
        执行 workflow

        执行 workflow，没有已发布的 workflow，不可执行。

        Args:
            payload:
            with_files:
            _filter_type: 目前仅允许 Telegram Translation Bot 接受图片翻译载体

        Returns:

        """
        _payload_files = []

        # 筛选图片上传
        if with_files:
            if not isinstance(with_files, list):
                with_files = [with_files]
            for file_path in with_files:
                if not isinstance(file_path, Path) or not file_path.is_file():
                    continue
                if fs := await self.upload_files(
                    payload.user_id, file_path, filter_type=_filter_type
                ):
                    fs_body = WorkflowFileInputBody(
                        type=_filter_type, transfer_method="local_file", upload_file_id=fs.id
                    )
                    _payload_files.append(fs_body)

        if _payload_files:
            payload.inputs.files = _payload_files

        payload_json = payload.dumps_params()
        if payload.response_mode == "blocking":
            response = await self._client.post("/workflows/run", json=payload_json)
            response.raise_for_status()
            result = response.json()
            return WorkflowRunResponse(**result)
        return None

    async def get_run_status(self, workflow_id: str):
        """获取 workflow 执行情况"""
        response = await self._client.get(f"/workflows/run/{workflow_id}")
        response.raise_for_status()

    async def stop(self, task_id: str, user_id: str):
        """停止响应"""
        payload = {"user": user_id}
        response = await self._client.post(f"/workflows/tasks/{task_id}/stop", json=payload)
        response.raise_for_status()

    async def upload_files(
        self, user_id: str, file_path: Path, filter_type: FILE_TYPE = "image"
    ) -> FilesUploadResponse | None:
        """
        上传文件

        上传文件并在发送消息时使用，可实现图文多模态理解。 支持您的工作流程所支持的任何格式。 上传的文件仅供当前终端用户使用。
        Args:
            filter_type:
            file_path:
            user_id: 用户标识，用于定义终端用户的身份，必须和发送消息接口传入 user 保持一致。服务 API 不会共享 WebApp 创建的对话。

        Returns:

        """
        file_suffix = file_path.suffix.upper().lstrip(".")

        # remove GIF, SVG
        if filter_type == "image" and file_suffix not in ["JPG", "JPEG", "PNG", "WEBP"]:
            return None

        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = 'application/octet-stream'

        file_bytes = file_path.read_bytes()
        data = {"user": user_id}
        files = {"file": (file_path.name, file_bytes, mime_type)}
        response = await self._client.post("/files/upload", data=data, files=files)
        response.raise_for_status()
        result = response.json()
        logger.debug(f"upload files: {user_id} {file_path.name}")

        return FilesUploadResponse(**result)

    async def logs(self):
        """
        获取 workflow 日志
        Returns:

        """
        params = {}
        response = await self._client.get("/workflows/logs", params=params)
        response.raise_for_status()

    async def info(self):
        """获取应用基本信息"""
        response = await self._client.get("/info")
        response.raise_for_status()
        return response.json()

    async def parameters(self):
        """
        获取应用参数

        用于进入页面一开始，获取功能开关、输入参数名称、类型及默认值等使用。
        Returns:

        """
        response = await self._client.get("/parameters")
        response.raise_for_status()
        return response.json()

    async def meta(self):
        """
        获取应用 WebAPP 设置

        Returns:

        """
        response = await self._client.get("/meta")
        response.raise_for_status()
        return response.json()
