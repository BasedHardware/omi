"""Stale job reads must leave recovery to the lease-owning route/coordinator.

See docs/runbooks/sync-two-lane.md: progress age is not lease ownership.
test_sync_status_read_ownership covers this reader through the real HTTP route.
"""

import json
import time

import pytest

import database.sync_jobs as sync_jobs


@pytest.fixture(autouse=True)
def _prod_sync_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')


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


def test_is_sync_job_stale_sequenced_processing(monkeypatch):
    # Processing sequenced jobs must be flagged stale if the worker died past threshold (#21943)
    monkeypatch.setenv('SYNC_SEQUENCED_STALE_SECONDS', '600')
    stale_job = {
        'id': 'j5',
        'status': 'processing',
        'dispatch_mode': 'sequenced',
        'updated_at': time.time() - 700,
    }
    assert sync_jobs.is_sync_job_stale(stale_job) is True

    fresh_job = {
        'id': 'j6',
        'status': 'processing',
        'dispatch_mode': 'sequenced',
        'updated_at': time.time(),
    }
    assert sync_jobs.is_sync_job_stale(fresh_job) is False


def test_is_sync_job_stale_sequenced_queued(monkeypatch):
    # Queued sequenced jobs exceeding the stale threshold are flagged stale
    monkeypatch.setenv('SYNC_SEQUENCED_STALE_SECONDS', '1800')
    stale_queued = {
        'id': 'j7',
        'status': 'queued',
        'dispatch_mode': 'sequenced',
        'updated_at': time.time() - 2000,
    }
    assert sync_jobs.is_sync_job_stale(stale_queued) is True

    fresh_queued = {
        'id': 'j8',
        'status': 'queued',
        'dispatch_mode': 'sequenced',
        'updated_at': time.time() - 100,
    }
    assert sync_jobs.is_sync_job_stale(fresh_queued) is False

    # Pending retry (attempt/started_at set) must never be flipped stale
    retrying_queued = {
        'id': 'j9',
        'status': 'queued',
        'dispatch_mode': 'sequenced',
        'attempt': 1,
        'started_at': time.time() - 2000,
        'updated_at': time.time() - 2000,
    }
    assert sync_jobs.is_sync_job_stale(retrying_queued) is False


def test_is_sync_job_stale_sequenced_completed_never_stale():
    # Completed sequenced jobs must never be evaluated stale regardless of age
    completed_job = {
        'id': 'j10',
        'status': 'completed',
        'dispatch_mode': 'sequenced',
        'updated_at': time.time() - 50000,
    }
    assert sync_jobs.is_sync_job_stale(completed_job) is False


def test_is_sync_job_stale_sequenced_malformed_env(monkeypatch):
    # Malformed env must fall back safely to 43200s default without raising
    monkeypatch.setenv('SYNC_SEQUENCED_STALE_SECONDS', 'invalid_number')
    recent_job = {
        'id': 'j11',
        'status': 'queued',
        'dispatch_mode': 'sequenced',
        'updated_at': time.time() - 1000,
    }
    assert sync_jobs.is_sync_job_stale(recent_job) is False

    old_job = {
        'id': 'j12',
        'status': 'queued',
        'dispatch_mode': 'sequenced',
        'updated_at': time.time() - 45000,
    }
    assert sync_jobs.is_sync_job_stale(old_job) is True
