"""Unit tests for task_recommendations router store error exception detail sanitization.

Verifies that IdempotencyConflictError, StaleSnapshotError, RecommendationGenerationMismatchError,
and SnapshotValidationError do not leak internal database state, account generations,
or schema validation details in HTTP response details.
"""

from fastapi import HTTPException, status
import pytest

import routers.task_recommendations as tr_routes


def test_idempotency_conflict_error_is_masked():
    """IdempotencyConflictError must return sanitized 409 detail."""
    leak_text = "idempotency key conflict: idemp-987654 account_generation=42 (store=task_recommendations)"
    exc = tr_routes.recommendation_db.IdempotencyConflictError(leak_text)

    with pytest.raises(HTTPException) as exc_info:
        tr_routes._raise_store_error(exc)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Idempotency conflict detected."
    assert "idemp-987654" not in exc_info.value.detail
    assert "account_generation" not in exc_info.value.detail


def test_stale_snapshot_error_is_masked():
    """StaleSnapshotError must return sanitized 409 detail."""
    leak_text = "snapshot snap-112233 version mismatch: current=3 expected=4 table=task_snapshots"
    exc = tr_routes.recommendation_db.StaleSnapshotError(leak_text)

    with pytest.raises(HTTPException) as exc_info:
        tr_routes._raise_store_error(exc)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Stale snapshot state detected."
    assert "snap-112233" not in exc_info.value.detail
    assert "table=task_snapshots" not in exc_info.value.detail


def test_recommendation_generation_mismatch_error_is_masked():
    """RecommendationGenerationMismatchError must return sanitized 409 detail."""
    leak_text = "account gen mismatch: uid=user-999 expected_gen=5 actual_gen=2"
    exc = tr_routes.recommendation_db.RecommendationGenerationMismatchError(leak_text)

    with pytest.raises(HTTPException) as exc_info:
        tr_routes._raise_store_error(exc)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Recommendation generation mismatch."
    assert "user-999" not in exc_info.value.detail
    assert "actual_gen=2" not in exc_info.value.detail


def test_snapshot_validation_error_is_masked():
    """SnapshotValidationError must return sanitized 422 detail."""
    leak_text = "validation error in snapshot payload: column user_metrics.private_score invalid"
    exc = tr_routes.recommendations.SnapshotValidationError(leak_text)

    with pytest.raises(HTTPException) as exc_info:
        tr_routes._raise_store_error(exc)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == "Snapshot validation failed."
    assert "user_metrics.private_score" not in exc_info.value.detail
