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
from utils.integration_telemetry import emit_posthog_event
from utils.retrieval.frame_request_storage import delete_frame_request_pixels

logger = logging.getLogger(__name__)
_STATE_COLLECTION = "maintenance_state"
_STATE_DOCUMENT = "frame_request_retention"


def _retry_collection(client: Any) -> Any:
    return client.collection(_STATE_COLLECTION).document(_STATE_DOCUMENT).collection("retry_accounts")


def _load_user_page(client: Any, *, user_limit: int) -> tuple[list[Any], str | None, list[str]]:
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

    # Retry failures independently from the population cursor while reserving
    # capacity for fresh accounts. A permanently failing UID therefore cannot
    # pin the global scan, and a transient failure is retried on the next run.
    retry_budget = max(1, user_limit // 4)
    if user_limit > 1:
        retry_budget = min(retry_budget, user_limit - 1)
    retry_snapshots = list(
        _retry_collection(client).order_by("__name__", direction=firestore.Query.ASCENDING).limit(retry_budget).stream()
    )
    retry_uids = [str(snapshot.id) for snapshot in retry_snapshots]
    retry_rows: list[Any] = []
    selected_retry_uids: list[str] = []
    for uid in retry_uids:
        snapshot = users_ref.document(uid).get()
        if getattr(snapshot, "exists", False):
            retry_rows.append(snapshot)
            selected_retry_uids.append(uid)
    fresh_limit = max(0, user_limit - len(retry_rows))

    def query_page(after_uid: str | None) -> list[Any]:
        query = users_ref.order_by("__name__", direction=firestore.Query.ASCENDING)
        if after_uid:
            query = query.start_after({"__name__": users_ref.document(after_uid)})
        return list(query.limit(fresh_limit + 1).stream()) if fresh_limit else []

    rows = query_page(cursor_uid or None)
    if not rows and cursor_uid:
        rows = query_page(None)
    raw_selected = rows[:fresh_limit]
    selected_retry_set = set(selected_retry_uids)
    selected = [row for row in raw_selected if str(getattr(row, "id", "")) not in selected_retry_set]
    # Advance by the raw population page, including any duplicate already
    # served from the retry queue. Filtering must never move the cursor past an
    # account which was not selected.
    next_cursor = str(raw_selected[-1].id) if len(rows) > fresh_limit and raw_selected else None
    return retry_rows + selected, next_cursor, retry_uids


def _store_user_cursor(client: Any, cursor_uid: str | None) -> None:
    client.collection(_STATE_COLLECTION).document(_STATE_DOCUMENT).set(
        {
            "cursor_uid": cursor_uid or "",
            "updated_at": datetime.now(timezone.utc),
        },
        merge=True,
    )


def _drain_due_pages(operation: Any, *, page_size: int) -> int:
    """Drain a finite due query while preserving its bounded page size."""

    total = 0
    while True:
        changed = int(operation())
        total += changed
        if changed < page_size:
            return total


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
    users, next_cursor, retry_uids = _load_user_page(client, user_limit=user_limit)
    users_truncated = next_cursor is not None
    attempted = cleaned = pruned = failures = 0
    retry_set = set(retry_uids)
    retry_collection = _retry_collection(client)
    for user in users:
        uid = str(getattr(user, "id", "")).strip()
        if not uid:
            continue
        attempted += 1
        try:
            pruned += _drain_due_pages(
                lambda: prune_expired_frame_requests(uid, limit=rows_per_user, firestore_client=client),
                page_size=rows_per_user,
            )
            cleaned += _drain_due_pages(
                lambda: cleanup_frame_request_pixels(
                    uid,
                    delete_storage=lambda storage_id, owner=uid: (delete_frame_request_pixels(owner, storage_id)),
                    limit=rows_per_user,
                    firestore_client=client,
                ),
                page_size=rows_per_user,
            )
            cleaned += _drain_due_pages(
                lambda: cleanup_ambiguous_frame_upload_pixels(
                    uid,
                    delete_storage=lambda storage_id, owner=uid: (delete_frame_request_pixels(owner, storage_id)),
                    limit=rows_per_user,
                    firestore_client=client,
                ),
                page_size=rows_per_user,
            )
            if uid in retry_set:
                retry_collection.document(uid).delete()
        except Exception:
            # Keep the scheduler moving across accounts. The row-level retry
            # state is written by the cleanup adapter for external failures;
            # unexpected query failures are retried by the next run.
            logger.exception("frame retention maintenance failed for one account")
            failures += 1
            retry_collection.document(uid).set({"uid": uid, "updated_at": datetime.now(timezone.utc)}, merge=True)
    _store_user_cursor(client, next_cursor)
    result = {
        "users_scanned": attempted,
        "rows_pruned": pruned,
        "pixels_cleaned": cleaned,
        "users_page_full": int(users_truncated),
        "accounts_with_errors": failures,
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
