# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/10 00:02
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from typing import Type, Literal

from pydantic import BaseModel
from pydantic import Field
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
FORCED_COMMAND_TYPE = Union[str, Literal["Any", "CommitMessageGeneration", "AutoTranslation"]]


class WorkflowFileInputBody(BaseModel):
    type: FILE_TYPE
    transfer_method: Literal["remote_url", "local_file"] = "local_file"
    url: str | None = Field(default=None, description="仅当传递方式为 `remote_url` 时")
    upload_file_id: str | None = Field(default=None, description="仅当传递方式为 local_file 时")


class WorkflowInputs(BaseModel):
    bot_username: str = Field(description="机器人username，在群聊中区分谁是谁")
    message_context: str = Field(description="翻译上下文")
    files: List[WorkflowFileInputBody] | None = Field(default_factory=list)
    parse_mode: Literal["HTML", "Markdown", "MarkdownV2"] = "HTML"
    forced_command: FORCED_COMMAND_TYPE | None = Field(default=None)


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
    WEB_SEARCH = "联网搜索与时事问答"
    FULLTEXT_TRANSLATION = "翻译与文本编辑"
    DATA_SCIENCE = "科学计算"
    URL_CONTEXT = "外链上下文问答"
    GEOLOCATION_IDENTIFICATION = "地理位置识别"
    GENERAL_QA = "通用问答与指令"


WORKFLOW_RUN_OUTPUTS_TYPE = Union[str, AnswerType]


class WorkflowCompletionOutputs(BaseModel):
    type: WORKFLOW_RUN_OUTPUTS_TYPE | None = Field(default=None, description="任务类型")
    answer: str | dict | None = Field(default=None, description="处理结果")
    extras: Any | None = Field(default=None, description="扩展数据")


class WorkflowCompletionData(BaseModel):
    id: str
    workflow_id: str
    status: str
    outputs: WorkflowCompletionOutputs = Field(description="工作流返回的 dict data")
    error: str | None = Field(default="")


class WorkflowCompletionResponse(BaseModel):
    task_id: str
    workflow_run_id: str
    data: WorkflowCompletionData


# --- Nested Data Models for the 'data' field ---


class ExecutionMetadata(BaseModel):
    """
    Metadata about the execution, such as token usage and cost.
    Appears within the 'node_finished' event data.
    """

    total_tokens: Optional[int] = None
    total_price: Optional[Decimal] = None
    currency: Optional[str] = None


class WorkflowStartedData(BaseModel):
    """
    Data payload for the 'workflow_started' event.
    """

    id: str
    workflow_id: str
    created_at: int


class NodeStartedData(BaseModel):
    """
    Data payload for the 'node_started' event.
    """

    id: str
    node_id: str
    node_type: str
    title: str
    index: int
    predecessor_node_id: Optional[str] = None
    inputs: Dict[str, Any]
    created_at: int


class TextChunkData(BaseModel):
    """
    Data payload for the 'text_chunk' event.
    """

    text: str
    from_variable_selector: List[str]


class NodeFinishedData(BaseModel):
    """
    Data payload for the 'node_finished' event.
    """

    id: str
    node_id: str
    index: int
    predecessor_node_id: Optional[str] = None
    inputs: Dict[str, Any]
    process_data: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    status: Literal["running", "succeeded", "failed", "stopped"]
    error: Optional[str] = None
    elapsed_time: Optional[float] = None
    execution_metadata: Optional[ExecutionMetadata] = None
    created_at: int


class WorkflowFinishedData(BaseModel):
    """
    Data payload for the 'workflow_finished' event.
    """

    id: str
    workflow_id: str
    status: Literal["running", "succeeded", "failed", "stopped"]
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    elapsed_time: Optional[float] = None
    total_tokens: Optional[int] = None
    total_steps: int
    created_at: int
    finished_at: int


# --- Top-Level Event Models ---


class BaseWorkflowEvent(BaseModel):
    """
    A base model for standard workflow events that contain a 'data' payload.
    """

    task_id: str
    workflow_run_id: str


class WorkflowStartedEvent(BaseWorkflowEvent):
    """
    Event fired when a workflow run starts.
    """

    event: Literal["workflow_started"]
    data: WorkflowStartedData


class NodeStartedEvent(BaseWorkflowEvent):
    """
    Event fired when a node in the workflow starts execution.
    """

    event: Literal["node_started"]
    data: NodeStartedData


class TextChunkEvent(BaseWorkflowEvent):
    """
    Represents a chunk of text generated by a node.
    """

    event: Literal["text_chunk"]
    data: TextChunkData


class NodeFinishedEvent(BaseWorkflowEvent):
    """
    Event fired when a node in the workflow finishes execution.
    """

    event: Literal["node_finished"]
    data: NodeFinishedData


class WorkflowFinishedEvent(BaseWorkflowEvent):
    """
    Event fired when a workflow run finishes.
    """

    event: Literal["workflow_finished"]
    data: WorkflowFinishedData


class BaseMessageEvent(BaseModel):
    """
    A base model for message-related events like TTS.
    Note: These events have a flatter structure than workflow events.
    """

    task_id: str
    message_id: str
    conversation_id: str
    created_at: int


class TTSMessageEvent(BaseMessageEvent):
    """
    TTS audio stream event, containing a base64 encoded audio chunk.
    """

    event: Literal["tts_message"]
    audio: str


class TTSMessageEndEvent(BaseMessageEvent):
    """
    TTS audio stream end event.
    """

    event: Literal["tts_message_end"]
    audio: str  # According to the docs, this will be an empty string.


class PingEvent(BaseModel):
    """
    A keep-alive ping event, sent every 10s.
    """

    event: Literal["ping"]


# --- Discriminated Union for Parsing ---

# This Union uses the 'event' field with Literal types as a discriminator.
# Pydantic can automatically use this to parse an incoming dictionary
# into the correct Pydantic model. For example, using `pydantic.parse_obj_as`.
ChunkCompletionResponse = Union[
    WorkflowStartedEvent,
    NodeStartedEvent,
    TextChunkEvent,
    NodeFinishedEvent,
    WorkflowFinishedEvent,
    TTSMessageEvent,
    TTSMessageEndEvent,
    PingEvent,
]
