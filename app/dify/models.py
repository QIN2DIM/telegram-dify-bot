# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/7 05:41
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from typing import Type, Literal

from pydantic import BaseModel, Field
from telegram import User


class WorkflowInputs(BaseModel):
    message_context: str = Field(description="翻译上下文")
    user_language_code: str = Field(description="客户端语言代码")
    output_language: str | None = Field(default="")


class WorkflowRunPayload(BaseModel):
    inputs: WorkflowInputs
    user: Type[User]
    response_mode: Literal["streaming", "blocking"] = "streaming"

    @property
    def user_id(self) -> str:
        return self.user.id

    def dumps_params(self) -> dict:
        _payload = self.model_dump(mode="json")
        _payload["user"] = self.user_id
        return _payload
