"""Durable, metadata-only bridge from desktop finalization to one keyframe.

Finalization writes an outbox row before it completes. Screen sync reconciles
that row after persisting capture metadata, so offline/restarted clients do not
lose the request and text finalization never waits for pixels.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from google.cloud import firestore

from database._client import get_data_plane_firestore_client
from database.firestore_index_registry import (
    CONVERSATION_KEYFRAME_JOBS_DEVICE_STATE_QUERY,
    SCREEN_ACTIVITY_KEYFRAME_QUERY,
)
from database.frame_requests import enqueue_frame_request
from utils.retrieval.keyframe_policy import KeyframeCandidate, select_conversation_keyframe
from utils.integration_telemetry import emit_posthog_event
from utils.retrieval.frame_request_policy import FRAME_REQUEST_MAX_TTL_SECONDS

_COLLECTION = "conversation_keyframe_jobs"
_MAX_CANDIDATES = 500
_MAX_CANDIDATE_PAGES = 10
_JOB_RETENTION = timedelta(days=7)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _select_screen_winner(screens: list[Any]) -> tuple[Any, str, int | None] | None:
    """Select from a newest-first page, using only locally admitted captures."""
    candidates: list[KeyframeCandidate] = []
    metadata: dict[str, tuple[str, int | None]] = {}
    for screen in screens[:_MAX_CANDIDATES]:
        data = screen.to_dict() or {}
        if data.get("captureEligible") is not True:
            continue
        local_id = str(data.get("localScreenshotId") or "")
        if not local_id.isdigit():
            continue
        try:
            captured = datetime.fromisoformat(str(data.get("timestamp")).replace(" ", "T")).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        frame_id = str(screen.id)
        candidates.append(
            KeyframeCandidate(
                frame_id=frame_id,
                captured_at=captured,
                app_name=str(data.get("appName") or ""),
                window_title=str(data.get("windowTitle") or ""),
                content_hash=hashlib.sha256(f"{frame_id}\0{data.get('timestamp')}".encode()).hexdigest(),
            )
        )
        retention = data.get("deviceRetentionSeconds")
        metadata[frame_id] = (local_id, int(retention) if isinstance(retention, int) and retention > 0 else None)
    winner = select_conversation_keyframe(candidates)
    if winner is None:
        return None
    local_id, retention = metadata[winner.frame_id]
    return winner, local_id, retention


def _select_screen_pages(
    fetch_page: Callable[[Any | None], list[Any]],
) -> tuple[tuple[Any, str, int | None] | None, bool]:
    """Page past ineligible prefixes; return selection and bound exhaustion."""
    cursor = None
    for _page in range(_MAX_CANDIDATE_PAGES):
        screens = fetch_page(cursor)
        selection = _select_screen_winner(screens[:_MAX_CANDIDATES])
        if selection is not None:
            return selection, False
        if len(screens) <= _MAX_CANDIDATES:
            return None, False
        cursor = screens[_MAX_CANDIDATES - 1]
    return None, True


def ensure_conversation_keyframe_job(uid: str, conversation: Any, *, firestore_client: Any | None = None) -> bool:
    """Persist one idempotent desktop keyframe intent; return whether eligible."""
    source = getattr(getattr(conversation, "source", None), "value", getattr(conversation, "source", None))
    started = getattr(conversation, "started_at", None)
    finished = getattr(conversation, "finished_at", None)
    device_id = str(getattr(conversation, "client_device_id", None) or "").strip()
    if source != "desktop" or not isinstance(started, datetime) or not isinstance(finished, datetime) or not device_id:
        return False
    client = firestore_client or get_data_plane_firestore_client()
    ref = client.collection("users").document(uid).collection(_COLLECTION).document(str(conversation.id))
    transaction = client.transaction()

    @firestore.transactional
    def _create_once(transaction: Any) -> None:
        if ref.get(transaction=transaction).exists:
            return
        transaction.create(
            ref,
            {
                "conversation_id": str(conversation.id),
                "device_id": device_id,
                "started_at": _utc(started),
                "finished_at": _utc(finished),
                "state": "pending",
                "expires_at": _utc(finished) + _JOB_RETENTION,
                "updated_at": datetime.now(timezone.utc),
            },
        )

    _create_once(transaction)
    return True


def reconcile_conversation_keyframe_jobs(
    uid: str,
    *,
    device_id: str,
    account_generation: int,
    device_retention_seconds: int | None = None,
    firestore_client: Any | None = None,
    limit: int = 16,
) -> int:
    """Select and enqueue one deterministic eligible frame for pending jobs."""
    client = firestore_client or get_data_plane_firestore_client()
    user = client.collection("users").document(uid)
    jobs = CONVERSATION_KEYFRAME_JOBS_DEVICE_STATE_QUERY.build(
        user.collection(_COLLECTION),
        {"device_id": device_id, "state": "pending"},
        field_filter_factory=firestore.FieldFilter,
    )
    jobs = jobs.limit(limit).stream()
    enqueued = 0
    for snapshot in jobs:
        row = snapshot.to_dict() or {}
        started, finished = row.get("started_at"), row.get("finished_at")
        if not isinstance(started, datetime) or not isinstance(finished, datetime):
            snapshot.reference.update({"state": "pruned", "terminal_reason": "invalid_conversation_window"})
            continue
        base_query = SCREEN_ACTIVITY_KEYFRAME_QUERY.build(
            user.collection("screen_activity"),
            {
                "device_id": device_id,
                "account_generation": account_generation,
                "started_at": started.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23],
                "finished_at": finished.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23],
            },
            field_filter_factory=firestore.FieldFilter,
        ).order_by("timestamp", direction=firestore.Query.DESCENDING)

        def fetch_page(cursor: Any | None) -> list[Any]:
            query = base_query.start_after(cursor) if cursor is not None else base_query
            return list(query.limit(_MAX_CANDIDATES + 1).stream())

        selection, exhausted_bound = _select_screen_pages(fetch_page)
        if selection is None:
            # Keep pending: metadata can arrive after finalization and another
            # screen sync will retry. The device's own pruning is authoritative.
            if exhausted_bound:
                snapshot.reference.update(
                    {
                        "state": "pruned",
                        "terminal_reason": "candidate_scan_bound_exhausted",
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                emit_posthog_event(
                    uid,
                    "conversation_keyframe_terminal",
                    {"outcome": "pruned", "reason": "candidate_scan_bound_exhausted", "scan_limit": 5000},
                )
                continue
            retention = min(
                device_retention_seconds or FRAME_REQUEST_MAX_TTL_SECONDS,
                FRAME_REQUEST_MAX_TTL_SECONDS,
            )
            if datetime.now(timezone.utc) >= _utc(finished) + timedelta(seconds=retention):
                snapshot.reference.update(
                    {
                        "state": "pruned",
                        "terminal_reason": "local_capture_retention_elapsed",
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
            continue
        _winner, local_id, device_retention = selection
        try:
            request, _ = enqueue_frame_request(
                uid,
                device_id=device_id,
                account_generation=account_generation,
                dedupe_key=f"conversation-keyframe:{row.get('conversation_id')}",
                conversation_id=str(row.get("conversation_id")),
                screenshot_id=local_id,
                device_retention_seconds=device_retention,
                firestore_client=client,
            )
        except ValueError as exc:
            if "already has an active frame request" not in str(exc):
                raise
            snapshot.reference.update({"state": "requested", "updated_at": datetime.now(timezone.utc)})
            continue
        snapshot.reference.update(
            {
                "state": "requested",
                "account_generation": account_generation,
                "frame_request_id": request.request_id,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        enqueued += 1
    return enqueued


def prune_expired_conversation_keyframe_jobs(
    uid: str,
    *,
    firestore_client: Any | None = None,
    now: datetime | None = None,
    limit: int = 32,
) -> int:
    """Delete bounded expired operational intents, independent of rollout.

    Attached conversation evidence lives in the permanent photo/request rows,
    not in this delivery intent. Expiring an unsatisfied or already-requested
    intent therefore bounds dark/disabled metadata without shortening an
    attached image's conversation lifetime.
    """

    if not 1 <= limit <= 128:
        raise ValueError("keyframe job cleanup limit is outside the bounded window")
    current = _utc(now or datetime.now(timezone.utc))
    rows = (
        (firestore_client or get_data_plane_firestore_client())
        .collection("users")
        .document(uid)
        .collection(_COLLECTION)
        .where(filter=firestore.FieldFilter("expires_at", "<=", current))
        .limit(limit)
        .stream()
    )
    deleted = 0
    for snapshot in rows:
        snapshot.reference.delete()
        deleted += 1
    return deleted


__all__ = [
    "ensure_conversation_keyframe_job",
    "prune_expired_conversation_keyframe_jobs",
    "reconcile_conversation_keyframe_jobs",
]
