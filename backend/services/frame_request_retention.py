"""Scheduled convergence for temporary frame-request pixels.

This worker is intentionally independent from the queue delivery endpoint and
its product rollout.  It only deletes owner-scoped temporary objects whose
terminal metadata records a retryable cleanup state; attached evidence is
never selected.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from database._client import get_firestore_client
from database.frame_requests import cleanup_frame_request_pixels, prune_expired_frame_requests
from utils.retrieval.frame_request_storage import delete_frame_request_pixels
from utils.integration_telemetry import emit_posthog_event

logger = logging.getLogger(__name__)


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
    users = list(client.collection("users").limit(user_limit + 1).stream())
    if len(users) > user_limit:
        raise RuntimeError("frame retention user scan exceeded its safety bound")
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
        except Exception:
            # Keep the scheduler moving across accounts. The row-level retry
            # state is written by the cleanup adapter for external failures;
            # unexpected query failures are retried by the next run.
            logger.exception("frame retention maintenance failed for one account")
            failures += 1
    result = {"users_scanned": attempted, "rows_pruned": pruned, "pixels_cleaned": cleaned}
    elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
    emit_posthog_event(
        "frame-retention-worker",
        "frame_retention_maintenance",
        {
            "users_scanned": min(attempted, user_limit),
            "rows_pruned": min(pruned, user_limit * rows_per_user),
            "pixels_cleaned": min(cleaned, user_limit * rows_per_user),
            "accounts_with_errors": min(failures, user_limit),
            "latency_bucket": "0_1s" if elapsed_ms <= 1000 else "1s_plus",
            "outcome": "degraded" if failures else "completed",
        },
    )
    return result


__all__ = ["run_frame_request_retention_maintenance"]
