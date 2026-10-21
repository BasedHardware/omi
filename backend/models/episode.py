"""Wire models for episodes: the live occasion overlay over conversations.

An episode never owns conversation content. It lists the conversations
("moments" are the speech stretches inside them) that belong to one occasion
and carries the compact running state the cheap incremental update keeps:
a topic, running bullets, people, and provisional tasks that are shown live
but are not tasks until the conversation's normal processing saves them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

EpisodeStatus = Literal['live', 'closed']
EpisodeCloseReason = Literal['user', 'gap', 'idle', 'hard_cap', 'source_change', 'calendar_boundary', 'moved_on']
ProvisionalItemKind = Literal['task', 'reminder']
ProvisionalItemStatus = Literal['provisional', 'kept', 'dropped', 'dismissed']


class EpisodeMoment(BaseModel):
    id: str
    conversation_id: str
    started_at: datetime
    ended_at: datetime
    # Offsets (seconds) into the conversation's own transcript.
    start_offset: float = 0.0
    end_offset: float = 0.0
    heading: str = ''


class EpisodeProvisionalItem(BaseModel):
    id: str
    text: str
    kind: ProvisionalItemKind = 'task'
    status: ProvisionalItemStatus = 'provisional'
    # True when the speaker addressed Omi directly ("Hey Omi, remind me…").
    explicit: bool = False
    due_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    # Seconds into the conversation's transcript where the item was heard.
    segment_offset: Optional[float] = None
    created_at: datetime
    # The saved task this item matched at reconciliation, when kept.
    action_item_id: Optional[str] = None


class Episode(BaseModel):
    id: str
    status: EpisodeStatus
    started_at: datetime
    last_activity_at: datetime
    closed_at: Optional[datetime] = None
    close_reason: Optional[EpisodeCloseReason] = None
    title: str = ''
    bullets: list[str] = Field(default_factory=list)
    people: list[str] = Field(default_factory=list)
    provisional_items: list[EpisodeProvisionalItem] = Field(default_factory=list)
    moments: list[EpisodeMoment] = Field(default_factory=list)
    conversation_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    state_updated_at: Optional[datetime] = None


class EpisodeLiveResponse(BaseModel):
    """``enabled`` is the server capability: false means today's per-conversation UI."""

    enabled: bool
    episode: Optional[Episode] = None


class EpisodeLookupResponse(BaseModel):
    enabled: bool
    episode: Optional[Episode] = None


class EpisodeWrapUpRequest(BaseModel):
    # The in-progress conversation the client is finishing alongside the wrap-up.
    conversation_id: Optional[str] = None
