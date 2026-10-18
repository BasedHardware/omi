"""Status polling must obey the same run ownership as sync workers.

Unlike the route-only tests, these exercise the real Redis reader as well.
The ownership contract is documented in docs/runbooks/sync-two-lane.md.
"""

from __future__ import annotations

import json
import os
import sys
import time
import types
from unittest.mock import MagicMock

# Ensure test encryption key is configured before router imports
os.environ.setdefault('ENCRYPTION_SECRET', '0123456789abcdef0123456789abcdef')
os.environ.setdefault('OMI_ENV_STAGE', 'prod')


# Stub heavy third-party packages not required for status routing tests
class _MockModule(types.ModuleType):
    def __getattr__(self, name):
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


class _StubFinder:
    def find_spec(self, fullname, path, target=None):
        stubs = (
            'deepgram',
            'langchain_google_genai',
            'av',
            'pinecone',
            'opuslib',
            'pydub',
            'stripe',
            'modal',
            'ulid',
            'typesense',
            'pusher',
            'firebase_admin',
        )
        for s in stubs:
            if fullname == s or fullname.startswith(s + '.'):
                mod = _MockModule(fullname)
                mod.__file__ = f'<stub {fullname}>'
                mod.__loader__ = self
                sys.modules[fullname] = mod
                import importlib.machinery

                spec = importlib.machinery.ModuleSpec(fullname, None)
                spec.loader = self
                return spec
        return None

    def create_module(self, spec):
        return sys.modules.get(spec.name)

    def exec_module(self, module):
        pass


if not any(isinstance(finder, _StubFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _StubFinder())

import database._client as db_client

db_client._firestore_client = MagicMock()

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.sync_jobs as sync_jobs
import routers.sync as sync_router


def _install_fake_eval(redis):
    def fake_eval(script, numkeys, *keys_and_args):
        keys = keys_and_args[:numkeys]
        args = keys_and_args[numkeys:]
        if 'tostring(epoch)' in script:
            if redis.get(keys[0]) is not None:
                return [0]
            epoch = redis.incr(keys[1])
            token = f'{epoch}:{args[0]}'
            redis.set(keys[0], token, ex=args[1])
            return [1, token.encode(), str(epoch).encode()]
        elif 'missing_owner' in script:
            owner = redis.get(keys[0])
            if owner is None:
                return [b'missing_owner']
            expected_owner = args[0].encode() if isinstance(args[0], str) else args[0]
            if owner != expected_owner:
                return [b'stale_owner']
            raw_job = redis.get(keys[1])
            if raw_job is None:
                return [b'missing_job']
            expected_job = args[1].encode() if isinstance(args[1], str) else args[1]
            if raw_job != expected_job:
                return [b'conflict', raw_job]
            next_raw = args[2].encode() if isinstance(args[2], str) else args[2]
            redis.set(keys[1], next_raw, ex=int(args[3]))
            return [b'applied', next_raw]
        elif 'applied' in script:
            raw = redis.get(keys[0])
            if raw is None:
                return [b'missing_job']
            expected = args[0].encode() if isinstance(args[0], str) else args[0]
            if raw != expected:
                return [b'conflict', raw]
            next_raw = args[1].encode() if isinstance(args[1], str) else args[1]
            redis.set(keys[0], next_raw, ex=int(args[2]))
            return [b'applied', next_raw]
        elif 'del' in script:
            current = redis.get(keys[0])
            expected = args[0].encode() if isinstance(args[0], str) else args[0]
            if current == expected:
                return redis.delete(keys[0])
            return 0
        return [0]

    redis.eval = fake_eval


@pytest.fixture(autouse=True)
def legacy_production_keys(monkeypatch):
    # These ownership tests seed the existing production Redis key names.
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')


@pytest.fixture
def status_client(monkeypatch):
    redis = fakeredis.FakeRedis()
    _install_fake_eval(redis)
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setenv('SYNC_LEDGER_FENCE_MODE', 'active')
    monkeypatch.setattr(
        sync_router.sync_dead_letters,
        'get_dead_letter',
        lambda job_id: {'job_id': job_id, 'uid': 'owner', 'status': 'dead_letter'},
    )
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


def _seed_sequenced_backfill_job(
    redis,
    *,
    job_id='job-seq-1',
    status='processing',
    stale_delta=1000,
):
    job = {
        'job_id': job_id,
        'uid': 'owner',
        'status': status,
        'lane': 'backfill',
        'dispatch_mode': 'sequenced',
        'created_at': time.time() - (stale_delta + 1000),
        'updated_at': time.time() - stale_delta,
        'total_segments': 1,
    }
    key = f'{sync_jobs.JOB_KEY_PREFIX}{job_id}'
    redis.set(key, json.dumps(job), ex=sync_jobs.JOB_TTL_SECONDS)
    return key


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
    _install_fake_eval(redis)
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


def test_poll_sequenced_stale_owned_job_releases_sequencer(status_client, monkeypatch):
    """Owned stale sequenced jobs must release ownership with stale_failed and kick."""
    client, redis = status_client
    monkeypatch.setenv('SYNC_SEQUENCED_STALE_SECONDS', '600')
    _seed_sequenced_backfill_job(redis, job_id='job-seq-owned')

    mock_finish = MagicMock()
    mock_retire = MagicMock()
    mock_kick = MagicMock()

    monkeypatch.setattr(sync_router.uid_sequencer, 'production_stage', lambda: True)
    monkeypatch.setattr(
        sync_router.sync_backfill_sequencer,
        'get_owner',
        lambda uid: {'active_job_id': 'job-seq-owned', 'active_epoch': 11},
    )
    monkeypatch.setattr(sync_router.sync_backfill_sequencer, 'finish_job', mock_finish)
    monkeypatch.setattr(sync_router.sync_backfill_sequencer, 'retire_expired', mock_retire)
    monkeypatch.setattr(sync_router.uid_sequencer, 'kick', mock_kick)

    response = client.get('/v2/sync-local-files/job-seq-owned')

    assert response.status_code == 200
    assert response.json()['status'] == 'failed'
    mock_finish.assert_called_once_with('owner', 'job-seq-owned', 11, 'stale_failed')
    mock_retire.assert_not_called()
    mock_kick.assert_called_once_with('owner')


def test_poll_sequenced_stale_unowned_job_retires_expired(status_client, monkeypatch):
    """Unowned/expired stale sequenced jobs must retire expired pending records and kick."""
    client, redis = status_client
    monkeypatch.setenv('SYNC_SEQUENCED_STALE_SECONDS', '600')
    _seed_sequenced_backfill_job(redis, job_id='job-seq-unowned')

    mock_finish = MagicMock()
    mock_retire = MagicMock()
    mock_kick = MagicMock()

    monkeypatch.setattr(sync_router.uid_sequencer, 'production_stage', lambda: True)
    monkeypatch.setattr(
        sync_router.sync_backfill_sequencer,
        'get_owner',
        lambda uid: {'active_job_id': 'other-job', 'active_epoch': 12},
    )
    monkeypatch.setattr(sync_router.sync_backfill_sequencer, 'finish_job', mock_finish)
    monkeypatch.setattr(sync_router.sync_backfill_sequencer, 'retire_expired', mock_retire)
    monkeypatch.setattr(sync_router.uid_sequencer, 'kick', mock_kick)

    response = client.get('/v2/sync-local-files/job-seq-unowned')

    assert response.status_code == 200
    assert response.json()['status'] == 'failed'
    mock_retire.assert_called_once_with('owner', 'job-seq-unowned')
    mock_finish.assert_not_called()
    mock_kick.assert_called_once_with('owner')


def test_poll_sequenced_stale_sequencer_exception_does_not_crash_poll(status_client, monkeypatch):
    """Failure during sequencer release must log a warning without crashing client polling."""
    client, redis = status_client
    monkeypatch.setenv('SYNC_SEQUENCED_STALE_SECONDS', '600')
    _seed_sequenced_backfill_job(redis, job_id='job-seq-err')

    def _broken_get_owner(uid):
        raise RuntimeError('Firestore transient error')

    monkeypatch.setattr(sync_router.uid_sequencer, 'production_stage', lambda: True)
    monkeypatch.setattr(sync_router.sync_backfill_sequencer, 'get_owner', _broken_get_owner)

    response = client.get('/v2/sync-local-files/job-seq-err')

    assert response.status_code == 200
    assert response.json()['status'] == 'failed'


def test_poll_sequenced_stale_non_production_stage_bypasses_sequencer(status_client, monkeypatch):
    """Non-production environments must skip sequencer releases safely."""
    client, redis = status_client
    monkeypatch.setenv('SYNC_SEQUENCED_STALE_SECONDS', '600')
    _seed_sequenced_backfill_job(redis, job_id='job-seq-dev')

    mock_owner = MagicMock()
    mock_kick = MagicMock()

    monkeypatch.setattr(sync_router.uid_sequencer, 'production_stage', lambda: False)
    monkeypatch.setattr(sync_router.sync_backfill_sequencer, 'get_owner', mock_owner)
    monkeypatch.setattr(sync_router.uid_sequencer, 'kick', mock_kick)

    response = client.get('/v2/sync-local-files/job-seq-dev')

    assert response.status_code == 200
    assert response.json()['status'] == 'failed'
    mock_owner.assert_not_called()
    mock_kick.assert_not_called()
