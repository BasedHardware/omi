"""First-party linking API wire models. Proofs are never identity claims."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ChannelLinkRequest(BaseModel):
    channel: str = Field(min_length=1, max_length=80, pattern=r'^[a-z0-9_-]+$')
    provider: str = Field(min_length=1, max_length=80, pattern=r'^[a-z0-9_-]+$')
    kind: Literal['token', 'code']


class ChannelLinkProof(BaseModel):
    proof: str
    kind: Literal['token', 'code']
    expires_at: datetime


class ChannelLink(BaseModel):
    id: str
    channel: str
    provider: str
    external_id: str
    visible_in_app: bool = False
    linked_at: datetime


class ChannelLinksResponse(BaseModel):
    links: list[ChannelLink]


class ChannelVisibilityRequest(BaseModel):
    visible_in_app: bool


class ChannelLinkReceipt(BaseModel):
    status: str
