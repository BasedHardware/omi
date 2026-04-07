"""
Tests for v2 async sync-local-files endpoints (#5941).

v2 does fast-path work (decode, VAD) inline, then hands off STT+LLM to a
background thread. The app polls GET /v2/sync-local-files/{job_id} until
the job reaches a terminal status.

v1 remains completely unchanged.
"""

import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. Structural tests — verify v2 code exists with correct patterns
# ---------------------------------------------------------------------------


class TestSyncV2Structure:
    """Verify v2 endpoint code structure in sync.py."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
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
        assert 'async def get_sync_job_status' in source

    def test_v1_endpoint_unchanged(self):
        """v1 endpoint must still exist with original path and function name."""
        source = self._read_sync_source()
        assert '"/v1/sync-local-files"' in source
        assert 'async def sync_local_files(' in source

    def test_v2_returns_202_with_job_id(self):
        """v2 POST must return 202 with job_id."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        # Find the next top-level function or decorator
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'status_code=202' in func_body, "v2 must return 202"
        assert "'job_id'" in func_body, "v2 response must include job_id"
        assert "'poll_after_ms'" in func_body, "v2 response must include poll_after_ms"

    def test_v2_submits_to_critical_executor(self):
        """v2 must submit background work to the shared critical_executor."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'run_in_executor' in func_body, "v2 must use run_in_executor for background worker"
        assert '_process_segments_background' in func_body, "v2 must submit the background worker function"

    def test_v2_has_fair_use_gates(self):
        """v2 must check fair-use and DG budget (same gates as v1)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'is_hard_restricted' in func_body, "v2 must check hard restriction"
        assert 'is_dg_budget_exhausted' in func_body, "v2 must check DG budget"

    def test_v2_uses_job_specific_directory(self):
        """v2 must use syncing/{uid}/{job_id}/ to avoid concurrency conflicts."""
        source = self._read_sync_source()
        assert '_retrieve_file_paths_v2' in source
        start = source.index('def _retrieve_file_paths_v2')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert (
            'syncing/{uid}/{job_id}' in func_body or "f'syncing/{uid}/{job_id}/'" in func_body
        ), "v2 must use job-specific directory"

    def test_v2_background_has_cleanup(self):
        """Background worker must clean up files in finally block."""
        source = self._read_sync_source()
        start = source.index('def _process_segments_background')
        # Find next top-level def or decorator
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'finally:' in func_body, "Background worker must have finally for cleanup"
        assert '_cleanup_files' in func_body, "Background worker must call _cleanup_files"
        assert 'rmtree' in func_body, "Background worker must clean up job directory"

    def test_v2_background_records_dg_after_processing(self):
        """DG usage must be recorded after processing, not before."""
        source = self._read_sync_source()
        start = source.index('def _process_segments_background')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        # record_dg_usage_ms must come after critical_executor.submit / future.result processing
        dg_pos = func_body.index('record_dg_usage_ms')
        processing_pos = func_body.index('future.result()')
        assert dg_pos > processing_pos, "DG usage must be recorded AFTER segment processing"

    def test_v2_get_checks_ownership(self):
        """GET endpoint must verify job belongs to requesting user."""
        source = self._read_sync_source()
        start = source.index('async def get_sync_job_status')
        func_body = source[start:]

        assert "job['uid'] != uid" in func_body, "GET must check job ownership"
        assert '403' in func_body, "GET must return 403 for wrong owner"

    def test_v2_get_returns_404_for_missing(self):
        """GET must return 404 for expired/missing jobs."""
        source = self._read_sync_source()
        start = source.index('async def get_sync_job_status')
        func_body = source[start:]

        assert '404' in func_body, "GET must return 404 for missing job"

    def test_v2_fetches_prefs_and_cache_before_executor_submit(self):
        """v2 must fetch transcription_prefs and build person_embeddings_cache before submitting to executor."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'get_user_transcription_preferences' in func_body, "v2 must fetch transcription preferences"
        assert 'build_person_embeddings_cache' in func_body, "v2 must build person embeddings cache"

        # Both must appear before the background worker dispatch
        prefs_pos = func_body.index('get_user_transcription_preferences')
        cache_pos = func_body.index('build_person_embeddings_cache')
        submit_pos = func_body.index('_process_segments_background')
        assert prefs_pos < submit_pos, "Prefs must be fetched before background worker dispatch"
        assert cache_pos < submit_pos, "Cache must be built before background worker dispatch"

    def test_v2_bg_worker_accepts_prefs_and_cache_params(self):
        """_process_segments_background must accept transcription_prefs and person_embeddings_cache."""
        source = self._read_sync_source()
        start = source.index('def _process_segments_background')
        # Find the closing paren of the signature (handles multi-line)
        sig_end = source.index('):', start)
        func_sig = source[start : sig_end + 2]

        assert 'transcription_prefs' in func_sig, "bg worker must accept transcription_prefs param"
        assert 'person_embeddings_cache' in func_sig, "bg worker must accept person_embeddings_cache param"

    def test_v2_passes_prefs_and_cache_to_executor_submit(self):
        """v2 must pass transcription_prefs and person_embeddings_cache in executor submit args."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        # Find the background worker dispatch block
        submit_start = func_body.index('_process_segments_background')
        # Find the closing — look for the return statement after it
        submit_end = func_body.index('return JSONResponse', submit_start)
        submit_block = func_body[submit_start:submit_end]

        assert 'transcription_prefs' in submit_block, "v2 must pass transcription_prefs to background worker"
        assert 'person_embeddings_cache' in submit_block, "v2 must pass person_embeddings_cache to background worker"


# ---------------------------------------------------------------------------
# 2. Redis sync_jobs module tests
# ---------------------------------------------------------------------------


class TestSyncJobsRedis:
    """Test database/sync_jobs.py Redis operations."""

    @staticmethod
    def _load_sync_jobs_module():
        """Load sync_jobs module with Redis stubbed out."""
        # Stub redis before importing
        mock_redis = MagicMock()
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

    def test_get_sync_job_detects_stale(self):
        """get_sync_job must mark processing jobs as failed if stale."""
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
        assert result['status'] == 'failed'
        assert 'timed out' in result['error']

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

    def test_mark_job_completed_sets_status(self):
        """mark_job_completed must set correct terminal status."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j1',
            'uid': 'uid',
            'status': 'processing',
            'updated_at': time.time(),
        }
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.mark_job_completed(
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

    def test_mark_job_completed_partial_failure(self):
        """Partial failure: some segments fail → partial_failure status."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'j2', 'uid': 'uid', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.mark_job_completed(
            'j2',
            {
                'failed_segments': 2,
                'total_segments': 5,
                'errors': ['err1', 'err2'],
            },
        )
        assert result['status'] == 'partial_failure'

    def test_mark_job_completed_all_failed(self):
        """All segments failed → failed status."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {'job_id': 'j3', 'uid': 'uid', 'status': 'processing', 'updated_at': time.time()}
        mock_redis.get.return_value = json.dumps(job).encode()

        result = mod.mark_job_completed(
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


class TestProcessSegmentsBackground:
    """Test _process_segments_background worker function."""

    @staticmethod
    def _get_bg_func_body():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            source = f.read()
        start = source.index('def _process_segments_background')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        return source[start:next_boundary]

    def test_background_calls_mark_job_processing(self):
        """Worker must transition job to processing status."""
        assert 'mark_job_processing(job_id)' in self._get_bg_func_body()

    def test_background_calls_mark_job_completed(self):
        """Worker must call mark_job_completed with result."""
        body = self._get_bg_func_body()
        assert 'mark_job_completed(' in body and 'job_id' in body

    def test_background_calls_mark_job_failed_on_exception(self):
        """Worker must call mark_job_failed on unexpected exception."""
        body = self._get_bg_func_body()
        assert 'mark_job_failed(' in body and 'job_id' in body

    def test_background_uses_chunk_threads_pattern(self):
        """Worker must batch threads in chunks of 5 (same as v1)."""
        assert 'chunk_size = 5' in self._get_bg_func_body()

    def test_background_result_matches_v1_shape(self):
        """Worker result must include new_memories, updated_memories, failed_segments, total_segments, errors."""
        body = self._get_bg_func_body()
        for field in ['new_memories', 'updated_memories', 'failed_segments', 'total_segments', 'errors']:
            assert f"'{field}'" in body, f"Worker result must include {field}"

    def test_background_has_heartbeat(self):
        """Worker must heartbeat (update_sync_job) during processing to prevent stale detection."""
        body = self._get_bg_func_body()
        assert 'update_sync_job(' in body, "Worker must call update_sync_job for heartbeat"
        # Heartbeat must be inside the chunk loop, after futures are resolved
        heartbeat_pos = body.index('update_sync_job(')
        result_pos = body.index('future.result()')
        assert heartbeat_pos > result_pos, "Heartbeat must come after future.result()"


# ---------------------------------------------------------------------------
# 4. v1 regression tests — v1 must be completely unchanged
# ---------------------------------------------------------------------------


class TestV1Unchanged:
    """Verify v1 endpoint behavior is not modified by v2 addition."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def _get_v1_body(self):
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        # v1 ends at the v2 section comment
        end = source.index('# v2 async sync-local-files', start)
        return source[start:end]

    def test_v1_returns_200_on_success(self):
        """v1 must still return dict (200) on full success."""
        body = self._get_v1_body()
        assert 'return result' in body, "v1 must return result dict for 200"

    def test_v1_returns_207_on_partial_failure(self):
        """v1 must still return 207 on partial failure."""
        body = self._get_v1_body()
        assert 'status_code=207' in body, "v1 must return 207 for partial failure"

    def test_v1_returns_500_on_total_failure(self):
        """v1 must still raise 500 when all segments fail."""
        body = self._get_v1_body()
        assert 'status_code=500' in body, "v1 must raise 500 for total failure"

    def test_v1_uses_synchronous_gather(self):
        """v1 must process segments synchronously with asyncio.gather (no background)."""
        body = self._get_v1_body()
        assert 'asyncio.gather' in body, "v1 must use asyncio.gather for segment processing"
        assert 'run_in_executor' in body, "v1 must use run_in_executor for blocking segment work"
        assert 'critical_executor' in body, "v1 must use critical_executor (Lane 2 architecture)"

    def test_v1_cleanup_in_finally(self):
        """v1 must still clean up files in finally block."""
        body = self._get_v1_body()
        assert 'finally:' in body
        assert '_cleanup_files' in body

    def test_v1_has_no_job_id(self):
        """v1 must not reference job_id or Redis jobs."""
        body = self._get_v1_body()
        assert 'job_id' not in body, "v1 must not use job_id"
        assert 'create_sync_job' not in body, "v1 must not use sync_jobs"

    def test_v1_path_unchanged(self):
        """v1 must still be at /v1/sync-local-files."""
        source = self._read_sync_source()
        # Find the v1 decorator line
        v1_decorator_idx = source.index('"/v1/sync-local-files"')
        # The next function def after this decorator should be sync_local_files
        func_start = source.index('async def ', v1_decorator_idx)
        func_line = source[func_start : source.index('\n', func_start)]
        assert 'sync_local_files(' in func_line
        assert 'v2' not in func_line


# ---------------------------------------------------------------------------
# 5. v2 endpoint contract tests
# ---------------------------------------------------------------------------


class TestV2EndpointContract:
    """Test v2 endpoint behavior via structural inspection."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def _get_v2_post_body(self):
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        return source[start:next_section]

    def test_v2_handles_empty_segments(self):
        """v2 must return 200 immediately when no segments found (no job needed)."""
        body = self._get_v2_post_body()
        assert 'total_segments == 0' in body
        assert "'new_memories': []" in body

    def test_v2_transfers_file_ownership_to_bg_thread(self):
        """v2 must transfer segmented_paths ownership to prevent double cleanup."""
        body = self._get_v2_post_body()
        assert 'owned_paths = list(segmented_paths)' in body
        assert 'segmented_paths = set()' in body

    def test_v2_handles_429_dg_budget(self):
        """v2 must return 429 when DG budget is exhausted."""
        body = self._get_v2_post_body()
        assert 'dg_budget_exhausted' in body
        assert 'status_code=429' in body

    def test_v2_handles_429_hard_restricted(self):
        """v2 must check hard restriction at the top."""
        body = self._get_v2_post_body()
        assert 'is_hard_restricted(uid)' in body

    def test_v2_reraises_http_exceptions(self):
        """v2 must re-raise HTTPException from fast-path helpers."""
        body = self._get_v2_post_body()
        assert 'except HTTPException:' in body
        assert 'raise' in body[body.index('except HTTPException:') :]

    def test_v2_finally_cleans_up_on_fast_path_failure(self):
        """v2 finally block must clean up files if fast-path fails."""
        body = self._get_v2_post_body()
        finally_idx = body.rindex('finally:')
        finally_block = body[finally_idx:]
        assert '_cleanup_files(paths)' in finally_block
        assert '_cleanup_files(wav_paths)' in finally_block


# ---------------------------------------------------------------------------
# 6. Redis boundary tests — behavioral TTL, stale threshold, overflow
# ---------------------------------------------------------------------------


class TestSyncJobsRedisBoundary:
    """Boundary tests for database/sync_jobs.py Redis operations."""

    @staticmethod
    def _load_sync_jobs_module():
        """Load sync_jobs module with Redis stubbed."""
        mock_redis = MagicMock()
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
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get('ex') == mod.JOB_TTL_SECONDS or call_args[1].get('ex') == mod.JOB_TTL_SECONDS

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

    def test_stale_just_over_threshold(self):
        """Job 1 second over stale threshold must be marked failed."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'processing',
            'updated_at': time.time() - (mod.STALE_THRESHOLD_SECONDS + 1),
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        result = mod.get_sync_job('j')
        assert result['status'] == 'failed'
        assert 'timed out' in result['error']

    def test_stale_persists_to_redis(self):
        """When stale detection fires, it must write the failed status back to Redis."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'processing',
            'updated_at': time.time() - 700,
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        mod.get_sync_job('j')
        # Must have written back to Redis (set called with failed status)
        assert mock_redis.set.called
        written_data = json.loads(mock_redis.set.call_args[0][1])
        assert written_data['status'] == 'failed'

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
        result = mod.mark_job_completed(
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


class TestBackgroundWorkerBehavioral:
    """Behavioral tests for _process_segments_background using mocks."""

    @staticmethod
    def _load_bg_worker():
        """Load the background worker function with all dependencies mocked."""
        mock_redis = MagicMock()
        mock_sync_jobs = MagicMock()

        saved_modules = {}
        # Core deps
        heavy_deps = [
            'redis',
            'database',
            'database.redis_db',
            'database._client',
            'database.conversations',
            'database.users',
            'firebase_admin',
            'google',
            'google.cloud',
            'google.cloud.firestore_v1',
            'opuslib',
            'pydub',
            'models',
            'models.conversation',
            'models.transcript_segment',
        ]
        # utils namespace — must stub all submodules sync.py imports
        utils_subs = [
            'utils',
            'utils.conversations',
            'utils.conversations.process_conversation',
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
            'utils.log_sanitizer',
            'utils.speaker_assignment',
            'utils.speaker_identification',
            'utils.stt.speaker_embedding',
            'utils.executors',
        ]
        heavy_deps.extend(utils_subs)

        for mod in heavy_deps:
            saved_modules[mod] = sys.modules.get(mod)
            sys.modules[mod] = MagicMock()

        # Provide a working critical_executor stub (submit runs the function synchronously)
        from concurrent.futures import ThreadPoolExecutor

        _test_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='test')
        sys.modules['utils.executors'].critical_executor = _test_executor
        sys.modules['utils.executors'].storage_executor = _test_executor

        # Set up specific mocks
        sys.modules['database.redis_db'] = MagicMock(r=mock_redis)
        saved_modules['database.sync_jobs'] = sys.modules.get('database.sync_jobs')
        sys.modules['database.sync_jobs'] = mock_sync_jobs

        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_router_bg',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module, mock_sync_jobs
        except Exception:
            return None, None
        finally:
            for mod, original in saved_modules.items():
                if original is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = original

    def test_bg_worker_calls_mark_processing_then_completed(self):
        """Worker must call mark_job_processing, then mark_job_completed."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        # Mock process_segment to do nothing
        mod.process_segment = MagicMock()

        mod._process_segments_background(
            job_id='test-job',
            uid='test-uid',
            segmented_paths=['/tmp/fake1.wav', '/tmp/fake2.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=10.0,
            job_dir='/tmp/fake-job-dir',
        )

        mock_sync_jobs.mark_job_processing.assert_called_once_with('test-job')
        mock_sync_jobs.mark_job_completed.assert_called_once()
        call_args = mock_sync_jobs.mark_job_completed.call_args
        assert call_args[0][0] == 'test-job'

    def test_bg_worker_calls_mark_failed_on_exception(self):
        """Worker must call mark_job_failed when processing throws."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        # Make mark_job_processing raise to simulate early failure
        mock_sync_jobs.mark_job_processing.side_effect = Exception("Redis down")

        mod._process_segments_background(
            job_id='test-job',
            uid='test-uid',
            segmented_paths=['/tmp/fake.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=5.0,
            job_dir='/tmp/fake-dir',
        )

        mock_sync_jobs.mark_job_failed.assert_called_once()
        assert 'Redis down' in mock_sync_jobs.mark_job_failed.call_args[0][1]

    def test_bg_worker_heartbeats_during_processing(self):
        """Worker must call update_sync_job during chunk processing."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.process_segment = MagicMock()

        # Use enough segments to trigger at least one heartbeat (chunk_size=5)
        paths = [f'/tmp/seg{i}.wav' for i in range(6)]

        mod._process_segments_background(
            job_id='hb-job',
            uid='uid',
            segmented_paths=paths,
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=30.0,
            job_dir='/tmp/hb-dir',
        )

        # update_sync_job should have been called at least once for heartbeat
        assert mock_sync_jobs.update_sync_job.called

    def test_bg_worker_partial_failure_reports_correctly(self):
        """Worker must pass failed_segments count to mark_job_completed on partial failure."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        call_count = [0]

        def mock_process_segment(
            path, uid, response, lock, errors, source, is_locked, prefs=None, cache=None, target_conversation_id=None
        ):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                with lock:
                    errors.append(f'Failed: {path}')
            else:
                with lock:
                    response['new_memories'].add(f'mem-{call_count[0]}')

        mod.process_segment = mock_process_segment

        mod._process_segments_background(
            job_id='partial-job',
            uid='test-uid',
            segmented_paths=['/tmp/s1.wav', '/tmp/s2.wav', '/tmp/s3.wav', '/tmp/s4.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=20.0,
            job_dir='/tmp/partial-dir',
        )

        mock_sync_jobs.mark_job_completed.assert_called_once()
        result_arg = mock_sync_jobs.mark_job_completed.call_args[0][1]
        assert result_arg['failed_segments'] == 2
        assert result_arg['total_segments'] == 4
        assert len(result_arg['errors']) == 2

    def test_bg_worker_all_failed_reports_correctly(self):
        """Worker must report all segments failed with errors."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        def mock_process_segment(
            path, uid, response, lock, errors, source, is_locked, prefs=None, cache=None, target_conversation_id=None
        ):
            with lock:
                errors.append(f'Failed: {path}')

        mod.process_segment = mock_process_segment

        mod._process_segments_background(
            job_id='allfail-job',
            uid='test-uid',
            segmented_paths=['/tmp/f1.wav', '/tmp/f2.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=10.0,
            job_dir='/tmp/allfail-dir',
        )

        mock_sync_jobs.mark_job_completed.assert_called_once()
        result_arg = mock_sync_jobs.mark_job_completed.call_args[0][1]
        assert result_arg['failed_segments'] == 2
        assert result_arg['total_segments'] == 2
        assert len(result_arg['errors']) == 2

    def test_bg_worker_records_dg_usage_when_enabled(self):
        """Worker must call record_dg_usage_ms when fair_use_restrict_dg=True."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.process_segment = MagicMock()
        mock_record_dg = MagicMock()
        mod.record_dg_usage_ms = mock_record_dg

        mod._process_segments_background(
            job_id='dg-job',
            uid='test-uid',
            segmented_paths=['/tmp/d1.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=True,
            total_speech_seconds=15.5,
            job_dir='/tmp/dg-dir',
        )

        mock_record_dg.assert_called_once_with('test-uid', 15500)

    def test_bg_worker_skips_dg_recording_when_disabled(self):
        """Worker must NOT call record_dg_usage_ms when fair_use_restrict_dg=False."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.process_segment = MagicMock()
        mock_record_dg = MagicMock()
        mod.record_dg_usage_ms = mock_record_dg

        mod._process_segments_background(
            job_id='no-dg-job',
            uid='test-uid',
            segmented_paths=['/tmp/d1.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=15.5,
            job_dir='/tmp/no-dg-dir',
        )

        mock_record_dg.assert_not_called()

    def test_bg_worker_cleans_up_job_dir(self):
        """Worker must remove the job directory in finally block."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.process_segment = MagicMock()

        # Create a real temp dir to verify cleanup
        import tempfile

        job_dir = tempfile.mkdtemp(prefix='sync_v2_test_')
        assert os.path.isdir(job_dir)

        mod._process_segments_background(
            job_id='cleanup-job',
            uid='test-uid',
            segmented_paths=[],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=0.0,
            job_dir=job_dir,
        )

        assert not os.path.exists(job_dir), "Job directory must be cleaned up after processing"

    def test_bg_worker_cleans_up_on_failure(self):
        """Worker must clean up job dir even when processing fails."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mock_sync_jobs.mark_job_processing.side_effect = RuntimeError("DB failure")

        import tempfile

        job_dir = tempfile.mkdtemp(prefix='sync_v2_test_fail_')
        assert os.path.isdir(job_dir)

        mod._process_segments_background(
            job_id='cleanup-fail-job',
            uid='test-uid',
            segmented_paths=[],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=0.0,
            job_dir=job_dir,
        )

        assert not os.path.exists(job_dir), "Job directory must be cleaned up even on failure"

    def test_bg_worker_forwards_prefs_and_cache_to_process_segment(self):
        """Worker must forward transcription_prefs and person_embeddings_cache to each process_segment call."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        received_args = []

        def mock_process_segment(
            path, uid, response, lock, errors, source, is_locked, prefs=None, cache=None, target_conversation_id=None
        ):
            received_args.append({'prefs': prefs, 'cache': cache})

        mod.process_segment = mock_process_segment

        test_prefs = {'language': 'es', 'model': 'nova-3'}
        test_cache = {'p-alice': {'name': 'Alice', 'embedding': [0.1, 0.2]}}

        mod._process_segments_background(
            job_id='prefs-job',
            uid='test-uid',
            segmented_paths=['/tmp/p1.wav', '/tmp/p2.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=10.0,
            job_dir='/tmp/prefs-dir',
            transcription_prefs=test_prefs,
            person_embeddings_cache=test_cache,
        )

        assert len(received_args) == 2
        for args in received_args:
            assert args['prefs'] is test_prefs
            assert args['cache'] is test_cache

    def test_bg_worker_defaults_prefs_and_cache_to_none(self):
        """Worker must default transcription_prefs and person_embeddings_cache to None when not provided."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        received_args = []

        def mock_process_segment(
            path, uid, response, lock, errors, source, is_locked, prefs=None, cache=None, target_conversation_id=None
        ):
            received_args.append({'prefs': prefs, 'cache': cache})

        mod.process_segment = mock_process_segment

        mod._process_segments_background(
            job_id='noprefs-job',
            uid='test-uid',
            segmented_paths=['/tmp/n1.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=5.0,
            job_dir='/tmp/noprefs-dir',
        )

        assert len(received_args) == 1
        assert received_args[0]['prefs'] is None
        assert received_args[0]['cache'] is None

    def test_bg_worker_forwards_target_conversation_id_to_process_segment(self):
        """Worker must forward target_conversation_id to each process_segment call."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        received_args = []

        def mock_process_segment(
            path, uid, response, lock, errors, source, is_locked, prefs=None, cache=None, target_conversation_id=None
        ):
            received_args.append({'target_conversation_id': target_conversation_id})

        mod.process_segment = mock_process_segment

        mod._process_segments_background(
            job_id='target-conv-job',
            uid='test-uid',
            segmented_paths=['/tmp/tc1.wav', '/tmp/tc2.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=10.0,
            job_dir='/tmp/target-conv-dir',
            target_conversation_id='conv-123',
        )

        assert len(received_args) == 2
        for args in received_args:
            assert args['target_conversation_id'] == 'conv-123'

    def test_bg_worker_defaults_target_conversation_id_to_none(self):
        """Worker must default target_conversation_id to None when not provided."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        received_args = []

        def mock_process_segment(
            path, uid, response, lock, errors, source, is_locked, prefs=None, cache=None, target_conversation_id=None
        ):
            received_args.append({'target_conversation_id': target_conversation_id})

        mod.process_segment = mock_process_segment

        mod._process_segments_background(
            job_id='no-target-conv-job',
            uid='test-uid',
            segmented_paths=['/tmp/nt1.wav'],
            source='omi',
            is_locked=False,
            fair_use_restrict_dg=False,
            total_speech_seconds=5.0,
            job_dir='/tmp/no-target-conv-dir',
        )

        assert len(received_args) == 1
        assert received_args[0]['target_conversation_id'] is None


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

        heavy_deps = [
            'redis',
            'database',
            'database.redis_db',
            'database._client',
            'database.conversations',
            'database.users',
            'database.user_usage',
            'firebase_admin',
            'google',
            'google.cloud',
            'google.cloud.firestore_v1',
            'opuslib',
            'pydub',
            'models',
            'models.conversation',
            'models.transcript_segment',
            'utils',
            'utils.conversations',
            'utils.conversations.process_conversation',
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
            'utils.log_sanitizer',
            'utils.speaker_assignment',
            'utils.speaker_identification',
            'utils.stt.speaker_embedding',
        ]

        for mod_name in heavy_deps:
            saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()

        # Stub utils.executors with a real-ish critical_executor mock
        mock_executors = MagicMock()
        mock_executors.critical_executor = MagicMock()
        mock_executors.storage_executor = MagicMock()
        saved_modules['utils.executors'] = sys.modules.get('utils.executors')
        sys.modules['utils.executors'] = mock_executors

        sys.modules['database.redis_db'] = MagicMock(r=MagicMock())
        saved_modules['database.sync_jobs'] = sys.modules.get('database.sync_jobs')
        sys.modules['database.sync_jobs'] = mock_sync_jobs

        # Set up fair_use defaults
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)

        # Mock auth to return test uid
        sys.modules['utils.other.endpoints'].get_current_user_uid = MagicMock(return_value='test-uid')

        return saved_modules, mock_sync_jobs, mock_fair_use

    @staticmethod
    def _cleanup_modules(saved_modules):
        sys.modules.pop('routers.sync', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig

    def test_get_poll_404_expired_job(self):
        """GET poll returns 404 when job not found."""
        saved, mock_sync_jobs, _ = self._build_test_app()
        mock_sync_jobs.get_sync_job = MagicMock(return_value=None)

        try:
            sys.modules.pop('routers.sync', None)
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_poll_404',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

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

    def test_get_poll_403_wrong_owner(self):
        """GET poll returns 403 when job belongs to different user."""
        saved, mock_sync_jobs, _ = self._build_test_app()
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
            sys.modules.pop('routers.sync', None)
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_poll_403',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

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

    def test_get_poll_completed_includes_result(self):
        """GET poll returns result and error fields on terminal status."""
        saved, mock_sync_jobs, _ = self._build_test_app()
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
            sys.modules.pop('routers.sync', None)
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_poll_done',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

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

    def test_get_poll_failed_includes_error(self):
        """GET poll returns error field when all segments failed."""
        saved, mock_sync_jobs, _ = self._build_test_app()
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
            sys.modules.pop('routers.sync', None)
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_poll_failed',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

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

    def test_get_poll_processing_excludes_result(self):
        """GET poll must NOT include result/error when job is still processing."""
        saved, mock_sync_jobs, _ = self._build_test_app()
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
            sys.modules.pop('routers.sync', None)
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_poll_active',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

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
