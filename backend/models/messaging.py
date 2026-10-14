"""First-party linking API wire models. Proofs are never identity claims."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class ChannelLinkRequest(BaseModel):
    channel: str = Field(min_length=1, max_length=80, pattern=r'^[a-z0-9_-]+$')
    provider: str = Field(min_length=1, max_length=80, pattern=r'^[a-z0-9_-]+$')
    kind: Literal['token', 'code']


class ChannelLinkProof(BaseModel):
    proof: str
    kind: Literal['token', 'code']
    expires_at: datetime
    deep_link: Optional[str] = None
    address: Optional[str] = None


class ChannelLink(BaseModel):
    id: str
    channel: str
    provider: str
    external_id: str
    visible_in_app: bool = False
    voice_notes: bool = True
    keep_private_memories_in_app: bool = True
    insights: bool = False
    display_handle: Optional[str] = None
    linked_at: datetime


class ChannelLinksResponse(BaseModel):
    links: list[ChannelLink]


class ChannelVisibilityRequest(BaseModel):
    """Partial per-link settings. Omitted fields stay as stored."""

    visible_in_app: Optional[bool] = None
    voice_notes: Optional[bool] = None
    keep_private_memories_in_app: Optional[bool] = None
    insights: Optional[bool] = None

    @model_validator(mode='after')
    def require_one_setting(self):
        if all(
            value is None
            for value in (
                self.visible_in_app,
                self.voice_notes,
                self.keep_private_memories_in_app,
                self.insights,
            )
        ):
            raise ValueError('At least one setting is required')
        return self


class ChannelLinkReceipt(BaseModel):
    status: str
