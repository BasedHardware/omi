"""Scheduled convergence for temporary frame-request pixels.

This worker is intentionally independent from the queue delivery endpoint and
its product rollout.  It only deletes owner-scoped temporary objects whose
terminal metadata records a retryable cleanup state; attached evidence is
never selected.
"""

from __future__ import annotations

import logging
import time
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client
from database.frame_requests import (
    FrameCleanupPage,
    cleanup_ambiguous_frame_upload_pixels,
    cleanup_conversation_frame_deletion_outbox,
    cleanup_expired_frame_vision_outputs,
    cleanup_frame_request_pixels,
    delete_expired_frame_request_metadata,
    prune_expired_frame_requests,
)
from utils.integration_telemetry import emit_posthog_event
from utils.retrieval.frame_request_storage import delete_frame_request_pixels
from services.conversation_keyframes import prune_expired_conversation_keyframe_jobs

logger = logging.getLogger(__name__)
_STATE_COLLECTION = "maintenance_state"
_STATE_DOCUMENT = "frame_request_retention"
_LEASE_SECONDS = 20 * 60


def _acquire_lease(client: Any, *, owner: str, now: datetime) -> int | None:
    ref = client.collection(_STATE_COLLECTION).document(_STATE_DOCUMENT)
    transaction = client.transaction()

    @firestore.transactional
    def _claim(transaction: Any) -> int | None:
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() if snapshot.exists else {}
        expires = (row or {}).get("lease_expires_at")
        if isinstance(expires, datetime) and expires > now:
            return None
        generation = max(0, int((row or {}).get("lease_generation") or 0)) + 1
        transaction.set(
            ref,
            {
                "lease_owner": owner,
                "lease_generation": generation,
                "lease_expires_at": now + timedelta(seconds=_LEASE_SECONDS),
            },
            merge=True,
        )
        return generation

    return _claim(transaction)


def _release_lease(client: Any, *, owner: str, generation: int) -> bool:
    ref = client.collection(_STATE_COLLECTION).document(_STATE_DOCUMENT)
    transaction = client.transaction()

    @firestore.transactional
    def _release(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() if snapshot.exists else {}
        if row.get("lease_owner") != owner or row.get("lease_generation") != generation:
            return False
        transaction.update(ref, {"lease_expires_at": datetime.now(timezone.utc), "lease_owner": ""})
        return True

    return _release(transaction)


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
    retry_cursor_uid = str((state or {}).get("retry_cursor_uid") or "").strip()
    users_ref = client.collection("users")

    # Retry failures independently from the population cursor while reserving
    # capacity for fresh accounts. A permanently failing UID therefore cannot
    # pin the global scan, and a transient failure is retried on the next run.
    retry_budget = max(1, user_limit // 4)
    if user_limit > 1:
        retry_budget = min(retry_budget, user_limit - 1)
    retry_query = _retry_collection(client).order_by("__name__", direction=firestore.Query.ASCENDING)
    if retry_cursor_uid:
        retry_query = retry_query.start_after({"__name__": _retry_collection(client).document(retry_cursor_uid)})
    retry_snapshots = list(retry_query.limit(retry_budget).stream())
    if not retry_snapshots and retry_cursor_uid:
        retry_snapshots = list(
            _retry_collection(client)
            .order_by("__name__", direction=firestore.Query.ASCENDING)
            .limit(retry_budget)
            .stream()
        )
    retry_uids = [str(snapshot.id) for snapshot in retry_snapshots]
    retry_rows: list[Any] = []
    selected_retry_uids: list[str] = []
    for uid in retry_uids:
        snapshot = users_ref.document(uid).get()
        if getattr(snapshot, "exists", False):
            retry_rows.append(snapshot)
            selected_retry_uids.append(uid)
        else:
            _retry_collection(client).document(uid).delete()
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


def _store_user_cursor(
    client: Any,
    cursor_uid: str | None,
    retry_cursor_uid: str | None = None,
    *,
    lease_owner: str | None = None,
    lease_generation: int | None = None,
) -> bool:
    ref = client.collection(_STATE_COLLECTION).document(_STATE_DOCUMENT)
    data = {
        "cursor_uid": cursor_uid or "",
        "retry_cursor_uid": retry_cursor_uid or "",
        "updated_at": datetime.now(timezone.utc),
    }
    if lease_owner is None or lease_generation is None:
        ref.set(data, merge=True)
        return True
    transaction = client.transaction()

    @firestore.transactional
    def _fenced_store(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() if snapshot.exists else {}
        if row.get("lease_owner") != lease_owner or row.get("lease_generation") != lease_generation:
            return False
        transaction.set(ref, data, merge=True)
        return True

    return _fenced_store(transaction)


def _drain_due_pages(operation: Any, *, page_size: int, max_pages: int = 8) -> tuple[int, bool]:
    """Drain a finite due query while preserving its bounded page size."""

    total = 0
    for _page in range(max_pages):
        result = operation()
        processed = result.processed if isinstance(result, FrameCleanupPage) else int(result)
        changed = result.cleaned if isinstance(result, FrameCleanupPage) else processed
        total += changed
        if processed < page_size:
            return total, False
    return total, True


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
    lease_owner = uuid4().hex
    lease_generation = _acquire_lease(client, owner=lease_owner, now=datetime.now(timezone.utc))
    if lease_generation is None:
        return {
            "users_scanned": 0,
            "rows_pruned": 0,
            "pixels_cleaned": 0,
            "metadata_deleted": 0,
            "vision_outputs_stripped": 0,
            "users_page_full": 0,
            "accounts_with_errors": 0,
            "lease_skipped": 1,
        }
    users, next_cursor, retry_uids = _load_user_page(client, user_limit=user_limit)
    users_truncated = next_cursor is not None
    attempted = cleaned = pruned = metadata_deleted = outputs_stripped = failures = 0
    retry_set = set(retry_uids)
    retry_collection = _retry_collection(client)
    for user in users:
        uid = str(getattr(user, "id", "")).strip()
        if not uid:
            continue
        attempted += 1
        try:
            prune_expired_conversation_keyframe_jobs(
                uid,
                firestore_client=client,
                limit=rows_per_user,
            )
            changed, more_due = _drain_due_pages(
                lambda: prune_expired_frame_requests(uid, limit=rows_per_user, firestore_client=client),
                page_size=rows_per_user,
            )
            pruned += changed
            changed, more_cleanup = _drain_due_pages(
                lambda: cleanup_frame_request_pixels(
                    uid,
                    delete_storage=lambda storage_id, owner=uid: (delete_frame_request_pixels(owner, storage_id)),
                    limit=rows_per_user,
                    firestore_client=client,
                    report_page=True,
                ),
                page_size=rows_per_user,
            )
            cleaned += changed
            changed, more_metadata = _drain_due_pages(
                lambda: delete_expired_frame_request_metadata(
                    uid,
                    limit=rows_per_user,
                    firestore_client=client,
                    report_page=True,
                ),
                page_size=rows_per_user,
            )
            metadata_deleted += changed
            changed, more_outputs = _drain_due_pages(
                lambda: cleanup_expired_frame_vision_outputs(
                    uid,
                    limit=rows_per_user,
                    firestore_client=client,
                    report_page=True,
                ),
                page_size=rows_per_user,
            )
            outputs_stripped += changed
            changed, more_orphans = _drain_due_pages(
                lambda: cleanup_ambiguous_frame_upload_pixels(
                    uid,
                    delete_storage=lambda storage_id, owner=uid: (delete_frame_request_pixels(owner, storage_id)),
                    limit=rows_per_user,
                    firestore_client=client,
                    report_page=True,
                ),
                page_size=rows_per_user,
            )
            cleaned += changed
            changed, more_deletions = _drain_due_pages(
                lambda: cleanup_conversation_frame_deletion_outbox(
                    uid,
                    delete_storage=lambda storage_id, owner=uid: delete_frame_request_pixels(owner, storage_id),
                    limit=rows_per_user,
                    firestore_client=client,
                    report_page=True,
                ),
                page_size=rows_per_user,
            )
            cleaned += changed
            if more_due or more_cleanup or more_metadata or more_outputs or more_orphans or more_deletions:
                retry_collection.document(uid).set({"uid": uid, "updated_at": datetime.now(timezone.utc)}, merge=True)
            elif uid in retry_set:
                retry_collection.document(uid).delete()
        except Exception:
            # Keep the scheduler moving across accounts. The row-level retry
            # state is written by the cleanup adapter for external failures;
            # unexpected query failures are retried by the next run.
            logger.exception("frame retention maintenance failed for one account")
            failures += 1
            retry_collection.document(uid).set({"uid": uid, "updated_at": datetime.now(timezone.utc)}, merge=True)
    cursor_committed = _store_user_cursor(
        client,
        next_cursor,
        retry_uids[-1] if retry_uids else None,
        lease_owner=lease_owner,
        lease_generation=lease_generation,
    )
    _release_lease(client, owner=lease_owner, generation=lease_generation)
    result = {
        "users_scanned": attempted,
        "rows_pruned": pruned,
        "pixels_cleaned": cleaned,
        "metadata_deleted": metadata_deleted,
        "vision_outputs_stripped": outputs_stripped,
        "users_page_full": int(users_truncated),
        "accounts_with_errors": failures,
        "lease_skipped": 0,
        "cursor_committed": int(cursor_committed),
    }
    elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
    emit_posthog_event(
        "frame-retention-worker",
        "frame_retention_maintenance",
        {
            "users_scanned": min(attempted, user_limit),
            "rows_pruned": min(pruned, user_limit * rows_per_user),
            "pixels_cleaned": min(cleaned, user_limit * rows_per_user),
            "metadata_deleted": min(metadata_deleted, user_limit * rows_per_user),
            "vision_outputs_stripped": min(outputs_stripped, user_limit * rows_per_user),
            "accounts_with_errors": min(failures, user_limit),
            "users_page_full": int(users_truncated),
            "latency_bucket": "0_1s" if elapsed_ms <= 1000 else "1s_plus",
            "outcome": "degraded" if failures else "completed",
        },
    )
    return result


__all__ = ["run_frame_request_retention_maintenance"]
