"""Contract for conversation and episode boundary evidence (refactor lane L4; desktop sends via L5).

The server owns segmentation for every client. A client or integration reports what it
observed; the server decides where conversations and episodes start and end.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

BoundaryKind = Literal['calendar_event', 'desktop_meeting', 'screen_meeting', 'phone_call', 'media_playback']


class BoundaryParticipant(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class BoundarySignal(BaseModel):
    kind: BoundaryKind
    started_at: datetime
    ended_at: Optional[datetime] = None  # None while ongoing
    title: Optional[str] = None
    meeting_link: Optional[str] = None
    call_controls_detected: Optional[bool] = None
    call_platform: Optional[str] = None
    participants: List[BoundaryParticipant] = []
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_device: Optional[str] = None
    external_id: Optional[str] = None  # calendar event id, call id; idempotency key with kind
