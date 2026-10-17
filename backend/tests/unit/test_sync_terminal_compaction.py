"""Terminal retention must not change WAL acknowledgement or fence semantics."""

import copy
import json
import uuid

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import sync_jobs
from routers import sync as sync_router


@pytest.fixture
def redis(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', client)
    return client


def seed(redis, *, status='processing', owner='1:owner'):
    job = sync_jobs.create_sync_job('owner', 1, 100, content_id='c' * 64)
    ids = [str(uuid.UUID(int=i + 1)) for i in range(100)]
    job.update(
        status=status,
        partial_result={'new_memories': ids, 'updated_memories': [], 'pending_enrichment_ids': ids},
        last_error='earlier attempt failed',
    )
    key = f'sync_job:{job["job_id"]}'
    redis.set(key, json.dumps(job), ex=12345)
    redis.set(f'sync_job_lock:{job["job_id"]}', owner, ex=1800)
    redis.set(f'sync_job_lock_epoch:{job["job_id"]}', 1)
    redis.sadd(f'sync_job_segments:{job["job_id"]}', 'synthetic/path.wav')
    redis.expire(f'sync_job_segments:{job["job_id"]}', 12345)
    redis.set(f'sync_job_once:{job["job_id"]}:usage', '1', ex=86400)
    return job, key


def result(failed):
    return {
        'new_memories': [str(uuid.UUID(int=i + 1)) for i in range(100)],
        'updated_memories': [],
        'total_segments': 100,
        'failed_segments': failed,
        'errors': ['synthetic failure'] if failed else [],
        'stage_timings': {'total_ms': 1234},
        'provider': 'parakeet',
        'model': 'parakeet',
        'outcome': 'upstream_error' if failed else 'success',
        'repeat_failure_key': 'persistent_persistence',
        'repeat_failure_fingerprint': 'a' * 64,
    }


@pytest.mark.parametrize('fenced', [False, True])
@pytest.mark.parametrize('failed,status', [(0, 'completed'), (1, 'partial_failure'), (100, 'failed')])
def test_terminal_compaction_keeps_real_poll_response(redis, monkeypatch, fenced, failed, status):
    job, key = seed(redis)
    final_result = result(failed)
    original_result = copy.deepcopy(final_result)
    _, _, _, updates = sync_jobs._sync_job_finalization_updates(final_result, completed_at=123.0)
    # Baseline is the original terminal document passed through the real route,
    # FastAPI response model and serializer, not a hand-maintained wire fixture.
    old_terminal = {**job, **updates}
    redis.set(key, json.dumps(old_terminal), ex=86400)
    monkeypatch.setattr(sync_router, 'admit_sync_job_poll', lambda uid: True)
    monkeypatch.setattr(sync_router, 'release_sync_content_claim', lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(sync_router.router)
    app.dependency_overrides[sync_router.auth.get_current_user_uid] = lambda: 'owner'
    with TestClient(app) as client:
        before = client.get(f'/v2/sync-local-files/{job["job_id"]}')
        redis.set(key, json.dumps(job), ex=12345)
        if fenced:
            mutation = sync_jobs.fenced_finalize_sync_job(job['job_id'], '1:owner', final_result, now=123.0)
            assert mutation.applied
            finalized = mutation.job
        else:
            finalized = sync_jobs.finalize_sync_job(job['job_id'], final_result)
        after = client.get(f'/v2/sync-local-files/{job["job_id"]}')
    assert before.status_code == after.status_code == 200
    assert before.json() == after.json()
    assert after.json()['status'] == status
    assert final_result == original_result
    assert 'partial_result' not in finalized
    assert 'last_error' not in finalized
    assert 'stage_timings' not in finalized['result']
    assert finalized['result']['repeat_failure_fingerprint'] == 'a' * 64
    assert sync_router._terminal_repeat_failure_kwargs(finalized) == (
        {'failure_key': 'persistent_persistence', 'failure_fingerprint': 'a' * 64} if failed else {}
    )
    assert len(redis.get(key)) < len(json.dumps(old_terminal).encode()) / 2
    assert redis.ttl(key) >= 86398
    assert not redis.exists(f'sync_job_segments:{job["job_id"]}')
    assert redis.get(f'sync_job_lock:{job["job_id"]}') == b'1:owner'
    assert redis.get(f'sync_job_lock_epoch:{job["job_id"]}') == b'1'
    assert redis.get(f'sync_job_once:{job["job_id"]}:usage') == b'1'


@pytest.mark.parametrize('fenced', [False, True])
def test_progress_and_retry_keep_checkpoints(redis, fenced):
    job, key = seed(redis)
    patch = {'status': 'queued', 'last_error': 'retry'}
    if fenced:
        assert sync_jobs.fenced_update_sync_job(job['job_id'], '1:owner', patch).applied
    else:
        assert sync_jobs.update_sync_job(job['job_id'], patch)
    stored = json.loads(redis.get(key))
    assert stored['partial_result'] == job['partial_result']
    assert stored['last_error'] == 'retry'
    assert redis.exists(f'sync_job_segments:{job["job_id"]}')


@pytest.mark.parametrize('owner', ['stale', None])
def test_stale_or_missing_owner_cannot_compact_or_delete(redis, owner):
    job, key = seed(redis)
    before = redis.get(key)
    if owner is None:
        redis.delete(f'sync_job_lock:{job["job_id"]}')
    mutation = sync_jobs.fenced_finalize_sync_job(job['job_id'], owner or '1:owner', result(0))
    assert not mutation.applied
    assert redis.get(key) == before
    assert redis.exists(f'sync_job_segments:{job["job_id"]}')
    assert redis.ttl(key) <= 12345


@pytest.mark.parametrize('fenced', [False, True])
def test_existing_terminal_is_never_rewritten_or_cleaned(redis, fenced):
    job, key = seed(redis, status='completed')
    before = redis.get(key)
    if fenced:
        assert not sync_jobs.fenced_update_sync_job(job['job_id'], '1:owner', {'status': 'queued'}).applied
    else:
        assert sync_jobs.update_sync_job(job['job_id'], {'status': 'failed'}) is None
    assert redis.get(key) == before
    assert redis.exists(f'sync_job_segments:{job["job_id"]}')
    assert redis.ttl(key) <= 12345


@pytest.mark.parametrize('fenced', [False, True])
def test_cleanup_failure_does_not_fail_committed_terminal(redis, monkeypatch, fenced):
    job, key = seed(redis)
    monkeypatch.setattr(redis, 'delete', lambda *args: (_ for _ in ()).throw(ConnectionError('synthetic')))
    if fenced:
        assert sync_jobs.fenced_mark_job_failed(job['job_id'], '1:owner', 'synthetic').applied
    else:
        assert sync_jobs.mark_job_failed(job['job_id'], 'synthetic')
    assert json.loads(redis.get(key))['status'] == 'failed'
    assert redis.ttl(f'sync_job_segments:{job["job_id"]}') > 0


@pytest.mark.parametrize('value', [None, {}, {'outcome': 'superseded'}, {'new_memories': [], 'errors': []}])
def test_compaction_preserves_result_presence_and_empty_arrays(value):
    old = {'job_id': 'job', 'status': 'completed', 'result': value}
    new = copy.deepcopy(old)
    sync_jobs._compact_terminal_job(new)

    def wire(job):
        payload = {key: val for key, val in job.items() if key != 'result'}
        if job.get('result'):
            payload['result'] = job['result']
        return sync_router.SyncJobStatusResponse(**payload).model_dump(exclude_none=True)

    assert wire(old) == wire(new)


@pytest.mark.parametrize('fenced', [False, True])
def test_racing_terminal_winner_is_not_compacted_or_cleaned(redis, monkeypatch, fenced):
    job, key = seed(redis)
    winner = {**job, 'status': 'completed', 'result': {'new_memories': ['winner']}}
    winner_raw = json.dumps(winner).encode()
    original_eval = redis.eval

    def complete_before_cas(script, key_count, *args):
        redis.set(key, winner_raw, ex=12345)
        return original_eval(script, key_count, *args)

    monkeypatch.setattr(redis, 'eval', complete_before_cas)
    if fenced:
        mutation = sync_jobs.fenced_finalize_sync_job(job['job_id'], '1:owner', result(0))
        assert mutation.outcome is sync_jobs.FencedSyncJobMutationOutcome.INVALID_STATE
    else:
        assert sync_jobs.finalize_sync_job(job['job_id'], result(0)) is None
    assert redis.get(key) == winner_raw
    assert redis.exists(f'sync_job_segments:{job["job_id"]}')


def test_cleanup_uses_stage_namespace(redis, monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    job = sync_jobs.create_sync_job('owner', 1, 1)
    segment_key = f'sync_job_segments:{job["job_id"]}'
    redis.sadd(segment_key, 'prod-path')
    redis.sadd(f'dev:{segment_key}', 'dev-path')
    assert sync_jobs.mark_job_completed(job['job_id'], {'new_memories': [], 'updated_memories': []})
    assert not redis.exists(f'dev:{segment_key}')
    assert redis.smembers(segment_key) == {b'prod-path'}
