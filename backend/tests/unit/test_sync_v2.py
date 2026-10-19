"""
Tests for v2 async sync-local-files endpoints (#5941, #7281).

v2 saves raw files and returns 202 immediately, then runs the full pipeline
(decode → VAD → fair-use → STT → LLM) in a background thread. The app
polls GET /v2/sync-local-files/{job_id} until the job reaches a terminal status.

v1 remains completely unchanged.
"""

from utils.other import owned_paths  # noqa: F401 - retain real scratch guard across legacy package stubs

from utils import conversation_continuity  # noqa: F401 - retain pure policy across legacy package stubs
from utils import dream_vocabulary  # noqa: F401 - retain shared keyterms across legacy package stubs
from utils import firestore_document_size  # noqa: F401 - retain pure size estimate across legacy package stubs
from utils import manual_speaker_assignments  # noqa: F401 - retain pure policy across legacy package stubs
from utils.stt import speaker_identity  # noqa: F401 - retain allocator across legacy package stubs
from utils.stt import sync_speaker_evidence  # noqa: F401 - retain pure evidence policy across legacy package stubs
from utils.stt import voiceprints  # noqa: F401 - retain pure voiceprint policy across legacy package stubs
from utils.observability import speaker_identification  # noqa: F401 - retain telemetry across legacy package stubs
from utils.observability import sync_phases  # noqa: F401 - retain aggregate telemetry across legacy package stubs

import asyncio
import json
import os
import re
import sys
import time
import types
import unittest
from unittest.mock import MagicMock

import pytest
import gc

# Keep additive batch imports real before legacy fixtures replace package roots.
from utils.batch_pipeline import intake as _batch_intake  # noqa: F401
from utils.batch_pipeline import live_projection as _batch_live_projection  # noqa: F401
from utils.batch_pipeline import live_upload as _batch_live_upload  # noqa: F401
from routers import batch_pipeline as _batch_router  # noqa: F401
from models import sync_job_status as _sync_job_status  # noqa: F401
from fastapi.routing import APIRoute

PIPELINE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'legacy_segment_core.py')


@pytest.fixture(autouse=True)
def _prod_sync_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')


@pytest.fixture(autouse=True)
def _collect_previous_case_mocks():
    # Endpoint and coordinator cases both create cyclic MagicMock graphs.
    # Collect prior-case mocks in setup so a later call does not pay their cleanup.
    import gc

    gc.collect()


def _read_pipeline_source():
    with open(PIPELINE_PATH, encoding='utf-8') as f:
        return f.read()


from pydantic import BaseModel

# ---------------------------------------------------------------------------
# 1. Structural tests — verify v2 code exists with correct patterns
# ---------------------------------------------------------------------------


class TestSyncV2Structure:
    """Verify v2 endpoint code structure in sync.py."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path, encoding='utf-8') as f:
            return f.read()

    def test_v2_post_endpoint_exists(self):
        """POST /v2/sync-local-files must exist."""
        source = self._read_sync_source()
        assert '"/v2/sync-local-files"' in source
        assert 'async def sync_local_files_v2' in source

    def test_v2_get_endpoint_exists(self):
        """GET /v2/sync-local-files/{job_id} must exist."""
        source = self._read_sync_source()
        assert '"/v2/sync-local-files/{job_id}"' in source
        assert 'def get_sync_job_status' in source

    def test_v1_endpoint_is_a_410_stub(self):
        """v1 keeps its path and function name but answers 410 (lane 10 slice 2b; 7-day census: zero calls)."""
        source = self._read_sync_source()
        assert '"/v1/sync-local-files", deprecated=True, status_code=410' in source
        assert '\ndef sync_local_files(' in source

    def test_v2_has_hard_restriction_gate(self):
        """v2 inline path must check hard restriction (fast 429 for restricted users)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'get_hard_restriction_status' in func_body, "v2 must check hard restriction inline"

    def test_v2_does_not_decode_inline(self):
        """v2 fast path must NOT run decode/VAD inline (#7281)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'decode_files_to_wav' not in func_body, "v2 must NOT decode inline"
        assert 'retrieve_vad_segments' not in func_body, "v2 must NOT run VAD inline"
        assert 'build_person_embeddings_cache' not in func_body, "v2 must NOT build embeddings inline"

    def test_v2_get_checks_ownership(self):
        """GET endpoint must verify job belongs to requesting user."""
        source = self._read_sync_source()
        start = source.index('def get_sync_job_status')
        func_body = source[start:]

        assert "job['uid'] != uid" in func_body, "GET must check job ownership"
        assert '403' in func_body, "GET must return 403 for wrong owner"

    def test_v2_get_returns_404_for_missing(self):
        """GET must return 404 for expired/missing jobs."""
        source = self._read_sync_source()
        start = source.index('def get_sync_job_status')
        func_body = source[start:]

        assert '404' in func_body, "GET must return 404 for missing job"

    def test_v2_fast_path_uses_sync_executor(self):
        """Fast-path file save must use sync_executor, not storage_executor (#7372)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert (
            'run_blocking(sync_executor' in func_body
        ), "fast-path file save must use sync_executor to avoid storage_executor saturation (#7372)"
        assert (
            'run_blocking(storage_executor' not in func_body
        ), "fast-path must NOT use storage_executor — background pipeline saturates it (#7372)"


# ---------------------------------------------------------------------------
# 2. Redis sync_jobs module tests
# ---------------------------------------------------------------------------


def _configure_legacy_raw_cas(mock_redis):
    """Model the tokenless raw-CAS script in lightweight Redis unit fixtures."""

    def _eval(script, key_count, *args):
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

    mock_redis.eval.side_effect = _eval


class TestSyncJobsRedis:
    """Test database/sync_jobs.py Redis operations."""

    @staticmethod
    def _load_sync_jobs_module():
        """Load sync_jobs module with Redis stubbed out."""
        # Stub redis before importing
        mock_redis = MagicMock()
        _configure_legacy_raw_cas(mock_redis)
        mock_redis_module = MagicMock()
        mock_redis_module.Redis.return_value = mock_redis

        saved_modules = {}
        modules_to_stub = {
            'redis': mock_redis_module,
            'database': MagicMock(),
            'database.redis_db': MagicMock(r=mock_redis),
            'database._client': MagicMock(),
        }
        for mod, mock in modules_to_stub.items():
            saved_modules[mod] = sys.modules.get(mod)
            sys.modules[mod] = mock

        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_jobs',
                os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'sync_jobs.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module, mock_redis
        finally:
            for mod, original in saved_modules.items():
                if original is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = original

    def test_create_sync_job_stores_in_redis(self):
        """create_sync_job must store a JSON blob in Redis."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = mod.create_sync_job('test-uid', total_files=3, total_segments=10)

        assert job['uid'] == 'test-uid'
        assert job['status'] == 'queued'
        assert job['total_files'] == 3
        assert job['total_segments'] == 10
        assert 'job_id' in job
        mock_redis.set.assert_called_once()

    def test_create_sync_job_uses_provided_job_id(self):
        """create_sync_job with explicit job_id must use it."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = mod.create_sync_job('uid', total_files=1, total_segments=5, job_id='custom-id')
        assert job['job_id'] == 'custom-id'

    def test_get_sync_job_returns_none_for_missing(self):
        """get_sync_job must return None for non-existent keys."""
        mod, mock_redis = self._load_sync_jobs_module()
        mock_redis.get.return_value = None
        assert mod.get_sync_job('nonexistent') is None

    def test_get_sync_job_preserves_stale_processing_job(self):
        """Progress age alone cannot bypass the route's run-lease recovery boundary."""
        mod, mock_redis = self._load_sync_jobs_module()
        stale_job = {
            'job_id': 'stale-1',
            'uid': 'uid',
            'status': 'processing',
            'updated_at': time.time() - 700,  # 700s ago > 600s threshold
            'created_at': time.time() - 800,
        }
        mock_redis.get.return_value = json.dumps(stale_job).encode()

        result = mod.get_sync_job('stale-1')
        assert result == stale_job
        mock_redis.set.assert_not_called()

    def test_get_sync_job_does_not_mark_fresh_as_stale(self):
        """Processing jobs within threshold should not be marked failed."""
        mod, mock_redis = self._load_sync_jobs_module()
        fresh_job = {
            'job_id': 'fresh-1',
            'uid': 'uid',
            'status': 'processing',
            'updated_at': time.time() - 30,  # 30s ago < 600s
            'created_at': time.time() - 60,
        }
        mock_redis.get.return_value = json.dumps(fresh_job).encode()

        result = mod.get_sync_job('fresh-1')
        assert result['status'] == 'processing'

    def test_get_sync_job_does_not_fail_stale_queued(self):
        """A stale 'queued' job was never picked up (pool saturation) — it is
        NOT a worker failure and must stay 'queued' (see issue #7469)."""
        mod, mock_redis = self._load_sync_jobs_module()
        stale_queued = {
            'job_id': 'queued-1',
            'uid': 'uid',
            'status': 'queued',
            'updated_at': time.time() - 700,  # 700s ago > 600s threshold
            'created_at': time.time() - 800,
        }
        mock_redis.get.return_value = json.dumps(stale_queued).encode()

        result = mod.get_sync_job('queued-1')
        assert result['status'] == 'queued'
        assert result.get('error') is None
        mock_redis.set.assert_not_called()

    def test_never_dispatched_cloud_tasks_queued_job_goes_stale(self):
        """#10033: a cloud_tasks job that never left 'queued' lost its task and
        must become stale-eligible instead of zombieing until JOB_TTL expiry."""
        mod, mock_redis = self._load_sync_jobs_module()
        base = {
            'job_id': 'q-lost',
            'uid': 'uid',
            'status': 'queued',
            'dispatch_mode': 'cloud_tasks',
            'started_at': None,
            'created_at': time.time() - mod.QUEUED_DISPATCH_STALE_SECONDS - 100,
            'updated_at': time.time() - mod.QUEUED_DISPATCH_STALE_SECONDS - 100,
        }
        assert mod.is_sync_job_stale(dict(base)) is True
        # Under the dispatch threshold: not stale yet.
        assert mod.is_sync_job_stale({**base, 'updated_at': time.time() - 60}) is False
        # Inline queued jobs keep the #7469 contract at any age.
        assert mod.is_sync_job_stale({**base, 'dispatch_mode': 'inline'}) is False
        # A pending Cloud Tasks retry (worker re-queued between attempts) must
        # never be flipped terminal by a poll, however long its backoff.
        assert mod.is_sync_job_stale({**base, 'attempt': 2, 'started_at': time.time() - 4000}) is False

    def test_finalize_sync_job_sets_status(self):
        """finalize_sync_job must set correct terminal status."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j1',
            'uid': 'uid',
            'status': 'processing',
            'updated_at': time.time(),
        }
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.finalize_sync_job(
            'j1',
            {
                'new_memories': ['m1'],
                'updated_memories': [],
                'failed_segments': 0,
                'total_segments': 5,
                'errors': [],
            },
        )
        assert result['status'] == 'completed'

    def test_finalize_sync_job_partial_failure(self):
        """Partial failure: some segments fail → partial_failure status."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'j2', 'uid': 'uid', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.finalize_sync_job(
            'j2',
            {
                'failed_segments': 2,
                'total_segments': 5,
                'errors': ['err1', 'err2'],
            },
        )
        assert result['status'] == 'partial_failure'

    def test_finalize_sync_job_all_failed(self):
        """All segments failed → failed status."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'j3', 'uid': 'uid', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.finalize_sync_job(
            'j3',
            {
                'failed_segments': 5,
                'total_segments': 5,
                'errors': ['err1'],
            },
        )
        assert result['status'] == 'failed'
        assert result['error'] is not None
        assert 'err1' in result['error']

    def test_mark_job_completed_compatibility_alias(self):
        """Legacy router callers retain the same truthful finalization contract."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'legacy', 'uid': 'uid', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.mark_job_completed(
            'legacy',
            {
                'failed_segments': 1,
                'total_segments': 2,
                'errors': ['stt_timeout'],
            },
        )

        assert result['status'] == 'partial_failure'

    def test_mark_job_failed_sets_error(self):
        """mark_job_failed must set status=failed with error message."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'j4', 'uid': 'uid', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.mark_job_failed('j4', 'Worker crashed')
        assert result['status'] == 'failed'
        assert result['error'] == 'Worker crashed'


# ---------------------------------------------------------------------------
# 3. Background worker tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 4. v1 regression tests — v1 must be completely unchanged
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 5. v2 endpoint contract tests
# ---------------------------------------------------------------------------


class TestV2EndpointContract:
    """Test v2 endpoint behavior via structural inspection."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path, encoding='utf-8') as f:
            return f.read()

    def _get_v2_post_body(self):
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        return source[start:next_section]

    def test_v2_handles_429_hard_restricted(self):
        """v2 must check hard restriction at the top."""
        body = self._get_v2_post_body()
        assert 'get_hard_restriction_status' in body and 'uid' in body

    def test_v2_reraises_http_exceptions(self):
        """v2 must re-raise HTTPException from fast-path helpers."""
        body = self._get_v2_post_body()
        assert 'except HTTPException:' in body
        assert 'raise' in body[body.index('except HTTPException:') :]

    def test_v2_finally_cleans_up_on_fast_path_failure(self):
        """v2 finally block must clean up raw files if fast-path fails."""
        body = self._get_v2_post_body()
        finally_idx = body.rindex('finally:')
        finally_block = body[finally_idx:]
        assert '_cleanup_files(paths)' in finally_block


# ---------------------------------------------------------------------------
# 6. Redis boundary tests — behavioral TTL, stale threshold, overflow
# ---------------------------------------------------------------------------


class TestSyncJobsRedisBoundary:
    """Boundary tests for database/sync_jobs.py Redis operations."""

    @staticmethod
    def _load_sync_jobs_module():
        """Load sync_jobs module with Redis stubbed."""
        mock_redis = MagicMock()
        _configure_legacy_raw_cas(mock_redis)
        mock_redis_module = MagicMock()
        mock_redis_module.Redis.return_value = mock_redis

        saved_modules = {}
        modules_to_stub = {
            'redis': mock_redis_module,
            'database': MagicMock(),
            'database.redis_db': MagicMock(r=mock_redis),
            'database._client': MagicMock(),
        }
        for mod, mock in modules_to_stub.items():
            saved_modules[mod] = sys.modules.get(mod)
            sys.modules[mod] = mock

        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_jobs_boundary',
                os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'sync_jobs.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module, mock_redis
        finally:
            for mod, original in saved_modules.items():
                if original is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = original

    def test_create_sets_ttl(self):
        """create_sync_job must set TTL (ex=JOB_TTL_SECONDS) on Redis key."""
        mod, mock_redis = self._load_sync_jobs_module()
        mod.create_sync_job('uid', 1, 5)
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get('ex') == mod.JOB_TTL_SECONDS or call_args[1].get('ex') == mod.JOB_TTL_SECONDS

    def test_update_refreshes_ttl(self):
        """update_sync_job must refresh TTL on each update."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'j', 'uid': 'u', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()
        mod.update_sync_job('j', {'processed_segments': 3})
        assert mock_redis.eval.call_args.args[5] == mod.JOB_TTL_SECONDS

    def test_stale_at_exactly_threshold(self):
        """Job at exactly STALE_THRESHOLD_SECONDS should NOT be marked stale (> not >=)."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'processing',
            'updated_at': time.time() - mod.STALE_THRESHOLD_SECONDS,
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        result = mod.get_sync_job('j')
        # At exactly threshold: time.time() - updated_at == STALE_THRESHOLD_SECONDS
        # Since time passes between test setup and check, this may be slightly > threshold
        # The important behavioral test is the "just under" case below
        assert result is not None

    def test_stale_just_under_threshold(self):
        """Job 1 second under stale threshold must remain processing."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'processing',
            'updated_at': time.time() - (mod.STALE_THRESHOLD_SECONDS - 1),
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        result = mod.get_sync_job('j')
        assert result['status'] == 'processing'

    def test_stale_just_over_threshold_is_read_only(self):
        """Crossing the stale bound does not give a reader terminal-write authority."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'processing',
            'updated_at': time.time() - (mod.STALE_THRESHOLD_SECONDS + 1),
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        result = mod.get_sync_job('j')
        assert result == job
        mock_redis.set.assert_not_called()

    def test_stale_read_preserves_worker_state(self):
        """Only the owning coordinator can persist a failure, never the reader."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'processing',
            'updated_at': time.time() - 700,
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        result = mod.get_sync_job('j')
        assert result == job
        mock_redis.set.assert_not_called()

    def test_completed_job_not_stale_checked(self):
        """Terminal jobs must not be re-evaluated for staleness."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'completed',
            'updated_at': time.time() - 9999,
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        result = mod.get_sync_job('j')
        assert result['status'] == 'completed'

    def test_overflow_failed_segments_gt_total(self):
        """If failed_segments > total_segments, status should still reflect failure."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'j', 'uid': 'u', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()
        # This shouldn't happen in practice — if it does, partial_failure is safe
        # because the app treats any failure as retryable
        result = mod.finalize_sync_job(
            'j',
            {
                'failed_segments': 10,
                'total_segments': 5,
                'errors': [],
            },
        )
        # failed(10) >= total(5), so status is 'failed'
        assert result['status'] == 'failed'
        assert result['failed_segments'] == 10
        assert result['successful_segments'] == 0  # Clamped, not -5

    def test_update_sync_job_returns_none_for_missing(self):
        """update_sync_job must return None for non-existent jobs."""
        mod, mock_redis = self._load_sync_jobs_module()
        mock_redis.get.return_value = None
        result = mod.update_sync_job('nonexistent', {'status': 'processing'})
        assert result is None

    def test_update_sync_job_refreshes_updated_at(self):
        """update_sync_job must set updated_at to current time."""
        mod, mock_redis = self._load_sync_jobs_module()
        old_time = time.time() - 100
        job = {'job_id': 'j', 'uid': 'u', 'status': 'processing', 'updated_at': old_time}
        mock_redis.get.return_value = json.dumps(job).encode()
        before = time.time()
        result = mod.update_sync_job('j', {'processed_segments': 5})
        after = time.time()
        assert before <= result['updated_at'] <= after
        assert result['processed_segments'] == 5


# ---------------------------------------------------------------------------
# 7. Background worker behavioral tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 7b. Async coordinator behavioral test
# ---------------------------------------------------------------------------


class TestAsyncCoordinatorSemaphore:
    """Verify the loop-scoped semaphore limits concurrent sync pipelines."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path, encoding='utf-8') as f:
            return f.read()

    def test_semaphore_no_duplicate_cache(self):
        """sync.py must NOT have its own _sync_semaphores cache (use http_client's)."""
        source = self._read_sync_source()
        assert '_sync_semaphores' not in source, "Must not duplicate semaphore cache — use http_client"


# ---------------------------------------------------------------------------
# 7c. Async coordinator scenario coverage tests (#7361 tester round 1)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 7d. Behavioral async coordinator tests (invoke the actual coroutine)
# ---------------------------------------------------------------------------


async def _passthrough_resolve_geolocation(geolocation):
    """Stub for utils.conversations.location: identity, like the real resolver on a geocode miss."""
    return geolocation


def _install_sync_observability_stubs():
    """Stub observability modules + metrics for routers.sync imports.

    MagicMock('utils.observability') is not a package, so submodule imports fail
    unless we install a real ModuleType package with __path__.
    """
    obs_pkg = types.ModuleType('utils.observability')
    obs_pkg.__path__ = []  # type: ignore[attr-defined]
    fallback_mod = types.ModuleType('utils.observability.fallback')
    fallback_mod.record_fallback = MagicMock()
    transcription_mod = types.ModuleType('utils.observability.transcription')
    transcription_mod.record_sync_transcription_outcome = MagicMock()
    transcription_mod.record_sync_intake_outcome = MagicMock()
    journeys_mod = types.ModuleType('utils.observability.journeys')
    journeys_mod.record_client_journey_accepted = MagicMock()
    journeys_mod.record_client_journey_terminal = MagicMock()
    sys.modules['utils.observability'] = obs_pkg
    sys.modules['utils.observability.fallback'] = fallback_mod
    sys.modules['utils.observability.transcription'] = transcription_mod
    sys.modules['utils.observability.journeys'] = journeys_mod
    obs_pkg.fallback = fallback_mod
    obs_pkg.transcription = transcription_mod
    obs_pkg.journeys = journeys_mod
    sys.modules['utils.metrics'] = MagicMock(OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL=MagicMock())
    return fallback_mod


class TestAsyncCoordinatorBehavioral:
    """Behavioral tests that invoke _run_full_pipeline_background_async with
    mocked dependencies. Verifies actual call sequences and outcomes."""

    @staticmethod
    def _load_sync_module():
        """Load routers/sync.py with all heavy deps stubbed, return (module, stubs)."""
        # Load the optional repair dependency before replacing database/google
        # with non-package stubs. It stays real and gated off in dispatch tests.
        from services import summary_debt_repair  # noqa: F401

        saved_modules = {}
        stubs = {}
        from database.sync_jobs import SyncLedgerFenceMode

        prior_utils = sys.modules.get('utils')
        prior_utils_sync = sys.modules.get('utils.sync')
        prior_utils_stt = sys.modules.get('utils.stt')
        prior_outcomes = sys.modules.get('utils.stt.outcomes')
        from utils.stt import outcomes as actual_outcomes

        prior_speaker_match = sys.modules.get('utils.stt.speaker_match')
        from utils.stt import speaker_match as actual_speaker_match

        prior_speaker_identity = sys.modules.get('utils.stt.speaker_identity')
        from utils.stt import speaker_identity as actual_speaker_identity

        prior_manual_assignments = sys.modules.get('utils.manual_speaker_assignments')
        from utils import manual_speaker_assignments as actual_manual_assignments

        prior_capture_evidence = sys.modules.get('utils.capture_evidence')
        from utils import capture_evidence as actual_capture_evidence

        prior_sync_lanes = sys.modules.get('utils.sync.lanes')
        from utils.sync import lanes as actual_sync_lanes

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
            'database.firestore_read_metrics',
            'firebase_admin',
            'google',
            'google.cloud',
            'google.cloud.firestore_v1',
            'opuslib',
            'pydub',
            'models',
            'models.conversation',
            'models.conversation_enums',
            'models.geolocation',
            'models.sync_contract',
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
            'utils.conversations.smart_merge_policy',
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
            'utils.observability.transcription',
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

        # routers/sync.py resolves its handler budget at import time against the
        # dispatch deadline; a MagicMock attr cannot be compared inside min().
        sys.modules['utils.cloud_tasks'].DISPATCH_DEADLINE_SECONDS = 1500

        # Dispatch tests supply their own cache and do not acquire voiceprints.
        sys.modules['utils.stt.owner_profile'].load_owner_embedding = MagicMock(return_value=None)
        sys.modules['utils.stt.owner_profile'].validated_embedding = MagicMock(return_value=None)

        # The speaker entitlement must be a visible, fixed contract, not a truthy
        # MagicMock: sync identification consults it when building the person
        # cache, so pin it to paid explicitly.
        sys.modules['utils.speaker_permissions'].named_speaker_prompts_allowed = lambda uid: True

        # New conversation-assignment seam: pipeline imports the pure
        # deterministic minimum and the lifecycle intake. The former is
        # dependency-free production code (exec the real module); the latter
        # drags in the real database stack, so it stays a stub whose
        # ingest_sync_conversation attribute auto-mocks per call.
        import importlib.util as _il

        from testing.import_isolation import AutoMockModule

        _lifecycle_name = 'utils.conversations.lifecycle'
        saved_modules[_lifecycle_name] = sys.modules.get(_lifecycle_name)
        sys.modules[_lifecycle_name] = AutoMockModule(_lifecycle_name)

        # Keep deterministic title logic real with Structured and CategoryEnum before exec.
        from pydantic import BaseModel as _BaseModel

        class _Structured(_BaseModel):
            title: str = ''
            overview: str = ''
            category: str = 'other'
            sections: list = []
            action_items: list = []
            events: list = []

        class _CategoryEnum(str, __import__('enum').Enum):
            other = 'other'

        _enums_mod = sys.modules['models.conversation_enums']
        _enums_mod.CategoryEnum = _CategoryEnum
        _structured_mod = MagicMock()
        _structured_mod.Structured = _Structured
        _structured_name = 'models.structured'
        saved_modules[_structured_name] = sys.modules.get(_structured_name)
        sys.modules[_structured_name] = _structured_mod

        _dmin_name = 'utils.conversations.deterministic_minimum'
        _dmin_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'utils', 'conversations', 'deterministic_minimum.py'
        )
        saved_modules[_dmin_name] = sys.modules.get(_dmin_name)
        _dmin_spec = _il.spec_from_file_location(_dmin_name, _dmin_path)
        _dmin_mod = _il.module_from_spec(_dmin_spec)
        sys.modules[_dmin_name] = _dmin_mod
        _dmin_spec.loader.exec_module(_dmin_mod)

        class _Geolocation:
            def model_dump(self):
                return {}

        sys.modules['models.geolocation'].Geolocation = _Geolocation

        sys.modules['utils.account_cutover.access'].should_skip_background_account_mutation = MagicMock(
            return_value=False
        )
        # Keep the outcome contract real; the coordinator tests exercise its
        # enum values while every heavyweight provider dependency stays stubbed.
        saved_modules['utils'] = prior_utils
        saved_modules['utils.sync'] = prior_utils_sync
        saved_modules['utils.stt'] = prior_utils_stt
        saved_modules['utils.stt.outcomes'] = prior_outcomes
        sys.modules['utils.stt.outcomes'] = actual_outcomes
        saved_modules['utils.stt.speaker_match'] = prior_speaker_match
        # Keep the decision policy real (pure, dependency-free): the sync pipeline now
        # calls select_speaker_match(), and a MagicMock stand-in would return a MagicMock
        # decision whose fields blow up the %.3f log formatting even on an empty match set.
        sys.modules['utils.stt.speaker_match'] = actual_speaker_match
        saved_modules['utils.stt.speaker_identity'] = prior_speaker_identity
        # Keep the conversation-local allocator real: assignment.py imports it at
        # module scope, and a MagicMock parent for utils.stt is not a package.
        sys.modules['utils.stt.speaker_identity'] = actual_speaker_identity
        saved_modules['utils.manual_speaker_assignments'] = prior_manual_assignments
        # Keep receipt apply/remap real: pipeline → assignment imports the policy
        # module at scope, and a MagicMock parent for utils is not a package.
        sys.modules['utils.manual_speaker_assignments'] = actual_manual_assignments
        saved_modules['utils.capture_evidence'] = prior_capture_evidence
        # Keep the S1 evidence envelope builder real (pure, stdlib-only): the
        # pipeline imports unknown_envelope at module scope, and a MagicMock
        # parent for utils is not a package.
        sys.modules['utils.capture_evidence'] = actual_capture_evidence
        saved_modules['utils.sync.lanes'] = prior_sync_lanes
        # Keep SyncLane real: V2 responses serialize lane as a str-enum value, and a
        # MagicMock lane fails response validation. lanes.py is stdlib-only.
        sys.modules['utils.sync.lanes'] = actual_sync_lanes
        from testing.import_isolation import register_pure_relevance_modules

        register_pure_relevance_modules(saved_modules)
        sys.modules['utils.conversations.location'].async_resolve_geolocation = _passthrough_resolve_geolocation
        sys.modules['utils.multipart'].MultipartMaxPartSizeRoute = APIRoute
        sys.modules['utils.multipart'].SYNC_AUDIO_MAX_PART_SIZE = 200 * 1024 * 1024
        sys.modules['utils.multipart'].max_part_size = lambda _size: lambda endpoint: endpoint

        sys.modules['python_multipart'].__version__ = '0.0.99'
        sys.modules['python_multipart.multipart'].parse_options_header = MagicMock(return_value={})
        sys.modules['utils.log_sanitizer'].sanitize = lambda value: value
        sys.modules['utils.stt.pre_recorded'].get_prerecorded_service = MagicMock(
            return_value=('deepgram', 'multi', 'nova-3')
        )
        sys.modules['utils.client_device'].resolve_client_device = MagicMock(
            return_value=MagicMock(client_device_id=None, platform=None)
        )
        sys.modules['utils.client_device'].resolve_client_device_from_request = MagicMock(
            return_value=MagicMock(client_device_id=None, platform=None)
        )
        sys.modules['database.sync_ledger'].claim_sync_content = MagicMock(return_value={'outcome': 'owned'})
        sys.modules['database.sync_ledger'].release_sync_content_claim = MagicMock()
        sys.modules['database.sync_ledger'].release_sync_content_claim_after_job_retired = MagicMock()
        sys.modules['database.sync_ledger'].bind_sync_content_run_token = MagicMock(
            return_value=types.SimpleNamespace(bound=True, completed=False, result=None)
        )
        sys.modules['database.sync_ledger'].is_valid_completed_sync_content_result = MagicMock(return_value=False)
        sys.modules['database.sync_ledger'].mark_sync_content_completed = MagicMock()
        sys.modules['database.sync_ledger'].try_mark_sync_content_side_effect = MagicMock(return_value=True)
        sys.modules['utils.sync.backfill'].try_acquire_backfill_slot = MagicMock(return_value=True)
        sys.modules['utils.sync.backfill'].release_backfill_slot = MagicMock()
        sys.modules['utils.sync.backfill'].reserve_backfill_speech = MagicMock(
            return_value=MagicMock(allowed=True, reason=None, retry_after=None)
        )
        sys.modules['utils.sync.content_id'].compute_sync_content_id = MagicMock(return_value='content-1')

        _install_sync_observability_stubs()

        mock_executors = MagicMock()
        mock_executors.critical_executor = MagicMock()
        mock_executors.sync_executor = MagicMock()
        mock_executors.postprocess_executor = MagicMock()
        mock_executors.storage_executor = MagicMock()
        mock_executors.db_executor = MagicMock()

        async def _passthrough_run_blocking(_executor, fn, *args, **kwargs):
            if getattr(fn, '__name__', '') == '_process_one_segment':
                # Segment work runs in a worker in production and may run an async keyterm lookup.
                return await asyncio.to_thread(fn, *args, **kwargs)
            return fn(*args, **kwargs)

        mock_executors.run_blocking = _passthrough_run_blocking
        mock_executors.submit_with_context = MagicMock()
        saved_modules['utils.executors'] = sys.modules.get('utils.executors')
        sys.modules['utils.executors'] = mock_executors

        mock_sync_jobs = MagicMock()
        mock_sync_jobs.mark_job_processing = MagicMock()
        mock_sync_jobs.finalize_sync_job = MagicMock()
        mock_sync_jobs.mark_job_failed = MagicMock()
        mock_sync_jobs.update_sync_job = MagicMock()
        mock_sync_jobs.fenced_mark_job_processing = MagicMock(return_value=types.SimpleNamespace(applied=True, job={}))
        mock_sync_jobs.fenced_update_sync_job = MagicMock(return_value=types.SimpleNamespace(applied=True, job={}))
        mock_sync_jobs.fenced_finalize_sync_job = MagicMock(return_value=types.SimpleNamespace(applied=True, job={}))
        mock_sync_jobs.fenced_mark_job_failed = MagicMock(return_value=types.SimpleNamespace(applied=True, job={}))
        mock_sync_jobs.add_processed_segment_if_run_owner = MagicMock(
            return_value=types.SimpleNamespace(applied=True, job={})
        )
        mock_sync_jobs.create_sync_job = MagicMock()
        mock_sync_jobs.get_sync_job = MagicMock()
        mock_sync_jobs.release_job_run_lock = MagicMock()
        mock_sync_jobs.renew_job_run_lock = MagicMock(return_value=True)
        mock_sync_jobs.try_acquire_sync_job_run_lock = MagicMock()
        mock_sync_jobs.get_sync_job_run_lock_epoch = MagicMock(return_value=1)
        mock_sync_jobs.delete_sync_job_run_lock_epoch = MagicMock()
        mock_sync_jobs.SyncLedgerFenceMode = SyncLedgerFenceMode
        mock_sync_jobs.get_sync_ledger_fence_mode = MagicMock(return_value=SyncLedgerFenceMode.ACTIVE)
        mock_sync_jobs.sync_job_uses_ledger_fence = MagicMock(
            side_effect=lambda job: bool(job and job.get('ledger_fence_mode') == SyncLedgerFenceMode.ACTIVE.value)
        )
        mock_sync_jobs.mark_job_queued_for_retry = MagicMock()
        mock_sync_jobs.try_acquire_job_run_lock = MagicMock(return_value='legacy-lock-token')
        mock_sync_jobs.RUN_LOCK_HEARTBEAT_SECONDS = 300
        mock_sync_jobs.RUN_LOCK_TTL_SECONDS = 1800
        mock_sync_jobs.RUN_LOCK_RENEWAL_SAFETY_SECONDS = 300
        mock_sync_jobs.TERMINAL_STATUSES = ('completed', 'partial_failure', 'failed')
        mock_sync_jobs.is_sync_job_stale = MagicMock(return_value=False)
        saved_modules['database.sync_jobs'] = sys.modules.get('database.sync_jobs')
        sys.modules['database.sync_jobs'] = mock_sync_jobs

        sys.modules['database.redis_db'] = MagicMock(r=MagicMock())
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_hard_restriction_status = MagicMock(return_value=(False, None))
        sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
        sys.modules['utils.fair_use'].record_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].get_rolling_speech_ms = MagicMock(return_value={})
        sys.modules['utils.fair_use'].check_soft_caps = MagicMock(return_value=[])
        sys.modules['utils.fair_use'].trigger_classifier_if_needed = MagicMock()
        sys.modules['utils.fair_use'].record_dg_usage_ms = MagicMock()
        sys.modules['utils.byok'].set_byok_keys = MagicMock()
        sys.modules['utils.byok'].set_byok_uid = MagicMock()
        sys.modules['utils.byok'].get_byok_keys = MagicMock(return_value={})
        sys.modules['utils.analytics'].record_usage = MagicMock()
        sys.modules['utils.request_validation'].parse_sync_filename_timestamp = MagicMock(return_value=time.time())
        sync_pkg = types.ModuleType('utils.sync')
        sync_pkg.__path__ = [os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync')]
        sys.modules['utils.sync'] = sync_pkg
        sys.modules['utils.sync'].files = sys.modules['utils.sync.files']
        sys.modules['utils.sync'].playback = sys.modules['utils.sync.playback']
        sys.modules['utils.sync.playback'].build_playback_artifact = MagicMock(return_value=b'')
        sys.modules['utils.sync.playback'].PlaybackBuildError = type('PlaybackBuildError', (Exception,), {})
        sys.modules['models.conversation_enums'].ConversationSource = MagicMock()
        sys.modules['models.sync_contract'].SYNC_LOCAL_FILES_V2_RESPONSES = {}

        class _AudioPrecacheResponse(BaseModel):
            pass

        class _AudioUrlsResponse(BaseModel):
            pass

        sys.modules['models.sync_audio'].AudioPrecacheResponse = _AudioPrecacheResponse
        sys.modules['models.sync_audio'].AudioUrlsResponse = _AudioUrlsResponse
        sys.modules['utils.other.endpoints'].get_current_user_uid = MagicMock(return_value='test-uid')
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)

        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.legacy_segment_core', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            'sync_behavioral',
            os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
        )
        module = importlib.util.module_from_spec(spec)

        spec.loader.exec_module(module)

        pipeline_mod = sys.modules['utils.sync.legacy_segment_core']

        stubs['sync_jobs'] = mock_sync_jobs
        stubs['fair_use'] = sys.modules['utils.fair_use']
        stubs['byok'] = sys.modules['utils.byok']
        stubs['analytics'] = sys.modules['utils.analytics']
        stubs['pipeline'] = pipeline_mod
        stubs['saved_modules'] = saved_modules

        return module, stubs

    @staticmethod
    def _cleanup(saved_modules):
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.legacy_segment_core', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        sys.modules.pop('sync_behavioral', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig

    @pytest.fixture
    def fenced_worker_module(self):
        """Build the import-heavy behavioral harness outside the test call budget."""
        module, stubs = self._load_sync_module()
        # Release prior cyclic mock graphs during harness setup, so a full-heap
        # collection does not get charged to an unrelated request assertion.
        gc.collect()
        try:
            yield module, stubs
        finally:
            self._cleanup(stubs['saved_modules'])

    def test_merged_reprocess_fence_isolated_to_its_conversation(self, fenced_worker_module):
        """One replaced merge target must not supersede its sibling conversations."""
        _module, stubs = fenced_worker_module
        pipeline = stubs['pipeline']

        class ConversationPersistenceFenced(RuntimeError):
            pass

        pipeline.SyncConversationPersistenceFenced = ConversationPersistenceFenced
        pipeline.logger = MagicMock()
        pipeline._reprocess_conversation_after_update = MagicMock(
            side_effect=[ConversationPersistenceFenced('conversation replaced'), None]
        )
        response = {
            '_merged': {'replaced-conversation': 'en', 'current-conversation': 'fr'},
            'updated_memories': {'replaced-conversation', 'current-conversation'},
            # A conversation can appear in both new_memories (created in an
            # earlier segment) and updated_memories (merged into by a later
            # segment).  The fence must discard it from both.
            'new_memories': {'replaced-conversation'},
        }
        checkpointed_fences = []

        pipeline._reprocess_merged_conversations(
            'uid',
            response,
            on_fenced=lambda: checkpointed_fences.append(
                {
                    'fenced': set(response['_fenced_conversation_ids']),
                    'updated': set(response['updated_memories']),
                }
            ),
        )

        assert response == {
            '_fenced_conversation_ids': {'replaced-conversation'},
            'updated_memories': {'current-conversation'},
            'new_memories': set(),
        }
        assert checkpointed_fences == [{'fenced': {'replaced-conversation'}, 'updated': {'current-conversation'}}]
        # `_merged` reprocessing runs for every conversation that gained segments;
        # created rows enrich through the same update path (the intake already
        # persisted the deterministic minimum, so the processor must not re-create).
        assert pipeline._reprocess_conversation_after_update.call_args_list == [
            unittest.mock.call('uid', 'replaced-conversation', 'en'),
            unittest.mock.call('uid', 'current-conversation', 'fr'),
        ]
        pipeline.logger.info.assert_called_once_with(
            'event=sync_conversation_reprocess outcome=fenced conversation_id=%s',
            'replaced-conversation',
        )
        pipeline.logger.error.assert_not_called()

        audio_file = MagicMock()
        audio_file.model_dump.return_value = {'path': 'current.opus'}
        pipeline.conversations_db = MagicMock()
        pipeline.conversations_db.create_audio_files_from_chunks.return_value = [audio_file]
        pipeline.precache_conversation_audio = MagicMock()
        pipeline.is_audio_merge_dispatch_enabled = MagicMock(return_value=False)

        pipeline._finalize_sync_audio_files('uid', response)

        pipeline.conversations_db.create_audio_files_from_chunks.assert_called_once_with('uid', 'current-conversation')
        pipeline.conversations_db.update_conversation.assert_called_once_with(
            'uid', 'current-conversation', {'audio_files': [{'path': 'current.opus'}]}
        )

    def test_merged_reprocess_destructive_op_fence_is_not_swallowed(self, fenced_worker_module):
        '''A transient destructive-op fence must fail the batch, not log-and-continue.'''
        _module, stubs = fenced_worker_module
        pipeline = stubs['pipeline']

        class DestructiveOperationInProgress(RuntimeError):
            pass

        pipeline.logger = MagicMock()
        pipeline._reprocess_conversation_after_update = MagicMock(
            side_effect=DestructiveOperationInProgress('legal_hold_deletion_gates')
        )
        response = {
            '_merged': {'conv-a': 'en', 'conv-b': 'fr'},
            'updated_memories': {'conv-a', 'conv-b'},
            'new_memories': set(),
        }

        with pytest.raises(DestructiveOperationInProgress):
            pipeline._reprocess_merged_conversations('uid', response)

        pipeline.logger.error.assert_not_called()
        assert pipeline._reprocess_conversation_after_update.call_args_list == [
            unittest.mock.call('uid', 'conv-a', 'en'),
        ]
        assert response['updated_memories'] == {'conv-a', 'conv-b'}

    def test_limitless_discard_recovery_emits_one_creation_webhook(self, fenced_worker_module):
        """A pendant conversation becomes webhook-visible when merged speech revives it."""
        _module, stubs = fenced_worker_module
        pipeline = stubs['pipeline']
        limitless_source = pipeline.ConversationSource.limitless
        original = types.SimpleNamespace(source=limitless_source, discarded=True)
        recovered = types.SimpleNamespace(source=limitless_source, discarded=False)

        pipeline.conversations_db.get_conversation = MagicMock(return_value={'id': 'limitless-conversation'})
        pipeline.deserialize_conversation = MagicMock(return_value=original)
        pipeline.process_conversation = MagicMock(return_value=recovered)
        pipeline._run_conversation_created_webhook = MagicMock()
        pipeline.submit_with_context = MagicMock(side_effect=lambda _executor, fn, *args: fn(*args))

        pipeline._reprocess_conversation_after_update('uid-1', 'limitless-conversation', 'en')

        pipeline._run_conversation_created_webhook.assert_called_once_with('uid-1', recovered)

        original.discarded = False
        pipeline._reprocess_conversation_after_update('uid-1', 'limitless-conversation', 'en')
        pipeline._run_conversation_created_webhook.assert_called_once()


# ---------------------------------------------------------------------------
# 8. v2 endpoint execution tests via FastAPI TestClient
# ---------------------------------------------------------------------------


class TestV2EndpointExecution:
    """Execute v2 endpoints using FastAPI TestClient with mocked dependencies."""

    @staticmethod
    def _build_test_app():
        """Build a minimal FastAPI app with the sync router, all deps mocked."""
        saved_modules = {}
        mock_sync_jobs = MagicMock()
        mock_fair_use = MagicMock()
        prior_utils = sys.modules.get('utils')
        prior_utils_sync = sys.modules.get('utils.sync')
        prior_utils_stt = sys.modules.get('utils.stt')
        prior_outcomes = sys.modules.get('utils.stt.outcomes')
        from utils.stt import outcomes as actual_outcomes

        prior_speaker_match = sys.modules.get('utils.stt.speaker_match')
        from utils.stt import speaker_match as actual_speaker_match

        prior_speaker_identity = sys.modules.get('utils.stt.speaker_identity')
        from utils.stt import speaker_identity as actual_speaker_identity

        prior_manual_assignments = sys.modules.get('utils.manual_speaker_assignments')
        from utils import manual_speaker_assignments as actual_manual_assignments

        prior_capture_evidence = sys.modules.get('utils.capture_evidence')
        from utils import capture_evidence as actual_capture_evidence

        prior_sync_lanes = sys.modules.get('utils.sync.lanes')
        from utils.sync import lanes as actual_sync_lanes

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
            'database.firestore_read_metrics',
            'firebase_admin',
            'google',
            'google.cloud',
            'google.cloud.firestore_v1',
            'opuslib',
            'pydub',
            'models',
            'models.conversation',
            'models.conversation_enums',
            'models.geolocation',
            'models.sync_contract',
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
            'utils.conversations.smart_merge_policy',
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
            'utils.observability.transcription',
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

        # routers/sync.py resolves its handler budget at import time against the
        # dispatch deadline; a MagicMock attr cannot be compared inside min().
        sys.modules['utils.cloud_tasks'].DISPATCH_DEADLINE_SECONDS = 1500

        # Dispatch tests supply their own cache and do not acquire voiceprints.
        sys.modules['utils.stt.owner_profile'].load_owner_embedding = MagicMock(return_value=None)
        sys.modules['utils.stt.owner_profile'].validated_embedding = MagicMock(return_value=None)

        # The speaker entitlement must be a visible, fixed contract, not a truthy
        # MagicMock: sync identification consults it when building the person
        # cache, so pin it to paid explicitly.
        sys.modules['utils.speaker_permissions'].named_speaker_prompts_allowed = lambda uid: True

        # New conversation-assignment seam: pipeline imports the pure
        # deterministic minimum and the lifecycle intake. The former is
        # dependency-free production code (exec the real module); the latter
        # drags in the real database stack, so it stays a stub whose
        # ingest_sync_conversation attribute auto-mocks per call.
        import importlib.util as _il

        from testing.import_isolation import AutoMockModule

        _lifecycle_name = 'utils.conversations.lifecycle'
        saved_modules[_lifecycle_name] = sys.modules.get(_lifecycle_name)
        sys.modules[_lifecycle_name] = AutoMockModule(_lifecycle_name)

        # Keep deterministic title logic real with Structured and CategoryEnum before exec.
        from pydantic import BaseModel as _BaseModel

        class _Structured(_BaseModel):
            title: str = ''
            overview: str = ''
            category: str = 'other'
            sections: list = []
            action_items: list = []
            events: list = []

        class _CategoryEnum(str, __import__('enum').Enum):
            other = 'other'

        _enums_mod = sys.modules['models.conversation_enums']
        _enums_mod.CategoryEnum = _CategoryEnum
        _structured_mod = MagicMock()
        _structured_mod.Structured = _Structured
        _structured_name = 'models.structured'
        saved_modules[_structured_name] = sys.modules.get(_structured_name)
        sys.modules[_structured_name] = _structured_mod

        _dmin_name = 'utils.conversations.deterministic_minimum'
        _dmin_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'utils', 'conversations', 'deterministic_minimum.py'
        )
        saved_modules[_dmin_name] = sys.modules.get(_dmin_name)
        _dmin_spec = _il.spec_from_file_location(_dmin_name, _dmin_path)
        _dmin_mod = _il.module_from_spec(_dmin_spec)
        sys.modules[_dmin_name] = _dmin_mod
        _dmin_spec.loader.exec_module(_dmin_mod)

        class _Geolocation:
            def model_dump(self):
                return {}

        sys.modules['models.geolocation'].Geolocation = _Geolocation

        sys.modules['utils.account_cutover.access'].should_skip_background_account_mutation = MagicMock(
            return_value=False
        )
        saved_modules['utils'] = prior_utils
        saved_modules['utils.sync'] = prior_utils_sync
        saved_modules['utils.stt'] = prior_utils_stt
        saved_modules['utils.stt.outcomes'] = prior_outcomes
        sys.modules['utils.stt.outcomes'] = actual_outcomes
        saved_modules['utils.stt.speaker_match'] = prior_speaker_match
        # Keep the decision policy real (pure, dependency-free): the sync pipeline now
        # calls select_speaker_match(), and a MagicMock stand-in would return a MagicMock
        # decision whose fields blow up the %.3f log formatting even on an empty match set.
        sys.modules['utils.stt.speaker_match'] = actual_speaker_match
        saved_modules['utils.stt.speaker_identity'] = prior_speaker_identity
        # Keep the conversation-local allocator real: assignment.py imports it at
        # module scope, and a MagicMock parent for utils.stt is not a package.
        sys.modules['utils.stt.speaker_identity'] = actual_speaker_identity
        saved_modules['utils.manual_speaker_assignments'] = prior_manual_assignments
        # Keep receipt apply/remap real: pipeline → assignment imports the policy
        # module at scope, and a MagicMock parent for utils is not a package.
        sys.modules['utils.manual_speaker_assignments'] = actual_manual_assignments
        saved_modules['utils.capture_evidence'] = prior_capture_evidence
        # Keep the S1 evidence envelope builder real (pure, stdlib-only): the
        # pipeline imports unknown_envelope at module scope, and a MagicMock
        # parent for utils is not a package.
        sys.modules['utils.capture_evidence'] = actual_capture_evidence
        saved_modules['utils.sync.lanes'] = prior_sync_lanes
        # Keep SyncLane real: V2 responses serialize lane as a str-enum value, and a
        # MagicMock lane fails response validation. lanes.py is stdlib-only.
        sys.modules['utils.sync.lanes'] = actual_sync_lanes
        from testing.import_isolation import register_pure_relevance_modules

        register_pure_relevance_modules(saved_modules)
        sys.modules['utils.conversations.location'].async_resolve_geolocation = _passthrough_resolve_geolocation
        sys.modules['utils.multipart'].MultipartMaxPartSizeRoute = APIRoute
        sys.modules['utils.multipart'].SYNC_AUDIO_MAX_PART_SIZE = 200 * 1024 * 1024
        sys.modules['utils.multipart'].max_part_size = lambda _size: lambda endpoint: endpoint

        sys.modules['python_multipart'].__version__ = '0.0.99'
        sys.modules['python_multipart.multipart'].parse_options_header = MagicMock(return_value={})
        sys.modules['utils.log_sanitizer'].sanitize = lambda value: value
        sys.modules['utils.stt.pre_recorded'].get_prerecorded_service = MagicMock(
            return_value=('deepgram', 'multi', 'nova-3')
        )
        sys.modules['utils.client_device'].resolve_client_device = MagicMock(
            return_value=MagicMock(client_device_id=None, platform=None)
        )
        sys.modules['utils.client_device'].resolve_client_device_from_request = MagicMock(
            return_value=MagicMock(client_device_id=None, platform=None)
        )
        sys.modules['database.sync_ledger'].claim_sync_content = MagicMock(return_value={'outcome': 'owned'})
        sys.modules['database.sync_ledger'].release_sync_content_claim = MagicMock()
        sys.modules['database.sync_ledger'].release_sync_content_claim_after_job_retired = MagicMock()
        sys.modules['database.sync_ledger'].bind_sync_content_run_token = MagicMock(
            return_value=types.SimpleNamespace(bound=True, completed=False, result=None)
        )
        sys.modules['database.sync_ledger'].is_valid_completed_sync_content_result = MagicMock(return_value=False)
        sys.modules['database.sync_ledger'].mark_sync_content_completed = MagicMock()
        sys.modules['database.sync_ledger'].try_mark_sync_content_side_effect = MagicMock(return_value=True)
        sys.modules['utils.sync.backfill'].try_acquire_backfill_slot = MagicMock(return_value=True)
        sys.modules['utils.sync.backfill'].release_backfill_slot = MagicMock()
        sys.modules['utils.sync.backfill'].reserve_backfill_speech = MagicMock(
            return_value=MagicMock(allowed=True, reason=None, retry_after=None)
        )
        sys.modules['utils.sync.content_id'].compute_sync_content_id = MagicMock(return_value='content-1')

        _install_sync_observability_stubs()

        # Stub utils.executors with real-ish executor mocks
        import contextvars

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
        sys.modules['database.sync_jobs'] = mock_sync_jobs
        # Same import-time budget resolution as the first harness: the TTL and
        # stale threshold must be comparable numbers, not MagicMock attrs.
        mock_sync_jobs.RUN_LOCK_TTL_SECONDS = 1800
        mock_sync_jobs.STALE_THRESHOLD_SECONDS = 600
        mock_sync_jobs.QUEUED_DISPATCH_STALE_SECONDS = 1800
        mock_sync_jobs.is_sync_job_stale = MagicMock(return_value=False)
        mock_sync_jobs.try_acquire_sync_job_run_lock = MagicMock()
        mock_sync_jobs.get_sync_job_run_lock_epoch = MagicMock(return_value=1)
        mock_sync_jobs.delete_sync_job_run_lock_epoch = MagicMock()

        # Set up fair_use defaults
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_hard_restriction_status = MagicMock(return_value=(False, None))
        sys.modules['utils.fair_use'].is_daily_audio_ceiling_exceeded = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)
        sys.modules['utils.request_validation'].parse_sync_filename_timestamp = MagicMock(return_value=time.time())
        sync_pkg = types.ModuleType('utils.sync')
        sync_pkg.__path__ = [os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync')]
        sys.modules['utils.sync'] = sync_pkg
        sys.modules['utils.sync'].files = sys.modules['utils.sync.files']
        sys.modules['utils.sync'].playback = sys.modules['utils.sync.playback']
        sys.modules['utils.sync.playback'].build_playback_artifact = MagicMock(return_value=b'')
        sys.modules['utils.sync.playback'].PlaybackBuildError = type('PlaybackBuildError', (Exception,), {})

        class _AudioPrecacheResponse(BaseModel):
            pass

        class _AudioUrlsResponse(BaseModel):
            pass

        sys.modules['models.sync_audio'].AudioPrecacheResponse = _AudioPrecacheResponse
        sys.modules['models.sync_audio'].AudioUrlsResponse = _AudioUrlsResponse
        sys.modules['models.sync_contract'].SYNC_LOCAL_FILES_V2_RESPONSES = {}

        # Mock auth to return test uid
        sys.modules['utils.other.endpoints'].get_current_user_uid = MagicMock(return_value='test-uid')

        return saved_modules, mock_sync_jobs, mock_fair_use

    @staticmethod
    def _cleanup_modules(saved_modules):
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.legacy_segment_core', None)
        sys.modules.pop('utils.sync.ledger_completion', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig

    def test_get_poll_404_expired_job(self, sync_endpoint_module):
        """GET poll returns 404 when job not found."""
        saved, mock_sync_jobs, module = sync_endpoint_module
        mock_sync_jobs.get_sync_job = MagicMock(return_value=None)

        try:
            module.get_sync_job = mock_sync_jobs.get_sync_job
            module.create_sync_job = mock_sync_jobs.create_sync_job

            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(module.router)

            # Override auth dependency — use the module's reference, not the sys.modules mock
            app.dependency_overrides[module.auth.get_current_user_uid] = lambda: 'test-uid'

            client = TestClient(app)
            resp = client.get('/v2/sync-local-files/nonexistent-job-id')
            assert resp.status_code == 404
            assert 'not found' in resp.json()['detail'].lower()
        finally:
            self._cleanup_modules(saved)

    def test_get_poll_403_wrong_owner(self, sync_endpoint_module):
        """GET poll returns 403 when job belongs to different user."""
        saved, mock_sync_jobs, module = sync_endpoint_module
        mock_sync_jobs.get_sync_job = MagicMock(
            return_value={
                'job_id': 'some-job',
                'uid': 'other-user',
                'status': 'processing',
                'total_segments': 5,
                'processed_segments': 0,
                'successful_segments': 0,
                'failed_segments': 0,
            }
        )

        try:
            module.get_sync_job = mock_sync_jobs.get_sync_job
            module.create_sync_job = mock_sync_jobs.create_sync_job

            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(module.router)
            app.dependency_overrides[module.auth.get_current_user_uid] = lambda: 'test-uid'

            client = TestClient(app)
            resp = client.get('/v2/sync-local-files/some-job')
            assert resp.status_code == 403
        finally:
            self._cleanup_modules(saved)

    def test_get_poll_completed_includes_result(self, sync_endpoint_module):
        """GET poll returns result and error fields on terminal status."""
        saved, mock_sync_jobs, module = sync_endpoint_module
        mock_sync_jobs.get_sync_job = MagicMock(
            return_value={
                'job_id': 'done-job',
                'uid': 'test-uid',
                'status': 'completed',
                'total_segments': 3,
                'processed_segments': 3,
                'successful_segments': 3,
                'failed_segments': 0,
                'result': {'new_memories': ['m1'], 'updated_memories': []},
                'error': None,
            }
        )

        try:
            module.get_sync_job = mock_sync_jobs.get_sync_job
            module.create_sync_job = mock_sync_jobs.create_sync_job

            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(module.router)
            app.dependency_overrides[module.auth.get_current_user_uid] = lambda: 'test-uid'

            client = TestClient(app)
            resp = client.get('/v2/sync-local-files/done-job')
            assert resp.status_code == 200
            body = resp.json()
            assert body['status'] == 'completed'
            assert body['result']['new_memories'] == ['m1']
            assert body['successful_segments'] == 3
            assert body['failed_segments'] == 0
        finally:
            self._cleanup_modules(saved)

    def test_get_poll_failed_includes_error(self, sync_endpoint_module):
        """GET poll returns error field when all segments failed."""
        saved, mock_sync_jobs, module = sync_endpoint_module
        mock_sync_jobs.get_sync_job = MagicMock(
            return_value={
                'job_id': 'fail-job',
                'uid': 'test-uid',
                'status': 'failed',
                'total_segments': 2,
                'processed_segments': 2,
                'successful_segments': 0,
                'failed_segments': 2,
                'result': {'errors': ['err1', 'err2'], 'failed_segments': 2, 'total_segments': 2},
                'error': 'All 2 segments failed. First error: err1',
            }
        )

        try:
            module.get_sync_job = mock_sync_jobs.get_sync_job
            module.create_sync_job = mock_sync_jobs.create_sync_job

            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(module.router)
            app.dependency_overrides[module.auth.get_current_user_uid] = lambda: 'test-uid'

            client = TestClient(app)
            resp = client.get('/v2/sync-local-files/fail-job')
            assert resp.status_code == 200
            body = resp.json()
            assert body['status'] == 'failed'
            assert 'error' in body
            assert 'err1' in body['error']
        finally:
            self._cleanup_modules(saved)

    def test_get_poll_processing_excludes_result(self, sync_endpoint_module):
        """GET poll must NOT include result/error when job is still processing."""
        saved, mock_sync_jobs, module = sync_endpoint_module
        mock_sync_jobs.get_sync_job = MagicMock(
            return_value={
                'job_id': 'active-job',
                'uid': 'test-uid',
                'status': 'processing',
                'total_segments': 5,
                'processed_segments': 2,
                'successful_segments': 0,
                'failed_segments': 0,
                'result': None,
                'error': None,
            }
        )

        try:
            module.get_sync_job = mock_sync_jobs.get_sync_job
            module.create_sync_job = mock_sync_jobs.create_sync_job

            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(module.router)
            app.dependency_overrides[module.auth.get_current_user_uid] = lambda: 'test-uid'

            client = TestClient(app)
            resp = client.get('/v2/sync-local-files/active-job')
            assert resp.status_code == 200
            body = resp.json()
            assert body['status'] == 'processing'
            assert 'result' not in body
            assert 'error' not in body
            assert body['processed_segments'] == 2
        finally:
            self._cleanup_modules(saved)

    @pytest.fixture
    def sync_endpoint_module(self):
        """Keep real router import/setup outside the endpoint execution budget."""
        saved, jobs, _ = self._build_test_app()
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_endpoint_fixture', os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            gc.collect()
            yield saved, jobs, module
        finally:
            self._cleanup_modules(saved)


# ---------------------------------------------------------------------------
# Conversation finalizer executor pattern
# ---------------------------------------------------------------------------


class TestConversationFinalizerExecutor:
    """The durable finalizer must use the post-processing bulkhead."""

    @staticmethod
    def _read_finalizer_source():
        finalizer_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'conversations', 'finalizer.py')
        with open(finalizer_path, encoding='utf-8') as f:
            return f.read()

    def test_process_conversation_uses_postprocess_bulkhead(self):
        source = self._read_finalizer_source()
        assert 'postprocess_executor' in source
        assert re.search(
            r'run_blocking\(\s+postprocess_executor,\s+process_with_episode_budget,\s+process_conversation', source
        )


# 14. Bulkhead executor infrastructure tests


class TestBulkheadExecutors:
    """Verify bulkhead executor configuration in utils/executors.py."""

    @staticmethod
    def _read_executors_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'executors.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_sync_executor_exists(self):
        source = self._read_executors_source()
        assert 'sync_executor' in source
        assert "thread_name_prefix=\"sync\"" in source or "thread_name_prefix='sync'" in source

    def test_postprocess_executor_exists(self):
        source = self._read_executors_source()
        assert 'postprocess_executor' in source
        assert "thread_name_prefix=\"postproc\"" in source or "thread_name_prefix='postproc'" in source

    def test_executor_worker_counts(self):
        source = self._read_executors_source()
        assert 'sync_executor = MonitoredThreadPoolExecutor(' in source
        assert 'max_workers=16' in source
        assert 'postprocess_executor = MonitoredThreadPoolExecutor(' in source
        assert 'max_workers=24' in source
        assert 'storage_executor = MonitoredThreadPoolExecutor(' in source
        assert 'max_workers=128' in source

    def test_all_executors_in_shutdown(self):
        source = self._read_executors_source()
        for name in ['critical', 'sync', 'postprocess', 'storage']:
            assert f"'{name}'" in source or f'"{name}"' in source, f"Executor '{name}' must be in shutdown_executors"

    def test_submit_with_context_exists(self):
        source = self._read_executors_source()
        assert 'def submit_with_context(' in source
        assert 'contextvars.copy_context()' in source

    def test_submit_with_context_propagates_contextvars(self):
        """submit_with_context must propagate ContextVar values to the submitted thread."""
        import contextvars
        from concurrent.futures import ThreadPoolExecutor

        test_var = contextvars.ContextVar('test_key', default=None)
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='test_ctx')

        try:
            test_var.set('hello')
            ctx = contextvars.copy_context()
            future = executor.submit(ctx.run, test_var.get)
            assert future.result(timeout=5) == 'hello'

            test_var.set('different')
            ctx2 = contextvars.copy_context()
            future2 = executor.submit(ctx2.run, test_var.get)
            assert future2.result(timeout=5) == 'different'
        finally:
            executor.shutdown(wait=False)

    def test_executor_isolation_different_pools(self):
        """sync_executor and postprocess_executor must be distinct objects."""
        source = self._read_executors_source()
        lines = source.strip().split('\n')
        sync_lines = [l for l in lines if l.startswith('sync_executor')]
        post_lines = [l for l in lines if l.startswith('postprocess_executor')]
        assert len(sync_lines) >= 1, "sync_executor must be defined at module level"
        assert len(post_lines) >= 1, "postprocess_executor must be defined at module level"
        assert sync_lines[0] != post_lines[0], "sync and postprocess executors must be separate"


# ---------------------------------------------------------------------------
# 15. BYOK context propagation tests
# ---------------------------------------------------------------------------


class TestBYOKContextPropagation:
    """Verify BYOK context lifecycle in the async coordinator sync pipeline (#7361).

    With asyncio.create_task, ContextVars (including BYOK keys) are inherited
    automatically by the child task. The coordinator clears BYOK in finally.
    """

    @staticmethod
    def _read_sync_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_no_plain_submit_in_sync(self):
        """All executor .submit() calls in sync.py must use submit_with_context."""
        source = self._read_sync_source()
        import re as _re

        plain_submits = _re.findall(
            r'(?:critical_executor|sync_executor|storage_executor|postprocess_executor)\.submit\(', source
        )
        assert (
            len(plain_submits) == 0
        ), f"Found {len(plain_submits)} plain .submit() calls — must use submit_with_context"

    def test_no_plain_submit_in_process_conversation(self):
        """All executor .submit() calls in process_conversation.py must use submit_with_context."""
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'conversations', 'process_conversation.py')
        with open(path, encoding='utf-8') as f:
            source = f.read()
        import re as _re

        plain_submits = _re.findall(
            r'(?:critical_executor|sync_executor|storage_executor|postprocess_executor)\.submit\(', source
        )
        assert (
            len(plain_submits) == 0
        ), f"Found {len(plain_submits)} plain .submit() calls — must use submit_with_context"


# ---------------------------------------------------------------------------
# 16. Timeout configuration tests
# ---------------------------------------------------------------------------


class TestTimeoutConfiguration:
    """Verify timeout settings on LLM and STT clients."""

    @staticmethod
    def _read_clients_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'llm', 'clients.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def _read_pre_recorded_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'stt', 'pre_recorded.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def _read_classifier_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'llm', 'fair_use_classifier.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def _read_llm_providers_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'llm', 'providers.py')
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_llm_mini_has_timeout(self):
        source = self._read_clients_source()
        start = source.index('def _create_legacy_llm_mini')
        end = source.find('\n\ndef ', start + 1)
        factory_body = source[start:end]
        assert 'request_timeout=120' in factory_body
        assert 'max_retries=1' in factory_body

    def test_anthropic_default_has_timeout(self):
        source = self._read_clients_source()
        default_line = [l for l in source.split('\n') if '= anthropic.AsyncAnthropic' in l][0]
        assert 'timeout=120' in default_line
        assert 'max_retries=1' in default_line

    def test_anthropic_byok_has_timeout(self):
        source = self._read_clients_source()
        start = source.index('def _cached_anthropic')
        end = source.find('\ndef ', start + 1)
        func_body = source[start:end]
        assert 'timeout=120' in func_body
        assert 'max_retries=1' in func_body

    def test_byok_client_has_timeout(self):
        source = self._read_clients_source()
        start = source.index('def _create_byok_client')
        end = source.find('\ndef ', start + 1)
        func_body = source[start:end]
        assert "'request_timeout': 120" in func_body
        assert "'max_retries': 1" in func_body

    def test_classifier_llm_has_timeout(self):
        classifier_source = self._read_classifier_source()
        providers_source = self._read_llm_providers_source()

        assert "get_llm('fair_use')" in classifier_source
        assert "'request_timeout': options.get('request_timeout', 120)" in providers_source
        assert "'max_retries': options.get('max_retries', 1)" in providers_source

    def test_dg_timeout_read_within_budget(self):
        """DG read timeout must be <= 150s so 2 attempts fit within 300s segment budget."""
        source = self._read_pre_recorded_source()
        assert 'read=120.0' in source, "DG read timeout must be 120s"

    def test_dg_timeout_connect_reasonable(self):
        source = self._read_pre_recorded_source()
        assert 'connect=10.0' in source

    def test_dg_max_two_attempts(self):
        """Deepgram prerecorded must retry at most once (2 total attempts)."""
        source = self._read_pre_recorded_source()
        start = source.index('def deepgram_prerecorded(')
        end = source.find('\ndef ', start + 1)
        func_body = source[start:end]
        assert 'attempts < 1' in func_body, "DG url transcription must use attempts < 1 (max 2 attempts)"

    def test_dg_from_bytes_max_two_attempts(self):
        """Deepgram prerecorded_from_bytes must retry at most once (2 total attempts)."""
        source = self._read_pre_recorded_source()
        start = source.index('def deepgram_prerecorded_from_bytes(')
        end = source.find('\ndef ', start + 1)
        if end == -1:
            end = len(source)
        func_body = source[start:end]
        assert 'attempts < 1' in func_body, "DG bytes transcription must use attempts < 1 (max 2 attempts)"
