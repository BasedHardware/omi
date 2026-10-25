"""
Tests for Cloud Tasks dispatch of the v2 sync pipeline.

Covers the new primitives in database/sync_jobs.py (run lock, queued-reset,
processed-segment ledger, metering once-guards), the OIDC verification in
utils/cloud_tasks.py, and the structural contract of the /v2/sync-jobs/run
handler in routers/sync.py.
"""

from utils.other import owned_paths  # noqa: F401 - retain real scratch guard across legacy package stubs
from models import conversation_continuity  # noqa: F401 - retain pure policy across legacy package stubs
from utils import dream_vocabulary  # noqa: F401 - retain shared keyterms across legacy package stubs
from utils import firestore_document_size  # noqa: F401 - retain pure size estimate across legacy package stubs
from utils import manual_speaker_assignments  # noqa: F401 - retain pure policy across legacy package stubs
from utils.stt import speaker_identity  # noqa: F401 - retain allocator across legacy package stubs
from utils.stt import sync_speaker_evidence  # noqa: F401 - retain pure evidence policy across legacy package stubs
from utils.stt import voiceprints  # noqa: F401 - retain pure voiceprint policy across legacy package stubs
from utils.observability import speaker_identification  # noqa: F401 - retain telemetry across legacy package stubs
from utils.observability import sync_phases  # noqa: F401 - retain aggregate telemetry across legacy package stubs
from config.sync_telemetry import SyncFailureReason

import asyncio
import hashlib
import json
import logging
import os
import sys
import threading
import time
import types
import unittest
import unittest.mock
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from starlette.datastructures import UploadFile

# Keep additive batch imports real before legacy fixtures replace package roots.
from utils.batch_pipeline import intake as _batch_intake  # noqa: F401
from utils.batch_pipeline import live_projection as _batch_live_projection  # noqa: F401
from utils.batch_pipeline import live_upload as _batch_live_upload  # noqa: F401
from routers import batch_pipeline as _batch_router  # noqa: F401
from models import sync_job_status as _sync_job_status  # noqa: F401

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', '..')


@pytest.fixture(autouse=True)
def legacy_production_keys(monkeypatch):
    # This suite asserts the existing production Redis key contract.
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')


async def _passthrough_async_resolve_geolocation(geolocation):
    """Identity stub for utils.conversations.location: the real resolver returns its input on a miss."""
    return geolocation


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
        (
            script,
            key_count,
            lock_key,
            job_key,
            token,
            expected_raw,
            next_raw,
            ttl_seconds,
        ) = mock_redis.eval.call_args.args
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

    def test_durable_ledger_finalizer_converges_a_current_queued_retry(self):
        """A durable-ledger recovery may finish the queued retry that owns its new lease."""
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        job_id = 'job-queued-recovery'
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            job_id,
            {'job_id': job_id, 'status': 'queued', 'lane': 'fresh', 'result': None},
            owner='2:recovery-owner',
        )
        result = {'total_segments': 1, 'failed_segments': 0, 'provider': 'deepgram', 'model': 'nova-3'}

        ordinary = sync_jobs.fenced_finalize_sync_job(job_id, '2:recovery-owner', result, now=101.0)
        assert ordinary.outcome is sync_jobs.FencedSyncJobMutationOutcome.INVALID_STATE

        converged = sync_jobs.fenced_finalize_sync_job_from_durable_ledger(
            job_id,
            '2:recovery-owner',
            result,
            now=102.0,
        )
        assert converged.applied is True
        assert converged.job['status'] == 'completed'

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
            'failure_stage': 'prod',
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
# Finalization diagnostics
# ---------------------------------------------------------------------------


class TestFinalizationDiagnostics:
    def test_diagnostic_kwargs_are_bounded_and_never_stored(self, caplog):
        """Logging-only kwargs collapse to closed tokens and never reach the job doc."""
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        job_id = 'job-diag'
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

        with caplog.at_level(logging.INFO):
            finalized = sync_jobs.finalize_sync_job(
                job_id,
                {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'},
                attempt_ref='uid-leaked-abc123',
                failure_phase='/tmp/private/audio.wav',
                failure_class='user-uid-abc123 detail',
                failure_subtype='uid-leaked-abc123',
            )

        assert finalized is not None
        record = next(r for r in caplog.records if 'event=sync_transcription_job_finalized' in r.getMessage())
        message = record.getMessage()
        assert 'job_ref=none' in message
        assert 'attempt_ref=none' in message
        assert 'failure_phase=unknown' in message
        assert 'failure_class=OtherException' in message
        assert 'failure_subtype=other' in message
        for leaked in ('uid-leaked-abc123', '/tmp/private/audio.wav', 'user-uid-abc123'):
            assert leaked not in message
        stored = sync_jobs.get_sync_job(job_id)
        for diagnostic in ('attempt_ref', 'failure_phase', 'failure_class', 'failure_subtype'):
            assert diagnostic not in stored['result']

    def test_diagnostic_kwargs_survive_closed_tokens_and_non_str(self, caplog):
        redis_client = fakeredis.FakeRedis()
        sync_jobs, _ = _load_sync_jobs(redis_client)
        job_id = str(uuid.uuid4())
        attempt_ref = uuid.uuid4().hex
        _seed_fenced_job(
            redis_client,
            sync_jobs,
            job_id,
            {
                'job_id': job_id,
                'status': 'processing',
                'ledger_fence_mode': 'legacy',
                'result': None,
                'failed_segments': 1,
            },
        )

        with caplog.at_level(logging.INFO):
            sync_jobs.finalize_sync_job(
                job_id,
                {
                    'failed_segments': 1,
                    'total_segments': 2,
                    'errors': ['stt_timeout'],
                    'outcome': 'upstream_error',
                },
                attempt_ref=attempt_ref,
                failure_phase='provider_call',
                failure_class='TimeoutError',
                failure_subtype='provenance_mismatch',
            )
            sync_jobs._log_sync_job_finalized(
                finalized={'lane': 'fresh'},
                result={'outcome': 'success', 'provider': 'deepgram', 'model': 'nova-3'},
                status='completed',
                total=0,
                failed=0,
                job_id=job_id,
                attempt_ref=42,
                failure_phase=object(),
                failure_class=object(),
                failure_subtype=object(),
            )

        records = [r.getMessage() for r in caplog.records if 'event=sync_transcription_job_finalized' in r.getMessage()]
        assert f'job_ref={uuid.UUID(job_id).hex}' in records[0]
        assert f'attempt_ref={attempt_ref}' in records[0]
        assert 'failure_phase=provider_call' in records[0]
        assert 'failure_class=TimeoutError' in records[0]
        assert 'failure_subtype=provenance_mismatch' in records[0]
        assert 'failure_phase=unknown' in records[1]
        assert 'failure_class=OtherException' in records[1]
        assert 'failure_subtype=other' in records[1]
        assert 'attempt_ref=none' in records[1]


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


def _valid_sync_task_payload(**overrides):
    payload = {key: None for key in _load_cloud_tasks().SYNC_JOB_TASK_PAYLOAD_KEYS}
    payload.update(
        {
            'schema_version': 1,
            'job_id': 'job-1',
            'uid': 'uid-1',
            'raw_blob_paths': ['gs://bucket/job-1.opus'],
            'source': 'omi',
            'should_lock': False,
            'lane': 'fresh',
        }
    )
    payload.update(overrides)
    return payload


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
                cloud_tasks.enqueue_sync_job(_valid_sync_task_payload(job_id='j'))

    def test_backfill_lane_still_uses_the_main_queue(self):
        # Flag-off is the #10400 contract: every offline upload classifies as
        # backfill, and routing that lane to the bounded recovery worker used
        # to strand recordings for hours. Default-off keeps that behaviour.
        cloud_tasks = _load_cloud_tasks()
        env = {
            'SYNC_BACKFILL_ROUTING_ENABLED': 'false',
            'SYNC_TASKS_QUEUE': 'sync-jobs',
            'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
        }
        payload = _valid_sync_task_payload(lane='backfill')
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job(payload)

        enqueue.assert_called_once_with(
            'sync-jobs',
            'https://backend-sync.example.com/v2/sync-jobs/run',
            'job-1',
            payload,
        )

    def test_backfill_lane_uses_backfill_queue_when_routing_enabled(self):
        cloud_tasks = _load_cloud_tasks()
        payload = _valid_sync_task_payload(lane='backfill')
        env = {
            'SYNC_BACKFILL_ROUTING_ENABLED': 'true',
            'SYNC_TASKS_QUEUE': 'sync-jobs',
            'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
        }
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job(payload)

        enqueue.assert_called_once_with(
            'sync-backfill',
            'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
            'job-1',
            payload,
            audience='https://backend-sync-backfill.example.com/v2/sync-jobs/run',
        )

    def test_sequenced_task_uses_epoch_specific_name_on_existing_backfill_queue(self):
        cloud_tasks = _load_cloud_tasks()
        payload = _valid_sync_task_payload(lane='backfill')
        payload['sequencer_epoch'] = 7
        env = {
            'SYNC_BACKFILL_ROUTING_ENABLED': 'true',
            'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
        }
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job(payload)
        assert enqueue.call_args.args[:3] == (
            'sync-backfill',
            'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
            'job-1-s7',
        )
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job(payload, dispatch_attempt=2)
            cloud_tasks.enqueue_sync_job(payload, dispatch_attempt=2)
        assert [call.args[2] for call in enqueue.call_args_list] == ['job-1-s7-d2', 'job-1-s7-d2']
        assert all(call.args[3] == payload for call in enqueue.call_args_list)

    @pytest.mark.parametrize('sequencer', ['on', 'off'])
    def test_direct_backfill_newest_gets_earlier_eligibility(self, sequencer):
        cloud_tasks = _load_cloud_tasks()
        env = {
            'SYNC_BACKFILL_ORDER': 'newest',
            'SYNC_BACKFILL_UID_SEQUENCER': sequencer,
            'SYNC_BACKFILL_ROUTING_ENABLED': 'true',
            'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': 'https://backend-sync-backfill.example.com/run',
        }
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            for age in (3600, 21600):
                cloud_tasks.enqueue_sync_job(
                    _valid_sync_task_payload(lane='backfill', enqueued_at=1000000, recording_age_seconds=age)
                )
            assert [call.kwargs['schedule_at'] for call in enqueue.call_args_list] == [1000013, 1000075]
            cloud_tasks.enqueue_sync_job(_valid_sync_task_payload(lane='backfill', sequencer_epoch=1))
            assert 'schedule_at' not in enqueue.call_args.kwargs

    def test_explicit_oldest_cloud_task_is_byte_identical_to_default(self):
        cloud_tasks = _load_cloud_tasks()
        fake = MagicMock()
        fake.queue_path.return_value = 'projects/p/locations/l/queues/sync'
        fake.task_path.return_value = 'projects/p/locations/l/queues/sync/tasks/job-1'
        env = {
            **OIDC_ENV,
            'SYNC_TASKS_PROJECT': 'p',
            'SYNC_TASKS_LOCATION': 'l',
            'SYNC_TASKS_QUEUE': 'sync',
            'SYNC_BACKFILL_ROUTING_ENABLED': 'false',
        }
        payload = _valid_sync_task_payload(lane='backfill')
        with patch.dict(os.environ, env), patch.object(cloud_tasks, '_get_tasks_client', return_value=fake):
            os.environ.pop('SYNC_BACKFILL_ORDER', None)
            cloud_tasks.enqueue_sync_job(payload)
            default = fake.create_task.call_args.kwargs['task']
            os.environ['SYNC_BACKFILL_ORDER'] = 'oldest'
            cloud_tasks.enqueue_sync_job(payload)
            explicit = fake.create_task.call_args.kwargs['task']
            assert type(default).pb(default).SerializeToString(deterministic=True) == type(explicit).pb(
                explicit
            ).SerializeToString(deterministic=True)

    def test_fresh_lane_uses_main_queue_when_backfill_routing_enabled(self):
        cloud_tasks = _load_cloud_tasks()
        payload = _valid_sync_task_payload(lane='fresh')
        env = {
            'SYNC_BACKFILL_ROUTING_ENABLED': 'true',
            'SYNC_TASKS_QUEUE': 'sync-jobs',
            'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_QUEUE': 'sync-backfill',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE': 'https://backend-sync-backfill.example.com/v2/sync-jobs/run',
        }
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job(payload)

        enqueue.assert_called_once_with(
            'sync-jobs',
            'https://backend-sync.example.com/v2/sync-jobs/run',
            'job-1',
            payload,
        )

    def test_backfill_routing_falls_back_to_main_queue_when_env_missing(self):
        cloud_tasks = _load_cloud_tasks()
        payload = _valid_sync_task_payload(lane='backfill')
        env = {
            'SYNC_BACKFILL_ROUTING_ENABLED': 'true',
            'SYNC_TASKS_QUEUE': 'sync-jobs',
            'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/v2/sync-jobs/run',
            'SYNC_BACKFILL_TASKS_QUEUE': '',
            'SYNC_BACKFILL_TASKS_HANDLER_URL': '',
        }
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job(payload)

        enqueue.assert_called_once_with(
            'sync-jobs',
            'https://backend-sync.example.com/v2/sync-jobs/run',
            'job-1',
            payload,
        )

    def test_enqueue_rejects_payload_schema_drift_before_cloud_tasks(self):
        cloud_tasks = _load_cloud_tasks()
        payload = _valid_sync_task_payload(unexpected_field='must-not-be-admitted')
        with patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            with pytest.raises(ValueError, match='durable worker schema'):
                cloud_tasks.enqueue_sync_job(payload)
        enqueue.assert_not_called()

    @pytest.mark.parametrize('sequenced', [False, True])
    def test_enqueue_admits_capture_evidence_claims(self, sequenced):
        # Regression: routers/sync.py adds capture_evidence_claims whenever S1
        # claims parse; the exact-key check raised ValueError and wedged the
        # uid's sequencer for every claims-bearing upload.
        cloud_tasks = _load_cloud_tasks()
        extra = {'sequencer_epoch': 3} if sequenced else {}
        payload = _valid_sync_task_payload(capture_evidence_claims={'a.bin': {'version': 1}}, **extra)
        env = {'SYNC_TASKS_QUEUE': 'sync-jobs', 'SYNC_TASKS_HANDLER_URL': 'https://backend-sync.example.com/run'}
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue:
            cloud_tasks.enqueue_sync_job(payload)
        enqueue.assert_called_once()
        assert enqueue.call_args.args[3]['capture_evidence_claims'] == {'a.bin': {'version': 1}}

    def test_payload_key_validator_rejects_missing_core_key_even_with_optional(self):
        cloud_tasks = _load_cloud_tasks()
        payload = _valid_sync_task_payload(capture_evidence_claims={})
        del payload['lane']
        assert not cloud_tasks.sync_job_payload_keys_valid(payload)
        assert not cloud_tasks.sync_job_payload_keys_valid(
            {**_valid_sync_task_payload(), 'sequencer_epoch': 1}, allow_sequenced=False
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
        with patch.dict(os.environ, env), patch.object(cloud_tasks, 'enqueue_named_task') as enqueue, patch.object(
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
            ) == cloud_tasks.AccountDeletionTaskAuthentication(retry_count=0)

        assert verify.call_args.kwargs['audience'] == env['ACCOUNT_DELETION_HANDLER_URL']

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
            with patch.object(cloud_tasks, 'assert_account_deletion_queue_exists'):
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
    from services import summary_debt_repair  # noqa: F401 - load before flat database stubs

    import contextvars
    import importlib.util
    from io import BytesIO
    from fastapi.routing import APIRoute
    from models.geolocation import geolocation_from_private_header as actual_geolocation_from_private_header
    from pydantic import BaseModel
    from database.sync_jobs import SyncLedgerFenceMode
    from utils.stt import outcomes as actual_outcomes
    from utils.stt import prerecorded_health as actual_prerecorded_health
    from utils.stt import speaker_match as actual_speaker_match
    from utils.stt import speaker_identity as actual_speaker_identity
    from utils.stt import transcript_admission as actual_transcript_admission
    from utils.stt import vendor_guard as actual_vendor_guard
    from utils import manual_speaker_assignments as actual_manual_assignments
    from utils.sync import lanes as actual_sync_lanes, rate_limit as actual_rl
    from utils import capture_evidence as actual_capture_evidence

    saved_modules = {}
    prior_utils_sync = sys.modules.get('utils.sync')
    mock_sync_jobs = MagicMock()

    heavy_deps = [
        'redis',
        'database',
        'database.redis_db',
        'database._client',
        'database.auth',
        'database.conversations',
        'database.users',
        'database.user_usage',
        'database.sync_ledger',
        'database.sync_empty_recovery',
        'database.sync_backfill_sequencer',
        'database.firestore_read_metrics',
        'firebase_admin',
        'google',
        'google.cloud',
        'google.cloud.firestore_v2',
        'opuslib',
        'pydub',
        'models',
        'models.conversation',
        'models.conversation_enums',
        'models.sync_contract',
        'models.geolocation',
        'models.sync_audio',
        'models.transcript_segment',
        'utils',
        'utils.account_cutover',
        'utils.account_cutover.access',
        'utils.analytics',
        'utils.byok',
        'utils.client_device',
        'utils.cloud_tasks',
        'utils.conversations',
        'utils.conversations.process_conversation',
        'utils.sync.bridge',
        'utils.conversations.factory',
        'utils.conversations.location',
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
        'utils.product_metrics',
        'utils.journey_metrics_contract',
        'utils.sync.rate_limit',
        'utils.sync.lanes',
        'utils.sync.provenance',
        'utils.sync.capture_manifest',
        'utils.log_sanitizer',
        'utils.http_client',
        'utils.multipart',
        'utils.request_validation',
        'utils.sync.files',
        'utils.sync.playback',
        'utils.sync.backfill',
        'utils.sync.uid_sequencer',
        'utils.sync.backfill_cutover',
        'utils.sync.content_id',
        'utils.speaker_assignment',
        'utils.speaker_permissions',
        'utils.speaker_identification',
        'utils.speaker_learning_jobs',
        'utils.stt.speaker_embedding',
        'utils.stt.owner_profile',
        'python_multipart',
        'python_multipart.multipart',
    ]

    for mod_name in heavy_deps:
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = MagicMock()

    # utils.conversations is a namespace package on disk (no __init__.py), so the
    # sync pipeline's submodule imports resolve only through a real __path__.
    # Replace the heavy_deps MagicMock parent with a real-path package and keep
    # the existing submodule stubs on top of it — otherwise a new module-level
    # import like utils.conversations.deterministic_minimum fails with
    # "'utils.conversations' is not a package" during the file-path re-exec below.
    conv_pkg = types.ModuleType('utils.conversations')
    conv_pkg.__path__ = [os.path.join(BACKEND_DIR, 'utils', 'conversations')]
    saved_modules['utils.conversations'] = sys.modules.get('utils.conversations')
    sys.modules['utils.conversations'] = conv_pkg
    sys.modules['utils.conversations.deterministic_minimum'] = MagicMock()

    sys.modules['utils'].__path__ = []
    # These tests exercise Cloud Tasks dispatch, not voiceprint acquisition.
    # Register the new shared dependency under the existing non-package stubs.
    sys.modules['utils.stt.owner_profile'].load_owner_embedding = MagicMock(return_value=None)
    sys.modules['utils.stt.owner_profile'].validated_embedding = MagicMock(return_value=None)
    # Register pipeline submodules explicitly: MagicMock parents cannot resolve them.
    sys.modules['utils.conversations.location'].async_resolve_geolocation = _passthrough_async_resolve_geolocation
    sys.modules['utils.account_cutover.access'].should_skip_background_account_mutation = MagicMock(return_value=False)
    sys.modules['utils.multipart'].MultipartMaxPartSizeRoute = APIRoute
    sys.modules['utils.multipart'].SYNC_AUDIO_MAX_PART_SIZE = 200 * 1024 * 1024
    sys.modules['utils.multipart'].max_part_size = lambda _size: lambda endpoint: endpoint
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
    mock_sync_jobs.RUN_LOCK_TTL_SECONDS = 1800
    mock_sync_jobs.STALE_THRESHOLD_SECONDS = 600
    mock_sync_jobs.QUEUED_DISPATCH_STALE_SECONDS = 1800
    sys.modules['database.sync_jobs'] = mock_sync_jobs

    sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
    sys.modules['utils.fair_use'].get_hard_restriction_status = MagicMock(return_value=(False, None))
    sys.modules['utils.fair_use'].is_daily_audio_ceiling_exceeded = MagicMock(return_value=False)
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
    sys.modules['utils.sync.rate_limit'].retry_after_until_next_utc_day = actual_rl.retry_after_until_next_utc_day
    sys.modules['utils.sync'].playback = sys.modules['utils.sync.playback']
    sys.modules['utils.sync.playback'].build_playback_artifact = MagicMock(return_value=b'')
    sys.modules['utils.sync.playback'].PlaybackBuildError = type('PlaybackBuildError', (Exception,), {})
    sys.modules['utils.cloud_tasks'].is_cloud_tasks_dispatch_enabled = MagicMock(return_value=True)
    sys.modules['utils.cloud_tasks'].enqueue_sync_job = MagicMock()
    # The handler-budget resolver bounds the budget by the real dispatch
    # deadline; a MagicMock attr would silently lose comparisons inside min().
    sys.modules['utils.cloud_tasks'].DISPATCH_DEADLINE_SECONDS = 1500
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
    sys.modules['database.sync_backfill_sequencer'].enabled = MagicMock(return_value=False)
    sys.modules['database'].sync_backfill_sequencer = sys.modules['database.sync_backfill_sequencer']
    sys.modules['utils.sync'].uid_sequencer = sys.modules['utils.sync.uid_sequencer']
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
    transcription_mod.record_sync_intake_outcome = MagicMock()
    journeys_mod = types.ModuleType('utils.observability.journeys')
    journeys_mod.record_client_journey_accepted = MagicMock()
    journeys_mod.record_client_journey_terminal = MagicMock()
    journeys_mod.record_journey_accepted = MagicMock()
    shape_mod = types.ModuleType('utils.conversation_shape')
    shape_mod.observe_completed_conversation_shape = MagicMock()
    saved_modules['utils.conversation_shape'] = sys.modules.get('utils.conversation_shape')
    saved_modules['utils.stt.outcomes'] = sys.modules.get('utils.stt.outcomes')
    saved_modules['utils.stt.speaker_match'] = sys.modules.get('utils.stt.speaker_match')
    saved_modules['utils.stt.speaker_identity'] = sys.modules.get('utils.stt.speaker_identity')
    saved_modules['utils.stt.transcript_admission'] = sys.modules.get('utils.stt.transcript_admission')
    saved_modules['utils.manual_speaker_assignments'] = sys.modules.get('utils.manual_speaker_assignments')
    sys.modules['utils.observability'] = obs_pkg
    # Empty __path__ hides new observability modules. Derive the rest from disk
    # so held_content (and the next sibling) resolve; spies above stay in place.
    from testing.import_isolation import install_package_submodule_stubs

    install_package_submodule_stubs(
        'utils.observability',
        saved_modules,
        overrides={
            'utils.observability.fallback': fallback_mod,
            'utils.observability.transcription': transcription_mod,
            'utils.observability.journeys': journeys_mod,
        },
    )
    # The pipeline schedules the episodes finalize hook at module scope; the
    # fire-and-forget hook is no sync-coordinator concern, so the whole package
    # stubs like observability above (MagicMock('utils') is not a package).
    saved_modules.setdefault('utils.episodes', sys.modules.get('utils.episodes'))
    episodes_pkg = types.ModuleType('utils.episodes')
    episodes_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules['utils.episodes'] = episodes_pkg
    install_package_submodule_stubs('utils.episodes', saved_modules)
    sys.modules['utils.conversation_shape'] = shape_mod
    sys.modules['utils.stt.outcomes'] = actual_outcomes
    # Keep the empty-success guard's vendor-state reads real (stdlib+prometheus
    # only): the guard resolves them lazily at call time, and a MagicMock
    # parent for utils.stt is not a package.
    saved_modules['utils.stt.prerecorded_health'] = sys.modules.get('utils.stt.prerecorded_health')
    saved_modules['utils.stt.vendor_guard'] = sys.modules.get('utils.stt.vendor_guard')
    sys.modules['utils.stt.prerecorded_health'] = actual_prerecorded_health
    sys.modules['utils.stt.vendor_guard'] = actual_vendor_guard
    # Keep the decision policy real (pure, dependency-free): the sync pipeline now
    # calls select_speaker_match(), and a MagicMock stand-in would return a MagicMock
    # decision whose fields blow up the %.3f log formatting even on an empty match set.
    sys.modules['utils.stt.speaker_match'] = actual_speaker_match
    # Keep allocator + receipt policy real: assignment.py imports both at module
    # scope, and MagicMock parents for utils / utils.stt are not packages.
    sys.modules['utils.stt.speaker_identity'] = actual_speaker_identity
    sys.modules['utils.stt.transcript_admission'] = actual_transcript_admission
    sys.modules['utils.manual_speaker_assignments'] = actual_manual_assignments
    # Keep the S1 evidence envelope builder real (pure, stdlib-only): the sync
    # pipeline imports unknown_envelope at module scope, and a MagicMock parent
    # for utils is not a package.
    saved_modules['utils.capture_evidence'] = sys.modules.get('utils.capture_evidence')
    sys.modules['utils.capture_evidence'] = actual_capture_evidence
    saved_modules['utils.sync.lanes'] = sys.modules.get('utils.sync.lanes')
    # Keep SyncLane real: the dispatch job payload JSON-serializes lane as a str-enum
    # value, and a MagicMock lane breaks json.dumps. lanes.py is stdlib-only.
    sys.modules['utils.sync.lanes'] = actual_sync_lanes
    sys.modules['utils.metrics'] = MagicMock(OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL=mock_counter)

    class _AudioPrecacheResponse(BaseModel):
        pass

    class _AudioUrlsResponse(BaseModel):
        pass

    sys.modules['models.sync_audio'].AudioPrecacheResponse = _AudioPrecacheResponse
    sys.modules['models.sync_audio'].AudioUrlsResponse = _AudioUrlsResponse
    sys.modules['models.geolocation'].geolocation_from_private_header = actual_geolocation_from_private_header

    sys.modules.pop('routers.sync', None)
    sys.modules.pop('utils.sync.pipeline', None)
    sys.modules.pop('utils.sync.ledger_completion', None)
    spec = importlib.util.spec_from_file_location(
        'sync_post_enqueue_cleanup',
        os.path.join(BACKEND_DIR, 'routers', 'sync.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.sync_redrive = types.SimpleNamespace(
        enabled=lambda: os.getenv('SYNC_DURABLE_REDRIVE_GUARD') == 'true',
        legacy_convergence_enabled=lambda: os.getenv('SYNC_LEGACY_COMPLETION_CONVERGENCE') == 'true',
        preserve_missing_job=MagicMock(return_value='redrive_required'),
        converge_legacy_completion=MagicMock(return_value=None),
    )
    module.redrive_policy = module.sync_redrive
    module.uid_sequencer.enabled = MagicMock(return_value=False)
    module.uid_sequencer.production_fence_mode = MagicMock(
        side_effect=lambda: module.get_sync_ledger_fence_mode() if module.uid_sequencer.production_stage() else None
    )
    module.uid_sequencer.foreign_delivery = MagicMock(
        side_effect=lambda payload: not module.uid_sequencer.production_stage()
        and isinstance(payload, dict)
        and (payload.get('sequencer_epoch') is not None or payload.get('lane') == 'backfill')
    )

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
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


def test_polling_never_dispatched_queued_job_finalizes_as_dispatch_lost():
    """#10033: a queued cloud_tasks job whose task was lost finalizes with the
    dispatch-lost code so it is separable from died-worker staleness."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    stale_job = {
        'job_id': 'job-q',
        'uid': 'test-uid',
        'status': 'queued',
        'content_id': 'content-q',
        'stt_provider': 'deepgram',
        'stt_model': 'nova-3',
        'lane': 'fresh',
        'dispatch_mode': 'cloud_tasks',
        'ledger_fence_mode': 'active',
        'started_at': None,
    }
    failed_job = {**stale_job, 'status': 'failed', 'reason_code': 'sync_dispatch_lost'}
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

        response = module.get_sync_job_status('job-q', uid='test-uid')

        assert response['status'] == 'failed'
        assert response['reason_code'] == 'sync_dispatch_lost'
        assert module.finalize_sync_job_failure_now.call_args.kwargs['error_code'] == 'sync_dispatch_lost'
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


@pytest.mark.asyncio
@pytest.mark.parametrize('switch', ['on', 'off'])
async def test_sequenced_task_prepares_only_after_run_lock_and_kill_switch_skips(monkeypatch, switch):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(module, pipeline_error=None, latest_job={'status': 'completed'})
    request.json.return_value.update(lane='backfill', sequencer_epoch=7)
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY_ENABLED', switch)
    monkeypatch.setenv('SYNC_BACKFILL_OWNER_CONCURRENCY', '4')
    calls = []
    tasks = []

    def acquire(_job):
        calls.append('locked')
        return '1:lock-token'

    def warm(*args):
        assert calls[0] == 'locked'
        calls.append(args)

    def start(coro, *, name):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    module.try_acquire_sync_job_run_lock = MagicMock(side_effect=acquire)
    module.warm_owner = warm
    module.start_background_task = start
    try:
        # Enter the production body with a previously validated sequencer
        # identity; the public wrapper's lease behavior has separate coverage.
        response = await module._run_sync_job_body(request, task_retry_count=0)
        await asyncio.gather(*tasks)
        assert response.status_code == 200
        assert calls == (['locked', ('test-uid', 'job-1', 7)] if switch == 'on' else ['locked'])
        module._run_full_pipeline_background_async.assert_awaited_once()
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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

        first = await module.run_sync_job(request, task_retry_count=2)

        assert first.status_code == 500
        assert json.loads(first.body) == {'status': 'terminal_cleanup_retry', 'job_status': 'partial_failure'}
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._finalize_sync_job_failure.assert_not_awaited()
        module.delete_sync_job_run_lock_epoch.assert_not_called()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.bind_or_converge_sync_ledger_completion.assert_called_once_with(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            run_lock_token='1:lock-token',
        )

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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_persistence_fence_terminalizes_backfill_and_releases_its_slot():
    """A lifecycle-fenced processor result is terminal, not a Cloud Tasks retry."""
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=module.SyncConversationPersistenceFenced('conversation lifecycle replaced this worker'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    request.json.return_value['lane'] = 'backfill'
    setattr(module, 'finalize_sync_job_superseded', AsyncMock())
    # Sequencer off: the direct path goes straight to the processor without the
    # adoption read, so only the processor's own job reads happen.
    module.uid_sequencer.enabled = MagicMock(return_value=False)

    try:
        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'superseded'}
        module.finalize_sync_job_superseded.assert_awaited_once_with(
            job_id='job-1',
            run_lock_token='1:lock-token',
            lane='backfill',
            provider='deepgram',
            model='nova-3',
        )
        module._delete_staged_blobs_async.assert_awaited_once_with(['staged/audio.opus'])
        module.release_backfill_slot.assert_called_once_with('test-uid', 'job-1')
        module.release_sync_content_claim_after_job_retired.assert_called_once_with('test-uid', 'content-1', 'job-1')
        module.release_sync_content_claim.assert_not_called()
        module._finalize_sync_job_failure.assert_not_awaited()
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module.release_job_run_lock.assert_called_once_with('job-1', '1:lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_final_attempt_converges_a_ledger_completed_by_the_failing_pipeline():
    """A final Cloud Tasks delivery cannot overwrite its own durable completion."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('failure after durable ledger completion'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    try:
        module.bind_or_converge_sync_ledger_completion = MagicMock(
            side_effect=[None, {'total_segments': 1, 'outcome': 'success'}]
        )

        response = await module.run_sync_job(request, task_retry_count=2)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'done', 'reconciled': True}
        expected_bind = unittest.mock.call(
            job_id='job-1',
            uid='test-uid',
            content_id='content-1',
            run_lock_token='1:lock-token',
        )
        assert module.bind_or_converge_sync_ledger_completion.call_args_list == [expected_bind, expected_bind]
        module._run_full_pipeline_background_async.assert_awaited_once()
        module._finalize_sync_job_failure.assert_not_awaited()
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._delete_staged_blobs_async.assert_awaited_once_with(
            ['staged/audio.opus'], uid='test-uid', content_id='content-1', job_id='job-1'
        )
        module.release_job_run_lock.assert_called_once_with('job-1', '1:lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_final_attempt_ledger_bind_loss_preserves_retry_material():
    """A final recovery bind that loses ownership must not consume or clean the task."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('failure after a competing ledger update'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    try:
        module.bind_or_converge_sync_ledger_completion = MagicMock(
            side_effect=[None, module.SyncJobRunLeaseLost('newer ledger owner')]
        )

        response = await module.run_sync_job(request, task_retry_count=2)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module._run_full_pipeline_background_async.assert_awaited_once()
        module._finalize_sync_job_failure.assert_not_awaited()
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.release_job_run_lock.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
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
            failure_phase=None,
            failure_class='TimeoutError',
            failure_reason=SyncFailureReason.NONE,
        )
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._delete_staged_blobs_async.assert_awaited_once_with(['staged/audio.opus'])
        module.release_job_run_lock.assert_called_once_with('job-1', '1:lock-token')
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_final_attempt_keeps_the_pipeline_internal_cause():
    """A storage 429 re-raised from task mode must not be published as upstream_error."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    error = RuntimeError('bridge copy rate limited')
    setattr(error, 'sync_failure_reason', SyncFailureReason.STORAGE_RATE_LIMITED)
    setattr(error, 'sync_failure_phase', 'finalize')
    request = _configure_task_handler(
        module,
        pipeline_error=error,
        latest_job={'job_id': 'job-1', 'status': 'processing', 'stt_provider': 'deepgram', 'stt_model': 'nova-3'},
    )

    try:
        response = await module.run_sync_job(request, task_retry_count=2)

        assert json.loads(response.body) == {'status': 'failed_final'}
        kwargs = module._finalize_sync_job_failure.await_args.kwargs
        assert kwargs['failure_reason'] is SyncFailureReason.STORAGE_RATE_LIMITED
        assert kwargs['failure_phase'] == 'finalize'
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_non_retryable_failure_terminates_on_its_first_delivery():
    """A permanent failure must not spend the retry budget returning 5xx."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    from utils.stt.outcomes import TranscriptionFailure

    request = _configure_task_handler(
        module,
        pipeline_error=TranscriptionFailure(
            module.TranscriptionOutcome.CONFIG_ERROR,
            retryable=False,
        ),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'unknown',
            'stt_model': 'unknown',
        },
    )

    try:
        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'failed_final'}
        module._finalize_sync_job_failure.assert_awaited_once()
        assert (
            module._finalize_sync_job_failure.await_args.kwargs['outcome'] == module.TranscriptionOutcome.CONFIG_ERROR
        )
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._delete_staged_blobs_async.assert_awaited_once_with(['staged/audio.opus'])
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_destructive_operation_fence_retries_with_typed_error_code():
    '''A transient destructive-op fence must stay retryable and not look like STT failure.'''

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()

    class DestructiveOperationInProgress(RuntimeError):
        pass

    request = _configure_task_handler(
        module,
        pipeline_error=DestructiveOperationInProgress('legal_hold_deletion_gates kind=retention_cleanup'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'parakeet',
            'stt_model': 'parakeet',
        },
    )

    try:
        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 500
        assert json.loads(response.body) == {'status': 'retry'}
        module.fenced_mark_job_queued_for_retry.assert_called_once_with(
            'job-1', '1:lock-token', 1, 'destructive_operation_in_progress'
        )
        module._finalize_sync_job_failure.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sync_task_retryable_failure_still_retries_before_exhaustion():
    """The non-retryable short circuit must not collapse genuine transient retries."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=TimeoutError('transient upstream detail'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'parakeet',
            'stt_model': 'parakeet',
        },
    )

    try:
        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 500
        assert json.loads(response.body) == {'status': 'retry'}
        module._finalize_sync_job_failure.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_fresh_admission_daily_ceiling_prevents_staging_or_dispatch():
    """A fresh V2 upload over the hard ceiling must leave its WAL audio untouched."""
    from starlette.datastructures import UploadFile

    module, saved_modules, mock_sync_jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.is_daily_audio_ceiling_exceeded = MagicMock(return_value=True)
    module._fair_use_restriction_response = AsyncMock(
        return_value=module.JSONResponse(status_code=429, content={'code': 'fair_use_restricted'})
    )
    module.start_background_task = MagicMock()
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

        assert response.status_code == 429
        assert json.loads(response.body) == {'code': 'fair_use_restricted'}
        module.is_daily_audio_ceiling_exceeded.assert_called_once_with('test-uid')
        module._fair_use_restriction_response.assert_awaited_once()
        restriction_kwargs = module._fair_use_restriction_response.await_args.kwargs
        assert restriction_kwargs['uid'] == 'test-uid'
        assert restriction_kwargs['retry_after'] > 0
        module._retrieve_file_paths_v2.assert_not_called()
        mock_sync_jobs.create_sync_job.assert_not_called()
        module.claim_sync_content.assert_not_called()
        module.enqueue_sync_job.assert_not_called()
        module.start_background_task.assert_not_called()
        module.has_transcription_credits.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_backfill_admission_does_not_consume_fresh_daily_ceiling():
    """Historical recovery bypasses fresh ceiling and retired Redis slot with the kill switch off."""
    from starlette.datastructures import UploadFile

    module, saved_modules, mock_sync_jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.is_daily_audio_ceiling_exceeded = MagicMock(return_value=True)
    module.try_acquire_backfill_slot = MagicMock(side_effect=ConnectionError('retired slot unavailable'))
    module.start_background_task = MagicMock()
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.BACKFILL,
            trust=types.SimpleNamespace(value='legacy'),
            reason='historical_recovery',
            maximum_age_seconds=24 * 60 * 60,
            automatic_recovery_allowed=True,
        )
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')

        assert response.status_code == 202
        module.is_daily_audio_ceiling_exceeded.assert_not_called()
        module.try_acquire_backfill_slot.assert_not_called()
        mock_sync_jobs.create_sync_job.assert_called_once()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
async def test_sync_dispatch_carries_private_recording_location_into_cloud_task():
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    header = json.dumps(
        {
            'latitude': 40.7128,
            'longitude': -74.006,
            'captured_at': '2026-08-01T12:30:00Z',
            'capture_source': 'current_position',
            'accuracy': 8.5,
        }
    )

    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(
            files=[upload],
            uid='test-uid',
            x_omi_conversation_geolocation=header,
        )

        assert response.status_code == 202
        payload = module.enqueue_sync_job.call_args.args[0]
        assert payload['geolocation'] == {
            'latitude': 40.7128,
            'longitude': -74.006,
            'google_place_id': None,
            'address': None,
            'location_type': None,
            'captured_at': '2026-08-01T12:30:00Z',
            'capture_source': 'current_position',
            'accuracy': 8.5,
            'altitude': None,
        }
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        sys.modules.pop('utils.sync.ledger_completion', None)
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
        module.backfill_cutover.note_direct_admission.assert_called_once()
        assert module.backfill_cutover.note_direct_admission.call_args.args == (
            'test-uid',
            module.enqueue_sync_job.call_args.args[0]['job_id'],
        )
        module.start_background_task.assert_not_called()
        module._delete_staged_blobs_async.assert_not_awaited()
        assert not fallback_calls
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_backfill_uid_sequencer_accepts_202_without_redis_slot():
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.uid_sequencer.enabled.return_value = True
    module.sync_backfill_sequencer.get_owner = MagicMock(return_value={})
    module.sync_backfill_sequencer.register_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.try_acquire_backfill_slot = MagicMock(side_effect=AssertionError('old admission slot used'))
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.BACKFILL,
            trust=types.SimpleNamespace(value='legacy'),
            reason='unbound_capture_time',
            maximum_age_seconds=60,
            oldest_capture_at=time.time() - 60,
            automatic_recovery_allowed=True,
        )
    )
    try:
        response = await module.sync_local_files_v2(
            files=[UploadFile(filename='recent-offline.opus', file=BytesIO(b'\x00' * 10))], uid='test-uid'
        )
        assert response.status_code == 202
        assert json.loads(response.body)['status'] == 'queued'
        module.sync_backfill_sequencer.register_job.assert_called_once()
        module.uid_sequencer.kick.assert_called_once_with('test-uid')
        module.enqueue_sync_job.assert_not_called()
        module.try_acquire_backfill_slot.assert_not_called()
        assert module.create_sync_job.call_args.kwargs['dispatch_mode'] == 'sequenced'
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_backfill_registration_error_never_acks_202_or_releases_ambiguous_claim():
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.uid_sequencer.enabled.return_value = True
    module.sync_backfill_sequencer.register_job = MagicMock(side_effect=ConnectionError('write acknowledgement lost'))
    module.sync_backfill_sequencer.is_registered = MagicMock(side_effect=ConnectionError('read unavailable'))
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.BACKFILL,
            trust=types.SimpleNamespace(value='legacy'),
            reason='unbound_capture_time',
            maximum_age_seconds=60,
            oldest_capture_at=time.time() - 60,
            automatic_recovery_allowed=True,
        )
    )
    try:
        with pytest.raises(module.HTTPException) as error:
            await module.sync_local_files_v2(
                files=[UploadFile(filename='recent-offline.opus', file=BytesIO(b'\x00' * 10))], uid='test-uid'
            )
        assert error.value.status_code == 500
        module.release_sync_content_claim.assert_not_called()
        module.enqueue_sync_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_known_unregistered_backfill_cleans_up_and_returns_retryable_503():
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.uid_sequencer.enabled.return_value = True
    module.sync_backfill_sequencer.register_job = MagicMock(side_effect=ConnectionError('write rejected'))
    module.sync_backfill_sequencer.is_registered = MagicMock(return_value=False)
    module._delete_staged_blobs_async = AsyncMock()
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.BACKFILL,
            trust=types.SimpleNamespace(value='legacy'),
            reason='unbound_capture_time',
            maximum_age_seconds=60,
            oldest_capture_at=time.time() - 60,
            automatic_recovery_allowed=True,
        )
    )
    try:
        response = await module.sync_local_files_v2(
            files=[UploadFile(filename='recent-offline.opus', file=BytesIO(b'\x00' * 10))], uid='test-uid'
        )
        assert response.status_code == 503
        assert json.loads(response.body)['code'] == 'sync_dispatch_unavailable'
        module._delete_staged_blobs_async.assert_awaited_once()
        module._finalize_sync_job_failure.assert_awaited_once()
        module.enqueue_sync_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
@pytest.mark.parametrize('idle_owner', [{}, {'epoch': 3, 'reconcile_at': 0}])
async def test_old_backfill_task_migrates_on_flag_on_and_runs_direct_when_off(idle_owner):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    payload = {
        'uid': 'test-uid',
        'job_id': 'job-1',
        'lane': 'backfill',
        'enqueued_at': 1000.0,
        'recording_age_seconds': 60,
    }
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    module.get_sync_job = MagicMock(return_value={'status': 'queued'})
    module.uid_sequencer.enabled.return_value = True
    module.sync_backfill_sequencer.get_owner = MagicMock(return_value=idle_owner)
    module.sync_backfill_sequencer.has_pending = MagicMock(return_value=False)
    module.sync_backfill_sequencer.register_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module._run_sync_job_body = AsyncMock(return_value=module.JSONResponse(status_code=200, content={'status': 'done'}))
    try:
        migrated = await module.run_sync_job(request, task_retry_count=0)
        assert migrated.status_code == 200
        module.sync_backfill_sequencer.register_job.assert_called_once()
        assert module.sync_backfill_sequencer.register_job.call_args.args[-1] == 940.0
        module._run_sync_job_body.assert_not_awaited()

        # Kill switch: a sequenced backlog must not pull direct work back into
        # the one-per-UID queue, nor pause that queue's drain.
        module.uid_sequencer.enabled.return_value = False
        module.backfill_cutover.refresh_direct_run.reset_mock()
        for owner, has_pending in (
            (idle_owner, False),
            ({'active_job_id': 'older-sequenced-job'}, False),
            (idle_owner, True),
        ):
            module.sync_backfill_sequencer.get_owner.return_value = owner
            module.sync_backfill_sequencer.has_pending.return_value = has_pending
            direct = await module.run_sync_job(request, task_retry_count=0)
            assert direct.status_code == 200
        assert module.sync_backfill_sequencer.register_job.call_count == 1
        assert module._run_sync_job_body.await_count == 3
        module.backfill_cutover.refresh_direct_run.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'payload',
    [
        {'uid': 'test-uid', 'job_id': 'job-1', 'lane': 'backfill', 'sequencer_epoch': 3},
        {'uid': 'test-uid', 'job_id': 'job-1', 'lane': 'backfill'},
    ],
    ids=['sequenced', 'legacy-backfill'],
)
async def test_dev_sync_job_route_acks_before_shared_state_access(payload):
    module, saved_modules, mock_sync_jobs, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    module.uid_sequencer.production_stage = MagicMock(return_value=False)
    module.get_sync_ledger_fence_mode = MagicMock()
    module._run_sync_job_body = AsyncMock()
    module.get_sync_job = MagicMock()
    module.try_acquire_job_run_lock = MagicMock()
    module.sync_backfill_sequencer.reset_mock()
    module.backfill_cutover.reset_mock()
    mock_sync_jobs.reset_mock()
    redis_client = sys.modules['database.redis_db'].r
    redis_client.reset_mock()
    try:
        assert any(dep.dependency is module.sync_stage.require_http_stage for dep in module.router.dependencies)
        route = next(route for route in module.router.routes if route.path == '/v2/sync-jobs/run')
        response = await route.endpoint(request, task_retry_count=0)
        assert response.status_code == 200
        assert response.body == b'{"status":"foreign_stage"}'
        module.get_sync_ledger_fence_mode.assert_not_called()
        module.get_sync_job.assert_not_called()
        module.try_acquire_job_run_lock.assert_not_called()
        module._run_sync_job_body.assert_not_awaited()
        assert module.sync_backfill_sequencer.mock_calls == []
        assert module.backfill_cutover.mock_calls == []
        assert mock_sync_jobs.mock_calls == []
        assert redis_client.mock_calls == []  # No sync_backfill:uid_sequencer:* writes.
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_old_processing_backfill_emits_cutover_overlap_log(caplog):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'lane': 'backfill'})
    module.get_sync_job = MagicMock(return_value={'status': 'processing'})
    module.sync_backfill_sequencer.get_owner = MagicMock(return_value={'active_job_id': 'sequenced-job'})
    module.uid_sequencer.enabled.return_value = True
    module.backfill_cutover.uid_hash = MagicMock(return_value='private-hash')
    module._run_sync_job_body = AsyncMock(return_value=module.JSONResponse(status_code=200, content={'status': 'done'}))
    try:
        with caplog.at_level(logging.ERROR):
            response = await module.run_sync_job(request, task_retry_count=0)
        assert response.status_code == 200
        assert (
            'action=cutover_overlap outcome=direct_and_sequenced job_id=job-1 sequenced_job_id=sequenced-job uid_hash=private-hash'
            in caplog.text
        )
        assert 'test-uid' not in caplog.text
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sequenced_worker_retries_then_releases_terminal_failure_and_acks_duplicate():
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
    module.sync_backfill_sequencer.begin_job = MagicMock(side_effect=[True, True, False])
    module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.get_sync_job = MagicMock(return_value={'status': 'failed', 'attempt': 2})
    module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
    module._run_sync_job_body = AsyncMock(
        side_effect=[
            module.JSONResponse(status_code=500, content={'status': 'retry'}),
            module.JSONResponse(status_code=200, content={'status': 'failed_final'}),
        ]
    )
    try:
        retry = await module.run_sync_job(request, task_retry_count=0)
        assert retry.status_code == 500
        module.sync_backfill_sequencer.finish_job.assert_not_called()
        terminal = await module.run_sync_job(request, task_retry_count=0)
        assert terminal.status_code == 200
        assert module._run_sync_job_body.call_args.args[1] == 2
        module.sync_backfill_sequencer.finish_job.assert_called_once_with('test-uid', 'job-1', 3, 'failed')
        module.uid_sequencer.kick.assert_called_once_with('test-uid')
        duplicate = await module.run_sync_job(request, task_retry_count=0)
        assert duplicate.status_code == 200
        assert module._run_sync_job_body.await_count == 2
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sequenced_request_budget_is_anchored_at_route_entry():
    """The sequenced wrapper performs fence/begin/prior-read I/O before the
    attempt body runs; a stall there must be charged against the same single
    handler budget wall, not grant a fresh full budget afterwards — otherwise
    the request could still overshoot the Cloud Tasks dispatch deadline this
    cap exists to stay under. The anchor is captured at route entry and rides
    the shared attempt-state dict into the budget."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
    module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.get_sync_job = MagicMock(return_value={'status': 'completed', 'attempt': 1})
    module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
    captured = {}

    async def _capture_body(req, retry_count, attempt_state=None):
        captured['state'] = attempt_state
        return module.JSONResponse(status_code=200, content={'status': 'completed_final'})

    module._run_sync_job_body = AsyncMock(side_effect=_capture_body)
    try:
        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        anchor = captured['state'].get('budget_deadline_monotonic')
        # The anchor is an absolute deadline on the module's own monotonic
        # clock: captured at route entry, so it sits one full handler budget
        # ahead of the body's start (the fast preamble consumes only ms of
        # it). A budget granted fresh inside the body would anchor at body
        # start — indistinguishable here — but a stall in begin_job or the
        # prior-job read would push this deadline's remaining headroom below
        # the full budget, which is exactly the charge-at-route-entry
        # contract.
        assert isinstance(anchor, float)
        now = module.time.monotonic()
        assert now < anchor
        assert anchor <= now + module.SYNC_JOB_HANDLER_BUDGET_SECONDS + 5
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_sequenced_request_budget_is_anchored_at_middleware_request_start():
    """A slow verify_cloud_tasks_oidc resolves before the route handler runs,
    so anchoring the budget at route entry would hand the handler a deadline
    that can cross HTTP_SYNC_JOBS_RUN_TIMEOUT after an auth stall — the exact
    lingering-request path this budget exists to prevent. The deadline must
    derive from the middleware's request-start stamp (the same
    omi_request_started_monotonic state utils.other.list_budget anchors read
    budgets on), falling back to route entry only when no stamp exists."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    # Simulate the TimeoutMiddleware stamp written before call_next: the
    # request started 42s before the handler began resolving dependencies.
    request.state = types.SimpleNamespace(omi_request_started_monotonic=time.monotonic() - 42.0)
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
    module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.get_sync_job = MagicMock(return_value={'status': 'completed', 'attempt': 1})
    module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
    captured = {}

    async def _capture_body(req, retry_count, attempt_state=None):
        captured['state'] = attempt_state
        return module.JSONResponse(status_code=200, content={'status': 'completed_final'})

    module._run_sync_job_body = AsyncMock(side_effect=_capture_body)
    try:
        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        anchor = captured['state'].get('budget_deadline_monotonic')
        assert isinstance(anchor, float)
        # The anchor sits a full handler budget after the middleware's
        # request start, not after route entry: with a 42s-old stamp the
        # deadline must already be 42s closer than a freshly granted budget.
        now = module.time.monotonic()
        assert anchor <= now + module.SYNC_JOB_HANDLER_BUDGET_SECONDS - 40
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


def test_sync_task_budget_expiry_during_route_preamble_records_preamble_timeout_reason():
    """The preamble-deadline branches record reason='preamble_timeout'; the
    fallback vocabulary must contain it or bucket_reason silently exports it
    as 'other' and operators cannot distinguish route-setup expiry from
    unrelated fallback failures (backend/AGENTS.md fallback telemetry rule)."""

    from utils.observability.fallback import ALLOWED_REASONS, bucket_reason

    assert 'preamble_timeout' in ALLOWED_REASONS
    assert bucket_reason('preamble_timeout') == 'preamble_timeout'


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
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_oversized_backfill_upload_is_rejected_before_staging_or_custody_transfer():
    from starlette.datastructures import UploadFile
    from utils.sync.input_limits import MAX_BACKFILL_FILES

    module, saved_modules, jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.classify_sync_lane = MagicMock(
        return_value=types.SimpleNamespace(
            lane=module.SyncLane.BACKFILL,
            reason='synthetic',
            trust=module.CaptureTimeTrust.LEGACY,
            maximum_age_seconds=None,
        )
    )
    try:
        uploads = [UploadFile(filename='test.opus', file=BytesIO(b'')) for _ in range(MAX_BACKFILL_FILES + 1)]
        with pytest.raises(module.HTTPException) as error:
            await module.sync_local_files_v2(files=uploads, uid='test-uid')
        assert error.value.status_code == 413
        module._retrieve_file_paths_v2.assert_not_called()
        jobs.create_sync_job.assert_not_called()
        module.claim_sync_content.assert_not_called()
        module.enqueue_sync_job.assert_not_called()
        assert all(upload.file.tell() == 0 for upload in uploads)
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _decision(module, lane, reason='synthetic'):
    return types.SimpleNamespace(
        lane=lane,
        reason=reason,
        trust=module.CaptureTimeTrust.LEGACY,
        maximum_age_seconds=None,
        automatic_recovery_allowed=True,
    )


def _restore_modules(saved_modules):
    sys.modules.pop('routers.sync', None)
    sys.modules.pop('utils.sync.pipeline', None)
    for name, original in saved_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy_fresh_admits', [False, True])
async def test_over_cap_upload_in_the_final_fresh_lane_is_not_rejected_by_the_backfill_cap(legacy_fresh_admits):
    from starlette.datastructures import UploadFile
    from utils.sync.input_limits import MAX_BACKFILL_FILES

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    if legacy_fresh_admits:
        module.classify_sync_lane = MagicMock(
            return_value=_decision(module, module.SyncLane.BACKFILL, 'recent_legacy_capture')
        )
        module.legacy_fresh = types.SimpleNamespace(
            enabled_for=MagicMock(return_value=True),
            admit=MagicMock(return_value=_decision(module, module.SyncLane.FRESH, 'recent_legacy_capture')),
        )
    else:
        module.classify_sync_lane = MagicMock(return_value=_decision(module, module.SyncLane.FRESH))
    module.validate_backfill_uploads = MagicMock()
    try:
        uploads = [UploadFile(filename='test.opus', file=BytesIO(b'')) for _ in range(MAX_BACKFILL_FILES + 1)]
        try:
            await module.sync_local_files_v2(files=uploads, uid='test-uid')
        except module.HTTPException as error:
            assert error.status_code != 413
        except Exception:
            pass  # Later fresh-lane stubs may stop the call; only the cap matters here.
        module.validate_backfill_uploads.assert_not_called()
    finally:
        _restore_modules(saved_modules)


@pytest.mark.asyncio
async def test_v1_over_limit_backfill_upload_keeps_the_retryable_503_not_a_413():
    from starlette.datastructures import UploadFile
    from utils.sync.input_limits import MAX_BACKFILL_FILES

    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.classify_sync_lane = MagicMock(return_value=_decision(module, module.SyncLane.BACKFILL))
    module.validate_backfill_uploads = MagicMock()
    module.resolve_client_device_from_request = MagicMock(
        return_value=types.SimpleNamespace(device_hash='h', platform='p', app_version='v', client_device_id=None)
    )
    module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
    try:
        uploads = [UploadFile(filename='test.opus', file=BytesIO(b'')) for _ in range(MAX_BACKFILL_FILES + 1)]
        request = MagicMock()
        request.headers = {}
        response = await module.sync_local_files(
            request=request, response=MagicMock(headers={}), files=uploads, uid='u'
        )
        assert response.status_code == 503
        assert json.loads(response.body)['code'] == 'backfill_capacity'
        module.validate_backfill_uploads.assert_not_called()
    finally:
        _restore_modules(saved_modules)


@pytest.mark.asyncio
@pytest.mark.parametrize('pressure', [False, True])
async def test_backfill_limit_or_tmpfs_pressure_preserves_legacy_audio_and_claims(pressure):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=module.BackfillStoragePressure('synthetic') if pressure else RuntimeError('must not run'),
        latest_job={'job_id': 'job-1', 'status': 'queued', 'lane': 'backfill'},
    )
    payload = await request.json()
    payload['lane'] = 'backfill'
    request.json = AsyncMock(return_value=payload)
    module.uid_sequencer.foreign_delivery = MagicMock(return_value=False)
    if not pressure:
        module._download_staged_files.side_effect = module.BackfillInputLimitExceeded('synthetic')
    try:
        response = await module.run_sync_job(request, task_retry_count=100)
        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module._delete_staged_blobs_async.assert_not_awaited()
        module._finalize_sync_job_failure.assert_not_awaited()
        module.release_sync_content_claim_after_job_retired.assert_not_called()
        module.release_job_run_lock.assert_called_once()
        module.fenced_mark_job_queued_for_retry.assert_called_once_with(
            'job-1', '1:lock-token', 101, 'sync_resource_limit'
        )
        if not pressure:
            module._run_full_pipeline_background_async.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))


@pytest.mark.asyncio
@pytest.mark.parametrize('owner_job_id', ['existing-owner', None])
async def test_busy_upload_exposes_existing_owner_without_dispatching(owner_job_id):
    from starlette.datastructures import UploadFile

    module, saved_modules, jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.claim_sync_content = MagicMock(return_value={'outcome': 'busy', 'job_id': owner_job_id})
    module.start_background_task = MagicMock()
    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')
        assert response.status_code == 409
        assert response.headers['retry-after'] == '10'
        body = json.loads(response.body)
        assert body['code'] == 'sync_content_in_progress'
        assert body['job_id'] == owner_job_id
        assert body['poll_after_ms'] == 10000
        jobs.delete_sync_job.assert_called_once_with(module.claim_sync_content.call_args.args[2])
        assert jobs.delete_sync_job.call_args.args[0] != owner_job_id
        module.enqueue_sync_job.assert_not_called()
        module.start_background_task.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'flag,percent,reply,expected',
    [
        ('false', '100', 1, 'backfill'),
        ('true', '100', 1, 'fresh'),
        ('true', '100', 0, 'backfill'),
        ('true', '100', None, 'backfill'),
        ('true', '0', 1, 'backfill'),
    ],
)
async def test_legacy_fresh_budget_decides_persisted_and_dispatched_lane(monkeypatch, flag, percent, reply, expected):
    """Exercise the production admission handler; proof stays LEGACY in both lanes."""
    from starlette.datastructures import UploadFile
    from utils.sync import lanes, legacy_fresh

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', flag)
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', percent)
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda _: time.time() - 60)
    redis = MagicMock()
    redis.eval.return_value = reply
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.legacy_fresh = legacy_fresh
    module.classify_sync_lane = lanes.classify_sync_lane
    module.verify_capture_manifest = MagicMock(return_value=None)
    module.start_background_task = MagicMock()
    try:
        upload = UploadFile(filename='recent.bin', file=BytesIO(b'\x00' * 10), size=10)
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')
        assert response.status_code == 202
        assert json.loads(response.body)['lane'] == expected
        assert module.create_sync_job.call_args.kwargs['lane'] == expected
        assert module.create_sync_job.call_args.kwargs['capture_time_trust'] == 'legacy'
        assert module.enqueue_sync_job.call_args.args[0]['lane'] == expected
        assert module.enqueue_sync_job.call_args.args[0]['capture_time_trust'] == 'legacy'
        module.start_background_task.assert_not_called()
        if flag == 'false' or percent == '0':
            redis.eval.assert_not_called()
        else:
            redis.eval.assert_called_once()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.parametrize(
    'reply,gate,expected',
    [(1, None, 'fresh'), (0, None, 'backfill'), (1, 'hard_restriction', 'backfill'), (1, 'daily_ceiling', 'backfill')],
)
def test_legacy_fresh_http_multipart_measures_bytes_and_returns_lane(monkeypatch, reply, gate, expected):
    """HTTP multipart -> actual handler -> persisted task, with synthetic storage/auth."""
    from fastapi import FastAPI, File, UploadFile
    from fastapi.testclient import TestClient
    from utils.sync import lanes, legacy_fresh

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', '100')
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda _: time.time() - 60)
    redis = MagicMock()
    redis.eval.return_value = reply
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    module.legacy_fresh = legacy_fresh
    module.classify_sync_lane = lanes.classify_sync_lane
    module.verify_capture_manifest = MagicMock(return_value=None)
    module.get_hard_restriction_status = MagicMock(return_value=(gate == 'hard_restriction', 600))
    module.is_daily_audio_ceiling_exceeded = MagicMock(return_value=gate == 'daily_ceiling')
    module._fair_use_restriction_response = AsyncMock()
    try:
        # Restore the real multipart parser at the transport boundary; all other
        # test seams remain synthetic. This verifies UploadFile.size provenance.
        for name in ('python_multipart', 'python_multipart.multipart'):
            original = saved_modules.get(name)
            if original is not None:
                sys.modules[name] = original
        app = FastAPI()

        @app.post('/v2/sync-local-files')
        async def upload(files: list[UploadFile] = File(...)):
            return await module.sync_local_files_v2(files=files, uid='test-uid')

        response = TestClient(app).post('/v2/sync-local-files', files={'files': ('recent.bin', b'abc', 'audio/opus')})
        assert response.status_code == 202
        assert response.json()['lane'] == expected
        assert module.enqueue_sync_job.call_args.args[0]['lane'] == expected
        assert redis.eval.call_args.args[-1] == 1
        module._fair_use_restriction_response.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
@pytest.mark.parametrize('trust', ['legacy', 'device_bound'])
@pytest.mark.parametrize('gate', ['hard_restriction', 'daily_ceiling'])
async def test_fresh_only_refusal_demotes_legacy_but_keeps_device_bound_429(monkeypatch, trust, gate):
    """Optional LEGACY promotion must never turn backfill acceptance into 429."""
    from starlette.datastructures import UploadFile
    from utils.sync import lanes, legacy_fresh

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', '100')
    monkeypatch.setenv('SYNC_BACKFILL_ENABLED', 'true')
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda _: time.time() - 60)
    redis = MagicMock()
    redis.eval.return_value = 1
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.legacy_fresh = legacy_fresh
    module.classify_sync_lane = lanes.classify_sync_lane
    module.verify_capture_manifest = MagicMock(return_value=None if trust == 'legacy' else {})
    module.get_hard_restriction_status = MagicMock(return_value=(gate == 'hard_restriction', 600))
    module.is_daily_audio_ceiling_exceeded = MagicMock(return_value=gate == 'daily_ceiling')
    module._fair_use_restriction_response = AsyncMock(
        return_value=module.JSONResponse(status_code=429, content={'code': 'fair_use_restricted'})
    )
    module.OMI_SYNC_LANE_ADMISSIONS_TOTAL = MagicMock()
    module.logger = MagicMock()
    module.start_background_task = MagicMock()
    try:
        upload = UploadFile(filename='recent.bin', file=BytesIO(b'abc'), size=3)
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')
        if trust == 'legacy':
            assert response.status_code == 202
            assert json.loads(response.body)['lane'] == 'backfill'
            assert module.create_sync_job.call_args.kwargs['lane'] == 'backfill'
            assert module.create_sync_job.call_args.kwargs['capture_time_trust'] == 'legacy'
            payload = module.enqueue_sync_job.call_args.args[0]
            assert payload['lane'] == 'backfill'
            assert payload['capture_time_trust'] == 'legacy'
            module._retrieve_file_paths_v2.assert_called_once()
            module._fair_use_restriction_response.assert_not_awaited()
            reason = 'legacy_fresh_hard_restricted' if gate == 'hard_restriction' else 'legacy_fresh_daily_ceiling'
            module.OMI_SYNC_LANE_ADMISSIONS_TOTAL.labels.assert_called_once_with(
                lane='backfill', trust='legacy', reason=reason
            )
            admission_log = next(
                c for c in module.logger.info.call_args_list if c.args[0].startswith('sync_lane_admission')
            )
            assert admission_log.args[-1] == reason
        else:
            assert response.status_code == 429
            assert json.loads(response.body) == {'code': 'fair_use_restricted'}
            module._fair_use_restriction_response.assert_awaited_once()
            retry = module._fair_use_restriction_response.await_args.kwargs['retry_after']
            assert retry == 600 if gate == 'hard_restriction' else retry > 0
            module._retrieve_file_paths_v2.assert_not_called()
            module.create_sync_job.assert_not_called()
            module.enqueue_sync_job.assert_not_called()
            redis.eval.assert_not_called()
            module.OMI_SYNC_LANE_ADMISSIONS_TOTAL.labels.assert_called_once_with(
                lane='fresh', trust='device_bound', reason='recent_capture'
            )
        if gate == 'hard_restriction':
            module.is_daily_audio_ceiling_exceeded.assert_not_called()
        else:
            module.is_daily_audio_ceiling_exceeded.assert_called_once_with('test-uid')
        module.start_background_task.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_legacy_fresh_refusal_preserves_backfill_pause_instead_of_429(monkeypatch):
    from starlette.datastructures import UploadFile
    from utils.sync import lanes, legacy_fresh

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LEGACY_FRESH_PERCENT', '100')
    monkeypatch.setenv('SYNC_BACKFILL_ENABLED', 'false')
    monkeypatch.setattr(lanes, 'parse_sync_filename_timestamp', lambda _: time.time() - 60)
    redis = MagicMock()
    redis.eval.return_value = 1
    monkeypatch.setattr(legacy_fresh, 'redis_client', redis)
    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.legacy_fresh = legacy_fresh
    module.classify_sync_lane = lanes.classify_sync_lane
    module.verify_capture_manifest = MagicMock(return_value=None)
    module.get_hard_restriction_status = MagicMock(return_value=(True, 600))
    module._fair_use_restriction_response = AsyncMock()
    try:
        response = await module.sync_local_files_v2(
            files=[UploadFile(filename='recent.bin', file=BytesIO(b'abc'), size=3)], uid='test-uid'
        )
        assert response.status_code == 503
        assert json.loads(response.body)['code'] == 'backfill_capacity'
        module._fair_use_restriction_response.assert_not_awaited()
        module._retrieve_file_paths_v2.assert_not_called()
        module.create_sync_job.assert_not_called()
        module.enqueue_sync_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig


@pytest.mark.asyncio
async def test_byok_upload_enters_batch_admission_like_any_upload(monkeypatch):
    """David 10-19: no special BYOK path; the request keys are never needed by the batch stages."""
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'test-uid')
    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    transaction, store = MagicMock(), MagicMock()
    transaction.get.return_value = {}
    store.run.side_effect = lambda body: body(transaction)
    monkeypatch.setattr(_batch_intake, 'FirestoreStore', lambda *_: store)
    module.has_byok_keys = MagicMock(return_value=True)
    authorize = MagicMock(side_effect=RuntimeError('synthetic staging stop'))
    monkeypatch.setattr(_batch_intake, 'batch_artifact_authorize', authorize)
    accepted = AsyncMock(wraps=_batch_intake.accept_upload)
    module.accept_batch_upload = accepted
    try:
        response = await module.sync_local_files_v2(
            files=[UploadFile(filename='test.opus', file=BytesIO(b'synthetic-audio'))],
            uid='test-uid',
            conversation_id='unowned-record',
        )
        # The synthetic stop inside batch admission answers the ordinary batch retry, not a BYOK hold.
        assert response.status_code == 503
        assert json.loads(response.body)['code'] == 'sync_batch_unavailable'
        accepted.assert_awaited_once()
        assert accepted.call_args.kwargs['byok_enabled'] is True
        authorize.assert_called_once()
        transaction.put.assert_not_called()
        module.create_sync_job.assert_not_called()
        module.claim_sync_content.assert_not_called()
        module.enqueue_sync_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
@pytest.mark.parametrize('batch_status', [202, 503])
async def test_batch_cohort_upload_never_dispatches_or_claims_legacy(monkeypatch, batch_status):
    """Even ambiguous batch admission owns the route; it must never fall through."""
    from starlette.datastructures import UploadFile
    from fastapi.responses import JSONResponse

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    module, saved_modules, mock_sync_jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    accepted = AsyncMock(return_value=JSONResponse(status_code=batch_status, content={'job_id': 'bp_synthetic'}))
    module.accept_batch_upload = accepted
    module._run_full_pipeline_background_async = AsyncMock()
    try:
        upload = UploadFile(filename='test.opus', file=BytesIO(b'synthetic-audio'))
        response = await module.sync_local_files_v2(files=[upload], uid='test-uid')
        assert response.status_code == batch_status
        accepted.assert_awaited_once()
        module.create_sync_job.assert_not_called()
        module.claim_sync_content.assert_not_called()
        module.enqueue_sync_job.assert_not_called()
        module.release_sync_content_claim.assert_not_called()
        module._run_full_pipeline_background_async.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_coalesced_enrichment_task_uses_adapter_before_legacy_job_parsing(monkeypatch):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    handler = AsyncMock(return_value=module.JSONResponse(status_code=200, content={'status': 'processed'}))
    module.enrichment_response = handler
    request = MagicMock()
    payload = {'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32}
    request.json = AsyncMock(return_value=payload)
    try:
        response = await module.run_sync_job(request, task_retry_count=0)
        assert response.status_code == 200
        handler.assert_awaited_once_with(payload)
        module.get_sync_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_cohort_prior_legacy_receipt_retains_original_claim_and_dispatch(monkeypatch):
    from starlette.datastructures import UploadFile

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    module, saved_modules, _, BytesIO, _, _ = _load_sync_router_for_fast_path()
    module.accept_batch_upload = AsyncMock(return_value=None)
    try:
        response = await module.sync_local_files_v2(
            files=[UploadFile(filename='test.opus', file=BytesIO(b'synthetic-audio'))], uid='test-uid'
        )
        assert response.status_code == 202
        module.accept_batch_upload.assert_awaited_once()
        module.claim_sync_content.assert_called_once()
        module.enqueue_sync_job.assert_called_once()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_legacy_completion_convergence_before_provider_under_lock(monkeypatch):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('provider must not run'),
        latest_job={'job_id': 'job-1', 'status': 'processing'},
    )
    try:
        monkeypatch.setenv('SYNC_LEGACY_COMPLETION_CONVERGENCE', 'true')
        module.sync_job_uses_ledger_fence = MagicMock(return_value=False)
        module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.LEGACY)
        module.sync_redrive.converge_legacy_completion = MagicMock(return_value={'status': 'completed'})
        response = await module.run_sync_job(request, task_retry_count=0)
        assert response.status_code == 200
        assert json.loads(response.body)['reconciled'] is True
        module.sync_redrive.converge_legacy_completion.assert_called_once_with(
            job_id='job-1', uid='test-uid', content_id='content-1', run_lock_token='legacy-lock-token'
        )
        module._download_staged_files.assert_not_called()
        module._run_full_pipeline_background_async.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_pipeline_budget_ends_attempt_before_platform_timeout():
    """A pipeline that outlives the in-request budget must be cancelled and the
    attempt handed back to Cloud Tasks without releasing ownership. Without the
    budget, the 504 from TimeoutMiddleware does not cancel the pipeline, the
    request stays open until the work finishes, and Cloud Run terminates it at
    the service's maximum request timeout — the platform kill this guards
    against."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        # Below HTTP_SYNC_JOBS_RUN_TIMEOUT (1500s) and the Cloud Tasks dispatch
        # deadline, leaving room for the retry response to reach the queue.
        assert 0 < module.SYNC_JOB_HANDLER_BUDGET_SECONDS < module.SYNC_JOB_ROUTE_TIMEOUT_SECONDS
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        before = time.time()

        response = await module.run_sync_job(request, task_retry_count=0)

        # A budget expiry is a lease loss, not a generic retry: an executor
        # leaf can still be mutating state under this token, so the job stays
        # owned (no queued-reset, no terminal failure, no staged-blob delete,
        # no lock release). The preserved lock outlives every queue-level
        # retry, so instead of a 409 that would burn the task's remaining
        # attempts against it, the attempt acks and schedules one replacement
        # named task past the lock's TTL.
        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        payload, schedule_at = module.enqueue_sync_job_budget_replacement.call_args.args
        assert payload['job_id'] == 'job-1'
        assert (
            before + module.RUN_LOCK_TTL_SECONDS
            <= schedule_at
            <= time.time() + module.SYNC_JOB_BUDGET_REPLACEMENT_DELAY_SECONDS
        )
        # The replacement carries the chain count so repeated expiries end at
        # the queue's attempt contract instead of chaining forever.
        assert payload[module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY] == 1
        # The preserved lock expires before the replacement is due; the job
        # is marked deferred so a poll in that gap cannot finalize it stale.
        # The horizon covers queue congestion past schedule_at (the poller's
        # own queued-dispatch-stale allowance), not just the stale threshold.
        module.update_sync_job.assert_called_once_with(
            'job-1', {'deferred_until': schedule_at + module.QUEUED_DISPATCH_STALE_SECONDS}
        )
        assert fallback_calls == []
        module.fenced_mark_job_queued_for_retry.assert_not_called()
        module._finalize_sync_job_failure.assert_not_awaited()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.release_job_run_lock.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_counts_pre_pipeline_io_from_handler_entry():
    """The budget must anchor at handler entry, not at the pipeline call: a
    slow staged-file download consumes the same request clock the middleware
    measures, so expiry during pre-pipeline I/O must still end the attempt
    with ownership preserved instead of letting the pipeline start with a
    budget the platform timeout can outlive."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not start'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    passthrough_run_blocking = module.run_blocking

    async def _download_hangs(_executor, fn, *args, **kwargs):
        if fn is module._download_staged_files:
            await asyncio.sleep(30)
        return await passthrough_run_blocking(_executor, fn, *args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.run_blocking = _download_hangs

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        module._run_full_pipeline_background_async.assert_not_awaited()
        module._finalize_sync_job_failure.assert_not_awaited()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.release_job_run_lock.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_missing_job_guard_retains_payload_before_ack_and_keeps_staged_bytes(monkeypatch):
    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(module, pipeline_error=RuntimeError('unused'), latest_job={})
    try:
        monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
        module.get_sync_job = MagicMock(return_value=None)
        response = await module.run_sync_job(request, task_retry_count=0)
        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'redrive_required'}
        module.sync_redrive.preserve_missing_job.assert_called_once()
        module._delete_staged_blobs_async.assert_not_awaited()
        module.release_sync_content_claim.assert_not_called()
        module.release_sync_content_claim_after_job_retired.assert_not_called()
        module._run_full_pipeline_background_async.assert_not_awaited()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_expiry_falls_back_to_409_when_replacement_not_schedulable():
    """The deferred ack must never drop the job: when the replacement task
    cannot be scheduled, the 409 keeps Cloud Tasks' own retry owning the
    redelivery exactly as before, preserved lock and all."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        module.enqueue_sync_job_budget_replacement = MagicMock(side_effect=RuntimeError('create_task failed'))

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        module.release_job_run_lock.assert_not_called()
        # The marker written before the failed enqueue is cleared: it names a
        # replacement that does not exist, and left in place it would suppress
        # stale self-heal long past the preserved run lock's TTL while the
        # 409's queue-owned retries exhaust inside that TTL.
        assert module.update_sync_job.call_count == 2
        assert module.update_sync_job.call_args == unittest.mock.call('job-1', {'deferred_until': None})
        # Switching back to queue-owned retries is a fallback and must not
        # fail dark: operators see it in the fallback telemetry.
        assert fallback_calls == [
            {
                'component': 'sync_dispatch',
                'from_mode': 'budget_replacement',
                'to_mode': 'queue_retry',
                'reason': 'enqueue_failed',
                'outcome': 'degraded',
            }
        ]
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_marker_clear_failure_keeps_409():
    """The marker clear after a failed enqueue is best-effort: the same Redis
    that just failed the enqueue can fail the clear too, and the queue-owned
    409 must still return — the surviving marker only delays stale self-heal,
    exactly the pre-clear behavior."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(
            side_effect=[{'job_id': 'job-1', 'status': 'processing'}, RuntimeError('redis unavailable')]
        )
        module.enqueue_sync_job_budget_replacement = MagicMock(side_effect=RuntimeError('create_task failed'))

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        assert module.update_sync_job.call_count == 2
        # The failed clear gets its own bounded record before the primary
        # fallback return: the surviving marker suppresses stale recovery
        # long after the queue retries exhaust — a materially worse state
        # than the clean re-arm the primary reason implies.
        assert [call['reason'] for call in fallback_calls] == ['marker_clear_failed', 'enqueue_failed']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_expiry_keeps_409_when_cloud_tasks_dispatch_disabled():
    """Inline/local stacks without Cloud Tasks dispatch cannot schedule a
    replacement, so the budget expiry keeps the pre-deferral 409 semantics."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.is_cloud_tasks_dispatch_enabled = MagicMock(return_value=False)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        assert [call['reason'] for call in fallback_calls] == ['dispatch_disabled']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_chain_ends_at_queue_attempt_contract():
    """Every replacement is a fresh named task whose queue retry count restarts
    at zero, so the chain must bound itself: once the original delivery plus
    replacements have spent the queue's attempt contract in whole-budget
    attempts, no further replacement is scheduled. The 409 ends the task
    through the queue with the lock still preserved for any live leaf; the
    stale self-heal finalizes the job once that lock expires."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    max_attempts = module.get_sync_tasks_max_attempts()
    request.json = AsyncMock(
        return_value={
            **(await request.json()),
            module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY: max_attempts - 1,
        }
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock()

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        # No replacement is coming, so the job must stay eligible for the
        # stale self-heal once the preserved lock expires.
        module.update_sync_job.assert_not_called()
        module.release_job_run_lock.assert_not_called()
        module._finalize_sync_job_failure.assert_not_awaited()
        assert [(call['reason'], call['outcome']) for call in fallback_calls] == [('deferrals_exhausted', 'exhausted')]
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_sync_task_replacement_enqueue_timeout_fits_inside_route_margin():
    """The replacement enqueue runs after the budget has expired, so its bound
    must come out of the margin the configured budget actually leaves below the
    route cap — an explicit override close to the cap must not let the
    middleware 504 fire before the deferral response."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    resolve = module._resolve_sync_job_replacement_enqueue_timeout
    try:
        assert resolve(1500.0, 1380.0) == 60.0
        assert resolve(30.0, 20.0) == 5.0
        assert resolve(1500.0, 1490.0) == 5.0
        # The margin is measured below the earliest attempt wall, not only the
        # route cap: a route timeout above the 1500s dispatch deadline must not
        # buy post-budget work another margin the queue ends the attempt first.
        assert resolve(1800.0, 1380.0) == 60.0
        assert resolve(1500.0, 1380.0, run_lock_ttl_seconds=1600.0) == 60.0
        assert (
            module.SYNC_JOB_HANDLER_BUDGET_SECONDS + module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS
            < min(
                module.SYNC_JOB_ROUTE_TIMEOUT_SECONDS,
                module.DISPATCH_DEADLINE_SECONDS,
                module.RUN_LOCK_TTL_SECONDS,
            )
        )
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_deferred_processing_job_is_not_stale_until_its_replacement_is_due():
    """A budget-deferred job sits processing without a run lock between the
    preserved lock's expiry and its scheduled replacement; polling must not
    treat that planned silence as a lost owner, but must resume once the
    replacement is overdue so a lost replacement still self-heals."""

    sync_jobs, _ = _load_sync_jobs()
    job = {
        'status': 'processing',
        'dispatch_mode': 'cloud_tasks',
        'updated_at': 1_000.0,
        'deferred_until': 5_000.0,
    }
    silent_past_threshold = 1_000.0 + sync_jobs.STALE_THRESHOLD_SECONDS + 1

    assert sync_jobs.is_sync_job_stale(job, now=silent_past_threshold) is False
    assert sync_jobs.is_sync_job_stale(job, now=4_999.0) is False
    assert sync_jobs.is_sync_job_stale(job, now=5_000.0) is True
    assert sync_jobs.is_sync_job_stale({**job, 'deferred_until': 'later'}, now=silent_past_threshold) is True
    assert sync_jobs.is_sync_job_stale({**job, 'dispatch_mode': 'sequenced'}, now=6_000.0) is False
    # Overdue marker on a queued job is the recovery signal even when an
    # earlier retryable failure left attempt/started_at populated: the
    # budget-deferral chain already spent the queue's attempts, so no pending
    # queue retry exists to protect.
    assert (
        sync_jobs.is_sync_job_stale({**job, 'status': 'queued', 'attempt': 1, 'started_at': 900.0}, now=6_000.0) is True
    )


def test_deferred_queued_job_is_not_dispatch_lost_before_its_replacement_is_due():
    """A budget expiry during post-lock setup (staged download, account checks)
    leaves the job queued with the deferral marker set and no run lock held;
    the replacement is scheduled past the preserved lock's TTL (~31 minutes),
    beyond the 30-minute queued-dispatch-stale threshold. The marker must guard
    that window in the queued state too, then resume dispatch-lost detection
    once the replacement is overdue so a lost replacement still self-heals."""

    sync_jobs, _ = _load_sync_jobs()
    job = {
        'status': 'queued',
        'dispatch_mode': 'cloud_tasks',
        'started_at': None,
        'attempt': None,
        'updated_at': 1_000.0,
        'deferred_until': 5_000.0,
    }
    past_queued_threshold = 1_000.0 + sync_jobs.QUEUED_DISPATCH_STALE_SECONDS + 1

    assert sync_jobs.is_sync_job_stale(job, now=past_queued_threshold) is False
    assert sync_jobs.is_sync_job_stale(job, now=4_999.0) is False
    assert sync_jobs.is_sync_job_stale(job, now=5_000.0) is True
    # No marker: normal queued dispatch-lost detection is untouched.
    assert (
        sync_jobs.is_sync_job_stale({k: v for k, v in job.items() if k != 'deferred_until'}, now=past_queued_threshold)
        is True
    )
    # A marker that is not a number protects nothing.
    assert sync_jobs.is_sync_job_stale({**job, 'deferred_until': 'later'}, now=past_queued_threshold) is True


def test_processing_transition_retires_the_deferral_marker():
    """The delivery that transitions a job to processing IS the deferred
    replacement arriving: the marker must be retired by that transition rather
    than lingering to suppress stale detection for a job that is actively
    running under a fresh run lock. Both the fenced and legacy transitions
    clear it."""

    redis_client = fakeredis.FakeRedis()
    sync_jobs, _ = _load_sync_jobs(redis_client)
    job_id = 'job-1'
    deferred_until = time.time() + sync_jobs.QUEUED_DISPATCH_STALE_SECONDS
    _seed_fenced_job(
        redis_client,
        sync_jobs,
        job_id,
        {
            'job_id': job_id,
            'status': 'queued',
            'lane': 'backfill',
            'result': None,
            'deferred_until': deferred_until,
        },
        owner='owner-a',
    )

    processing = sync_jobs.fenced_mark_job_processing(job_id, 'owner-a', now=100.0)

    assert processing.applied is True
    assert processing.job['status'] == 'processing'
    assert processing.job['deferred_until'] is None

    # Legacy (tokenless) path: same retirement on its queued->processing CAS.
    legacy_job_id = 'job-legacy'
    redis_client.set(
        f'{sync_jobs.JOB_KEY_PREFIX}{legacy_job_id}',
        json.dumps(
            {
                'job_id': legacy_job_id,
                'status': 'queued',
                'lane': 'backfill',
                'result': None,
                'deferred_until': deferred_until,
            },
            separators=(',', ':'),
        ),
        ex=12_345,
    )
    legacy = sync_jobs.mark_job_processing(legacy_job_id)
    assert legacy is not None
    assert legacy['status'] == 'processing'
    assert legacy['deferred_until'] is None


@pytest.mark.asyncio
async def test_sequenced_budget_deferral_acks_without_finishing_sequencer_owner():
    """A budget-expired sequenced delivery is an ack, not a completion claim:
    the job is nonterminal and still owned by its epoch, so the wrapper must
    pass the deferral through instead of converting it into a retry-burning
    nonterminal_ack 500 or finishing the owner out from under the job."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
    module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
    module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.get_sync_job = MagicMock(return_value={'status': 'processing', 'attempt': 1})
    module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
    module._run_sync_job_body = AsyncMock(
        return_value=module.JSONResponse(
            status_code=200, content={'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        )
    )
    try:
        deferred = await module.run_sync_job(request, task_retry_count=0)

        assert deferred.status_code == 200
        assert json.loads(deferred.body)['status'] == module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS
        module.get_sync_job.assert_called_with('job-1')  # prior-attempt read only
        assert module.get_sync_job.call_count == 1
        module.sync_backfill_sequencer.finish_job.assert_not_called()
        module.uid_sequencer.kick.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sequenced_delivery_heartbeat_drain_is_bounded():
    """A heartbeat blocked in its Firestore renewal ignores the stop event, so
    joining it after the attempt must be bounded: the deferral response has to
    return inside the middleware/dispatch headroom, cancelling the heartbeat
    rather than waiting out its executor leaf."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
    module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.get_sync_job = MagicMock(return_value={'status': 'processing', 'attempt': 1})
    module._run_sync_job_body = AsyncMock(
        return_value=module.JSONResponse(
            status_code=200, content={'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        )
    )
    module.SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS = 0.05

    async def _heartbeat_blocked_in_renewal(uid, job_id, epoch, stop, owner):
        await asyncio.sleep(30)

    module._maintain_uid_sequencer_lease = _heartbeat_blocked_in_renewal
    created = []

    def _capture_task(coro, *, name):
        task = asyncio.create_task(coro, name=name)
        created.append(task)
        return task

    module.start_background_task = _capture_task
    try:
        started = time.monotonic()
        deferred = await module.run_sync_job(request, task_retry_count=0)
        elapsed = time.monotonic() - started

        assert deferred.status_code == 200
        assert json.loads(deferred.body)['status'] == module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS
        # The join gave up on the stuck heartbeat instead of waiting for it:
        # the response returned near the drain bound and the heartbeat was
        # cancelled out of its renewal.
        assert elapsed < 5
        assert created and created[0].cancelled()
        module.sync_backfill_sequencer.finish_job.assert_not_called()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_requires_marker_before_ack():
    """The deferred marker is a prerequisite for the ack, not best-effort: the
    preserved run lock expires before the replacement is due, so acking after
    a lost marker write would leave that unlocked poll window unprotected and
    a status poll could terminally fail the job before its continuation runs.
    The 409 fallback keeps Cloud Tasks owning the redelivery instead."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        # First call (the marker write) raises; the compensating clear that
        # the fallback must now run succeeds, removing any marker the EVAL
        # applied server-side before the response was lost.
        module.update_sync_job = MagicMock(
            side_effect=[RuntimeError('redis unavailable'), {'job_id': 'job-1', 'status': 'processing'}]
        )

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        # The replacement must never be scheduled against an unprotected poll
        # window: losing the marker aborts the deferral before the enqueue.
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        module.release_job_run_lock.assert_not_called()
        assert module.update_sync_job.call_count == 2
        assert module.update_sync_job.call_args_list[-1] == unittest.mock.call('job-1', {'deferred_until': None})
        assert fallback_calls == [
            {
                'component': 'sync_dispatch',
                'from_mode': 'budget_replacement',
                'to_mode': 'queue_retry',
                'reason': 'marker_failed',
                'outcome': 'degraded',
            }
        ]
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_treats_missing_marker_update_as_failed():
    """update_sync_job also fails by returning None — a missing/nonmutable job
    or a CAS that lost every retry — and that sentinel is as good as a raised
    error: the marker is not on the job, so acking would leave the unlocked
    poll window unprotected exactly like a lost write. The deferral must fall
    back to the queue-owned 409."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        # The sentinel-marker write returns None; the compensating clear
        # succeeds so no marker the EVAL applied survives the fallback.
        module.update_sync_job = MagicMock(side_effect=[None, {'job_id': 'job-1', 'status': 'processing'}])

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        module.release_job_run_lock.assert_not_called()
        assert module.update_sync_job.call_count == 2
        assert module.update_sync_job.call_args_list[-1] == unittest.mock.call('job-1', {'deferred_until': None})
        assert [call['reason'] for call in fallback_calls] == ['marker_failed']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_expiry_before_run_lock_keeps_queue_owned_retry():
    """An expiry during the read-only setup before lock admission owns nothing
    — no preserved lock whose TTL a delayed replacement must outlive, no
    mutating leaf a redelivery could overlap — so the lock-delay deferral would
    stall the job for ~31 minutes for no reason and suppress stale recovery for
    the same interval. The queue-owned 409 retry keeps the pre-deferral
    semantics instead."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not start'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    passthrough_run_blocking = module.run_blocking

    async def _fence_read_hangs(_executor, fn, *args, **kwargs):
        # The handler's first read: expiring here cancels the attempt long
        # before try_acquire_sync_job_run_lock is reached.
        if fn is module.get_sync_ledger_fence_mode:
            await asyncio.sleep(30)
        return await passthrough_run_blocking(_executor, fn, *args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.run_blocking = _fence_read_hangs

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        # No lock was ever acquired, so nothing is deferred past: no delayed
        # replacement is scheduled and no marker suppresses stale detection.
        module.try_acquire_sync_job_run_lock.assert_not_called()
        module.try_acquire_job_run_lock.assert_not_called()
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        module.update_sync_job.assert_not_called()
        module.release_job_run_lock.assert_not_called()
        module._finalize_sync_job_failure.assert_not_awaited()
        module._delete_staged_blobs_async.assert_not_awaited()
        assert fallback_calls == [
            {
                'component': 'sync_dispatch',
                'from_mode': 'budget_replacement',
                'to_mode': 'queue_retry',
                'reason': 'pre_lock_expiry',
                'outcome': 'degraded',
            }
        ]
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_expiry_during_lock_acquire_still_defers():
    """The pre-lock branch must not fire while the acquire is in flight: the
    executor thread can still land the lock after the await was cancelled, so a
    mid-acquire expiry must keep the preserved-lock deferral — marker, delayed
    replacement and all — never the queue-owned retry that could redeliver into
    a lock nobody expects. The acquire lands after the expiry here, inside the
    post-budget drain: the replacement's schedule must be anchored to that
    confirmed acquisition — the drained completion upper-bounds when Redis
    started the TTL — not to the earlier expiry instant."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not start'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    passthrough_run_blocking = module.run_blocking
    acquire_settled_at = {}

    async def _acquire_lands_after_expiry(_executor, fn, *args, **kwargs):
        if fn is module.try_acquire_sync_job_run_lock:
            # Past the 0.05s budget, comfortably inside the drain's deadline:
            # late enough that an expiry-anchored schedule would come due while
            # this late-acquired lock is still held.
            await asyncio.sleep(1.5)
            acquire_settled_at['at'] = time.time()
        return await passthrough_run_blocking(_executor, fn, *args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 2.0
        module.run_blocking = _acquire_lands_after_expiry
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        payload, schedule_at = module.enqueue_sync_job_budget_replacement.call_args.args
        # Anchored to the confirmed acquisition: the whole replacement delay
        # must outlive the drained settle instant, not the earlier expiry. (The
        # 1s slack absorbs only int() truncation — an expiry-anchored schedule
        # sits ~1.45s earlier and cannot pass.)
        assert schedule_at >= acquire_settled_at['at'] + module.SYNC_JOB_BUDGET_REPLACEMENT_DELAY_SECONDS - 1
        module.update_sync_job.assert_called_once_with(
            'job-1', {'deferred_until': schedule_at + module.QUEUED_DISPATCH_STALE_SECONDS}
        )
        module.release_job_run_lock.assert_not_called()
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_enqueue_failure_clears_deferred_marker():
    """The marker suppresses stale detection until the instant the replacement
    would have run; when the enqueue failed there is no replacement, so leaving
    it set would keep the job nonterminal for ~41 minutes after the queue's
    retries exhaust — an unnecessary stall. The fallback must clear it before
    handing the retry back to the queue."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        module.enqueue_sync_job_budget_replacement = MagicMock(side_effect=RuntimeError('create_task failed'))

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        schedule_at = module.enqueue_sync_job_budget_replacement.call_args.args[1]
        # The marker write from the deferral, then the clear for the failed
        # enqueue: stale detection resumes instead of waiting out a
        # replacement that was never scheduled.
        assert module.update_sync_job.call_args_list == [
            (('job-1', {'deferred_until': schedule_at + module.QUEUED_DISPATCH_STALE_SECONDS}),),
            (('job-1', {'deferred_until': None}),),
        ]
        assert [call['reason'] for call in fallback_calls] == ['enqueue_failed']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sequenced_attempt_heartbeat_drain_is_bounded():
    """A renewal blocked inside its Firestore run_blocking cannot be interrupted
    by the stop event, and the heartbeat join sits between the attempt's
    response and its return: unbounded, it holds the request open past every
    wall the handler budget exists to stay under. The drain must cancel the
    heartbeat at a bound and return the response."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 0.01
    module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
    module.sync_backfill_sequencer.renew_job = MagicMock(return_value=True)
    module.get_sync_job = MagicMock(return_value={'status': 'processing', 'attempt': 1})

    renewal_started = asyncio.Event()

    async def _body_returns_after_renewal_started(_request, _task_retry_count, *_args, **_kwargs):
        # Synchronize with the blocked renewal instead of assuming a sleep
        # gives the heartbeat enough scheduler time on a loaded runner.
        await asyncio.wait_for(renewal_started.wait(), timeout=2)
        return module.JSONResponse(status_code=200, content={'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS})

    passthrough_run_blocking = module.run_blocking
    renewal_reached = False

    async def _renewal_hangs(_executor, fn, *args, **kwargs):
        nonlocal renewal_reached
        if fn is module.sync_backfill_sequencer.renew_job:
            renewal_reached = True
            renewal_started.set()
            await asyncio.sleep(10)
        return await passthrough_run_blocking(_executor, fn, *args, **kwargs)

    heartbeat_tasks = []

    def _capture_heartbeat(coro, *, name):
        task = asyncio.create_task(coro, name=name)
        heartbeat_tasks.append(task)
        return task

    try:
        module._run_sync_job_body = _body_returns_after_renewal_started
        module.run_blocking = _renewal_hangs
        module.start_background_task = _capture_heartbeat
        module.SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS = 0.1

        started = time.monotonic()
        response = await module.run_sync_job(request, task_retry_count=0)
        elapsed = time.monotonic() - started

        assert response.status_code == 200
        assert json.loads(response.body)['status'] == module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS
        assert renewal_reached
        # The blocked renewal is cancelled at the drain bound (~0.1s), not
        # joined for its full 10s: the response returns inside the headroom.
        assert elapsed < 5
        assert heartbeat_tasks[0].cancelled()
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sequenced_budget_deferral_owner_write_failure_records_fallback():
    """The owner-side chain count is a prerequisite, not a post-ack nicety: the
    sweep's lease-expiry redrive reloads the original payload and restarts the
    chain at zero, and repeated lost counts would restore an unbounded
    whole-budget sequence. A write that fails must therefore abort the
    deferral BEFORE any marker or replacement exists — the queue-owned 409
    keeps the task and no orphaned schedule survives the lost count."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    base_payload = await request.json()
    request.json = AsyncMock(
        return_value={
            **base_payload,
            'sequencer_epoch': 3,
            module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY: 1,
        }
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    call_order = []

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
        module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            return {
                'job_id': job_id,
                'status': 'queued' if reads['n'] == 1 else 'processing',
                'lane': 'fresh',
                'ledger_fence_mode': 'active',
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        def _track_update(job_id, updates):
            call_order.append(('marker' if updates.get('deferred_until') is not None else 'update', job_id))
            return {'job_id': job_id, 'status': 'processing'}

        module.update_sync_job = MagicMock(side_effect=_track_update)  # type: ignore[attr-defined]

        def _track_owner_write(uid, job_id, epoch, deferrals):
            call_order.append(('owner_write', job_id))
            raise RuntimeError('firestore unavailable')

        module.sync_backfill_sequencer.note_budget_deferral = MagicMock(side_effect=_track_owner_write)

        response = await module.run_sync_job(request, task_retry_count=0)

        # The queue keeps the task: no replacement, no marker, and the failed
        # count never acks a schedule it cannot bound.
        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        assert call_order == [('owner_write', 'job-1')]
        assert fallback_calls == [
            {
                'component': 'sync_dispatch',
                'from_mode': 'budget_replacement',
                'to_mode': 'queue_retry',
                'reason': 'owner_write_failed',
                'outcome': 'degraded',
            }
        ]
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sequenced_budget_deferral_owner_write_shares_one_post_budget_deadline():
    """The owner-count write, marker, and replacement enqueue share one absolute
    post-budget deadline: each block getting its own margin-sized timeout would
    sum to the whole route margin, letting the middleware 504 fire before the
    deferral response is returned. Here the owner write spends 0.45s of the
    0.9s shared deadline and the enqueue would still fit a fresh 0.9s timeout —
    but only the ~0.45s remainder is left, so the whole deferral aborts at the
    one deadline instead of running to the write's own 1.15s horizon."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    base_payload = await request.json()
    request.json = AsyncMock(
        return_value={
            **base_payload,
            'sequencer_epoch': 3,
            module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY: 1,
        }
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    owner_write_finished = False

    async def _run_blocking(executor, fn, *args, **kwargs):
        nonlocal owner_write_finished
        if fn is module.sync_backfill_sequencer.note_budget_deferral:
            # 0.45s: consumes half the shared 0.9s deadline and settles.
            await asyncio.sleep(0.45)
            owner_write_finished = True
        if fn is module.enqueue_sync_job_budget_replacement:
            # 0.7s: fits a fresh 0.9s timeout, but not the ~0.45s the shared
            # deadline still has after the owner write above.
            await asyncio.sleep(0.7)
        return fn(*args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 0.9
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        module.sync_backfill_sequencer.note_budget_deferral = MagicMock(return_value=True)
        module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
        module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
        module.run_blocking = _run_blocking
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            return {
                'job_id': job_id,
                'status': 'queued' if reads['n'] == 1 else 'processing',
                'lane': 'fresh',
                'ledger_fence_mode': 'active',
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        started = time.monotonic()
        response = await module.run_sync_job(request, task_retry_count=0)
        elapsed = time.monotonic() - started

        # The deadline fired during the enqueue (its create may or may not
        # have landed, so the uncertain class keeps the marker and returns
        # the queue-owned 409) at the one shared wall: a fresh per-block
        # timeout would have let the enqueue finish and acked the 200
        # deferral instead. The coarse stopwatch bound only tolerates CI
        # scheduling and post-409 cleanup drain; the outcome above is the
        # contract proof.
        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        assert owner_write_finished is True
        assert elapsed < 5
        assert [call['reason'] for call in fallback_calls] == ['enqueue_uncertain']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sequenced_budget_deferral_persists_chain_count_on_owner():
    """A sequenced deferral must persist its chain count on the sequencer
    owner: the sweep's lease-expiry redrive re-dispatches the owner's original
    ``active_payload`` — which carries no count — so without the owner-side
    copy the redrive would restart the chain at zero and an over-budget job
    could defer forever."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    base_payload = await request.json()
    request.json = AsyncMock(
        return_value={
            **base_payload,
            'sequencer_epoch': 3,
            module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY: 1,
        }
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        module.sync_backfill_sequencer.note_budget_deferral = MagicMock()
        module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
        module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
        # The sequenced wrapper consumes one extra job read (prior attempt)
        # before the attempt body; keep the queued→processing sequence without
        # a bounded side_effect list.
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            return {
                'job_id': job_id,
                'status': 'queued' if reads['n'] == 1 else 'processing',
                'lane': 'fresh',
                'ledger_fence_mode': 'active',
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        # The replacement carries the incremented count and the owner is
        # pinned to the same number so a lease-expiry redrive cannot restart
        # the chain at zero.
        payload, _schedule_at = module.enqueue_sync_job_budget_replacement.call_args.args
        assert payload[module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY] == 2
        module.sync_backfill_sequencer.note_budget_deferral.assert_called_once_with('test-uid', 'job-1', 3, 2)
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def test_sync_task_handler_budget_derives_from_route_timeout():
    """The budget must track the configured route timeout so the middleware
    deadline can never fire first and reintroduce the lingering 504 path."""

    module, saved_modules, _, _, _, _ = _load_sync_router_for_fast_path()
    resolve = module._resolve_sync_job_handler_budget
    try:
        # Default derives from the configured route cap minus the margin.
        assert resolve(1500.0, None) == 1380.0
        assert resolve(1500.0, '') == 1380.0
        assert resolve(600.0, None) == 480.0
        # An explicit override still wins for the local stacks (20s under 30s).
        assert resolve(30.0, '20') == 20.0
        # The budget is bounded by the earliest attempt wall, not just the
        # route timeout: a route timeout above the 1500s dispatch deadline (or
        # the run lock TTL) must not derive or accept a budget past the wall
        # that Cloud Tasks or a lock-expiring retry ends the attempt at first.
        assert resolve(1800.0, None) == 1380.0
        assert resolve(1800.0, '1400') == 1400.0
        with pytest.raises(ValueError):
            resolve(1800.0, '1600')
        assert resolve(1500.0, None, run_lock_ttl_seconds=900.0) == 780.0
        with pytest.raises(ValueError):
            resolve(1500.0, '1000', run_lock_ttl_seconds=900.0)
        with pytest.raises(ValueError):
            resolve(1500.0, None, dispatch_deadline_seconds=100.0)
        # Any budget that is not strictly below the route cap fails at startup.
        with pytest.raises(ValueError):
            resolve(30.0, '30')
        with pytest.raises(ValueError):
            resolve(1500.0, '1600')
        with pytest.raises(ValueError):
            resolve(0.0, None)
        # A route cap smaller than the margin cannot derive a valid budget.
        with pytest.raises(ValueError):
            resolve(100.0, None)
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_uncertain_enqueue_keeps_deferred_marker():
    """A transport/deadline failure cannot prove the named replacement was not
    created: clearing the marker would rearm stale self-heal in the gap before
    a replacement that may still arrive, so an uncertain enqueue keeps it and
    records its own fallback reason."""

    from google.api_core.exceptions import ServiceUnavailable

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        module.enqueue_sync_job_budget_replacement = MagicMock(
            side_effect=ServiceUnavailable('transport terminated mid-request')
        )

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        # Only the marker write happened: the clear that a definitive failure
        # performs must not run for an uncertain outcome.
        assert module.update_sync_job.call_count == 1
        assert [call['reason'] for call in fallback_calls] == ['enqueue_uncertain']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_timeout_during_marker_is_not_uncertain_enqueue():
    """The shared deadline firing while the marker write itself is awaiting is
    NOT an uncertain enqueue: the enqueue call never ran, so no replacement can
    exist and retaining the marker would leave the queue's retries exhausting
    against the preserved lock with no delayed continuation to resume the job.
    The fallback must classify it as a marker timeout and clear the
    late-applied marker — but only after draining the timed-out write: the clear
    must never run while the write's CAS can still be mid-flight and overwrite
    it afterwards."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    marker_writes = []
    marker_events = []

    async def _marker_settles_just_past_deadline(job_id, updates):
        marker_writes.append(dict(updates))
        if updates.get('deferred_until') is not None:
            # Consumes the whole enqueue deadline, then settles just past it —
            # still inside the cleanup deadline the drain waits on, so the
            # clear below runs strictly after the late-applied write.
            await asyncio.sleep(0.15)
            marker_events.append('marker_settled')
            return {'job_id': job_id, 'status': 'processing'}
        marker_events.append('clear_started')
        return {'job_id': job_id, 'status': 'processing'}

    async def _awaiting_run_blocking(_executor, fn, *args, **kwargs):
        # The passthrough run_blocking returns fn(*args) without awaiting it,
        # which would make the marker coroutine "complete" instantly; the
        # deadline must expire while the marker write is genuinely awaited.
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.run_blocking = _awaiting_run_blocking
        # The deadline expires while the marker write awaits: the update is
        # abandoned before the enqueue is ever attempted.
        module.update_sync_job = MagicMock(
            side_effect=lambda job_id, updates: _marker_settles_just_past_deadline(job_id, updates)
        )
        module.enqueue_sync_job_budget_replacement = MagicMock(
            side_effect=AssertionError('enqueue must never run when the marker write timed out')
        )

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        # Marker write attempted, then cleared strictly after it settled: no
        # replacement was scheduled, so the marker must not outlive the
        # queue-owned retry handback — and the clear must not race the write.
        assert any(call.get('deferred_until') is not None for call in marker_writes)
        assert any(call.get('deferred_until') is None for call in marker_writes)
        assert marker_events == ['marker_settled', 'clear_started']
        assert [call['reason'] for call in fallback_calls] == ['marker_timeout']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_marker_drain_failure_skips_clear():
    """A marker write still mid-CAS when the cleanup deadline expires cannot be
    ordered behind the clear: clearing anyway would race the detached executor
    leaf — a late-applied marker could overwrite the clear and keep stale
    recovery suppressed with no replacement ever scheduled. The fallback must
    keep the 409 and leave the marker alone rather than pretend a racy clear
    settled the state."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    marker_writes = []

    async def _marker_never_settles(job_id, updates):
        marker_writes.append(dict(updates))
        if updates.get('deferred_until') is not None:
            # Still mid-CAS when both the enqueue deadline and the cleanup
            # deadline have passed: the drain cannot order the clear behind it.
            await asyncio.sleep(0.3)
            return {'job_id': job_id, 'status': 'processing'}
        raise AssertionError('clear must not run while the marker write is unsettled')

    async def _awaiting_run_blocking(_executor, fn, *args, **kwargs):
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 0.05
        module.SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.run_blocking = _awaiting_run_blocking
        module.update_sync_job = MagicMock(side_effect=lambda job_id, updates: _marker_never_settles(job_id, updates))
        module.enqueue_sync_job_budget_replacement = MagicMock(
            side_effect=AssertionError('enqueue must never run when the marker write timed out')
        )

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        # Only the marker write ran: the clear is skipped because the write
        # never settled inside the shared cleanup deadline.
        assert len(marker_writes) == 1
        assert marker_writes[0].get('deferred_until') is not None
        assert [call['reason'] for call in fallback_calls] == ['marker_timeout']
        # Let the abandoned write settle before the loop closes so its detached
        # task does not die pending.
        await asyncio.sleep(0.35)
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_unsettleable_acquire_keeps_queue_retry():
    """A run-lock acquire still mid-flight when the post-budget deadline expires
    leaves the lock's TTL start unbounded: any replacement schedule could come
    due while that late-acquired lock is held and exhaust the replacement's
    short-backoff attempts on 409s. The deferral must refuse to schedule against
    an unconfirmed acquisition — no marker write, no enqueue, queue-owned 409."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not start'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    passthrough_run_blocking = module.run_blocking

    async def _acquire_never_settles(_executor, fn, *args, **kwargs):
        if fn is module.try_acquire_sync_job_run_lock:
            await asyncio.sleep(0.3)
        return await passthrough_run_blocking(_executor, fn, *args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 0.05
        module.run_blocking = _acquire_never_settles
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        # Nothing was scheduled against the unconfirmed acquisition.
        module.update_sync_job.assert_not_called()
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        assert [call['reason'] for call in fallback_calls] == ['acquire_unsettled']
        # Let the abandoned acquire settle before the loop closes so its
        # detached task does not die pending.
        await asyncio.sleep(0.3)
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sync_task_budget_deferral_timeout_during_enqueue_keeps_deferred_marker():
    """The post-budget deadline firing mid-enqueue is the same uncertainty: the
    underlying create may have been accepted after the handler stopped
    waiting, so the marker stays rather than being cleared."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        # The shared post-budget deadline firing mid-enqueue surfaces as
        # TimeoutError from the timeout_at context: the handler stopped
        # waiting while the underlying create may still have landed.
        module.enqueue_sync_job_budget_replacement = MagicMock(side_effect=TimeoutError('post-budget deadline'))

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        assert module.update_sync_job.call_count == 1
        assert [call['reason'] for call in fallback_calls] == ['enqueue_uncertain']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _pipeline_expiring_the_handler_budget(module):
    """Pipeline stub that expires the attempt's handler budget from inside the
    pipeline, then never returns.

    A tiny real budget (0.05s) also races the attempt's pre-pipeline awaits
    (thread-pool job reads, lock acquire): on a loaded runner it can expire
    before the pipeline starts, so the recovery's job read lands on a
    nonterminal read and the handler takes the preserved-lock branch instead.
    Capturing the budget's timeout context and rescheduling it to now once the
    pipeline runs places the expiry deterministically, independent of runner
    speed; the budget itself keeps the module's production-sized default.
    """
    budgets = []

    class _BudgetCapturingAsyncio:
        def __getattr__(self, name):
            return getattr(asyncio, name)

        def timeout(self, delay):
            budget = asyncio.timeout(delay)
            budgets.append(budget)
            return budget

    module.asyncio = _BudgetCapturingAsyncio()

    async def _pipeline(*args, **kwargs):
        budgets[-1].reschedule(asyncio.get_running_loop().time())
        await asyncio.Event().wait()

    return _pipeline


@pytest.mark.asyncio
async def test_budget_expiry_after_terminal_transition_returns_terminal_cleanup_retry():
    """A pipeline that published a terminal result and then hit the budget
    during cleanup must not defer: update_sync_job rejects terminal jobs, so
    the marker write would fail and the 409 would burn the queue's retries
    against the preserved lock while the backfill slot stays held. The
    established terminal_cleanup_retry 500 redelivers into the cleanup-only
    terminal branch, and the run lock this attempt held is released because
    no leaf of this attempt owns it anymore."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    _pipeline_never_returns_then_terminal = _pipeline_expiring_the_handler_budget(module)

    try:
        module._run_full_pipeline_background_async = _pipeline_never_returns_then_terminal
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            # Two pre-terminal reads (admission + running), then the terminal
            # transition the pipeline completed before the budget expired.
            status = 'completed' if reads['n'] > 2 else ('queued' if reads['n'] == 1 else 'processing')
            return {
                'job_id': job_id,
                'status': status,
                'lane': 'fresh',
                'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 500
        body = json.loads(response.body)
        assert body['status'] == 'terminal_cleanup_retry'
        assert body['job_status'] == 'completed'
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        # The preserved lock of a terminal job protects nothing: released so
        # the redelivery's cleanup-only path is not deflected into a 409. The
        # release is confirmed through the strict compare-and-delete — the
        # 500's retry-only obligation stands behind it.
        module.release_job_run_lock_strict.assert_called_once_with('job-1', '1:lock-token')
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_sequenced_cleanup_waits_share_one_deadline():
    """The marker clear after a definitive enqueue failure and the sequenced
    heartbeat drain must share one absolute cleanup deadline: a slow enqueue
    that consumed the post-budget margin cannot buy each cleanup wait a fresh
    margin-sized timeout whose sum reaches the attempt wall. Here the enqueue
    fails quickly (definitive), the marker clear spends most of the shared
    bound, and the heartbeat drain gets only the remainder — not another full
    cleanup timeout."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(
        return_value={
            'job_id': 'job-1',
            'uid': 'test-uid',
            'sequencer_epoch': 3,
            'raw_blob_paths': ['staged/audio.opus'],
            'source': 'omi',
            'lane': 'fresh',
            'content_id': 'content-1',
            'ledger_fence_mode': 'active',
            module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY: 1,
        }
    )
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.get_sync_ledger_fence_mode = MagicMock(return_value=module.SyncLedgerFenceMode.ACTIVE)
    module.sync_job_uses_ledger_fence = MagicMock(
        side_effect=lambda job: bool(job and job.get('ledger_fence_mode') == module.SyncLedgerFenceMode.ACTIVE.value)
    )
    module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
    module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
    module.try_acquire_sync_job_run_lock = MagicMock(return_value='1:lock-token')
    module.try_acquire_job_run_lock = MagicMock(return_value='legacy-lock-token')
    module._download_staged_files = MagicMock(return_value=True)
    reads = {'n': 0}

    def _job_read(job_id):
        reads['n'] += 1
        return {
            'job_id': job_id,
            'status': 'queued' if reads['n'] == 1 else 'processing',
            'lane': 'fresh',
            'ledger_fence_mode': 'active',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        }

    module.get_sync_job = MagicMock(side_effect=_job_read)
    module.get_sync_tasks_max_attempts = MagicMock(return_value=5)

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    async def _heartbeat_blocked_in_renewal(uid, job_id, epoch, stop, owner):
        await asyncio.sleep(30)

    created = []

    def _capture_task(coro, *, name):
        task = asyncio.create_task(coro, name=name)
        created.append(task)
        return task

    passthrough_run_blocking = module.run_blocking
    marker_clear_started = threading.Event()

    async def _run_blocking(executor, fn, *args, **kwargs):
        if fn is module.update_sync_job and args and args[1] == {'deferred_until': None}:
            marker_clear_started.set()
            # 0.5s: runs past the post-budget deadline (~0.35s) but inside the
            # clear's own bound (deadline + 0.3s), so the heartbeat drain is
            # left only the shared window's remainder.
            await asyncio.sleep(0.5)
        if fn is module.enqueue_sync_job_budget_replacement:
            raise RuntimeError('create_task failed')
        return await passthrough_run_blocking(executor, fn, *args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 0.3
        module.SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS = 0.3
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module._maintain_uid_sequencer_lease = _heartbeat_blocked_in_renewal
        module.start_background_task = _capture_task
        module.run_blocking = _run_blocking
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})

        started = time.monotonic()
        response = await module.run_sync_job(request, task_retry_count=0)
        elapsed = time.monotonic() - started

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        assert marker_clear_started.is_set()
        # Shared window: budget expiry (~0.05) + enqueue timeout (0.3) + one
        # cleanup window (0.3) bounds the whole tail. The pre-fix behavior —
        # the clear spending its fresh 0.3s to completion (~0.86s) and the
        # drain adding another 0.3s (~1.16s) — is what this bound excludes.
        assert elapsed < 0.05 + 0.3 + 0.3 + 0.1
        assert created and created[0].cancelled()
        assert [call['reason'] for call in fallback_calls] == ['enqueue_failed']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_route_preamble_stall_in_begin_job_ends_request_at_the_route_deadline():
    """Thread: the route-entry budget anchor must be enforced, not just
    recorded. The sequenced wrapper performs fence read, parse, begin_job and
    the prior-job read before the attempt body's budget arms; without a
    timeout around those awaits a stalled begin_job hangs the request open
    past the Cloud Tasks dispatch deadline and the middleware cap — the exact
    lingering-request path this PR exists to end. A stall there owns nothing
    (no run lock), so the request ends through the queue-owned 409."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    module.TERMINAL_STATUSES = ('completed', 'failed', 'partial_failure')
    module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
    module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
    passthrough_run_blocking = module.run_blocking

    async def _begin_job_stalls(_executor, fn, *args, **kwargs):
        if fn is module.sync_backfill_sequencer.begin_job:
            await asyncio.sleep(30)
        return await passthrough_run_blocking(_executor, fn, *args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.run_blocking = _begin_job_stalls
        started = time.monotonic()

        response = await module.run_sync_job(request, task_retry_count=0)
        elapsed = time.monotonic() - started

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        assert elapsed < 5
        # The stall owned nothing: no attempt body ever ran, no lock was
        # acquired, no replacement or marker exists.
        module.try_acquire_sync_job_run_lock.assert_not_called()
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        module.update_sync_job.assert_not_called()
        module.release_job_run_lock.assert_not_called()
        assert [call['reason'] for call in fallback_calls] == ['preamble_timeout']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_route_preamble_stall_in_fence_read_ends_request_at_the_route_deadline():
    """Thread: the very first await — the production-fence read — must be
    inside the route deadline too. A stalled fence read hangs the request
    before anything (even payload parsing) runs; the queue-owned 409 ends it
    inside the budget instead."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'sequencer_epoch': 3})
    module.uid_sequencer.production_fence_mode = AsyncMock()  # never reached
    passthrough_run_blocking = module.run_blocking

    async def _fence_read_stalls(_executor, fn, *args, **kwargs):
        if fn is module.uid_sequencer.production_fence_mode:
            await asyncio.sleep(30)
        return await passthrough_run_blocking(_executor, fn, *args, **kwargs)

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.run_blocking = _fence_read_stalls
        started = time.monotonic()

        response = await module.run_sync_job(request, task_retry_count=0)
        elapsed = time.monotonic() - started

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        assert elapsed < 5
        request.json.assert_not_awaited()
        module.try_acquire_sync_job_run_lock.assert_not_called()
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        assert [call['reason'] for call in fallback_calls] == ['preamble_timeout']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _legacy_preamble_module(job_status, stalled_fn_name=None, raises=None):
    """Direct (epoch-less) backfill delivery with the sequencer on, stubbed so a
    single preamble await can stall or fail."""
    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = MagicMock()
    request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'lane': 'backfill'})
    module.uid_sequencer.foreign_delivery = MagicMock(return_value=False)
    module.uid_sequencer.production_stage = MagicMock(return_value=True)
    module.uid_sequencer.enabled = MagicMock(return_value=True)
    module.uid_sequencer.kick = MagicMock(return_value=True)
    module.get_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': job_status})
    module.update_sync_job = MagicMock(return_value={'job_id': 'job-1'})
    module.sync_backfill_sequencer.get_owner = MagicMock(return_value={})
    module.sync_backfill_sequencer.register_job = MagicMock()
    module.backfill_cutover.refresh_direct_run = MagicMock(side_effect=raises)
    module.warm_rollout_cohorts = AsyncMock()
    module._run_sync_job_body = AsyncMock(return_value=module.JSONResponse(status_code=200, content={'status': 'body'}))
    module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
    passthrough = module.run_blocking

    async def _stalling(executor, fn, *args, **kwargs):
        if stalled_fn_name and fn is getattr(module.uid_sequencer, stalled_fn_name, None):
            await asyncio.sleep(30)
        if stalled_fn_name == 'refresh_direct_run' and fn is module.backfill_cutover.refresh_direct_run:
            await asyncio.sleep(30)
        return await passthrough(executor, fn, *args, **kwargs)

    module.run_blocking = _stalling
    return module, saved_modules, request, fallback_calls


def _restore_sync_modules(saved_modules):
    sys.modules.pop('routers.sync', None)
    sys.modules.pop('utils.sync.pipeline', None)
    sys.modules.pop('utils.sync.ledger_completion', None)
    for name, original in saved_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


@pytest.mark.asyncio
async def test_route_preamble_stall_in_legacy_kick_still_acks_the_registered_job():
    """Registration already committed, so a kick stall ends inside the route
    deadline with the 200 ack; a 409 would redeliver a payload that no longer
    needs the queue."""
    module, saved_modules, request, fallback_calls = _legacy_preamble_module('queued', stalled_fn_name='kick')
    try:
        started = time.monotonic()
        response = await module.run_sync_job(request, task_retry_count=0)
        assert time.monotonic() - started < 5
        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'sequenced_legacy_job'}
        module.sync_backfill_sequencer.register_job.assert_called_once()
        module._run_sync_job_body.assert_not_awaited()
        assert fallback_calls == []
    finally:
        _restore_sync_modules(saved_modules)


@pytest.mark.asyncio
async def test_route_preamble_stall_in_direct_refresh_defers_with_the_queue_owned_409():
    module, saved_modules, request, fallback_calls = _legacy_preamble_module(
        'processing', stalled_fn_name='refresh_direct_run'
    )
    try:
        started = time.monotonic()
        response = await module.run_sync_job(request, task_retry_count=0)
        assert time.monotonic() - started < 5
        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module._run_sync_job_body.assert_not_awaited()
        assert [call['reason'] for call in fallback_calls] == ['preamble_timeout']
    finally:
        _restore_sync_modules(saved_modules)


@pytest.mark.asyncio
async def test_direct_refresh_error_continues_into_the_attempt_body_instead_of_a_fast_500():
    module, saved_modules, request, fallback_calls = _legacy_preamble_module(
        'processing', raises=RuntimeError('redis down')
    )
    try:
        response = await module.run_sync_job(request, task_retry_count=0)
        assert response.status_code == 200
        assert json.loads(response.body) == {'status': 'body'}
        module.backfill_cutover.refresh_direct_run.assert_called_once()
        module._run_sync_job_body.assert_awaited_once()
        assert fallback_calls == []
    finally:
        _restore_sync_modules(saved_modules)


@pytest.mark.asyncio
async def test_route_preamble_stall_in_cohort_warm_ends_request_at_the_route_deadline():
    module, saved_modules, request, fallback_calls = _legacy_preamble_module('queued')

    async def _warm_stalls(uid):
        await asyncio.sleep(30)

    module.warm_rollout_cohorts = _warm_stalls
    try:
        started = time.monotonic()
        response = await module.run_sync_job(request, task_retry_count=0)
        assert time.monotonic() - started < 5
        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module._run_sync_job_body.assert_not_awaited()
        module.update_sync_job.assert_not_called()
        assert [call['reason'] for call in fallback_calls] == ['preamble_timeout']
    finally:
        _restore_sync_modules(saved_modules)


@pytest.mark.asyncio
async def test_cohort_warm_error_is_not_turned_into_a_success_response():
    module, saved_modules, request, fallback_calls = _legacy_preamble_module('queued')
    module.warm_rollout_cohorts = AsyncMock(side_effect=RuntimeError('cohort read failed'))
    try:
        with pytest.raises(RuntimeError):
            await module.run_sync_job(request, task_retry_count=0)
        module._run_sync_job_body.assert_not_awaited()
        module.update_sync_job.assert_not_called()
        assert fallback_calls == []
    finally:
        _restore_sync_modules(saved_modules)


@pytest.mark.asyncio
async def test_terminal_cleanup_retry_requires_a_confirmed_lock_release():
    """Thread: the terminal_cleanup_retry 500 hands the queue a retry-only
    obligation, so the run-lock release behind it must be confirmed. An
    unconfirmed release leaves the lock held to its TTL while every
    short-backoff retry deflects off it as a 409 — the task exhausts without
    one cleanup retry landing. Here the strict release settles 0 (token
    mismatch: a racing leaf already replaced it), so the handler must keep
    the preserved-lock contract instead: ack and schedule one replacement
    past the lock's TTL, never return the 500."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    _pipeline_never_returns_then_terminal = _pipeline_expiring_the_handler_budget(module)

    strict_calls = []

    def _strict_release(job_id, token):
        strict_calls.append((job_id, token))
        return 0  # EVAL: token no longer owns the key

    try:
        module._run_full_pipeline_background_async = _pipeline_never_returns_then_terminal
        module.release_job_run_lock_strict = MagicMock(side_effect=_strict_release)
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            status = 'completed' if reads['n'] > 2 else ('queued' if reads['n'] == 1 else 'processing')
            return {
                'job_id': job_id,
                'status': status,
                'lane': 'fresh',
                'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        assert strict_calls == [('job-1', '1:lock-token')]
        # The preserved-lock deferral replaced the unconfirmed 500: marker and
        # delayed replacement exist, and no cleanup-retry obligation was
        # handed to the queue behind an unreleased lock.
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_terminal_cleanup_retry_returns_500_only_after_confirmed_release():
    """Thread (companion): with the strict release confirming (EVAL 1), the
    established behavior stands — the 500 redelivers into the terminal
    branch's retry-only cleanup against a lock this attempt no longer
    holds."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    _pipeline_never_returns_then_terminal = _pipeline_expiring_the_handler_budget(module)

    try:
        module._run_full_pipeline_background_async = _pipeline_never_returns_then_terminal
        module.release_job_run_lock_strict = MagicMock(return_value=1)
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            status = 'completed' if reads['n'] > 2 else ('queued' if reads['n'] == 1 else 'processing')
            return {
                'job_id': job_id,
                'status': status,
                'lane': 'fresh',
                'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 500
        body = json.loads(response.body)
        assert body['status'] == 'terminal_cleanup_retry'
        assert body['job_status'] == 'completed'
        module.release_job_run_lock_strict.assert_called_once_with('job-1', '1:lock-token')
        module.enqueue_sync_job_budget_replacement.assert_not_called()
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_terminal_cleanup_retry_unconfirmed_release_skips_impossible_marker():
    """Thread: after an unconfirmed strict release the terminal-job deferral
    must not route through the deferred-marker write. update_sync_job refuses
    terminal states by contract, so the marker path can only ever degrade to
    the marker_failed 409 — spending every short-backoff queue retry against
    the surviving lock with no replacement scheduled behind them, sticking a
    completed direct backfill job's per-UID slot until its ~2-day TTL. The
    terminal variant schedules the one cleanup replacement directly: no
    marker write is attempted, the replacement carries the bumped chain
    count, and the task acks instead of looping 409."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )

    _pipeline_never_returns_then_terminal = _pipeline_expiring_the_handler_budget(module)

    strict_calls = []

    def _strict_release(job_id, token):
        strict_calls.append((job_id, token))
        return 0  # EVAL: token no longer owns the key — release unconfirmed

    try:
        module._run_full_pipeline_background_async = _pipeline_never_returns_then_terminal
        module.release_job_run_lock_strict = MagicMock(side_effect=_strict_release)
        # Production contract: update_sync_job returns None for terminal
        # states, so any marker write on the completed job cannot apply.
        module.update_sync_job = MagicMock(return_value=None)
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            status = 'completed' if reads['n'] > 2 else ('queued' if reads['n'] == 1 else 'processing')
            return {
                'job_id': job_id,
                'status': status,
                'lane': 'fresh',
                'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        assert strict_calls == [('job-1', '1:lock-token')]
        # The structurally impossible marker write is never attempted…
        module.update_sync_job.assert_not_called()
        # …while the promised cleanup replacement is scheduled with the
        # bumped chain count, past the preserved lock's TTL.
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        payload, schedule_at = module.enqueue_sync_job_budget_replacement.call_args.args
        assert payload[module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY] == 1
        assert schedule_at > 0
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_terminal_cleanup_replacement_survives_the_attempt_cap():
    """Thread: the attempt-cap guard must not consume the terminal-cleanup
    deferral. A final-generation direct backfill attempt (deferrals at the
    cap) whose pipeline completed the job but whose strict run-lock release
    could not be confirmed still needs its one cleanup-only replacement:
    the cap bounds whole-budget re-runs, not the terminal branch's
    retry-only cleanup, and a direct delivery has no sequencer sweep to
    fail the job later — without the bypass the preserved lock outlives
    every short-backoff queue retry and the per-UID slot sticks to its
    TTL."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    # Bump the delivered chain count to the cap (max 3 in this fixture).
    base_payload = await request.json()
    request.json = AsyncMock(return_value={**base_payload, module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY: 2})

    _pipeline_never_returns_then_terminal = _pipeline_expiring_the_handler_budget(module)

    def _strict_release(job_id, token):
        return 0  # EVAL: token no longer owns the key — release unconfirmed

    try:
        module._run_full_pipeline_background_async = _pipeline_never_returns_then_terminal
        module.release_job_run_lock_strict = MagicMock(side_effect=_strict_release)
        module.update_sync_job = MagicMock(return_value=None)
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            status = 'completed' if reads['n'] > 2 else ('queued' if reads['n'] == 1 else 'processing')
            return {
                'job_id': job_id,
                'status': status,
                'lane': 'fresh',
                'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        module.update_sync_job.assert_not_called()
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        payload, _schedule_at = module.enqueue_sync_job_budget_replacement.call_args.args
        assert payload[module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY] == 3
        assert fallback_calls == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_owner_count_write_timeout_drains_and_rescues_the_deferral():
    """Thread: the owner-count write timeout cancels only the await — the
    Firestore transaction can still commit in db_executor. A drained True
    must rescue the deferral (the sweep will read exactly the count this
    chain carries, with its marker and replacement behind it); only a write
    that cannot settle keeps the queue-owned 409."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    base_payload = await request.json()
    request.json = AsyncMock(
        return_value={**base_payload, 'sequencer_epoch': 1, module.SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY: 1}
    )

    async def _pipeline_that_never_finishes(*args, **kwargs):
        await asyncio.sleep(30)

    owner_events = []

    async def _owner_count_commits_just_past_deadline(uid, job_id, epoch, count):
        owner_events.append(('write_started', count))
        # Consumes the whole deadline, then commits — still inside the
        # cleanup allowance the drain waits on.
        await asyncio.sleep(0.15)
        owner_events.append(('write_committed', count))
        return True

    async def _awaiting_run_blocking(_executor, fn, *args, **kwargs):
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    try:
        module.SYNC_JOB_HANDLER_BUDGET_SECONDS = 0.05
        module.SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = 0.05
        module._run_full_pipeline_background_async = _pipeline_that_never_finishes
        module.run_blocking = _awaiting_run_blocking
        module.sync_backfill_sequencer.note_budget_deferral = _owner_count_commits_just_past_deadline
        # The sequenced wrapper's preamble/heartbeat seams: begin admits the
        # epoch, the real create_task drives _maintain_uid_sequencer_lease
        # (HEARTBEAT_SECONDS must be a real number — the fixture's default
        # MagicMock would break the heartbeat's wait_for), and finish/kick
        # make the post-response owner handling inert.
        module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
        module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
        module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
        module.uid_sequencer.kick = MagicMock(return_value=True)
        module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
        module.update_sync_job = MagicMock(return_value={'job_id': 'job-1', 'status': 'processing'})
        module.enqueue_sync_job_budget_replacement = MagicMock()

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 200
        assert json.loads(response.body) == {'status': module.SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS}
        # The late commit was drained and rescued the deferral: the marker
        # and replacement landed behind the count the sweep will read.
        assert owner_events == [('write_started', 2), ('write_committed', 2)]
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        assert [call['reason'] for call in fallback_calls] == []
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


@pytest.mark.asyncio
async def test_terminal_cleanup_deferral_inherits_the_recovery_deadline():
    """Thread: the terminal-cleanup deferral must reuse the recovery's
    absolute deadline instead of minting a fresh enqueue allowance —
    post-budget windows must not stack against the route/dispatch wall. A
    sequenced terminal attempt whose recovery consumed the deadline gets
    its enqueue bounded by the inherited wall (timeout -> enqueue_uncertain
    409 — a timeout cannot prove the named task was not created), never a new
    SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS window."""

    module, saved_modules, _, _, fallback_calls, _ = _load_sync_router_for_fast_path()
    request = _configure_task_handler(
        module,
        pipeline_error=RuntimeError('pipeline must not complete'),
        latest_job={
            'job_id': 'job-1',
            'status': 'processing',
            'stt_provider': 'deepgram',
            'stt_model': 'nova-3',
        },
    )
    base_payload = await request.json()
    request.json = AsyncMock(return_value={**base_payload, 'sequencer_epoch': 1})

    _pipeline_never_returns_then_terminal = _pipeline_expiring_the_handler_budget(module)

    def _strict_release(job_id, token):
        return 0

    async def _awaiting_run_blocking(_executor, fn, *args, **kwargs):
        result = fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def _enqueue_never_settles(payload, schedule_at):
        # Records entry, then outlives any inherited deadline.
        await asyncio.sleep(30)

    try:
        # The recovery's deadline (now + cleanup timeout) is what the deferral inherits; the attempt's budget keeps
        # its production size and expires inside the pipeline stub, so runner speed can't move the expiry.
        module.SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS = 0.2
        module._run_full_pipeline_background_async = _pipeline_never_returns_then_terminal
        module.release_job_run_lock_strict = MagicMock(side_effect=_strict_release)
        module.update_sync_job = MagicMock(return_value=None)
        module.run_blocking = _awaiting_run_blocking
        # Sequenced-wrapper seams: a real heartbeat task needs a numeric
        # HEARTBEAT_SECONDS and a real create_task driver.
        module.sync_backfill_sequencer.HEARTBEAT_SECONDS = 120
        module.sync_backfill_sequencer.begin_job = MagicMock(return_value=True)
        module.sync_backfill_sequencer.finish_job = MagicMock(return_value=True)
        module.uid_sequencer.kick = MagicMock(return_value=True)
        module.start_background_task = lambda coro, *, name: asyncio.create_task(coro, name=name)
        module.enqueue_sync_job_budget_replacement = MagicMock(side_effect=_enqueue_never_settles)
        reads = {'n': 0}

        def _job_read(job_id):
            reads['n'] += 1
            # Sequenced delivery burns one read in the wrapper's prior-job
            # preamble (n=1), the attempt reads at n=2/n=3 (nonterminal, so
            # the pipeline runs and the budget expires mid-flight), and only
            # the recovery's terminal read (n=4) sees the completed job.
            status = 'completed' if reads['n'] > 3 else ('queued' if reads['n'] == 1 else 'processing')
            return {
                'job_id': job_id,
                'status': status,
                'lane': 'fresh',
                'ledger_fence_mode': module.SyncLedgerFenceMode.ACTIVE.value,
                'stt_provider': 'deepgram',
                'stt_model': 'nova-3',
            }

        module.get_sync_job = MagicMock(side_effect=_job_read)

        response = await module.run_sync_job(request, task_retry_count=0)

        assert response.status_code == 409
        assert json.loads(response.body) == {'status': 'locked'}
        module.enqueue_sync_job_budget_replacement.assert_called_once()
        assert [call['reason'] for call in fallback_calls] == ['enqueue_uncertain']
    finally:
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
