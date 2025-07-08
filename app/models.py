# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 12:34
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from enum import Enum

from pydantic import BaseModel, Field


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