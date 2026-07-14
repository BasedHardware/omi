"""
Tests for Cloud Tasks dispatch of the v2 sync pipeline.

Covers the new primitives in database/sync_jobs.py (run lock, queued-reset,
processed-segment ledger, metering once-guards), the OIDC verification in
utils/cloud_tasks.py, and the structural contract of the /v2/sync-jobs/run
handler in routers/sync.py.
"""

import asyncio
import hashlib
import json
import os
import sys
import time
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', '..')


def _load_module_with_stubs(relative_path, module_name, stubs):
    """Load a backend module with selected imports stubbed in sys.modules."""
    import importlib.util

    saved = {}
    for mod, mock in stubs.items():
        saved[mod] = sys.modules.get(mod)
        sys.modules[mod] = mock
    try:
        spec = importlib.util.spec_from_file_location(module_name, os.path.join(BACKEND_DIR, relative_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for mod, original in saved.items():
            if original is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = original


def _load_sync_jobs(redis_client=None):
    mock_redis = MagicMock() if redis_client is None else redis_client
    if redis_client is None:
        # Most primitive tests use a lightweight Redis mock. Model the new
        # tokenless raw-CAS boundary here while leaving all other Lua scripts
        # configurable through their explicit ``return_value`` fixtures.
        def _default_eval(script, key_count, *args):
            if key_count == 1 and 'raw_job ~= ARGV[1]' in script:
                _key, expected_raw, next_raw, _ttl_seconds = args
                current_raw = mock_redis.get.return_value
                if not current_raw:
                    return [b'missing_job']
                current_text = current_raw.decode('utf-8') if isinstance(current_raw, bytes) else str(current_raw)
                if current_text != expected_raw:
                    return [b'conflict', current_raw]
                return [b'applied', next_raw]
            return mock_redis.eval.return_value

        mock_redis.eval.side_effect = _default_eval
    module = _load_module_with_stubs(
        os.path.join('database', 'sync_jobs.py'),
        'sync_jobs_under_test',
        {
            'database': MagicMock(),
            'database.redis_db': MagicMock(r=mock_redis),
        },
    )
    return module, mock_redis


def _seed_fenced_job(redis_client, sync_jobs, job_id, job, *, owner=None, ttl_seconds=12_345):
    redis_client.set(
        f'{sync_jobs.JOB_KEY_PREFIX}{job_id}',
        json.dumps(job, separators=(',', ':')),
        ex=ttl_seconds,
    )
    if owner is not None:
        redis_client.set(
            f'{sync_jobs.RUN_LOCK_KEY_PREFIX}{job_id}',
            owner,
            ex=sync_jobs.RUN_LOCK_TTL_SECONDS,
        )


class _ConflictInjectingRedis(fakeredis.FakeRedis):
    """Runs a competing raw write immediately before selected CAS attempts."""

    def __init__(self, conflicts):
        super().__init__()
        self.conflicts_remaining = conflicts
        self.eval_calls = 0

    def eval(self, script, numkeys, *args, **kwargs):
        self.eval_calls += 1
        if self.conflicts_remaining:
            self.conflicts_remaining -= 1
            job_key = args[1]
            raw_job = super().get(job_key)
            if raw_job is not None:
                job = json.loads(raw_job)
                job['concurrent_writes'] = job.get('concurrent_writes', 0) + 1
                super().set(job_key, json.dumps(job, separators=(',', ':')), ex=12_345)
        return super().eval(script, numkeys, *args, **kwargs)


# ---------------------------------------------------------------------------
# Run lock
# ---------------------------------------------------------------------------


class TestJobRunLock:
    def test_acquire_returns_token_when_free(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.set.return_value = True
        token = sync_jobs.try_acquire_job_run_lock('job-1')
        assert token
        args, kwargs = mock_redis.set.call_args
        assert args[0] == 'sync_job_lock:job-1'
        assert kwargs['nx'] is True
        assert kwargs['ex'] == sync_jobs.RUN_LOCK_TTL_SECONDS

    def test_acquire_returns_none_when_held(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.set.return_value = None
        assert sync_jobs.try_acquire_job_run_lock('job-1') is None

    def test_acquire_fails_closed_on_redis_error(self):
        """A Redis outage must block execution, never allow duplicate runs."""
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.set.side_effect = ConnectionError('redis down')
        with pytest.raises(ConnectionError):
            sync_jobs.try_acquire_job_run_lock('job-1')

    def test_sync_acquire_issues_an_epoch_bearing_token(self):
        """Sync workers need a monotonic epoch, unlike generic task locks."""
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.eval.return_value = [b'1', b'7:uuid-token', b'7']

        token = sync_jobs.try_acquire_sync_job_run_lock('job-1')

        assert token == '7:uuid-token'
        assert sync_jobs.get_sync_job_run_lock_epoch(token) == 7
        args = mock_redis.eval.call_args.args
        assert args[1] == 2
        assert args[2:4] == ('sync_job_lock:job-1', 'sync_job_lock_epoch:job-1')

    def test_sync_acquire_returns_none_when_held(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.eval.return_value = [b'0']

        assert sync_jobs.try_acquire_sync_job_run_lock('job-1') is None

    def test_release_is_compare_and_delete(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        sync_jobs.release_job_run_lock('job-1', 'tok')
        args = mock_redis.eval.call_args[0]
        assert args[1] == 1
        assert args[2] == 'sync_job_lock:job-1'
        assert args[3] == 'tok'

    def test_release_swallows_redis_errors(self):
        """Failed release just lets the TTL expire — must not raise."""
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.eval.side_effect = ConnectionError('redis down')
        sync_jobs.release_job_run_lock('job-1', 'tok')

    def test_renew_compare_and_expire_succeeds_for_owner(self):
        """A renewal must atomically prove ownership before extending the TTL."""
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.eval.return_value = 1

        assert sync_jobs.renew_job_run_lock('job-1', 'tok') is True

        args = mock_redis.eval.call_args[0]
        assert args[1] == 1
        assert args[2] == 'sync_job_lock:job-1'
        assert args[3] == 'tok'
        assert args[4] == sync_jobs.RUN_LOCK_TTL_SECONDS
        assert 'expire' in args[0]

    def test_renew_does_not_extend_another_owner(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.eval.return_value = 0

        assert sync_jobs.renew_job_run_lock('job-1', 'stale-token') is False

    def test_renew_surfaces_redis_error(self):
        """A caller must not mistake an unavailable lease store for a renewal."""
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.eval.side_effect = ConnectionError('redis down')

        with pytest.raises(ConnectionError):
            sync_jobs.renew_job_run_lock('job-1', 'tok')

    def test_lock_ttl_exceeds_handler_timeout(self):
        """Invariant: a run-lock can never expire under a live run (request
        timeout HTTP_SYNC_JOBS_RUN_TIMEOUT=1500 < lock TTL)."""
        sync_jobs, _ = _load_sync_jobs()
        assert sync_jobs.RUN_LOCK_TTL_SECONDS > 1500
        assert 0 < sync_jobs.RUN_LOCK_HEARTBEAT_SECONDS < sync_jobs.STALE_THRESHOLD_SECONDS
        assert sync_jobs.STALE_THRESHOLD_SECONDS < sync_jobs.RUN_LOCK_TTL_SECONDS
        assert 0 < sync_jobs.RUN_LOCK_RENEWAL_SAFETY_SECONDS < sync_jobs.RUN_LOCK_TTL_SECONDS


# ---------------------------------------------------------------------------
# Token-fenced job mutation
# ---------------------------------------------------------------------------


class TestFencedJobMutations:
    def test_update_uses_raw_cas_and_refreshes_normal_job_retention(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.get.return_value = b'{"job_id":"job-1","status":"queued"}'
        mock_redis.eval.return_value = [b'applied', b'{"job_id":"job-1","status":"processing"}']

        mutation = sync_jobs.fenced_update_sync_job('job-1', 'owner-a', {'status': 'processing'}, now=123.0)

        assert mutation.applied is True
        assert mutation.job == {'job_id': 'job-1', 'status': 'processing'}
        script, key_count, lock_key, job_key, token, expected_raw, next_raw, ttl_seconds = (
            mock_redis.eval.call_args.args
        )
        assert key_count == 2
        assert lock_key == 'sync_job_lock:job-1'
        assert job_key == 'sync_job:job-1'
        assert token == 'owner-a'
        assert expected_raw == '{"job_id":"job-1","status":"queued"}'
        assert json.loads(next_raw) == {'job_id': 'job-1', 'status': 'processing', 'updated_at': 123.0}
        assert ttl_seconds == sync_jobs.JOB_TTL_SECONDS
        assert "'EX'" in script
        assert 'cjson' not in script.lower()

    def test_current_owner_cannot_update_an_already_terminal_job(self):
        """Cleanup after a terminal CAS cannot resurrect that job, even with its token."""
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'job-1',
            {'job_id': 'job-1', 'status': 'partial_failure', 'result': {'failed_segments': 1}},
            owner='owner-a',
        )
        before = redis_client.get('sync_job:job-1')

        mutation = sync_jobs.fenced_update_sync_job(
            'job-1', 'owner-a', {'status': 'queued', 'last_error': 'must not reset'}, now=123.0
        )

        assert mutation.outcome is sync_jobs.FencedSyncJobMutationOutcome.INVALID_STATE
        assert mutation.applied is False
        assert redis_client.get('sync_job:job-1') == before

    def test_real_raw_cas_preserves_nested_empty_arrays_and_refreshes_ttl(self):
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        nested_empty_arrays = {
            'top_level': [],
            'nested': {'inner': [], 'mixed': [[], {'also_empty': []}]},
        }
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'job-1',
            {'job_id': 'job-1', 'status': 'queued', 'result': nested_empty_arrays},
            owner='owner-a',
            ttl_seconds=10,
        )

        mutation = sync_jobs.fenced_update_sync_job('job-1', 'owner-a', {'status': 'processing'}, now=123.0)

        assert mutation.applied is True
        stored = json.loads(redis_client.get('sync_job:job-1'))
        assert stored['result'] == nested_empty_arrays
        assert redis_client.ttl('sync_job:job-1') >= sync_jobs.JOB_TTL_SECONDS - 1
        assert 'cjson' not in sync_jobs._FENCED_JOB_MUTATION_SCRIPT.lower()

    def test_concurrent_raw_write_is_rebased_before_fenced_update_applies(self):
        redis_client = _ConflictInjectingRedis(conflicts=1)
        sync_jobs, _ = _load_sync_jobs(redis_client)
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'job-1',
            {'job_id': 'job-1', 'status': 'queued', 'result': {'segments': []}},
            owner='owner-a',
        )

        mutation = sync_jobs.fenced_update_sync_job('job-1', 'owner-a', {'status': 'processing'}, now=124.0)

        assert mutation.applied is True
        assert mutation.job['concurrent_writes'] == 1
        assert mutation.job['status'] == 'processing'
        assert mutation.job['result']['segments'] == []
        assert redis_client.eval_calls == 2

    def test_conflicts_are_bounded_and_return_conflict_without_publishing_update(self):
        redis_client = _ConflictInjectingRedis(conflicts=3)
        sync_jobs, _ = _load_sync_jobs(redis_client)
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'job-1',
            {'job_id': 'job-1', 'status': 'queued'},
            owner='owner-a',
        )

        mutation = sync_jobs.fenced_update_sync_job('job-1', 'owner-a', {'status': 'processing'}, now=125.0)

        assert mutation.outcome is sync_jobs.FencedSyncJobMutationOutcome.CONFLICT
        assert mutation.applied is False
        assert redis_client.eval_calls == sync_jobs._FENCED_JOB_MUTATION_MAX_RETRIES
        assert json.loads(redis_client.get('sync_job:job-1'))['status'] == 'queued'

    def test_paused_old_worker_cannot_overwrite_new_owner_terminal_job(self):
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        job_id = 'job-1'
        job_key = f'{sync_jobs.JOB_KEY_PREFIX}{job_id}'
        lock_key = f'{sync_jobs.RUN_LOCK_KEY_PREFIX}{job_id}'
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            job_id,
            {'job_id': job_id, 'status': 'queued', 'lane': 'fresh', 'result': None},
            owner='owner-a',
        )

        processing = sync_jobs.fenced_mark_job_processing(job_id, 'owner-a', now=100.0)
        assert processing.applied is True
        assert processing.job['status'] == 'processing'
        partial = sync_jobs.fenced_update_sync_job(
            job_id, 'owner-a', {'partial_result': {'successful_segments': 1}}, now=101.0
        )
        assert partial.applied is True

        # A's lease expires; B acquires a new token and terminalizes the job.
        redis_client.set(lock_key, 'owner-b', ex=sync_jobs.RUN_LOCK_TTL_SECONDS)
        finalized = sync_jobs.fenced_finalize_sync_job(
            job_id,
            'owner-b',
            {'total_segments': 1, 'failed_segments': 0, 'provider': 'deepgram', 'model': 'nova-3'},
            now=102.0,
        )
        assert finalized.applied is True
        assert finalized.job['status'] == 'completed'
        terminal_json = redis_client.get(job_key)
        terminal_ttl = redis_client.ttl(job_key)

        # A resumes after B's terminal write. Every worker-driven transition
        # must reject A before it can mutate state or trigger downstream work.
        stale_mutations = (
            lambda: sync_jobs.fenced_mark_job_processing(job_id, 'owner-a', now=103.0),
            lambda: sync_jobs.fenced_update_sync_job(job_id, 'owner-a', {'partial_result': {}}, now=104.0),
            lambda: sync_jobs.fenced_finalize_sync_job(
                job_id, 'owner-a', {'total_segments': 1, 'failed_segments': 1}, now=105.0
            ),
            lambda: sync_jobs.fenced_mark_job_failed(job_id, 'owner-a', 'old worker failed', now=106.0),
            lambda: sync_jobs.fenced_mark_job_queued_for_retry(job_id, 'owner-a', 2, 'retry', now=107.0),
            lambda: sync_jobs.add_processed_segment_if_run_owner(job_id, 'owner-a', 'syncing/u/job-1/seg_1.wav'),
        )
        for index, mutate in enumerate(stale_mutations):
            mutation = mutate()
            expected_outcome = (
                sync_jobs.FencedSyncJobMutationOutcome.INVALID_STATE
                if index < len(stale_mutations) - 1
                else sync_jobs.FencedSyncJobMutationOutcome.STALE_OWNER
            )
            assert mutation.outcome is expected_outcome
            assert mutation.applied is False
            assert redis_client.get(job_key) == terminal_json
            assert redis_client.ttl(job_key) == terminal_ttl
        assert redis_client.smembers(f'{sync_jobs.PROCESSED_SEGMENTS_KEY_PREFIX}{job_id}') == set()

    def test_fenced_failed_and_queued_retry_primitives_publish_while_owner_matches(self):
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'failed-job',
            {'job_id': 'failed-job', 'status': 'processing'},
            owner='owner-a',
            ttl_seconds=4_321,
        )

        failed = sync_jobs.fenced_mark_job_failed(
            'failed-job',
            'owner-a',
            'upstream unavailable',
            reason_code='upstream_error',
            retry_after=30,
            now=200.0,
        )
        assert failed.applied is True
        assert failed.job == {
            'job_id': 'failed-job',
            'status': 'failed',
            'completed_at': 200.0,
            'error': 'upstream unavailable',
            'reason_code': 'upstream_error',
            'retry_after': 30,
            'updated_at': 200.0,
        }
        assert redis_client.ttl('sync_job:failed-job') >= sync_jobs.JOB_TTL_SECONDS - 1

        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'retry-job',
            {'job_id': 'retry-job', 'status': 'processing'},
            owner='owner-a',
            ttl_seconds=6_543,
        )
        queued = sync_jobs.fenced_mark_job_queued_for_retry('retry-job', 'owner-a', 2, 'temporary outage', now=201.0)
        assert queued.applied is True
        assert queued.job == {
            'job_id': 'retry-job',
            'status': 'queued',
            'attempt': 2,
            'last_error': 'temporary outage',
            'updated_at': 201.0,
        }
        assert redis_client.ttl('sync_job:retry-job') >= sync_jobs.JOB_TTL_SECONDS - 1

    def test_fenced_update_reports_missing_owner_and_missing_job_without_writing(self):
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'job-without-owner',
            {'job_id': 'job-without-owner', 'status': 'processing'},
        )
        before = redis_client.get('sync_job:job-without-owner')

        missing_owner = sync_jobs.fenced_update_sync_job(
            'job-without-owner', 'owner-a', {'status': 'failed'}, now=300.0
        )
        assert missing_owner.outcome is sync_jobs.FencedSyncJobMutationOutcome.MISSING_OWNER
        assert redis_client.get('sync_job:job-without-owner') == before

        redis_client.set('sync_job_lock:missing-job', 'owner-a', ex=sync_jobs.RUN_LOCK_TTL_SECONDS)
        missing_job = sync_jobs.fenced_update_sync_job('missing-job', 'owner-a', {'status': 'failed'}, now=301.0)
        assert missing_job.outcome is sync_jobs.FencedSyncJobMutationOutcome.MISSING_JOB

    def test_processed_segment_marker_requires_current_owner(self):
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            'job-1',
            {'job_id': 'job-1', 'status': 'processing'},
            owner='owner-a',
        )

        applied = sync_jobs.add_processed_segment_if_run_owner('job-1', 'owner-a', 'segments/one.wav')
        assert applied.applied is True
        assert redis_client.smembers('sync_job_segments:job-1') == {b'segments/one.wav'}
        assert redis_client.ttl('sync_job_segments:job-1') >= sync_jobs.JOB_TTL_SECONDS - 1

        redis_client.set('sync_job_lock:job-1', 'owner-b', ex=sync_jobs.RUN_LOCK_TTL_SECONDS)
        stale = sync_jobs.add_processed_segment_if_run_owner('job-1', 'owner-a', 'segments/two.wav')
        assert stale.outcome is sync_jobs.FencedSyncJobMutationOutcome.STALE_OWNER
        assert redis_client.smembers('sync_job_segments:job-1') == {b'segments/one.wav'}


# ---------------------------------------------------------------------------
# Legacy raw-CAS terminal monotonicity
# ---------------------------------------------------------------------------


class TestLegacyJobMutations:
    def test_late_legacy_worker_cannot_resurrect_partial_failure_as_completed(self):
        """The mixed-revision path is monotone even without an epoch token."""
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        job_id = 'legacy-job'
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            job_id,
            {
                'job_id': job_id,
                'status': 'processing',
                'ledger_fence_mode': 'legacy',
                'result': None,
                'failed_segments': 0,
            },
        )

        partial = sync_jobs.finalize_sync_job(
            job_id,
            {
                'failed_segments': 1,
                'total_segments': 2,
                'errors': ['upstream_timeout'],
                'outcome': 'upstream_error',
            },
        )
        assert partial is not None
        assert partial['status'] == 'partial_failure'
        terminal_json = redis_client.get(f'{sync_jobs.JOB_KEY_PREFIX}{job_id}')

        late_completed = sync_jobs.finalize_sync_job(
            job_id,
            {'failed_segments': 0, 'total_segments': 2, 'errors': [], 'outcome': 'success'},
        )
        late_processing = sync_jobs.mark_job_processing(job_id)
        late_retry = sync_jobs.mark_job_queued_for_retry(job_id, 2, 'old worker retry')

        assert late_completed is None
        assert late_processing is None
        assert late_retry is None
        assert redis_client.get(f'{sync_jobs.JOB_KEY_PREFIX}{job_id}') == terminal_json
        assert sync_jobs.get_sync_job(job_id)['status'] == 'partial_failure'


# ---------------------------------------------------------------------------
# Queued-reset, ledger, once-guards
# ---------------------------------------------------------------------------


class TestRetryPrimitives:
    def test_mark_job_queued_for_retry_resets_status(self):
        import json

        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.get.return_value = json.dumps({'job_id': 'job-1', 'status': 'processing'})
        sync_jobs.mark_job_queued_for_retry('job-1', attempt=2, error='boom')
        written = json.loads(mock_redis.eval.call_args.args[4])
        assert written['status'] == 'queued'
        assert written['attempt'] == 2
        assert written['last_error'] == 'boom'

    def test_terminal_statuses(self):
        sync_jobs, _ = _load_sync_jobs()
        assert set(sync_jobs.TERMINAL_STATUSES) == {'completed', 'partial_failure', 'failed'}

    def test_processed_segment_ledger_roundtrip(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        sync_jobs.add_processed_segment('job-1', 'syncing/u/job-1/seg_1.wav')
        mock_redis.sadd.assert_called_once_with('sync_job_segments:job-1', 'syncing/u/job-1/seg_1.wav')
        mock_redis.expire.assert_called_once()

        mock_redis.smembers.return_value = {b'a.wav', 'b.wav'}
        assert sync_jobs.get_processed_segments('job-1') == {'a.wav', 'b.wav'}

    def test_ledger_fails_open(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.sadd.side_effect = ConnectionError('redis down')
        sync_jobs.add_processed_segment('job-1', 'x.wav')  # must not raise
        mock_redis.smembers.side_effect = ConnectionError('redis down')
        assert sync_jobs.get_processed_segments('job-1') == set()

    def test_try_mark_once_first_and_second_call(self):
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.set.return_value = True
        assert sync_jobs.try_mark_once('job-1', 'speech_ms') is True
        mock_redis.set.return_value = None
        assert sync_jobs.try_mark_once('job-1', 'speech_ms') is False

    def test_try_mark_once_fails_open(self):
        """Metering guard prefers occasional double-count over never counting."""
        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.set.side_effect = ConnectionError('redis down')
        assert sync_jobs.try_mark_once('job-1', 'usage') is True


# ---------------------------------------------------------------------------
# OIDC verification (utils/cloud_tasks.py)
# ---------------------------------------------------------------------------


def _load_cloud_tasks():
    tasks_v2_mock = MagicMock()
    return _load_module_with_stubs(
        os.path.join('utils', 'cloud_tasks.py'),
        'cloud_tasks_under_test',
        {'google.cloud.tasks_v2': tasks_v2_mock},
    )


def _request_with(headers: dict):
    request = MagicMock()
    request.headers = headers
    return request


OIDC_ENV = {
    'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/v2/sync-jobs/run',
    'SYNC_TASKS_INVOKER_SA': 'invoker@project.iam.gserviceaccount.com',
}


class TestVerifyCloudTasksOidc:
    def test_env_unset_fails_closed(self):
        """Services not configured as task targets must reject all task traffic."""
        from fastapi import HTTPException

        cloud_tasks = _load_cloud_tasks()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SYNC_TASKS_HANDLER_URL', None)
            os.environ.pop('SYNC_TASKS_OIDC_AUDIENCE', None)
            os.environ.pop('SYNC_TASKS_INVOKER_SA', None)
            with pytest.raises(HTTPException) as exc:
                cloud_tasks.verify_cloud_tasks_oidc(_request_with({'authorization': 'Bearer x'}))
            assert exc.value.status_code == 403

    def test_missing_bearer_rejected(self):
        from fastapi import HTTPException

        cloud_tasks = _load_cloud_tasks()
        with patch.dict(os.environ, OIDC_ENV):
            with pytest.raises(HTTPException) as exc:
                cloud_tasks.verify_cloud_tasks_oidc(_request_with({}))
            assert exc.value.status_code == 403

    def test_invalid_token_rejected(self):
        from fastapi import HTTPException

        cloud_tasks = _load_cloud_tasks()
        with patch.dict(os.environ, OIDC_ENV):
            with patch.object(cloud_tasks.id_token, 'verify_oauth2_token', side_effect=ValueError('bad')):
                with pytest.raises(HTTPException) as exc:
                    cloud_tasks.verify_cloud_tasks_oidc(_request_with({'authorization': 'Bearer bad'}))
                assert exc.value.status_code == 403

    def test_wrong_identity_rejected(self):
        from fastapi import HTTPException

        cloud_tasks = _load_cloud_tasks()
        claims = {'email': 'attacker@project.iam.gserviceaccount.com', 'email_verified': True}
        with patch.dict(os.environ, OIDC_ENV):
            with patch.object(cloud_tasks.id_token, 'verify_oauth2_token', return_value=claims):
                with pytest.raises(HTTPException) as exc:
                    cloud_tasks.verify_cloud_tasks_oidc(_request_with({'authorization': 'Bearer t'}))
                assert exc.value.status_code == 403

    def test_valid_token_returns_retry_count(self):
        cloud_tasks = _load_cloud_tasks()
        claims = {'email': OIDC_ENV['SYNC_TASKS_INVOKER_SA'], 'email_verified': True}
        headers = {'authorization': 'Bearer t', 'x-cloudtasks-taskretrycount': '3'}
        with patch.dict(os.environ, OIDC_ENV):
            with patch.object(cloud_tasks.id_token, 'verify_oauth2_token', return_value=claims) as verify:
                assert cloud_tasks.verify_cloud_tasks_oidc(_request_with(headers)) == 3
                assert verify.call_args.kwargs['audience'] == OIDC_ENV['SYNC_TASKS_HANDLER_URL']

    def test_enqueue_requires_complete_env(self):
        cloud_tasks = _load_cloud_tasks()
        with patch.dict(os.environ, {}, clear=False):
            for var in ('SYNC_TASKS_PROJECT', 'SYNC_TASKS_LOCATION', 'SYNC_TASKS_QUEUE'):
                os.environ.pop(var, None)
            with pytest.raises(RuntimeError):
                cloud_tasks.enqueue_sync_job({'job_id': 'j'})

    def test_backfill_uses_dedicated_queue_handler_and_audience(self):
        cloud_tasks = _load_cloud_tasks()
        env = {
            'SYNC_TASKS_QUEUE': 'sync-jobs',
            'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
        }
        with patch.dict(os.environ, env), patch.object(cloud_tasks, '_enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job({'job_id': 'job-1', 'lane': 'backfill'})

        enqueue.assert_called_once_with(
            'sync-backfill',
            'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
            'job-1',
            {'job_id': 'job-1', 'lane': 'backfill'},
            audience='https://backend-sync-backfill.example.com/v2/sync-jobs/run',
        )

    def test_enqueue_account_deletion_task_is_named_by_job_id(self):
        cloud_tasks = _load_cloud_tasks()
        env = {
            'SYNC_TASKS_PROJECT': 'proj',
            'SYNC_TASKS_LOCATION': 'us-central1',
            'ACCOUNT_DELETION_TASKS_QUEUE': 'account-delete',
            'ACCOUNT_DELETION_HANDLER_URL': 'https://backend-sync.example.com/v1/users/account-deletion-wipes/run',
            'SYNC_TASKS_INVOKER_SA': 'invoker@proj.iam.gserviceaccount.com',
        }
        job_hash = hashlib.sha256(b'job-1').hexdigest()[:32]
        task_id = f'account-delete-{job_hash}-abc123'
        with patch.dict(os.environ, env), patch.object(cloud_tasks, '_enqueue_named_task') as enqueue, patch.object(
            cloud_tasks.uuid, 'uuid4', return_value=MagicMock(hex='abc123')
        ):
            cloud_tasks.enqueue_account_deletion_wipe('job-1')
        enqueue.assert_called_once_with(
            'account-delete',
            'https://backend-sync.example.com/v1/users/account-deletion-wipes/run',
            task_id,
            {'job_id': 'job-1'},
            audience='https://backend-sync.example.com/v1/users/account-deletion-wipes/run',
        )

    def test_account_deletion_oidc_verification_uses_its_handler_audience(self):
        cloud_tasks = _load_cloud_tasks()
        env = {
            'SYNC_TASKS_INVOKER_SA': 'invoker@project.iam.gserviceaccount.com',
            'ACCOUNT_DELETION_HANDLER_URL': 'https://backend-sync.example.com/v1/users/account-deletion-wipes/run',
        }
        claims = {'email': env['SYNC_TASKS_INVOKER_SA'], 'email_verified': True}

        with patch.dict(os.environ, env), patch.object(
            cloud_tasks.id_token, 'verify_oauth2_token', return_value=claims
        ) as verify:
            assert cloud_tasks.verify_account_deletion_cloud_tasks_oidc(
                _request_with({'authorization': 'Bearer t'})
            ) == cloud_tasks.AccountDeletionTaskAuthentication(retry_count=0, audience='account_deletion')

        assert verify.call_args.kwargs['audience'] == env['ACCOUNT_DELETION_HANDLER_URL']

    def test_account_deletion_oidc_verification_accepts_only_the_legacy_sync_audience_as_compatibility(self):
        cloud_tasks = _load_cloud_tasks()
        env = {
            'SYNC_TASKS_INVOKER_SA': 'invoker@project.iam.gserviceaccount.com',
            'SYNC_TASKS_OIDC_AUDIENCE': 'https://backend-sync.example.com/v2/sync-jobs/run',
            'ACCOUNT_DELETION_HANDLER_URL': 'https://backend-sync.example.com/v1/users/account-deletion-wipes/run',
        }
        claims = {'email': env['SYNC_TASKS_INVOKER_SA'], 'email_verified': True}

        with patch.dict(os.environ, env), patch.object(
            cloud_tasks.id_token, 'verify_oauth2_token', side_effect=[ValueError('wrong audience'), claims]
        ) as verify:
            assert cloud_tasks.verify_account_deletion_cloud_tasks_oidc(
                _request_with({'authorization': 'Bearer t'})
            ) == cloud_tasks.AccountDeletionTaskAuthentication(retry_count=0, audience='legacy_sync')

        assert [call.kwargs['audience'] for call in verify.call_args_list] == [
            env['ACCOUNT_DELETION_HANDLER_URL'],
            env['SYNC_TASKS_OIDC_AUDIENCE'],
        ]

    def test_account_deletion_dispatch_flag_default_inline(self):
        cloud_tasks = _load_cloud_tasks()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ACCOUNT_DELETION_DISPATCH_MODE', None)
            assert cloud_tasks.is_account_deletion_dispatch_enabled() is False
        with patch.dict(os.environ, {'ACCOUNT_DELETION_DISPATCH_MODE': 'cloud_tasks'}):
            assert cloud_tasks.is_account_deletion_dispatch_enabled() is True

    def test_account_deletion_startup_guard_rejects_inline_or_incomplete_prod_config(self):
        cloud_tasks = _load_cloud_tasks()
        complete_prod_env = {
            'OMI_ENV_STAGE': 'prod',
            'ACCOUNT_DELETION_DISPATCH_MODE': 'cloud_tasks',
            'SYNC_TASKS_PROJECT': 'proj',
            'SYNC_TASKS_LOCATION': 'us-central1',
            'SYNC_TASKS_INVOKER_SA': 'invoker@proj.iam.gserviceaccount.com',
            'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/v2/sync-jobs/run',
            'ACCOUNT_DELETION_TASKS_QUEUE': 'account-deletion',
            'ACCOUNT_DELETION_HANDLER_URL': 'https://backend-sync.example.com/v1/users/account-deletion-wipes/run',
        }

        with patch.dict(os.environ, complete_prod_env, clear=True):
            cloud_tasks.validate_account_deletion_dispatch_configuration()

        with patch.dict(os.environ, {**complete_prod_env, 'ACCOUNT_DELETION_DISPATCH_MODE': 'inline'}, clear=True):
            with pytest.raises(RuntimeError, match='ACCOUNT_DELETION_DISPATCH_MODE=cloud_tasks'):
                cloud_tasks.validate_account_deletion_dispatch_configuration()

        incomplete = dict(complete_prod_env)
        incomplete.pop('ACCOUNT_DELETION_HANDLER_URL')
        with patch.dict(os.environ, incomplete, clear=True):
            with pytest.raises(RuntimeError, match='ACCOUNT_DELETION_HANDLER_URL'):
                cloud_tasks.validate_account_deletion_dispatch_configuration()

        with patch.dict(os.environ, {'OMI_ENV_STAGE': 'dev', 'ACCOUNT_DELETION_DISPATCH_MODE': 'inline'}, clear=True):
            cloud_tasks.validate_account_deletion_dispatch_configuration()


# ---------------------------------------------------------------------------
# Structural contract of routers/sync.py and main.py wiring
# ---------------------------------------------------------------------------


class TestSyncRouterStructure:
    @staticmethod
    def _read(relative_path):
        with open(os.path.join(BACKEND_DIR, relative_path), encoding='utf-8') as f:
            return f.read()

    def test_handler_endpoint_exists_with_oidc(self):
        source = self._read(os.path.join('routers', 'sync.py'))
        assert '"/v2/sync-jobs/run"' in source
        assert 'Depends(verify_cloud_tasks_oidc)' in source

    def test_startup_applies_the_account_deletion_dispatch_guard(self):
        source = self._read('main.py')
        assert 'validate_account_deletion_dispatch_configuration()' in source

    def test_handler_respects_terminal_statuses(self):
        source = self._read(os.path.join('routers', 'sync.py'))
        handler = source[source.index('async def run_sync_job') :]
        assert 'TERMINAL_STATUSES' in handler
        assert 'mark_job_queued_for_retry' in handler
        assert 'status_code=409' in handler

    def test_fast_path_gates_on_env_and_byok(self):
        source = self._read(os.path.join('routers', 'sync.py'))
        assert 'cloud_task_eligible = cloud_tasks_dispatch_enabled and not byok_enabled' in source

    def test_pipeline_reraises_in_task_mode(self):
        source = self._read(os.path.join('utils', 'sync', 'pipeline.py'))
        assert 'task_mode: bool = False' in source
        # Catch-all must re-raise in task mode so the handler controls retry
        assert 'if task_mode:' in source

    def test_timeout_override_wired(self):
        main_src = self._read('main.py')
        assert 'paths_timeout' in main_src
        assert 'HTTP_SYNC_JOBS_RUN_TIMEOUT' in main_src
        assert 'HTTP_ACCOUNT_DELETION_WIPE_RUN_TIMEOUT' in main_src
        timeout_src = self._read(os.path.join('utils', 'other', 'timeout.py'))
        assert 'paths_timeout' in timeout_src

    def test_account_deletion_handler_exists_with_oidc(self):
        source = self._read(os.path.join('routers', 'users.py'))
        assert "'/v1/users/account-deletion-wipes/run'" in source
        handler = source[source.index('async def run_account_deletion_wipe') :]
        assert 'Depends(verify_account_deletion_cloud_tasks_oidc)' in handler[:250]
        assert 'try_acquire_job_run_lock' in handler
        assert 'claim_deletion_wipe_for_task' in handler
        assert 'status_code=500' in handler

    def test_v1_endpoint_unchanged(self):
        source = self._read(os.path.join('routers', 'sync.py'))
        assert '"/v1/sync-local-files"' in source

    def test_post_enqueue_cleanup_does_not_unstage_on_local_failure(self):
        """Post-enqueue local cleanup errors must not delete staged GCS blobs."""
        source = self._read(os.path.join('routers', 'sync.py'))
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'event=sync_post_enqueue_cleanup outcome=failed' in func_body
        post_enqueue_block = func_body[func_body.index('if dispatched:') : func_body.index('if not dispatched:')]
        assert '_delete_staged_blobs_async' not in post_enqueue_block


# ---------------------------------------------------------------------------
# Behavioral: post-enqueue cleanup must not unstage staged blobs
# ---------------------------------------------------------------------------


def _load_sync_router_for_fast_path():
    """Load routers/sync.py with heavy deps stubbed for fast-path behavioral tests."""
    import contextvars
    import importlib.util
    from io import BytesIO
    from pydantic import BaseModel
    from database.sync_jobs import SyncLedgerFenceMode
    from utils.stt import outcomes as actual_outcomes

    saved_modules = {}
    prior_utils_sync = sys.modules.get('utils.sync')
    mock_sync_jobs = MagicMock()

    heavy_deps = [
        'redis',
        'database',
        'database.redis_db',
        'database._client',
        'database.conversations',
        'database.users',
        'database.user_usage',
        'database.sync_ledger',
        'firebase_admin',
        'google',
        'google.cloud',
        'google.cloud.firestore_v2',
        'opuslib',
        'pydub',
        'models',
        'models.conversation',
        'models.conversation_enums',
        'models.sync_audio',
        'models.transcript_segment',
        'utils',
        'utils.analytics',
        'utils.byok',
        'utils.client_device',
        'utils.cloud_tasks',
        'utils.conversations',
        'utils.conversations.process_conversation',
        'utils.conversations.factory',
        'utils.other',
        'utils.other.endpoints',
        'utils.other.storage',
        'utils.encryption',
        'utils.stt',
        'utils.stt.pre_recorded',
        'utils.stt.vad',
        'utils.fair_use',
        'utils.subscription',
        'utils.observability',
        'utils.observability.fallback',
        'utils.metrics',
        'utils.log_sanitizer',
        'utils.http_client',
        'utils.request_validation',
        'utils.sync.files',
        'utils.sync.playback',
        'utils.sync.backfill',
        'utils.sync.content_id',
        'utils.sync.capture_manifest',
        'utils.speaker_assignment',
        'utils.speaker_identification',
        'utils.stt.speaker_embedding',
        'python_multipart',
        'python_multipart.multipart',
    ]

    for mod_name in heavy_deps:
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = MagicMock()

    sys.modules['python_multipart'].__version__ = '0.0.99'
    sys.modules['python_multipart.multipart'].parse_options_header = MagicMock(return_value={})

    def _submit_with_context(executor, fn, *args, **kwargs):
        ctx = contextvars.copy_context()
        return executor.submit(ctx.run, fn, *args, **kwargs)

    mock_executors = MagicMock()
    mock_executors.critical_executor = MagicMock()
    mock_executors.sync_executor = MagicMock()
    mock_executors.postprocess_executor = MagicMock()
    mock_executors.storage_executor = MagicMock()
    mock_executors.submit_with_context = _submit_with_context
    saved_modules['utils.executors'] = sys.modules.get('utils.executors')
    sys.modules['utils.executors'] = mock_executors

    sys.modules['database.redis_db'] = MagicMock(r=MagicMock())
    saved_modules['database.sync_jobs'] = sys.modules.get('database.sync_jobs')
    mock_sync_jobs.create_sync_job = MagicMock(
        return_value={
            'job_id': 'job-1',
            'uid': 'test-uid',
            'status': 'queued',
            'total_files': 1,
            'total_segments': 0,
        }
    )
    mock_sync_jobs.SyncLedgerFenceMode = SyncLedgerFenceMode
    mock_sync_jobs.get_sync_ledger_fence_mode = MagicMock(return_value=SyncLedgerFenceMode.LEGACY)
    mock_sync_jobs.sync_job_uses_ledger_fence = MagicMock(
        side_effect=lambda job: bool(job and job.get('ledger_fence_mode') == SyncLedgerFenceMode.ACTIVE.value)
    )
    mock_sync_jobs.mark_job_queued_for_retry = MagicMock()
    mock_sync_jobs.try_acquire_job_run_lock = MagicMock(return_value='legacy-lock-token')
    sys.modules['database.sync_jobs'] = mock_sync_jobs

    sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
    sys.modules['utils.fair_use'].get_hard_restriction_status = MagicMock(return_value=(False, None))
    sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
    sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
    sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
    sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
    sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)
    sys.modules['utils.request_validation'].parse_sync_filename_timestamp = MagicMock(return_value=time.time())
    saved_modules['utils.sync'] = prior_utils_sync
    sync_pkg = types.ModuleType('utils.sync')
    sync_pkg.__path__ = [os.path.join(BACKEND_DIR, 'utils', 'sync')]
    sys.modules['utils.sync'] = sync_pkg
    sys.modules['utils.sync'].files = sys.modules['utils.sync.files']
    sys.modules['utils.sync'].playback = sys.modules['utils.sync.playback']
    sys.modules['utils.sync.playback'].build_playback_artifact = MagicMock(return_value=b'')
    sys.modules['utils.sync.playback'].PlaybackBuildError = type('PlaybackBuildError', (Exception,), {})
    sys.modules['utils.cloud_tasks'].is_cloud_tasks_dispatch_enabled = MagicMock(return_value=True)
    sys.modules['utils.cloud_tasks'].enqueue_sync_job = MagicMock()
    sys.modules['utils.byok'].has_byok_keys = MagicMock(return_value=False)
    sys.modules['utils.client_device'].resolve_client_device = MagicMock(
        return_value=types.SimpleNamespace(
            client_device_id='ios_a1b2c3d4',
            device_hash='a1b2c3d4',
            platform='ios',
            app_version=None,
        )
    )
    sys.modules['utils.client_device'].resolve_client_device_from_request = MagicMock(
        return_value=types.SimpleNamespace(client_device_id=None, platform=None)
    )
    sys.modules['database.sync_ledger'].claim_sync_content = MagicMock(return_value={'outcome': 'owned'})
    sys.modules['database.sync_ledger'].release_sync_content_claim = MagicMock()
    sys.modules['database.sync_ledger'].release_sync_content_claim_after_job_retired = MagicMock()
    sys.modules['database.sync_ledger'].mark_sync_content_completed = MagicMock()
    sys.modules['database.sync_ledger'].try_mark_sync_content_side_effect = MagicMock(return_value=True)
    sys.modules['utils.sync.backfill'].try_acquire_backfill_slot = MagicMock(return_value=True)
    sys.modules['utils.sync.backfill'].release_backfill_slot = MagicMock()
    sys.modules['utils.sync.backfill'].reserve_backfill_speech = MagicMock(
        return_value=MagicMock(allowed=True, reason=None, retry_after=None)
    )
    sys.modules['utils.sync.content_id'].compute_sync_content_id = MagicMock(return_value='content-1')
    sys.modules['utils.sync.capture_manifest'].verify_capture_manifest = MagicMock(
        return_value=[{'name': 'test.opus', 'sha256': '0' * 64}]
    )
    sys.modules['utils.sync.capture_manifest'].manifest_claims_match_paths = MagicMock(return_value=True)
    sys.modules['utils.sync.capture_manifest'].issue_capture_manifest = MagicMock(return_value='manifest')

    sync_dispatch_fallback_calls = []
    sync_dispatch_attempt_modes = []

    def _track_record_fallback(**kwargs):
        sync_dispatch_fallback_calls.append(kwargs)

    def _counter_labels(**kwargs):
        child = MagicMock()
        mode = kwargs.get('mode')

        def _inc():
            sync_dispatch_attempt_modes.append(mode)

        child.inc = _inc
        return child

    mock_counter = MagicMock()
    mock_counter.labels = _counter_labels
    # Re-assign after the MagicMock loop so submodule imports resolve as a package.
    obs_pkg = types.ModuleType('utils.observability')
    obs_pkg.__path__ = []  # type: ignore[attr-defined]
    fallback_mod = types.ModuleType('utils.observability.fallback')
    fallback_mod.record_fallback = _track_record_fallback
    transcription_mod = types.ModuleType('utils.observability.transcription')
    transcription_mod.record_sync_transcription_outcome = MagicMock()
    saved_modules['utils.observability.transcription'] = sys.modules.get('utils.observability.transcription')
    saved_modules['utils.stt.outcomes'] = sys.modules.get('utils.stt.outcomes')
    sys.modules['utils.observability'] = obs_pkg
    sys.modules['utils.observability.fallback'] = fallback_mod
    sys.modules['utils.observability.transcription'] = transcription_mod
    obs_pkg.fallback = fallback_mod
    obs_pkg.transcription = transcription_mod
    sys.modules['utils.stt.outcomes'] = actual_outcomes
    sys.modules['utils.metrics'] = MagicMock(OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL=mock_counter)

    class _AudioPrecacheResponse(BaseModel):
        pass

    class _AudioUrlsResponse(BaseModel):
        pass

    sys.modules['models.sync_audio'].AudioPrecacheResponse = _AudioPrecacheResponse
    sys.modules['models.sync_audio'].AudioUrlsResponse = _AudioUrlsResponse

    sys.modules.pop('routers.sync', None)
    sys.modules.pop('utils.sync.pipeline', None)
    spec = importlib.util.spec_from_file_location(
        'sync_post_enqueue_cleanup',
        os.path.join(BACKEND_DIR, 'routers', 'sync.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def _passthrough_run_blocking(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    module.run_blocking = _passthrough_run_blocking
    module._retrieve_file_paths_v2 = MagicMock(return_value=['syncing/test-uid/job-1/file.bin'])
    module._capture_matches_server_conversation = MagicMock(return_value=True)
    module._stage_files_to_gcs = MagicMock()
    module._cleanup_files = MagicMock()
    module._finalize_sync_job_failure = AsyncMock()

    return module, saved_modules, mock_sync_jobs, BytesIO, sync_dispatch_fallback_calls, sync_dispatch_attempt_modes


def _configure_task_handler(module, *, pipeline_error: BaseException, latest_job: dict):
    """Configure the production task handler around a failing pipeline seam."""

    module.TERMINAL_STATUSES = ('completed', 'partial_failure', 'failed')
    module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
    module.sync_job_uses_ledger_fence = MagicMock(
        side_effect=lambda job: bool(job and job.get('ledger_fence_mode') == module.SyncLedgerFenceMode.ACTIVE.value)
    )
    module.try_acquire_sync_job_run_lock = MagicMock(return_value='1:lock-token')
    module.try_acquire_job_run_lock = MagicMock(return_value='legacy-lock-token')
    module.release_job_run_lock = MagicMock()
    admitted_job = {
        'job_id': 'job-1',
        'status': 'queued',
        'lane': 'fresh',
        'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
    }
    running_job = {
        'job_id': 'job-1',
        'status': 'processing',
        'lane': 'fresh',
        'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
    }
    module.get_sync_job = MagicMock(
        side_effect=[
            admitted_job,
            running_job,
            {**latest_job, 'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value},
        ]
    )
    module._download_staged_files = MagicMock(return_value=True)
    module._run_full_pipeline_background_async = AsyncMock(side_effect=pipeline_error)
    module._delete_staged_blobs_async = AsyncMock()
    module.release_backfill_slot = MagicMock()
    module.release_sync_content_claim = MagicMock()
    module.release_sync_content_claim_after_job_retired = MagicMock()
    module.delete_sync_job_run_lock_epoch = MagicMock()
    module.bind_or_converge_sync_ledger_completion = MagicMock(return_value=None)
    module.fenced_mark_job_queued_for_retry = MagicMock(return_value=types.SimpleNamespace(applied=True))
    module._finalize_sync_job_failure = AsyncMock()
    module.get_sync_tasks_max_attempts = MagicMock(return_value=3)

    request = MagicMock()
    request.json = AsyncMock(
        return_value={
            'job_id': 'job-1',
            'uid': 'test-uid',
            'raw_blob_paths': ['staged/audio.opus'],
            'source': 'omi',
            'lane': 'fresh',
            'content_id': 'content-1',
            'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
        }
    )
    return request


def _enable_active_ledger_fence(module):
    """Make a fast-path router fixture classify persisted active jobs literally.

    The router module is deliberately loaded with a synthetic dependency graph.
    Other tests can replace that graph, so these behavioral cases must not rely
    on a default ``MagicMock`` truth value for the persisted rollout marker.
    """
    module.sync_job_uses_ledger_fence = MagicMock(
        side_effect=lambda job: bool(job and job.get('ledger_fence_mode') == 'active')
    )


def test_polling_stale_job_releases_retry_claim_through_owned_finalizer():
    """A stale poll owns the lease before it publishes a retryable failure."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    stale_job = {
        'job_id': 'job-1',
        'uid': 'test-uid',
        'status': 'processing',
        'content_id': 'content-1',
        'stt_provider': 'deepgram',
        'stt_model': 'nova-3',
        'lane': 'fresh',
        'dispatch_mode': 'cloud_tasks',
        'ledger_fence_mode': 'active',
    }
    failed_job = {**stale_job, 'status': 'failed', 'reason_code': 'sync_worker_stale'}
    try:
        module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
        _enable_active_ledger_fence(module)
        module.get_sync_job = MagicMock(side_effect=[stale_job, stale_job])
        module.is_sync_job_stale = MagicMock(return_value=True)
        module.try_acquire_sync_job_run_lock = MagicMock(return_value='1:poll-lock')
        module.release_job_run_lock = MagicMock()
        module.bind_or_converge_sync_ledger_completion = MagicMock(return_value=None)
        module.delete_sync_job_run_lock_epoch = MagicMock()
        module.finalize_sync_job_failure_now = MagicMock(return_value=failed_job)

        response = module.get_sync_job_status('job-1', uid='test-uid')

        assert response['status'] == 'failed'
        assert response['reason_code'] == 'sync_worker_stale'
        module.finalize_sync_job_failure_now.assert_called_once_with(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            error_code='sync_worker_stale',
            outcome=module.TranscriptionOutcome.UPSTREAM_ERROR,
            provider='deepgram',
            model='nova-3',
            lane='fresh',
            run_lock_token='1:poll-lock',
        )
        module.bind_or_converge_sync_ledger_completion.assert_called_once_with(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            run_lock_token='1:poll-lock',
        )
        module.release_job_run_lock.assert_called_once_with('job-1', '1:poll-lock')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


def test_polling_stale_job_lease_loss_preserves_newer_owner_retry_material():
    """A stale poll that loses ledger fencing cannot publish or release a newer owner's work."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    stale_job = {
        'job_id': 'job-1',
        'uid': 'test-uid',
        'status': 'processing',
        'content_id': 'content-1',
        'stt_provider': 'deepgram',
        'stt_model': 'nova-3',
        'lane': 'backfill',
        'dispatch_mode': 'cloud_tasks',
        'ledger_fence_mode': 'active',
    }
    try:
        module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
        _enable_active_ledger_fence(module)
        module.get_sync_job = MagicMock(side_effect=[stale_job, stale_job])
        module.is_sync_job_stale = MagicMock(return_value=True)
        module.try_acquire_sync_job_run_lock = MagicMock(return_value='2:poll-lock')
        module.release_job_run_lock = MagicMock()
        module.bind_or_converge_sync_ledger_completion = MagicMock(
            side_effect=module.SyncJobRunLeaseLost('newer ledger epoch owns retry material')
        )
        module.finalize_sync_job_failure_now = MagicMock()
        module.release_backfill_slot = MagicMock()
        module.release_sync_content_claim = MagicMock()
        module.release_sync_content_claim_after_job_retired = MagicMock()

        response = module.get_sync_job_status('job-1', uid='test-uid')

        assert response['status'] == 'processing'
        module.bind_or_converge_sync_ledger_completion.assert_called_once_with(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            run_lock_token='2:poll-lock',
        )
        module.finalize_sync_job_failure_now.assert_not_called()
        module.release_backfill_slot.assert_not_called()
        module.release_sync_content_claim.assert_not_called()
        module.release_sync_content_claim_after_job_retired.assert_not_called()
        module.release_job_run_lock.assert_called_once_with('job-1', '2:poll-lock')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


def test_polling_never_finalizes_stale_job_while_an_active_run_owns_lease():
    """The status read remains processing when another worker holds the lease."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    stale_job = {
        'job_id': 'job-1',
        'uid': 'test-uid',
        'status': 'processing',
        'lane': 'fresh',
        'dispatch_mode': 'cloud_tasks',
        'ledger_fence_mode': 'active',
    }
    try:
        module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
        _enable_active_ledger_fence(module)
        module.get_sync_job = MagicMock(return_value=stale_job)
        module.is_sync_job_stale = MagicMock(return_value=True)
        module.try_acquire_sync_job_run_lock = MagicMock(return_value=None)
        module.finalize_sync_job_failure_now = MagicMock()

        response = module.get_sync_job_status('job-1', uid='test-uid')

        assert response['status'] == 'processing'
        module.finalize_sync_job_failure_now.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


def test_polling_never_finalizes_a_stale_inline_job():
    """An inline coordinator can outlive cancellation, so it is its own terminal owner."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    stale_job = {
        'job_id': 'job-1',
        'uid': 'test-uid',
        'status': 'processing',
        'lane': 'fresh',
        'dispatch_mode': 'inline',
    }
    try:
        module.get_sync_job = MagicMock(return_value=stale_job)
        module.is_sync_job_stale = MagicMock(return_value=True)
        module.try_acquire_sync_job_run_lock = MagicMock(return_value='unexpected-lock')
        module.finalize_sync_job_failure_now = MagicMock()

        response = module.get_sync_job_status('job-1', uid='test-uid')

        assert response['status'] == 'processing'
        module.try_acquire_sync_job_run_lock.assert_not_called()
        module.finalize_sync_job_failure_now.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


def test_polling_active_terminal_retries_claim_cleanup_before_exposing_result():
    """An inline terminal remains retryable to the WAL until its exact claim is released."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    terminal_job = {
        'job_id': 'job-1',
        'uid': 'test-uid',
        'status': 'partial_failure',
        'content_id': 'content-1',
        'lane': 'fresh',
        'dispatch_mode': 'inline',
        'ledger_fence_mode': 'active',
        'failed_segments': 1,
        'total_segments': 1,
    }
    cleanup_order = []

    def _release_retired_claim(uid, content_id, job_id):
        cleanup_order.append(('release', uid, content_id, job_id))
        if len(cleanup_order) == 1:
            raise ConnectionError('ledger temporarily unavailable')

    try:
        module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
        _enable_active_ledger_fence(module)
        module.get_sync_job = MagicMock(return_value=terminal_job)
        module.is_sync_job_stale = MagicMock(return_value=False)
        module.release_sync_content_claim_after_job_retired = MagicMock(side_effect=_release_retired_claim)
        module.delete_sync_job_run_lock_epoch = MagicMock(
            side_effect=lambda job_id: cleanup_order.append(('epoch', job_id))
        )

        with pytest.raises(module.HTTPException) as first_poll:
            module.get_sync_job_status('job-1', uid='test-uid')

        assert first_poll.value.status_code == 503
        assert first_poll.value.headers == {'Retry-After': '10'}
        assert cleanup_order == [('release', 'test-uid', 'content-1', 'job-1')]
        module.delete_sync_job_run_lock_epoch.assert_not_called()

        response = module.get_sync_job_status('job-1', uid='test-uid')

        assert response['status'] == 'partial_failure'
        assert response['failed_segments'] == 1
        assert cleanup_order == [
            ('release', 'test-uid', 'content-1', 'job-1'),
            ('release', 'test-uid', 'content-1', 'job-1'),
            ('epoch', 'job-1'),
        ]
        module.release_sync_content_claim_after_job_retired.assert_has_calls(
            [
                unittest.mock.call('test-uid', 'content-1', 'job-1'),
                unittest.mock.call('test-uid', 'content-1', 'job-1'),
            ]
        )
        module.delete_sync_job_run_lock_epoch.assert_called_once_with('job-1')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


@pytest.mark.asyncio
async def test_sync_task_retry_retains_staged_audio_and_safe_failure_code():
    """A non-final provider failure must remain queued without a terminal outcome."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=TimeoutError('private upstream detail'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    try:
        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 500
        assert json.loads(response.body) == {'status': 'retry'}
        module.fenced_mark_job_queued_for_retry.assert_called_once_with('job-1', '1:lock-token', 1, 'stt_timeout')
        module._finalize_sync_job_failure.assert_not_awaited()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.bind_or_converge_sync_ledger_completion.assert_called_once_with(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            run_lock_token='1:lock-token',
        )
        module._run_full_pipeline_background_async.assert_awaited_once()
        assert module._run_full_pipeline_background_async.await_args.kwargs['run_lock_token'] == '1:lock-token'
        assert module._run_full_pipeline_background_async.await_args.kwargs['content_run_bound'] is True
        module.release_job_run_lock.assert_called_once_with('job-1', '1:lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_converged_binding_skips_download_and_pipeline():
    """A durable completion converges Redis without touching staged audio or providers."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not run'),
        latest_job={'job_id': 'job-1', 'status': 'processing'},
    )
    try:
        module.bind_or_converge_sync_ledger_completion = MagicMock(
            return_value={'total_segments': 2, 'outcome': 'success'}
        )

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'done', 'reconciled': True}
        module.bind_or_converge_sync_ledger_completion.assert_called_once_with(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            run_lock_token='1:lock-token',
        )
        module._download_staged_files.assert_not_called()
        module._run_full_pipeline_background_async.assert_not_awaited()
        module.release_job_run_lock.assert_called_once_with('job-1', '1:lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_binding_loss_returns_locked_without_download_or_pipeline():
    """A higher ledger epoch stops the handler before it reads staged worker input."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not run'),
        latest_job={'job_id': 'job-1', 'status': 'processing'},
    )
    try:
        module.bind_or_converge_sync_ledger_completion = MagicMock(
            side_effect=module.SyncJobRunLeaseLost('newer ledger owner')
        )

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module._download_staged_files.assert_not_called()
        module._run_full_pipeline_background_async.assert_not_awaited()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.release_sync_content_claim_after_job_retired.assert_not_called()
        module.delete_sync_job_run_lock_epoch.assert_not_called()
        module.release_job_run_lock.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_legacy_sync_task_skips_epoch_binding_and_uses_generic_lock():
    """Persisted legacy jobs remain on the pre-cutover protocol during mixed revisions."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    legacy_job = {
        'job_id': 'job-1',
        'status': 'processing',
        'lane': 'fresh',
        'ledger_fence_mode': module.SyncLedgerFenceMode.LEGACY.value,
    }
    request = MagicMock()
    request.json = AsyncMock(
        return_value={
            'job_id': 'job-1',
            'uid': 'test-uid',
            'raw_blob_paths': ['staged/audio.opus'],
            'source': 'omi',
            'lane': 'fresh',
            'content_id': 'content-1',
            'ledger_fence_mode': module.SyncLedgerFenceMode.LEGACY.value,
        }
    )
    try:
        module.get_sync_job = MagicMock(return_value=legacy_job)
        module.try_acquire_job_run_lock = MagicMock(return_value='legacy-lock-token')
        module.try_acquire_sync_job_run_lock = MagicMock()
        module.release_job_run_lock = MagicMock()
        module.bind_or_converge_sync_ledger_completion = MagicMock()
        module._download_staged_files = MagicMock(return_value=True)
        module._run_full_pipeline_background_async = AsyncMock()
        module._delete_staged_blobs_async = AsyncMock()

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'done'}
        module.try_acquire_job_run_lock.assert_called_once_with('job-1')
        module.try_acquire_sync_job_run_lock.assert_not_called()
        module.bind_or_converge_sync_ledger_completion.assert_not_called()
        pipeline_kwargs = module._run_full_pipeline_background_async.await_args.kwargs
        assert pipeline_kwargs['run_lock_token'] is None
        assert pipeline_kwargs['content_run_bound'] is False
        assert pipeline_kwargs['ledger_fence_active'] is False
        module.release_job_run_lock.assert_called_once_with('job-1', 'legacy-lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_standby_sync_task_does_not_parse_or_consume_work():
    """The hard-cutover standby mode leaves queued audio untouched for later delivery."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock()
    try:
        module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.STANDBY)
        module.try_acquire_job_run_lock = MagicMock()
        module.try_acquire_sync_job_run_lock = MagicMock()
        module._download_staged_files = MagicMock()
        module._run_full_pipeline_background_async = AsyncMock()

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 503
        assert json.loads(response.body) == {'status': 'cutover_standby'}
        request.json.assert_not_awaited()
        module.try_acquire_job_run_lock.assert_not_called()
        module.try_acquire_sync_job_run_lock.assert_not_called()
        module._download_staged_files.assert_not_called()
        module._run_full_pipeline_background_async.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_post_terminal_retired_claim_cleanup_retries_through_terminal_branch():
    """A cleanup failure after terminal CAS retries exact cleanup without rerunning the worker."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('unused'),
        latest_job={'job_id': 'job-1', 'status': 'processing'},
    )
    active_job = {
        'job_id': 'job-1',
        'status': 'processing',
        'lane': 'fresh',
        'ledger_fence_mode': 'active',
    }
    terminal_job = {
        'job_id': 'job-1',
        'status': 'partial_failure',
        'lane': 'fresh',
        'ledger_fence_mode': 'active',
    }

    async def _terminalize_then_fail_retired_cleanup(*_args, **_kwargs):
        active_job.update(terminal_job)
        module.release_sync_content_claim_after_job_retired('test-uid', 'content-1', 'job-1')

    try:
        _enable_active_ledger_fence(module)
        module.get_sync_job = MagicMock(side_effect=lambda _job_id: dict(active_job))
        module.release_sync_content_claim_after_job_retired = MagicMock(
            side_effect=RuntimeError('retired claim cleanup unavailable')
        )
        module._run_full_pipeline_background_async = _terminalize_then_fail_retired_cleanup

        first = await module.run_sync_job(request, task_retry_count=0)

        assert first.status_code == 500
        assert json.loads(first.body) == {'status': 'terminal_cleanup_retry', 'job_status': 'partial_failure'}
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._finalize_sync_job_failure.assert_not_awaited()
        module.delete_sync_job_run_lock_epoch.assert_not_called()
        module._delete_staged_blobs_async.assert_not_awaited()

        module.release_sync_content_claim_after_job_retired.reset_mock()
        module.release_sync_content_claim_after_job_retired.side_effect = None
        module._download_staged_files.reset_mock()
        module._run_full_pipeline_background_async = AsyncMock()

        second = await module.run_sync_job(request, task_retry_count=0)

        assert second.status_code == 200
        assert json.loads(second.body) == {'status': 'acked', 'job_status': 'partial_failure'}
        module.release_sync_content_claim_after_job_retired.assert_called_once_with('test-uid', 'content-1', 'job-1')
        module.delete_sync_job_run_lock_epoch.assert_called_once_with('job-1')
        module._download_staged_files.assert_not_called()
        module._run_full_pipeline_background_async.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_cancellation_preserves_run_lock_and_retry_material():
    """A timeout cannot start a duplicate task while its executor leaf may run."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=asyncio.CancelledError(),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    try:
        with pytest.raises(asyncio.CancelledError):
            await module.run_sync_job(request, task_retry_count=0)

        module.release_job_run_lock.assert_not_called()
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.release_sync_content_claim_after_job_retired.assert_not_called()
        module.delete_sync_job_run_lock_epoch.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_lease_rejection_preserves_claim_and_staged_audio():
    """A rejected first worker fence is a retry, never a cleanup/terminal path."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('unused'),
        latest_job={'job_id': 'job-1', 'status': 'processing'},
    )

    async def _reject_first_worker_fence(*_args, **kwargs):
        assert kwargs['run_lock_token'] == '1:lock-token'
        assert kwargs['content_run_bound'] is True
        raise module.SyncJobRunLeaseLost('owner replaced before processing')

    try:
        module._run_full_pipeline_background_async = _reject_first_worker_fence

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module._delete_staged_blobs_async.assert_not_awaited()
        module.release_sync_content_claim.assert_not_called()
        module.release_sync_content_claim_after_job_retired.assert_not_called()
        module.delete_sync_job_run_lock_epoch.assert_not_called()
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module.release_job_run_lock.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_expired_task_releases_only_its_matching_claim_for_404_reupload_recovery():
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('unused'),
        latest_job={'job_id': 'job-1', 'status': 'processing'},
    )
    try:
        module.get_sync_job = MagicMock(return_value=None)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'dropped', 'reason': 'job_expired'}
        module.release_sync_content_claim_after_job_retired.assert_called_once_with('test-uid', 'content-1', 'job-1')
        module.release_sync_content_claim.assert_not_called()
        module._delete_staged_blobs_async.assert_awaited_once_with(['staged/audio.opus'])
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
@pytest.mark.parametrize('status, expects_release', [('failed', True), ('partial_failure', True), ('completed', False)])
async def test_duplicate_terminal_task_releases_only_retryable_matching_claim(status, expects_release):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('unused'),
        latest_job={'job_id': 'job-1', 'status': 'processing'},
    )
    try:
        module.get_sync_job = MagicMock(
            return_value={
                'job_id': 'job-1',
                'status': status,
                'lane': 'fresh',
                'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
            }
        )

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        if expects_release:
            module.release_sync_content_claim_after_job_retired.assert_called_once_with(
                'test-uid', 'content-1', 'job-1'
            )
        else:
            module.release_sync_content_claim_after_job_retired.assert_not_called()
        module.release_sync_content_claim.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_final_attempt_publishes_one_bounded_terminal_failure():
    """Retry exhaustion must publish a recoverable failure before consuming the task."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=TimeoutError('private upstream detail'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    try:
        response = await module.run_sync_job(request, task_retry_count=2)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'failed_final'}
        module._finalize_sync_job_failure.assert_awaited_once_with(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            error_code='stt_timeout',
            outcome=module.TranscriptionOutcome.TIMEOUT,
            provider='deepgram',
            model='nova-3',
            lane='fresh',
            run_lock_token='1:lock-token',
        )
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._delete_staged_blobs_async.assert_awaited_once_with(['staged/audio.opus'])
        module.release_job_run_lock.assert_called_once_with('job-1', '1:lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_post_enqueue_cleanup_does_not_unstage(monkeypatch):
    """Successful enqueue + failed local cleanup must keep staged blobs for the handler."""
    import shutil
    from starlette.datastructures import UploadFile

    module, saved_modules, mock_sync_jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    unstage_calls = []
    inline_pipeline_started = []

    async def _track_unstage(blob_paths):
        unstage_calls.append(list(blob_paths))

    async def _track_inline_pipeline(*args, **kwargs):
        inline_pipeline_started.append(True)

    module._delete_staged_blobs_async = _track_unstage
    module._run_full_pipeline_background_async = _track_inline_pipeline
    module.start_background_task = MagicMock()

    def _rmtree_raises(*args, **kwargs):
        raise OSError('cleanup failed')

    monkeypatch.setattr(shutil, 'rmtree', _rmtree_raises)

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        resp = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert resp.status_code == 202
        body = json.loads(resp.body)
        assert body['status'] == 'queued'
        assert unstage_calls == [], f'staged blobs must not be deleted after enqueue: {unstage_calls}'
        assert inline_pipeline_started == [], 'inline pipeline must not run when Cloud Task was enqueued'
        module.start_background_task.assert_not_called()
        module.create_sync_job.assert_called_once()
        module.enqueue_sync_job.assert_called_once()
        assert module.create_sync_job.call_args.kwargs['dispatch_mode'] == 'cloud_tasks'
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_dispatch_cloud_tasks_success_increments_attempts(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, attempt_modes = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        resp = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert resp.status_code == 202
        assert fallback_calls == []
        assert attempt_modes == ['cloud_tasks']
        module.enqueue_sync_job.assert_called_once()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_dispatch_carries_device_provenance_into_cloud_task(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    module.resolve_client_device.return_value = types.SimpleNamespace(
        client_device_id='ios_a1b2c3d4',
        device_hash='a1b2c3d4',
        platform='ios',
        app_version=None,
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(
            files=[upload],
            uid='test-uid',
            x_app_platform='ios',
            x_device_id_hash='a1b2c3d4',
        )

        assert response.status_code == 202
        payload = module.enqueue_sync_job.call_args.args[0]
        assert payload['client_device_id'] == 'ios_a1b2c3d4'
        assert payload['client_platform'] == 'ios'
    finally:
        sys.modules.pop('routers.sync', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_dispatch_enqueue_uncertain_keeps_durable_work_and_never_starts_inline(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, attempt_modes = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    module.enqueue_sync_job = MagicMock(side_effect=RuntimeError('enqueue boom'))
    module._delete_staged_blobs_async = AsyncMock()
    module._finalize_sync_job_failure = AsyncMock()
    module.release_sync_content_claim = MagicMock()
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.FRESH,
            trust=types.SimpleNamespace(value='device_bound'),
            reason='recent_capture',
            maximum_age_seconds=60,
            automatic_recovery_allowed=True,
        )
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        resp = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert resp.status_code == 202
        assert json.loads(resp.body)['status'] == 'queued'
        assert module.enqueue_sync_job.call_count == 2
        assert fallback_calls == []
        assert attempt_modes == ['enqueue_uncertain']
        module.start_background_task.assert_not_called()
        module._delete_staged_blobs_async.assert_not_awaited()
        module._finalize_sync_job_failure.assert_not_awaited()
        module.release_sync_content_claim.assert_not_called()
        assert module.create_sync_job.call_args.kwargs['dispatch_mode'] == 'cloud_tasks'
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_dispatch_named_enqueue_retry_recovers_an_ambiguous_first_ack(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, attempt_modes = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    module.enqueue_sync_job = MagicMock(side_effect=[RuntimeError('response lost'), None])

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert response.status_code == 202
        assert module.enqueue_sync_job.call_count == 2
        assert fallback_calls == []
        assert attempt_modes == ['cloud_tasks']
        module.start_background_task.assert_not_called()
        assert module.create_sync_job.call_args.kwargs['dispatch_mode'] == 'cloud_tasks'
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_dispatch_staging_failure_can_terminalize_and_release_for_wal_retry(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, _ = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    module._stage_files_to_gcs = MagicMock(side_effect=RuntimeError('gcs unavailable'))
    module._delete_staged_blobs_async = AsyncMock()
    module._finalize_sync_job_failure = AsyncMock()
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.FRESH,
            trust=types.SimpleNamespace(value='device_bound'),
            reason='recent_capture',
            maximum_age_seconds=60,
            automatic_recovery_allowed=True,
        )
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert response.status_code == 503
        assert json.loads(response.body)['code'] == 'sync_dispatch_unavailable'
        module.enqueue_sync_job.assert_not_called()
        module.start_background_task.assert_not_called()
        module._delete_staged_blobs_async.assert_awaited_once()
        module._finalize_sync_job_failure.assert_awaited_once_with(
            job_id=module.create_sync_job.call_args.kwargs['job_id'],
            uid='test-uid',
            content_id='content-1',
            error_code='sync_dispatch_staging_failed',
            outcome=module.TranscriptionOutcome.UPSTREAM_ERROR,
            provider='unknown',
            model='unknown',
            lane='fresh',
        )
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_inline_releases_run_lock_when_ledger_bind_loses_lease():
    """Fence-active inline admission must not keep a Redis lock after bind loss."""
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.has_byok_keys = MagicMock(return_value=True)
    module.start_background_task = MagicMock()
    module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
    module.try_acquire_sync_job_run_lock = MagicMock(return_value='1:lock-token')
    module.release_job_run_lock = MagicMock()
    module.bind_or_converge_sync_ledger_completion = MagicMock(
        side_effect=module.SyncJobRunLeaseLost('newer ledger epoch owns retry material')
    )
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.FRESH,
            trust=types.SimpleNamespace(value='legacy'),
            reason='recent_capture',
            maximum_age_seconds=60,
            automatic_recovery_allowed=True,
        )
    )
    module.create_sync_job = MagicMock(
        return_value={
            'job_id': 'job-lease-lost',
            'status': 'queued',
            'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
        }
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert response.status_code == 202
        body = json.loads(response.body)
        assert body['status'] == 'queued'
        module.start_background_task.assert_not_called()
        module.release_job_run_lock.assert_called_once_with(body['job_id'], '1:lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_dispatch_byok_records_recovered_inline(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, attempt_modes = _load_sync_router_for_fast_path()
    module.has_byok_keys = MagicMock(return_value=True)
    module.start_background_task = MagicMock()
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.FRESH,
            trust=types.SimpleNamespace(value='legacy'),
            reason='recent_capture',
            maximum_age_seconds=60,
            automatic_recovery_allowed=True,
        )
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        resp = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert resp.status_code == 202
        assert fallback_calls == [
            {
                'component': 'sync_dispatch',
                'from_mode': 'cloud_tasks',
                'to_mode': 'inline',
                'reason': 'byok',
                'outcome': 'recovered',
            }
        ]
        assert attempt_modes == ['inline']
        module.start_background_task.assert_called_once()
        module.enqueue_sync_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_dispatch_disabled_records_recovered_inline(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, attempt_modes = _load_sync_router_for_fast_path()
    module.is_cloud_tasks_dispatch_enabled = MagicMock(return_value=False)
    module.start_background_task = MagicMock()
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.FRESH,
            trust=types.SimpleNamespace(value='legacy'),
            reason='recent_capture',
            maximum_age_seconds=60,
            automatic_recovery_allowed=True,
        )
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        resp = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert resp.status_code == 202
        assert fallback_calls == [
            {
                'component': 'sync_dispatch',
                'from_mode': 'cloud_tasks',
                'to_mode': 'inline',
                'reason': 'dispatch_disabled',
                'outcome': 'recovered',
            }
        ]
        assert attempt_modes == ['inline']
        module.start_background_task.assert_called_once()
        module.enqueue_sync_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_backfill_enqueue_failure_never_falls_back_inline(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, _ = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    module.enqueue_sync_job = MagicMock(side_effect=RuntimeError('backfill queue unavailable'))
    module._delete_staged_blobs_async = AsyncMock(return_value=None)
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.BACKFILL,
            trust=types.SimpleNamespace(value='device_bound'),
            reason='historical_capture',
            maximum_age_seconds=8 * 86400,
            automatic_recovery_allowed=True,
        )
    )

    try:
        upload = UploadFile(filename='historical.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert response.status_code == 202
        assert json.loads(response.body)['status'] == 'queued'
        assert module.enqueue_sync_job.call_count == 2
        module.start_background_task.assert_not_called()
        module._delete_staged_blobs_async.assert_not_awaited()
        assert not fallback_calls
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
@pytest.mark.parametrize('dispatch_enabled,byok', [(False, False), (True, True)])
async def test_backfill_requires_isolated_dispatch(dispatch_enabled, byok):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    module.is_cloud_tasks_dispatch_enabled = MagicMock(return_value=dispatch_enabled)
    module.has_byok_keys = MagicMock(return_value=byok)
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.BACKFILL,
            trust=types.SimpleNamespace(value='device_bound'),
            reason='historical_capture',
            maximum_age_seconds=8 * 86400,
            automatic_recovery_allowed=True,
        )
    )

    try:
        upload = UploadFile(filename='historical.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert response.status_code == 503
        assert response.headers['x-omi-rate-limit-reason'] == 'backfill_capacity'
        module.enqueue_sync_job.assert_not_called()
        module.start_background_task.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
