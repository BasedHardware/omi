"""Status polling must obey the same run ownership as sync workers.

Unlike the route-only tests, these exercise the real Redis reader as well.
The ownership contract is documented in docs/runbooks/sync-two-lane.md.
"""

import json
import time

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.sync_jobs as sync_jobs
import routers.sync as sync_router


@pytest.fixture
def status_client(monkeypatch):
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setenv('SYNC_LEDGER_FENCE_MODE', 'active')
    app = FastAPI()
    app.include_router(sync_router.router)
    app.dependency_overrides[sync_router.auth.get_current_user_uid] = lambda: 'owner'
    with TestClient(app) as client:
        yield client, redis


def _seed_job(redis, *, dispatch_mode='cloud_tasks', fence_mode='active', status='processing'):
    job = {
        'job_id': 'job-1',
        'uid': 'owner',
        'status': status,
        'lane': 'fresh',
        'dispatch_mode': dispatch_mode,
        'ledger_fence_mode': fence_mode,
        'created_at': time.time() - 4000,
        'updated_at': time.time() - 3600,
        'total_segments': 1,
    }
    if fence_mode is None:
        job.pop('ledger_fence_mode')
    key = f'{sync_jobs.JOB_KEY_PREFIX}job-1'
    redis.set(key, json.dumps(job), ex=sync_jobs.JOB_TTL_SECONDS)
    return key, redis.get(key)


@pytest.mark.parametrize('fence_mode', [None, 'legacy', 'active'])
def test_poll_preserves_stale_job_owned_by_running_worker(status_client, fence_mode):
    client, redis = status_client
    key, before = _seed_job(redis, fence_mode=fence_mode)
    lock_key = f'{sync_jobs.RUN_LOCK_KEY_PREFIX}job-1'
    redis.set(lock_key, '1:running-worker', ex=sync_jobs.RUN_LOCK_TTL_SECONDS)

    response = client.get('/v2/sync-local-files/job-1')

    assert response.status_code == 200
    assert response.json()['status'] == 'processing'
    assert redis.get(key) == before
    assert redis.get(lock_key) == b'1:running-worker'


def test_poll_leaves_inline_liveness_to_coordinator(status_client):
    client, redis = status_client
    key, before = _seed_job(redis, dispatch_mode='inline')

    response = client.get('/v2/sync-local-files/job-1')

    assert response.status_code == 200
    assert response.json()['status'] == 'processing'
    assert redis.get(key) == before


def test_poll_respects_standby_cutover_fence(status_client, monkeypatch):
    client, redis = status_client
    monkeypatch.setenv('SYNC_LEDGER_FENCE_MODE', 'standby')
    key, before = _seed_job(redis)

    response = client.get('/v2/sync-local-files/job-1')

    assert response.status_code == 200
    assert response.json()['status'] == 'processing'
    assert redis.get(key) == before


def test_reader_cannot_overwrite_concurrent_worker_completion(monkeypatch):
    redis = fakeredis.FakeRedis()
    key, before = _seed_job(redis)
    completed = {**json.loads(before), 'status': 'completed', 'result': {'new_memories': ['conversation-1']}}
    original_get = redis.get

    def complete_after_snapshot(read_key):
        snapshot = original_get(read_key)
        if read_key == key:
            redis.set(key, json.dumps(completed))
        return snapshot

    monkeypatch.setattr(redis, 'get', complete_after_snapshot)
    monkeypatch.setattr(sync_jobs, 'r', redis)

    sync_jobs.get_sync_job('job-1')

    assert json.loads(original_get(key)) == completed


@pytest.mark.parametrize('fence_mode', [None, 'legacy', 'active'])
@pytest.mark.parametrize('status,reason', [('processing', 'sync_worker_stale'), ('queued', 'sync_dispatch_lost')])
def test_poll_recovers_abandoned_cloud_task_through_real_finalizer(status_client, fence_mode, status, reason):
    """Read-only lookup must not disable the owned stale-recovery path."""
    client, redis = status_client
    key, _ = _seed_job(redis, fence_mode=fence_mode, status=status)

    response = client.get('/v2/sync-local-files/job-1')

    assert response.status_code == 200
    assert response.json()['status'] == 'failed'
    assert response.json()['reason_code'] == reason
    assert json.loads(redis.get(key))['reason_code'] == reason
    assert redis.get(f'{sync_jobs.RUN_LOCK_KEY_PREFIX}job-1') is None
