# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 12:34
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from enum import Enum
from pathlib import Path
from typing import Type, Literal, List, Union

from pydantic import BaseModel, Field
from telegram import User


class UserPreferences(BaseModel):
    language_code: str | None = Field(
        default="", description="用户的语言编码", examples=["zh-hans"]
    )
    extra: dict | None = Field(default_factory=dict)


class UserProfile(BaseModel):
    id: str
    nickname: str
    preferences: UserPreferences


class TaskType(str, Enum):
    IRRELEVANT = "irrelevant"
    """
    无关的消息
    """

    REPLAY = "replay_me"
    """
    用户回复或引用机器人的消息
    """

    MENTION = "mention_me"
    """
    用户在 fulltext 中提及我
    """

    MENTION_WITH_REPLY = "mention_me_with_reply"
    """
    用户在引用的其他消息中提及我
    """

    AUTO = "auto_translation"
    """
    自动翻译模式触发的翻译
    """


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
    bot_username: str = Field(description="机器人username，在群聊中区分谁是谁")
    message_context: str = Field(description="翻译上下文")
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


class AnswerType(str, Enum):
    FULLTEXT_TRANSLATION = "翻译与文本编辑"
    GENERAL_QA = "通用问答与指令"
    WEB_SEARCH = "联网搜索与时事问答"

    TABLE_RECOGNITION = "table_recognition"
    TEXT_RECOGNITION_OCR = "text_recognition_ocr"
    GEOLOCATION_IDENTIFICATION = "geolocation_identification"
    IMAGE_TRANSLATION = "image_translation"
    GENERAL_QA_MODAL = "general_qa"


WORKFLOW_RUN_OUTPUTS_TYPE = Union[str, AnswerType]


class WorkflowRunOutputs(BaseModel):
    type: WORKFLOW_RUN_OUTPUTS_TYPE | None = Field(default=None, description="任务类型")
    answer: str | None = Field(default=None, description="处理结果")


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


class Interaction(BaseModel):
    task_type: TaskType | None = None
    photo_paths: List[Path] | None = None
    from_user_fmt: str | None = None
