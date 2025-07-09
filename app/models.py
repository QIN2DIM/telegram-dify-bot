# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 12:34
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from enum import Enum
from pathlib import Path
from typing import List

from pydantic import BaseModel


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


class Interaction(BaseModel):
    task_type: TaskType | None = None
    photo_paths: List[Path] | None = None
    from_user_fmt: str | None = None
