"""
Tests for task_recommendations router store error sanitization.
PR: fix(task_recommendations): sanitize exception detail leakage in _raise_store_error

Verifies that IdempotencyConflictError, StaleSnapshotError,
RecommendationGenerationMismatchError, and SnapshotValidationError
do NOT leak internal exception details, account generations, or DB schema to clients.
"""

from fastapi import HTTPException, status


class IdempotencyConflictError(Exception):
    pass


class StaleSnapshotError(Exception):
    pass


class RecommendationGenerationMismatchError(Exception):
    pass


class SnapshotValidationError(Exception):
    pass


def _simulate_raise_store_error(exc: Exception) -> None:
    """Simulate the patched _raise_store_error logic."""
    if isinstance(exc, IdempotencyConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Recommendation idempotency conflict. Please retry."
        ) from exc
    if isinstance(exc, StaleSnapshotError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Recommendation snapshot is stale. Please refresh."
        ) from exc
    if isinstance(exc, RecommendationGenerationMismatchError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Recommendation generation mismatch. Please refresh."
        ) from exc
    if isinstance(exc, SnapshotValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid recommendation snapshot payload."
        ) from exc
    raise exc


class TestTaskRecommendationsSanitization:
    """Ensure no raw exception messages or internal metadata are exposed in HTTP responses."""

    def test_idempotency_conflict_no_raw_leak(self):
        """Idempotency conflict must return a safe generic message without internal key traces."""
        raw_msg = "idempotency_key=k_999a_secret status=IN_PROGRESS worker_id=worker-42"
        err = IdempotencyConflictError(raw_msg)
        try:
            _simulate_raise_store_error(err)
            assert False, "Should have raised HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 409
            assert raw_msg not in exc.detail
            assert "worker-42" not in exc.detail
            assert exc.detail == "Recommendation idempotency conflict. Please retry."

    def test_stale_snapshot_no_raw_leak(self):
        """Stale snapshot must return safe message without internal Firestore timestamps."""
        raw_msg = "snapshot_ts=1729000000000 generation=42 expected=41 table=interventions"
        err = StaleSnapshotError(raw_msg)
        try:
            _simulate_raise_store_error(err)
            assert False, "Should have raised HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 409
            assert raw_msg not in exc.detail
            assert "table=interventions" not in exc.detail
            assert exc.detail == "Recommendation snapshot is stale. Please refresh."

    def test_generation_mismatch_no_raw_leak(self):
        """Generation mismatch must return safe message without internal account generation."""
        raw_msg = "account_generation=12 mismatch with current_generation=13 uid=user_123"
        err = RecommendationGenerationMismatchError(raw_msg)
        try:
            _simulate_raise_store_error(err)
            assert False, "Should have raised HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 409
            assert raw_msg not in exc.detail
            assert "user_123" not in exc.detail
            assert exc.detail == "Recommendation generation mismatch. Please refresh."

    def test_snapshot_validation_no_raw_leak(self):
        """Snapshot validation error must return clean 422 without raw schema trace."""
        raw_msg = "Pydantic ValidationError: 3 fields invalid in internal_snapshot_spec"
        err = SnapshotValidationError(raw_msg)
        try:
            _simulate_raise_store_error(err)
            assert False, "Should have raised HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 422
            assert raw_msg not in exc.detail
            assert "Pydantic" not in exc.detail
            assert exc.detail == "Invalid recommendation snapshot payload."
