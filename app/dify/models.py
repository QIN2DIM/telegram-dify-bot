# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:41
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from typing import Type, Literal, List, Union

from pydantic import BaseModel, Field
from telegram import User


class FilesUploadResponse(BaseModel):
    id: str
    name: str
    size: int
    extension: str
    mime_type: str
    created_by: str
    created_at: int


FILE_TYPE = Union[str, Literal["document", "image", "audio", "video", "custom"]]


class WorkflowFileInputBody(BaseModel):
    type: FILE_TYPE
    transfer_method: Literal["remote_url", "local_file"] = "local_file"
    url: str | None = Field(default=None, description="仅当传递方式为 `remote_url` 时")
    upload_file_id: str | None = Field(default=None, description="仅当传递方式为 local_file 时")


class WorkflowInputs(BaseModel):
    message_context: str = Field(description="翻译上下文")
    output_language: str | None = Field(default="")
    files: List[WorkflowFileInputBody] | None = Field(default_factory=list)


class WorkflowRunPayload(BaseModel):
    inputs: WorkflowInputs
    user: Type[User] | str
    response_mode: Literal["streaming", "blocking"] = "streaming"

    @property
    def user_id(self) -> str:
        return self.user.id if isinstance(self.user, User) else self.user

    def dumps_params(self) -> dict:
        _payload = self.model_dump(mode="json")
        _payload["user"] = self.user_id
        return _payload


class WorkflowLogsQuery(BaseModel):
    keyword: str
    status: Literal["succeeded", "failed", "stopped"]
    page: int = 1
    limit: int = 20
    created_by_end_user_session_id: str | None = ""
    created_by_account: str | None = ""


class WorkflowRunOutputs(BaseModel):
    quote: str | None = Field(default="", description="在自动模式下，自动翻译的原始文本段落")
    error: str | None = Field(default="", description="异常信息")
    translation: str = Field(description="翻译结果")


class WorkflowRunData(BaseModel):
    id: str
    workflow_id: str
    status: str
    outputs: WorkflowRunOutputs = Field(description="工作流返回的 dict data")
    error: str | None = Field(default="")


class WorkflowRunResponse(BaseModel):
    task_id: str
    workflow_run_id: str
    data: WorkflowRunData
