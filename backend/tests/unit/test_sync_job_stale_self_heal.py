"""Stale job reads must leave recovery to the lease-owning route/coordinator.

See docs/runbooks/sync-two-lane.md: progress age is not lease ownership.
test_sync_status_read_ownership covers this reader through the real HTTP route.
"""

import json
import time

import database.sync_jobs as sync_jobs


class _FakeRedis:
    def __init__(self, job: dict):
        self._blob = json.dumps(job).encode()
        self.sets: list[tuple[str, dict]] = []

    def get(self, key):
        return self._blob

    def set(self, key, value, ex=None):
        self._blob = value if isinstance(value, (bytes, str)) else json.dumps(value).encode()
        self.sets.append((key, json.loads(value)))


def _stale_at():
    return time.time() - (sync_jobs.STALE_THRESHOLD_SECONDS + 60)


def test_stale_processing_read_preserves_inline_dispatch(monkeypatch):
    fake = _FakeRedis({'id': 'j1', 'status': 'processing', 'dispatch_mode': 'inline', 'updated_at': _stale_at()})
    monkeypatch.setattr(sync_jobs, 'r', fake)

    job = sync_jobs.get_sync_job('j1')

    assert job['status'] == 'processing'
    assert fake.sets == []


def test_stale_processing_read_preserves_cloud_tasks_dispatch(monkeypatch):
    fake = _FakeRedis({'id': 'j2', 'status': 'processing', 'dispatch_mode': 'cloud_tasks', 'updated_at': _stale_at()})
    monkeypatch.setattr(sync_jobs, 'r', fake)

    assert sync_jobs.get_sync_job('j2')['status'] == 'processing'
    assert fake.sets == []


def test_fresh_processing_job_is_not_finalized(monkeypatch):
    fake = _FakeRedis({'id': 'j3', 'status': 'processing', 'dispatch_mode': 'inline', 'updated_at': time.time()})
    monkeypatch.setattr(sync_jobs, 'r', fake)

    assert sync_jobs.get_sync_job('j3')['status'] == 'processing'
    assert fake.sets == []


def test_stale_queued_job_is_never_finalized(monkeypatch):
    # No worker has claimed it — flipping queued -> failed caused #7469 retry loops.
    fake = _FakeRedis({'id': 'j4', 'status': 'queued', 'dispatch_mode': 'cloud_tasks', 'updated_at': _stale_at()})
    monkeypatch.setattr(sync_jobs, 'r', fake)

    assert sync_jobs.get_sync_job('j4')['status'] == 'queued'
    assert fake.sets == []
