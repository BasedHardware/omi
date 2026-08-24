"""Scheduled convergence for temporary frame-request pixels.

This worker is intentionally independent from the queue delivery endpoint and
its product rollout.  It only deletes owner-scoped temporary objects whose
terminal metadata records a retryable cleanup state; attached evidence is
never selected.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client
from database.frame_requests import (
    cleanup_ambiguous_frame_upload_pixels,
    cleanup_frame_request_pixels,
    prune_expired_frame_requests,
)
from utils.retrieval.frame_request_storage import delete_frame_request_pixels
from utils.integration_telemetry import emit_posthog_event

logger = logging.getLogger(__name__)
_STATE_COLLECTION = "maintenance_state"
_STATE_DOCUMENT = "frame_request_retention"


def _load_user_page(client: Any, *, user_limit: int) -> tuple[list[Any], str | None]:
    """Load one stable user page and return its durable continuation cursor.

    A cursor is cleared at the end of a cycle so the next invocation wraps to
    the first account. Duplicate work after a crash is safe; advancing only
    after the page finishes prevents a skipped account.
    """

    state_ref = client.collection(_STATE_COLLECTION).document(_STATE_DOCUMENT)
    state_snapshot = state_ref.get()
    state = state_snapshot.to_dict() if state_snapshot.exists else {}
    cursor_uid = str((state or {}).get("cursor_uid") or "").strip()
    users_ref = client.collection("users")

    def query_page(after_uid: str | None) -> list[Any]:
        query = users_ref.order_by("__name__", direction=firestore.Query.ASCENDING)
        if after_uid:
            query = query.start_after({"__name__": users_ref.document(after_uid)})
        return list(query.limit(user_limit + 1).stream())

    rows = query_page(cursor_uid or None)
    if not rows and cursor_uid:
        rows = query_page(None)
    selected = rows[:user_limit]
    next_cursor = str(selected[-1].id) if len(rows) > user_limit and selected else None
    return selected, next_cursor


def _store_user_cursor(client: Any, cursor_uid: str | None) -> None:
    client.collection(_STATE_COLLECTION).document(_STATE_DOCUMENT).set(
        {
            "cursor_uid": cursor_uid or "",
            "updated_at": datetime.now(timezone.utc),
        },
        merge=True,
    )


def run_frame_request_retention_maintenance(
    *,
    user_limit: int = 1000,
    rows_per_user: int = 32,
    firestore_client: Any | None = None,
) -> dict[str, int]:
    """Run one bounded scheduled pass and return content-free counters."""

    if user_limit < 1 or rows_per_user < 1:
        raise ValueError("maintenance limits must be positive")
    started = time.monotonic()
    client = firestore_client or get_firestore_client()
    users, next_cursor = _load_user_page(client, user_limit=user_limit)
    users_truncated = next_cursor is not None
    attempted = cleaned = pruned = failures = 0
    for user in users:
        uid = str(getattr(user, "id", "")).strip()
        if not uid:
            continue
        attempted += 1
        try:
            pruned += prune_expired_frame_requests(uid, limit=rows_per_user, firestore_client=client)
            cleaned += cleanup_frame_request_pixels(
                uid,
                delete_storage=lambda storage_id, owner=uid: delete_frame_request_pixels(owner, storage_id),
                limit=rows_per_user,
                firestore_client=client,
            )
            cleaned += cleanup_ambiguous_frame_upload_pixels(
                uid,
                delete_storage=lambda storage_id, owner=uid: delete_frame_request_pixels(owner, storage_id),
                limit=rows_per_user,
                firestore_client=client,
            )
        except Exception:
            # Keep the scheduler moving across accounts. The row-level retry
            # state is written by the cleanup adapter for external failures;
            # unexpected query failures are retried by the next run.
            logger.exception("frame retention maintenance failed for one account")
            failures += 1
    _store_user_cursor(client, next_cursor)
    result = {
        "users_scanned": attempted,
        "rows_pruned": pruned,
        "pixels_cleaned": cleaned,
        "users_page_full": int(users_truncated),
    }
    elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
    emit_posthog_event(
        "frame-retention-worker",
        "frame_retention_maintenance",
        {
            "users_scanned": min(attempted, user_limit),
            "rows_pruned": min(pruned, user_limit * rows_per_user),
            "pixels_cleaned": min(cleaned, user_limit * rows_per_user),
            "accounts_with_errors": min(failures, user_limit),
            "users_page_full": int(users_truncated),
            "latency_bucket": "0_1s" if elapsed_ms <= 1000 else "1s_plus",
            "outcome": "degraded" if failures else "completed",
        },
    )
    return result


__all__ = ["run_frame_request_retention_maintenance"]
