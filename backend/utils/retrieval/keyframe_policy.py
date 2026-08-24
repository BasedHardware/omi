"""Deterministic metadata-only selection for one conversation keyframe.

Capture/storage adapters supply candidates after applying their local screen
exclusion policy.  This boundary never receives pixels and leaves exact image
dimensions/egress budgets to the owning client contract; it only chooses a
stable winner and declares the conversation-lifetime retention class.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class KeyframeCandidate:
    frame_id: str
    captured_at: datetime
    app_name: str
    window_title: str = ""
    content_hash: str = ""
    excluded: bool = False
    capture_complete: bool = True


@dataclass(frozen=True)
class ConversationKeyframe:
    frame_id: str
    captured_at: datetime
    app_name: str
    window_title: str
    content_hash: str
    retention_class: str = "conversation_lifetime"
    expires_at: None = None


def select_conversation_keyframe(candidates: Iterable[KeyframeCandidate]) -> ConversationKeyframe | None:
    """Choose one complete, non-excluded candidate with deterministic ties.

    The latest eligible frame is used because it best represents the completed
    conversation.  The lexical frame id tie-breaker makes retries idempotent
    when two captures have the same timestamp.
    """

    eligible = [
        candidate
        for candidate in candidates
        if candidate.frame_id.strip()
        and candidate.content_hash.strip()
        and candidate.capture_complete
        and not candidate.excluded
    ]
    if not eligible:
        return None
    winner = max(eligible, key=lambda item: (_utc(item.captured_at), item.frame_id))
    return ConversationKeyframe(
        frame_id=winner.frame_id,
        captured_at=_utc(winner.captured_at),
        app_name=winner.app_name.strip(),
        window_title=winner.window_title.strip(),
        content_hash=winner.content_hash,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
