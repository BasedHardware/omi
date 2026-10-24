"""The unit the live stream and finalization hand to the episode service. Pure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class MomentInput:
    conversation_id: str
    source: Optional[str]
    segments: Sequence[Mapping[str, Any]]
    started_at: datetime
    ended_at: datetime
    trigger: str  # pause | rollover | interval | session_end | finalize
    calendar_identity: Optional[str] = None
    language: Optional[str] = None
