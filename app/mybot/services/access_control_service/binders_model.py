# -*- coding: utf-8 -*-
"""
Pydantic models for binders configuration
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class Binder(BaseModel):
    """Single binder (group/channel) configuration"""

    id: int = Field(..., description="Telegram chat ID (negative for groups/channels)")
    title: str = Field(..., description="Display name for the group/channel")
    invite_link: Optional[str] = Field("", description="Invite link for private channels")


class BindersConfig(BaseModel):
    """Root configuration containing all binders"""

    binders: List[Binder] = Field(
        default_factory=list, description="List of required groups/channels"
    )
