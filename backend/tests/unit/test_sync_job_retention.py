"""Opt-in Redis reductions preserve active, failure, billing and fence lifetimes."""

import json

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import sync_jobs
from routers import sync as sync_router


@pytest.fixture
def redis(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv(sync_jobs.COMPLETED_TTL_ENV, raising=False)
    monkeypatch.delenv(sync_jobs.METRIC_ONCE_TTL_ENV, raising=False)
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', client)
    return client


@pytest.mark.parametrize('raw', [None, '', 'bad', '0', '-1', '3599', '86401', '1.5'])
def test_unset_or_invalid_retention_preserves_default(redis, monkeypatch, raw):
    for env in (sync_jobs.COMPLETED_TTL_ENV, sync_jobs.METRIC_ONCE_TTL_ENV):
        if raw is not None:
            monkeypatch.setenv(env, raw)
        assert sync_jobs._retention_seconds(env) == 86400
    job = sync_jobs.create_sync_job('owner', 1, 1)
    assert sync_jobs.update_sync_job(job['job_id'], {'status': 'completed'})
    assert redis.ttl(f'sync_job:{job["job_id"]}') >= 86398
    assert sync_jobs.try_mark_once(job['job_id'], 'terminal_outcome_metric')
    assert redis.ttl(f'sync_job_once:{job["job_id"]}:terminal_outcome_metric') >= 86398


@pytest.mark.parametrize('fenced', [False, True])
@pytest.mark.parametrize('status', ['queued', 'processing', 'completed', 'partial_failure', 'failed'])
def test_only_successful_cas_changes_retention(redis, monkeypatch, fenced, status):
    monkeypatch.setenv(sync_jobs.COMPLETED_TTL_ENV, '21600')
    job = sync_jobs.create_sync_job('owner', 1, 1)
    job_id = job['job_id']
    assert redis.ttl(f'sync_job:{job_id}') >= 86398
    assert redis.ttl('pending_sync_jobs:owner') >= 86398
    redis.set(f'sync_job_lock:{job_id}', '1:owner', ex=1800)
    redis.set(f'sync_job_lock_epoch:{job_id}', 1)
    sync_jobs.add_processed_segment(job_id, 'synthetic.wav')
    assert redis.ttl(f'sync_job_segments:{job_id}') >= 86398
    if fenced:
        assert sync_jobs.fenced_update_sync_job(job_id, '1:owner', {'status': status}).applied
    else:
        assert sync_jobs.update_sync_job(job_id, {'status': status})
    expected = 21600 if status == 'completed' else 86400
    assert expected - 2 <= redis.ttl(f'sync_job:{job_id}') <= expected
    assert json.loads(redis.get(f'sync_job:{job_id}'))['status'] == status
    assert redis.ttl('pending_sync_jobs:owner') >= 86398
    assert redis.ttl(f'sync_job_lock:{job_id}') >= 1798
    assert redis.ttl(f'sync_job_lock_epoch:{job_id}') == -1


@pytest.mark.parametrize('tag', ['speech_ms', 'dg_ms', 'usage', 'future_guard', 'segment_outcome'])
def test_billing_and_unknown_once_tags_keep_full_window(redis, monkeypatch, tag):
    monkeypatch.setenv(sync_jobs.METRIC_ONCE_TTL_ENV, '3600')
    assert sync_jobs.try_mark_once('job', tag)
    key = f'sync_job_once:job:{tag}'
    assert redis.ttl(key) >= 86398
    assert not sync_jobs.try_mark_once('job', tag)


@pytest.mark.parametrize('tag', ['terminal_outcome_metric', 'segment_outcome:' + 'a' * 24])
def test_metric_guards_use_config_without_refreshing_duplicates(redis, monkeypatch, tag):
    monkeypatch.setenv(sync_jobs.METRIC_ONCE_TTL_ENV, '21600')
    assert sync_jobs.try_mark_once('job', tag)
    key = f'sync_job_once:job:{tag}'
    assert 21598 <= redis.ttl(key) <= 21600
    redis.expire(key, 1234)
    assert not sync_jobs.try_mark_once('job', tag)
    assert redis.ttl(key) <= 1234
    # Runtime changes affect new writes only, not an import-time snapshot.
    monkeypatch.setenv(sync_jobs.METRIC_ONCE_TTL_ENV, '3600')
    assert sync_jobs.try_mark_once('next-job', tag)
    assert 3598 <= redis.ttl(f'sync_job_once:next-job:{tag}') <= 3600


def test_stale_owner_and_terminal_updates_cannot_shorten_existing_result(redis, monkeypatch):
    job = sync_jobs.create_sync_job('owner', 1, 1)
    key = f'sync_job:{job["job_id"]}'
    redis.set(f'sync_job_lock:{job["job_id"]}', 'owner', ex=1800)
    monkeypatch.setenv(sync_jobs.COMPLETED_TTL_ENV, '3600')
    assert not sync_jobs.fenced_update_sync_job(job['job_id'], 'stale', {'status': 'completed'}).applied
    assert redis.ttl(key) >= 86398
    monkeypatch.delenv(sync_jobs.COMPLETED_TTL_ENV)
    assert sync_jobs.update_sync_job(job['job_id'], {'status': 'completed'})
    before = redis.get(key)
    monkeypatch.setenv(sync_jobs.COMPLETED_TTL_ENV, '3600')
    assert sync_jobs.update_sync_job(job['job_id'], {'status': 'completed'}) is None
    assert not sync_jobs.fenced_update_sync_job(job['job_id'], 'owner', {'status': 'completed'}).applied
    assert redis.get(key) == before
    assert redis.ttl(key) >= 86398


def test_configured_result_is_queryable_until_expiry_then_unknown(redis, monkeypatch):
    monkeypatch.setenv(sync_jobs.COMPLETED_TTL_ENV, '21600')
    monkeypatch.setattr(sync_router, 'admit_sync_job_poll', lambda uid: True)
    job = sync_jobs.create_sync_job('owner', 1, 1)
    assert sync_jobs.finalize_sync_job(
        job['job_id'], {'total_segments': 1, 'failed_segments': 0, 'new_memories': [], 'updated_memories': []}
    )
    key = f'sync_job:{job["job_id"]}'
    assert 21598 <= redis.ttl(key) <= 21600
    app = FastAPI()
    app.include_router(sync_router.router)
    app.dependency_overrides[sync_router.auth.get_current_user_uid] = lambda: 'owner'
    with TestClient(app) as client:
        response = client.get(f'/v2/sync-local-files/{job["job_id"]}')
        assert response.status_code == 200
        assert response.json()['status'] == 'completed'
        # Local fake only: exercise the endpoint's existing unknown-job recovery.
        redis.expire(key, 0)
        assert client.get(f'/v2/sync-local-files/{job["job_id"]}').status_code == 404
