"""Deterministic metadata-only selection for one conversation keyframe.

Capture/storage adapters supply candidates after applying their local Rewind
exclusion policy. This boundary never receives pixels; the upload boundary
decodes, strips metadata, and enforces the dimensions/egress budget. Here we
choose a stable winner and declare conversation-lifetime retention.
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
    # Sensitive surface names are deliberately not returned. They are inputs
    # to the fail-closed selection policy, not durable keyframe metadata.
    content_hash: str
    retention_class: str = "conversation_lifetime"
    expires_at: None = None


_SENSITIVE_SURFACE_MARKERS = (
    "1password",
    "bitwarden",
    "keychain",
    "password",
    "private browsing",
    "incognito",
    "secret",
    "security code",
    "authentication code",
)


def _sensitive(candidate: KeyframeCandidate) -> bool:
    surface = f"{candidate.app_name}\n{candidate.window_title}".casefold()
    return any(marker in surface for marker in _SENSITIVE_SURFACE_MARKERS)


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
        and not _sensitive(candidate)
    ]
    if not eligible:
        return None
    winner = max(eligible, key=lambda item: (_utc(item.captured_at), item.frame_id))
    return ConversationKeyframe(
        frame_id=winner.frame_id,
        captured_at=_utc(winner.captured_at),
        content_hash=winner.content_hash,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
