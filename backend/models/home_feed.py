"""Compact, content-bounded Home timeline contract (details hydrate separately)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class HomeFeedCard(BaseModel):
    id: str
    kind: Literal['episode', 'conversation']
    detail_id: str
    sort_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    title: str = Field('', max_length=240)
    emoji: str = Field('', max_length=32)
    preview: str = Field('', max_length=320)
    status: str
    home_step: Optional[str] = None
    starred: bool = False
    is_locked: bool = False
    has_tasks: bool = False
    member_count: int = Field(1, ge=0)
    sources: list[str] = Field(default_factory=list, max_length=16)
    summary_available: bool = False
    revision: str


class HomeFeedResponse(BaseModel):
    generation: str
    items: list[HomeFeedCard] = Field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool = False
    truncated: bool = False


class HomeFeedPreparationResponse(BaseModel):
    ready: bool
    processed: int
    has_more: bool
