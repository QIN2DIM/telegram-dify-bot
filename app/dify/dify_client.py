# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:40
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from httpx import AsyncClient

from dify.models import WorkflowRunPayload
from settings import settings


class DifyWorkflowClient:
    def __init__(
        self,
        api_key: str = settings.DIFY_WORKFLOW_API_KEY.get_secret_value(),
        base_url: str = settings.DIFY_APP_BASE_URL,
    ):
        headers = {"Authorization": f"Bearer {api_key}"}
        self._client = AsyncClient(base_url=base_url, headers=headers)

    async def _send_request(self, method, endpoint, payload=None, params=None, stream=False):
        if stream:
            response = self._client.stream(method, endpoint, params=params)
        else:
            response = await self._client.request(method, endpoint, json=payload, params=params)
        return response

    async def _send_request_with_files(self, method, endpoint, data, files):
        return await self._client.request(method, endpoint, data=data, files=files)

    async def get_application_parameters(self, user):
        params = {"user": user}
        return await self._send_request("GET", "/parameters", params=params)

    async def file_upload(self, user, files):
        data = {"user": user}
        return await self._send_request_with_files("POST", "/files/upload", data=data, files=files)

    async def get_meta(self, user):
        params = {"user": user}
        return await self._send_request("GET", "/meta", params=params)

    async def run(self, payload: WorkflowRunPayload):
        return await self._send_request("POST", "/workflows/run", payload.dumps_params())

    async def stop(self, task_id, user):
        data = {"user": user}
        return await self._send_request("POST", f"/workflows/tasks/{task_id}/stop", data)

    async def get_result(self, workflow_run_id):
        return await self._send_request("GET", f"/workflows/run/{workflow_run_id}")
