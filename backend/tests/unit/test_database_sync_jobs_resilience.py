"""Unit tests verifying defensive resilience and validation in sync_jobs."""

from __future__ import annotations

import json
from typing import Any
import pytest

from database.sync_jobs import (
    JOB_TTL_SECONDS,
    RUN_LOCK_TTL_SECONDS,
    SyncLedgerFenceMode,
    _sync_job_finalization_updates,
    create_sync_job,
    delete_sync_job,
    get_sync_job,
    get_sync_job_run_lock_epoch,
    is_sync_job_stale,
)


class _MockRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


@pytest.fixture(autouse=True)
def _patch_redis(monkeypatch: pytest.MonkeyPatch) -> _MockRedis:
    monkeypatch.setenv("OMI_ENV_STAGE", "prod")
    fake_redis = _MockRedis()
    monkeypatch.setattr("database.sync_jobs.r", fake_redis)
    return fake_redis


def test_create_sync_job_validates_inputs() -> None:
    """Verify create_sync_job strictly validates uid, total_files, total_segments, and job_id."""
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        create_sync_job("", 1, 1)

    with pytest.raises(ValueError, match="total_files must be a non-negative integer"):
        create_sync_job("u1", -1, 1)

    with pytest.raises(ValueError, match="total_files must be a non-negative integer"):
        create_sync_job("u1", True, 1)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="total_segments must be a non-negative integer"):
        create_sync_job("u1", 1, -2)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        create_sync_job("u1", 1, 1, job_id="bad/id")


def test_create_sync_job_normalizes_and_persists(_patch_redis: _MockRedis) -> None:
    """Verify create_sync_job normalizes fields and persists into Redis with proper TTL."""
    job = create_sync_job(
        "  user-123  ",
        5,
        10,
        job_id="  job-999  ",
        lane="backfill",
        content_id="  content-abc  ",
    )
    assert job["uid"] == "user-123"
    assert job["job_id"] == "job-999"
    assert job["lane"] == "backfill"
    assert job["content_id"] == "content-abc"
    assert job["status"] == "queued"

    # Verify readable from mock redis
    stored = get_sync_job("job-999")
    assert stored is not None
    assert stored["uid"] == "user-123"


def test_get_sync_job_handles_invalid_ids_and_corrupt_data(_patch_redis: _MockRedis) -> None:
    """Verify get_sync_job returns None on invalid ids or corrupt redis blobs."""
    assert get_sync_job("") is None
    assert get_sync_job("invalid/id") is None

    # Corrupt JSON in redis
    _patch_redis.store["sync_job:corrupt"] = "{not-valid-json"
    assert get_sync_job("corrupt") is None


def test_delete_sync_job_safe_noops(_patch_redis: _MockRedis) -> None:
    """Verify delete_sync_job safely handles empty or invalid strings."""
    delete_sync_job("")
    delete_sync_job("bad/id")
    _patch_redis.store["sync_job:good"] = "{}"
    delete_sync_job("good")
    assert "sync_job:good" not in _patch_redis.store


def test_sync_job_finalization_updates_validates_result() -> None:
    """Verify _sync_job_finalization_updates raises ValueError on non-dict result."""
    with pytest.raises(ValueError, match="result must be a dictionary"):
        _sync_job_finalization_updates(None, completed_at=100.0)  # type: ignore[arg-type]

    # Valid dictionary produces status and counts
    status, total, failed, updates = _sync_job_finalization_updates(
        {"total_segments": 5, "failed_segments": 2}, completed_at=100.0
    )
    assert status == "partial_failure"
    assert total == 5
    assert failed == 2
    assert updates["status"] == "partial_failure"
    assert updates["completed_at"] == 100.0


def test_get_sync_job_run_lock_epoch_resilience() -> None:
    """Verify get_sync_job_run_lock_epoch safely parses epoch from token."""
    assert get_sync_job_run_lock_epoch("5:random-uuid") == 5
    assert get_sync_job_run_lock_epoch("random-uuid") == 0
    assert get_sync_job_run_lock_epoch("-3:uuid") == 0
    assert get_sync_job_run_lock_epoch("invalid:uuid") == 0
    assert get_sync_job_run_lock_epoch("") == 0
