# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/8 12:34
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Union

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

    # 增强的上下文信息
    user_info: Dict[str, Any] | None = None
    """用户的完整信息，包括用户名、全名、是否机器人、语言代码等"""

    entities_info: Dict[str, List[Dict]] | None = None
    """消息中的实体信息，包括链接、mention、hashtag等富文本信息"""

    forward_info: Dict[str, Any] | None = None
    """转发消息的完整信息，包括原始发送者、转发来源等，现在也包括外部回复信息"""

    reply_info: Dict[str, Any] | None = None
    """回复消息的完整信息，包括被回复消息的内容、发送者、实体等"""

    chat_info: Dict[str, Any] | None = None
    """聊天的完整信息，包括聊天类型、标题、权限等"""

    quote_info: Dict[str, Any] | None = None
    """引用文本信息，包含从外部消息引用的文本内容"""

    class Config:
        arbitrary_types_allowed = True


class AgentStrategy(str, Enum):
    FUNCTION_CALLING = "function_calling"
    REACT = "ReAct"


AGENT_STRATEGY_TYPE = Union[str, AgentStrategy]
