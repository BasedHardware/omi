"""Pure policy for authenticated, bounded just-in-time frame requests.

This module is deliberately independent of Firestore, HTTP, and image
decoding.  It is the common authority used by the queue adapter and tests:
owner/account-generation fencing, deduplication, bounded expiry, quota, and
the distinction between temporary requested frames and conversation evidence.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from models.frame_request import (
    TERMINAL_FRAME_REQUEST_STATES,
    FrameRequest,
    FrameRequestState,
)

# Metadata must become terminal before the temporary bucket's day-6 lifecycle
# can remove pixels; this avoids a live row pointing at a lifecycle-pruned blob.
FRAME_REQUEST_MAX_TTL_SECONDS = 6 * 24 * 60 * 60
FRAME_REQUEST_MAX_BYTES = 10 * 1024 * 1024
FRAME_REQUEST_MAX_BATCH = 32
FRAME_REQUEST_MAX_PENDING_PER_DEVICE = 8
FRAME_REQUEST_MAX_BYTES_PER_DEVICE = 50 * 1024 * 1024
FRAME_REQUEST_DEDUPE_WINDOW_SECONDS = 60
FRAME_REQUEST_MAX_ATTACHED_PER_CONVERSATION = 1
FRAME_REQUEST_MAX_BYTES_PER_CONVERSATION = 10 * 1024 * 1024


def explicit_frame_requests_enabled(configurable: Mapping[str, Any] | None = None) -> bool:
    """Fail closed unless a request-scoped, authenticated decision is present.

    The environment variable remains a local development seam only.  A caller
    must provide a non-empty ``uid`` and explicit boolean decision; clients
    cannot opt themselves into the production queue through this helper.
    """

    if not isinstance(configurable, Mapping):
        return False
    uid = configurable.get("uid") or configurable.get("user_id")
    decision = configurable.get("frame_requests_enabled")
    if not isinstance(uid, str) or not uid.strip() or not isinstance(decision, bool):
        return False
    return decision


def canonical_dedupe_key(
    *,
    uid: str,
    device_id: str,
    screenshot_id: str | None,
    conversation_id: str | None,
    intent_key: str,
    account_generation: int = 0,
) -> str:
    """Return a non-reversible request identity without logging user content."""

    values = [
        uid.strip(),
        device_id.strip(),
        str(account_generation),
        screenshot_id or "",
        conversation_id or "",
        intent_key.strip(),
    ]
    if not uid.strip() or not device_id.strip() or not intent_key.strip() or not (screenshot_id or conversation_id):
        raise ValueError("frame request dedupe components must not be blank")
    if account_generation < 0:
        raise ValueError("account_generation must be nonnegative")
    material = "\x00".join(values).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def request_expiry(
    *, created_at: datetime, requested_ttl_seconds: int | None, device_retention_seconds: int | None
) -> datetime:
    """Bound temporary frame expiry by both the product and device windows."""

    created = _utc(created_at)
    requested = requested_ttl_seconds if requested_ttl_seconds is not None else FRAME_REQUEST_MAX_TTL_SECONDS
    if requested < 1:
        raise ValueError("requested_ttl_seconds must be positive")
    ttl = min(requested, FRAME_REQUEST_MAX_TTL_SECONDS)
    if device_retention_seconds is not None:
        if device_retention_seconds < 1:
            raise ValueError("device_retention_seconds must be positive")
        ttl = min(ttl, device_retention_seconds)
    return created + timedelta(seconds=ttl)


def conversation_lifetime_expiry(created_at: datetime) -> datetime:
    """Represent conversation-lifetime retention without a far-future date."""

    # The model uses created_at as the sentinel for attached evidence.  This is
    # intentionally not a year-9999 timestamp that could accidentally leak into
    # a TTL cleanup query or overflow a provider serializer.
    return _utc(created_at)


def is_expired(request: FrameRequest, *, now: datetime) -> bool:
    """Temporary rows expire at the effective device/product boundary only."""

    if request.conversation_id and request.state == FrameRequestState.attached:
        return False
    return _utc(now) >= request.expires_at and request.state not in TERMINAL_FRAME_REQUEST_STATES


def device_may_claim(request: FrameRequest, *, uid: str, device_id: str, account_generation: int) -> bool:
    """Only the current owner/device generation can claim a pending request."""

    return (
        request.uid == uid
        and request.device_id == device_id
        and request.account_generation == account_generation
        and request.state == FrameRequestState.requested
    )


def validate_transition(
    request: FrameRequest,
    *,
    next_state: FrameRequestState,
    uid: str,
    device_id: str,
    account_generation: int,
    now: datetime,
) -> None:
    """Raise on an unauthorized or impossible state transition."""

    if request.uid != uid or request.device_id != device_id or request.account_generation != account_generation:
        raise PermissionError("frame request owner or account generation mismatch")
    if request.state in TERMINAL_FRAME_REQUEST_STATES:
        raise ValueError("frame request is already terminal")
    if is_expired(request, now=now):
        raise ValueError("frame request has expired")
    allowed = {
        FrameRequestState.requested: {
            FrameRequestState.claimed,
            FrameRequestState.offline,
            FrameRequestState.pruned,
            FrameRequestState.failed,
            FrameRequestState.expired,
            FrameRequestState.cancelled,
        },
        FrameRequestState.claimed: {
            FrameRequestState.uploaded,
            FrameRequestState.offline,
            FrameRequestState.pruned,
            FrameRequestState.failed,
            FrameRequestState.expired,
            FrameRequestState.cancelled,
        },
        FrameRequestState.uploaded: {FrameRequestState.attached, FrameRequestState.failed, FrameRequestState.pruned},
    }
    if next_state not in allowed.get(request.state, set()):
        raise ValueError(f"invalid frame request transition {request.state.value}->{next_state.value}")
    if next_state == FrameRequestState.attached and not request.conversation_id:
        raise ValueError("only conversation-bound requests may be attached")


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    reason: str
    pending_count: int
    pending_bytes: int


def check_device_quota(
    requests: list[FrameRequest],
    *,
    uid: str,
    device_id: str,
    now: datetime,
    additional_bytes: int = 0,
) -> QuotaDecision:
    """Bound queued work before a request is persisted or claimed."""

    if additional_bytes < 0 or additional_bytes > FRAME_REQUEST_MAX_BYTES:
        return QuotaDecision(False, "invalid_bytes", 0, 0)
    live = [
        request
        for request in requests
        if request.uid == uid
        and request.device_id == device_id
        and request.state not in TERMINAL_FRAME_REQUEST_STATES
        and not is_expired(request, now=now)
    ]
    pending_count = len(live)
    pending_bytes = sum(request.byte_count for request in live)
    if pending_count >= FRAME_REQUEST_MAX_PENDING_PER_DEVICE:
        return QuotaDecision(False, "pending_count", pending_count, pending_bytes)
    if pending_bytes + additional_bytes > FRAME_REQUEST_MAX_BYTES_PER_DEVICE:
        return QuotaDecision(False, "pending_bytes", pending_count, pending_bytes)
    return QuotaDecision(True, "ok", pending_count, pending_bytes)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
