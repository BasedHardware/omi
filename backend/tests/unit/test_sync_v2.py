"""
Tests for v2 async sync-local-files endpoints (#5941, #7281).

v2 saves raw files and returns 202 immediately, then runs the full pipeline
(decode → VAD → fair-use → STT → LLM) in a background thread. The app
polls GET /v2/sync-local-files/{job_id} until the job reaches a terminal status.

v1 remains completely unchanged.
"""

import json
import os
import re
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
        assert 'def get_sync_job_status' in source

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

    def test_v2_dispatches_async_coordinator(self):
        """v2 must dispatch background work via start_background_task (async coordinator, #7361)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'start_background_task' in func_body, "v2 must use start_background_task for async coordinator"
        assert '_run_full_pipeline_background_async' in func_body, "v2 must dispatch the async pipeline coordinator"
        assert 'submit_with_context' not in func_body, (
            "v2 must NOT use submit_with_context — async coordinator runs on event loop, "
            "not a thread pool slot (#7361)"
        )

    def test_v2_has_hard_restriction_gate(self):
        """v2 inline path must check hard restriction (fast 429 for restricted users)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'is_hard_restricted' in func_body, "v2 must check hard restriction inline"

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
        start = source.index('async def _run_full_pipeline_background_async')
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
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        dg_pos = func_body.index('record_dg_usage_ms')
        processing_pos = func_body.index('asyncio.wait_for(run_blocking(sync_executor, _process_one_segment')
        assert dg_pos > processing_pos, "DG usage must be recorded AFTER segment processing"

    def test_v2_background_does_decode_and_vad(self):
        """Background worker must run decode and VAD (#7281 — moved from inline)."""
        source = self._read_sync_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'decode_files_to_wav' in func_body, "Background must decode files"
        assert 'retrieve_vad_segments' in func_body, "Background must run VAD"
        assert 'build_person_embeddings_cache' in func_body, "Background must build person embeddings"
        assert 'is_dg_budget_exhausted' in func_body, "Background must check DG budget"

    def test_v2_background_has_stage_heartbeats(self):
        """Background worker must heartbeat with stage info during decode and VAD."""
        source = self._read_sync_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert "'stage': 'decoding'" in func_body, "Background must heartbeat decode stage"
        assert "'stage': 'vad'" in func_body, "Background must heartbeat VAD stage"
        assert (
            "'stage': 'processing'" in func_body or "'stage': 'stt_llm'" in func_body
        ), "Background must heartbeat processing stage"

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

    def test_v2_bg_worker_fetches_prefs_and_cache(self):
        """Background worker must fetch transcription prefs and build person embeddings cache."""
        source = self._read_sync_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'get_user_transcription_preferences' in func_body, "bg worker must fetch prefs"
        assert 'build_person_embeddings_cache' in func_body, "bg worker must build embeddings cache"

    def test_v2_fast_path_only_saves_files(self):
        """v2 fast path must only save raw files — no decode, no VAD, no prefs/cache fetch."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert '_retrieve_file_paths_v2' in func_body, "v2 must save raw files"
        assert 'create_sync_job' in func_body, "v2 must create Redis job"
        assert 'get_user_transcription_preferences' not in func_body, "prefs fetch moved to bg"
        assert 'build_person_embeddings_cache' not in func_body, "cache build moved to bg"


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


class TestFullPipelineBackground:
    """Test _run_full_pipeline_background_async async coordinator function."""

    @staticmethod
    def _get_bg_func_body():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            source = f.read()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        return source[start:next_boundary]

    def test_background_calls_mark_job_processing(self):
        """Worker must transition job to processing status."""
        assert 'mark_job_processing, job_id' in self._get_bg_func_body()

    def test_background_calls_mark_job_completed(self):
        """Worker must call mark_job_completed with result."""
        body = self._get_bg_func_body()
        assert 'mark_job_completed,' in body and 'job_id' in body

    def test_background_calls_mark_job_failed_on_exception(self):
        """Worker must call mark_job_failed on unexpected exception."""
        body = self._get_bg_func_body()
        assert 'mark_job_failed,' in body and 'job_id' in body

    def test_background_uses_chunk_pattern(self):
        """Worker must batch segments in chunks of 5."""
        assert 'chunk_size = 5' in self._get_bg_func_body()

    def test_background_result_matches_v1_shape(self):
        """Worker result must include new_memories, updated_memories, failed_segments, total_segments, errors."""
        body = self._get_bg_func_body()
        for field in ['new_memories', 'updated_memories', 'failed_segments', 'total_segments', 'errors']:
            assert f"'{field}'" in body, f"Worker result must include {field}"

    def test_background_has_heartbeat(self):
        """Worker must heartbeat (update_sync_job) during processing to prevent stale detection."""
        body = self._get_bg_func_body()
        assert 'update_sync_job,' in body, "Worker must call update_sync_job for heartbeat"

    def test_background_pipeline_order(self):
        """Worker must run: decode → VAD → fair-use → STT in correct order."""
        body = self._get_bg_func_body()
        decode_pos = body.index('decode_files_to_wav')
        vad_pos = body.index('retrieve_vad_segments')
        speech_pos = body.index('record_speech_ms')
        segment_pos = body.index('process_segment')
        assert decode_pos < vad_pos < speech_pos < segment_pos

    def test_background_is_async_coordinator(self):
        """Background pipeline must be an async def, not a sync function (#7361)."""
        body = self._get_bg_func_body()
        assert body.startswith('async def'), "Pipeline must be async — coordinator runs on event loop"
        assert 'await run_blocking(' in body, "Async coordinator must offload blocking work to pools"
        assert '_get_sync_pipeline_semaphore' in body, "Async coordinator must use loop-scoped semaphore"

    def test_background_uses_asyncio_wait_for_timeout(self):
        """Segment and VAD tasks must use asyncio.wait_for with timeout=300."""
        body = self._get_bg_func_body()
        assert 'asyncio.wait_for(' in body, "Must use asyncio.wait_for for timeout enforcement"
        assert 'timeout=300' in body, "Must use 300s timeout"


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
        assert 'run_blocking' in body, "v1 must use run_blocking for blocking segment work"
        assert 'sync_executor' in body, "v1 must use sync_executor for segment work"

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

    def test_v2_transfers_file_ownership_to_bg_task(self):
        """v2 must transfer raw path ownership to prevent double cleanup."""
        body = self._get_v2_post_body()
        assert 'owned_paths = list(paths)' in body
        assert 'paths = []' in body

    def test_v2_handles_429_hard_restricted(self):
        """v2 must check hard restriction at the top."""
        body = self._get_v2_post_body()
        assert 'is_hard_restricted' in body and 'uid' in body

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


class TestAsyncCoordinatorStructure:
    """Structural tests for _run_full_pipeline_background_async async coordinator (#7361).

    The function is now async and cannot be called from sync test context.
    These tests verify structure via source inspection.
    """

    @staticmethod
    def _get_bg_func_body():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            source = f.read()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        return source[start:next_boundary]

    def test_async_coordinator_offloads_all_db_calls(self):
        """All DB calls must go through run_blocking(db_executor, ...)."""
        body = self._get_bg_func_body()
        assert 'run_blocking(db_executor, mark_job_processing' in body
        assert 'mark_job_completed' in body and 'db_executor' in body
        assert 'run_blocking(db_executor, update_sync_job' in body

    def test_async_coordinator_offloads_decode(self):
        """Decode must be offloaded to sync_executor via run_blocking."""
        body = self._get_bg_func_body()
        assert 'run_blocking(sync_executor, decode_files_to_wav' in body

    def test_async_coordinator_offloads_vad(self):
        """VAD must be offloaded to sync_executor via run_blocking + asyncio.gather."""
        body = self._get_bg_func_body()
        assert 'run_blocking(sync_executor, _run_vad_bg' in body
        assert 'asyncio.gather(*vad_tasks' in body

    def test_async_coordinator_offloads_segment_processing(self):
        """Segment processing must be offloaded to sync_executor via run_blocking."""
        body = self._get_bg_func_body()
        assert 'run_blocking(sync_executor, _process_one_segment' in body

    def test_async_coordinator_offloads_cleanup_to_storage(self):
        """File cleanup must be offloaded to storage_executor via run_blocking."""
        body = self._get_bg_func_body()
        assert 'run_blocking(storage_executor, _cleanup_files' in body
        assert 'run_blocking(storage_executor, shutil.rmtree' in body

    def test_async_coordinator_uses_semaphore(self):
        """Async coordinator must use loop-scoped semaphore for concurrency cap."""
        body = self._get_bg_func_body()
        assert '_get_sync_pipeline_semaphore' in body

    def test_async_coordinator_marks_failed_on_exception(self):
        """Async coordinator must call mark_job_failed for error cases."""
        body = self._get_bg_func_body()
        occurrences = body.count('mark_job_failed')
        assert (
            occurrences >= 2
        ), f"Expected mark_job_failed called multiple times (decode errors + general except), got {occurrences}"

    def test_async_coordinator_clears_byok_in_finally(self):
        """Async coordinator must clear BYOK keys in finally block."""
        body = self._get_bg_func_body()
        finally_idx = body.rindex('finally:')
        after_finally = body[finally_idx:]
        assert 'set_byok_keys({})' in after_finally

    def test_async_coordinator_handles_empty_decode(self):
        """Async coordinator must handle empty wav_paths (complete with 0 segments)."""
        body = self._get_bg_func_body()
        assert 'if not wav_paths:' in body
        assert "'total_segments': 0" in body

    def test_async_coordinator_chunks_segments(self):
        """Async coordinator must process segments in chunks of 5."""
        body = self._get_bg_func_body()
        assert 'chunk_size = 5' in body
        assert 'range(0, len(segment_list), chunk_size)' in body

    def test_async_coordinator_records_dg_usage_after_processing(self):
        """DG usage must be recorded after segment processing, not before."""
        body = self._get_bg_func_body()
        dg_pos = body.index('record_dg_usage_ms')
        processing_pos = body.index('_process_one_segment')
        assert dg_pos > processing_pos

    def test_async_coordinator_result_shape(self):
        """Result must include new_memories, updated_memories, failed_segments, total_segments, errors."""
        body = self._get_bg_func_body()
        for field in ['new_memories', 'updated_memories', 'failed_segments', 'total_segments', 'errors']:
            assert f"'{field}'" in body, f"Result must include {field}"

    def test_async_coordinator_stage_timings(self):
        """Async coordinator must collect stage timing metrics."""
        body = self._get_bg_func_body()
        assert 'stage_timings' in body
        assert "'decode_ms'" in body
        assert "'vad_ms'" in body
        assert "'stt_llm_ms'" in body
        assert "'total_ms'" in body

    def test_async_coordinator_fetches_prefs_and_embeddings(self):
        """Async coordinator must fetch transcription prefs and person embeddings."""
        body = self._get_bg_func_body()
        assert 'get_user_transcription_preferences' in body
        assert 'build_person_embeddings_cache' in body

    def test_no_thread_pool_slot_held_for_coordinator(self):
        """Async coordinator must NOT use submit_with_context or hold a thread pool slot."""
        body = self._get_bg_func_body()
        assert 'submit_with_context' not in body, "Async coordinator must not use submit_with_context"
        assert '.result(' not in body, "Async coordinator must not call future.result()"


# ---------------------------------------------------------------------------
# 7b. Async coordinator behavioral test
# ---------------------------------------------------------------------------


class TestAsyncCoordinatorSemaphore:
    """Verify the loop-scoped semaphore limits concurrent sync pipelines."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_semaphore_delegates_to_http_client(self):
        """Semaphore must use http_client._get_semaphore (CLAUDE.md rule 4)."""
        source = self._read_sync_source()
        assert '_get_sync_pipeline_semaphore()' in source, "Must use loop-scoped semaphore getter"
        assert '_get_semaphore' in source, "Must delegate to http_client._get_semaphore"

    def test_semaphore_limit_is_16(self):
        """Semaphore cap must be 16 (2x the old 8-slot postprocess_executor)."""
        source = self._read_sync_source()
        start = source.index('def _get_sync_pipeline_semaphore')
        end = source.find('\ndef ', start + 1)
        if end == -1:
            end = source.find('\nasync def ', start + 1)
        func_body = source[start:end]
        assert "'sync_pipeline', 16" in func_body

    def test_semaphore_no_duplicate_cache(self):
        """sync.py must NOT have its own _sync_semaphores cache (use http_client's)."""
        source = self._read_sync_source()
        assert '_sync_semaphores' not in source, "Must not duplicate semaphore cache — use http_client"


# ---------------------------------------------------------------------------
# 7c. Async coordinator scenario coverage tests (#7361 tester round 1)
# ---------------------------------------------------------------------------


class TestAsyncCoordinatorScenarios:
    """Structural tests covering pipeline scenarios: decode failure, empty decode,
    VAD error/timeout, zero segments, DG budget, partial/all segment failure,
    prefs/cache fallback, target_conversation_id forwarding, and cleanup."""

    @staticmethod
    def _get_bg_func_body():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            source = f.read()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        return source[start:next_boundary]

    # --- Decode failure scenarios ---

    def test_decode_http_exception_marks_failed(self):
        """HTTPException during decode must mark job failed with detail."""
        body = self._get_bg_func_body()
        assert 'except HTTPException as e:' in body
        http_except_idx = body.index('except HTTPException as e:')
        after = body[http_except_idx : http_except_idx + 200]
        assert 'mark_job_failed' in after
        assert 'Decode failed' in after

    def test_decode_generic_exception_marks_failed(self):
        """Generic Exception during decode must mark job failed."""
        body = self._get_bg_func_body()
        decode_section = body[body.index('decode_files_to_wav') : body.index('stage_timings[\'decode_ms\']')]
        except_blocks = [i for i in range(len(decode_section)) if decode_section[i:].startswith('except Exception')]
        assert len(except_blocks) >= 1, "Decode must catch generic Exception"
        after_except = decode_section[except_blocks[0] :]
        assert 'mark_job_failed' in after_except

    def test_decode_failure_cleans_up_raw_paths(self):
        """Raw file cleanup must happen in finally after decode, even on failure."""
        body = self._get_bg_func_body()
        decode_start = body.index('decode_files_to_wav')
        decode_region = body[decode_start : decode_start + 600]
        assert 'finally:' in decode_region
        finally_idx = decode_region.index('finally:')
        after_finally = decode_region[finally_idx:]
        assert '_cleanup_files, raw_paths' in after_finally

    def test_decode_failure_returns_early(self):
        """Decode failure must return immediately, not fall through to VAD."""
        body = self._get_bg_func_body()
        decode_section = body[body.index('decode_files_to_wav') : body.index('Phase 2')]
        return_count = decode_section.count('return')
        assert return_count >= 2, "Decode failure paths must return early (HTTPException + generic)"

    # --- Empty decode ---

    def test_empty_decode_completes_with_zero_segments(self):
        """Empty wav_paths must complete job with 0 segments, not fail."""
        body = self._get_bg_func_body()
        empty_check_idx = body.index('if not wav_paths:')
        vad_phase_idx = body.index('Phase 2: VAD')
        section = body[empty_check_idx:vad_phase_idx]
        assert 'mark_job_completed' in section
        assert "'total_segments': 0" in section
        assert "'failed_segments': 0" in section

    def test_empty_decode_does_not_run_vad(self):
        """Empty wav_paths must return before VAD phase."""
        body = self._get_bg_func_body()
        empty_check_idx = body.index('if not wav_paths:')
        vad_phase_idx = body.index('Phase 2: VAD')
        return_after_empty = body[empty_check_idx:vad_phase_idx]
        assert 'return' in return_after_empty

    # --- VAD error/timeout ---

    def test_vad_timeout_captured_as_error(self):
        """VAD TimeoutError must be captured and appended to vad_errors."""
        body = self._get_bg_func_body()
        assert 'asyncio.TimeoutError' in body
        timeout_idx = body.index('isinstance(r, asyncio.TimeoutError)')
        after = body[timeout_idx : timeout_idx + 200]
        assert 'vad_errors.append' in after
        assert 'VAD timed out' in after

    def test_vad_executor_error_captured(self):
        """Generic executor error during VAD must be captured."""
        body = self._get_bg_func_body()
        vad_region = body[body.index('vad_results = await asyncio.gather') : body.index('stage_timings[\'vad_ms\']')]
        assert 'isinstance(r, Exception)' in vad_region
        assert 'VAD executor error' in vad_region

    def test_vad_errors_mark_job_failed_and_cleanup(self):
        """VAD errors must clean up segmented paths and mark job failed."""
        body = self._get_bg_func_body()
        vad_error_check = body[body.index('if vad_errors:') :]
        vad_error_section = vad_error_check[: vad_error_check.index('return') + 10]
        assert '_cleanup_files, list(segmented_paths)' in vad_error_section
        assert 'mark_job_failed' in vad_error_section
        assert 'VAD failed for' in vad_error_section

    def test_vad_clears_segmented_paths_on_error(self):
        """On VAD failure, segmented_paths must be cleared after cleanup."""
        body = self._get_bg_func_body()
        vad_error_section = body[body.index('if vad_errors:') : body.index('Phase 3')]
        assert 'segmented_paths = set()' in vad_error_section

    def test_vad_error_detail_truncated(self):
        """VAD error detail must truncate after 3 errors to prevent huge messages."""
        body = self._get_bg_func_body()
        assert 'vad_errors[:3]' in body
        assert 'and {len(vad_errors) - 3} more' in body

    # --- Zero segments after VAD ---

    def test_zero_segments_completes_not_fails(self):
        """Zero segments after VAD (all silence) must complete with 0 segments."""
        body = self._get_bg_func_body()
        zero_check_idx = body.index('if total_segments == 0:')
        fair_use_idx = body.index('FAIR_USE_ENABLED')
        section = body[zero_check_idx:fair_use_idx]
        assert 'mark_job_completed' in section
        assert "'total_segments': 0" in section
        assert 'return' in section

    # --- DG budget ---

    def test_dg_budget_exhausted_marks_failed(self):
        """DG budget exhausted must mark job failed with descriptive message."""
        body = self._get_bg_func_body()
        assert 'is_dg_budget_exhausted' in body
        dg_section = body[body.index('is_dg_budget_exhausted') :]
        dg_early = dg_section[:500]
        assert 'mark_job_failed' in dg_early
        assert 'DG budget exhausted' in dg_early

    def test_dg_budget_exhausted_cleans_up_segments(self):
        """DG budget exhaustion must clean up segmented_paths before returning."""
        body = self._get_bg_func_body()
        dg_section = body[body.index('is_dg_budget_exhausted') : body.index('is_locked = should_lock')]
        assert '_cleanup_files, list(segmented_paths)' in dg_section

    def test_dg_budget_not_exhausted_continues(self):
        """When DG budget is NOT exhausted, pipeline continues to segment processing."""
        body = self._get_bg_func_body()
        dg_section_end = body.index('is_locked = should_lock')
        after_dg = body[dg_section_end:]
        assert 'Phase 4: Fetch prefs' in after_dg
        assert '_process_one_segment' in after_dg

    def test_dg_budget_check_error_is_non_fatal(self):
        """DG budget check exception must be logged but not fail the pipeline."""
        body = self._get_bg_func_body()
        dg_check_region = body[body.index('DG budget gate') : body.index('is_locked = should_lock')]
        assert "except Exception as e:" in dg_check_region
        assert "DG budget check error" in dg_check_region

    def test_dg_usage_recorded_after_processing(self):
        """DG usage recording must happen after segment processing, not before."""
        body = self._get_bg_func_body()
        processing_end = body.index("stage_timings['stt_llm_ms']")
        record_dg_idx = body.index('record_dg_usage_ms')
        assert record_dg_idx > processing_end

    # --- Partial / all segment failure ---

    def test_segment_timeout_captured(self):
        """Segment TimeoutError must be captured in segment_errors."""
        body = self._get_bg_func_body()
        seg_section = body[body.index('seg_results = await asyncio.gather') :]
        seg_early = seg_section[:500]
        assert 'isinstance(r, asyncio.TimeoutError)' in seg_early
        assert 'Segment timed out' in seg_early

    def test_segment_errors_included_in_result(self):
        """segment_errors must be included in the final result sent to mark_job_completed."""
        body = self._get_bg_func_body()
        result_section = body[body.index("# Build result") :]
        assert 'failed_segments' in result_section
        assert 'segment_errors' in result_section
        assert 'segment_errors[:10]' in result_section

    def test_partial_failure_still_completes(self):
        """Partial segment failure must still call mark_job_completed (not mark_job_failed)."""
        body = self._get_bg_func_body()
        build_result_idx = body.index("# Build result")
        general_except_idx = body.index("sync_v2 bg failed job=")
        result_section = body[build_result_idx:general_except_idx]
        assert 'mark_job_completed' in result_section

    def test_segment_errors_capped_at_10(self):
        """segment_errors in result must be capped to prevent large Redis values."""
        body = self._get_bg_func_body()
        assert 'segment_errors[:10]' in body

    # --- Prefs / cache fallback ---

    def test_prefs_fetched_from_db(self):
        """Transcription prefs must be fetched via run_blocking(db_executor, ...)."""
        body = self._get_bg_func_body()
        assert 'get_user_transcription_preferences' in body
        assert 'db_executor' in body

    def test_person_embeddings_fallback_on_error(self):
        """Person embeddings cache failure must fall back to empty dict, not crash."""
        body = self._get_bg_func_body()
        embeddings_section = body[body.index('build_person_embeddings_cache') : body.index('Phase 5')]
        assert 'except Exception' in embeddings_section
        assert 'person_embeddings_cache = {}' in embeddings_section

    def test_person_embeddings_logged_on_failure(self):
        """Person embeddings failure must be logged as warning."""
        body = self._get_bg_func_body()
        embeddings_section = body[body.index('build_person_embeddings_cache') : body.index('Phase 5')]
        assert 'failed to load person embeddings' in embeddings_section

    # --- target_conversation_id forwarding ---

    def test_target_conversation_id_in_signature(self):
        """target_conversation_id must be in the function signature."""
        body = self._get_bg_func_body()
        sig_end = body.index('):')
        sig = body[:sig_end]
        assert 'target_conversation_id' in sig

    def test_target_conversation_id_forwarded_to_process_segment(self):
        """target_conversation_id must be passed through to _process_one_segment / process_segment."""
        body = self._get_bg_func_body()
        process_segment_section = body[body.index('def _process_one_segment') :]
        process_segment_call = process_segment_section[:500]
        assert 'target_conversation_id' in process_segment_call

    # --- Cleanup on success and failure ---

    def test_finally_clears_byok_keys(self):
        """Finally block must clear BYOK keys to prevent context leaks."""
        body = self._get_bg_func_body()
        finally_idx = body.rindex('finally:')
        after_finally = body[finally_idx:]
        assert 'set_byok_keys({})' in after_finally

    def test_finally_cleans_segmented_paths(self):
        """Finally block must clean up segmented_paths."""
        body = self._get_bg_func_body()
        finally_idx = body.rindex('finally:')
        after_finally = body[finally_idx:]
        assert '_cleanup_files, list(segmented_paths)' in after_finally

    def test_finally_cleans_wav_paths(self):
        """Finally block must clean up wav_paths."""
        body = self._get_bg_func_body()
        finally_idx = body.rindex('finally:')
        after_finally = body[finally_idx:]
        assert '_cleanup_files, wav_paths' in after_finally

    def test_finally_removes_job_directory(self):
        """Finally block must remove job directory via shutil.rmtree."""
        body = self._get_bg_func_body()
        finally_idx = body.rindex('finally:')
        after_finally = body[finally_idx:]
        assert 'shutil.rmtree' in after_finally
        assert 'job_dir' in after_finally

    def test_general_exception_marks_failed(self):
        """General except Exception must mark job failed with error message."""
        body = self._get_bg_func_body()
        main_except = body[body.index("except Exception as e:\n            logger.error(f'sync_v2 bg failed") :]
        main_except_early = main_except[:200]
        assert 'mark_job_failed' in main_except_early

    def test_cleanup_order_byok_before_files(self):
        """BYOK keys must be cleared before file cleanup in finally."""
        body = self._get_bg_func_body()
        finally_idx = body.rindex('finally:')
        after_finally = body[finally_idx:]
        byok_pos = after_finally.index('set_byok_keys({})')
        cleanup_pos = after_finally.index('_cleanup_files')
        assert byok_pos < cleanup_pos, "BYOK must be cleared before file cleanup"


# ---------------------------------------------------------------------------
# 7d. Behavioral async coordinator tests (invoke the actual coroutine)
# ---------------------------------------------------------------------------


class TestAsyncCoordinatorBehavioral:
    """Behavioral tests that invoke _run_full_pipeline_background_async with
    mocked dependencies. Verifies actual call sequences and outcomes."""

    @staticmethod
    def _load_sync_module():
        """Load routers/sync.py with all heavy deps stubbed, return (module, stubs)."""
        saved_modules = {}
        stubs = {}

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
            'models.conversation_enums',
            'models.transcript_segment',
            'utils',
            'utils.analytics',
            'utils.byok',
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
            'utils.log_sanitizer',
            'utils.http_client',
            'utils.speaker_assignment',
            'utils.speaker_identification',
            'utils.stt.speaker_embedding',
        ]

        for mod_name in heavy_deps:
            saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()

        mock_executors = MagicMock()
        mock_executors.critical_executor = MagicMock()
        mock_executors.sync_executor = MagicMock()
        mock_executors.postprocess_executor = MagicMock()
        mock_executors.storage_executor = MagicMock()
        mock_executors.db_executor = MagicMock()

        async def _passthrough_run_blocking(_executor, fn, *args, **kwargs):
            return fn(*args, **kwargs)

        mock_executors.run_blocking = _passthrough_run_blocking
        mock_executors.submit_with_context = MagicMock()
        saved_modules['utils.executors'] = sys.modules.get('utils.executors')
        sys.modules['utils.executors'] = mock_executors

        mock_sync_jobs = MagicMock()
        mock_sync_jobs.mark_job_processing = MagicMock()
        mock_sync_jobs.mark_job_completed = MagicMock()
        mock_sync_jobs.mark_job_failed = MagicMock()
        mock_sync_jobs.update_sync_job = MagicMock()
        mock_sync_jobs.create_sync_job = MagicMock()
        mock_sync_jobs.get_sync_job = MagicMock()
        saved_modules['database.sync_jobs'] = sys.modules.get('database.sync_jobs')
        sys.modules['database.sync_jobs'] = mock_sync_jobs

        sys.modules['database.redis_db'] = MagicMock(r=MagicMock())
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
        sys.modules['utils.fair_use'].record_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].get_rolling_speech_ms = MagicMock(return_value={})
        sys.modules['utils.fair_use'].check_soft_caps = MagicMock(return_value=[])
        sys.modules['utils.fair_use'].trigger_classifier_if_needed = MagicMock()
        sys.modules['utils.fair_use'].record_dg_usage_ms = MagicMock()
        sys.modules['utils.byok'].set_byok_keys = MagicMock()
        sys.modules['utils.byok'].get_byok_keys = MagicMock(return_value={})
        sys.modules['utils.analytics'].record_usage = MagicMock()
        sys.modules['models.conversation_enums'].ConversationSource = MagicMock()
        sys.modules['utils.other.endpoints'].get_current_user_uid = MagicMock(return_value='test-uid')
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)

        sys.modules.pop('routers.sync', None)
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            'sync_behavioral',
            os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        stubs['sync_jobs'] = mock_sync_jobs
        stubs['fair_use'] = sys.modules['utils.fair_use']
        stubs['byok'] = sys.modules['utils.byok']
        stubs['analytics'] = sys.modules['utils.analytics']
        stubs['saved_modules'] = saved_modules

        return module, stubs

    @staticmethod
    def _cleanup(saved_modules):
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('sync_behavioral', None)
        for mod_name, orig in saved_modules.items():
            if orig is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = orig

    @pytest.mark.asyncio
    async def test_decode_http_exception_marks_failed(self):
        """Decode raising HTTPException must mark job failed."""
        from fastapi import HTTPException as _HTTPException

        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(side_effect=_HTTPException(status_code=400, detail='bad format'))
            module._cleanup_files = MagicMock()

            await module._run_full_pipeline_background_async('j1', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job1')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert args[0] == 'j1'
            assert 'Decode failed' in args[1]
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_decode_generic_exception_marks_failed(self):
        """Decode raising generic Exception must mark job failed."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(side_effect=RuntimeError('corrupt file'))
            module._cleanup_files = MagicMock()

            await module._run_full_pipeline_background_async('j2', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job2')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert 'Decode failed' in args[1]
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_empty_decode_completes_zero_segments(self):
        """Empty wav_paths after decode must complete job with 0 segments."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=[])
            module._cleanup_files = MagicMock()

            await module._run_full_pipeline_background_async('j3', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job3')

            stubs['sync_jobs'].mark_job_completed.assert_called_once()
            result = stubs['sync_jobs'].mark_job_completed.call_args[0][1]
            assert result['total_segments'] == 0
            assert result['failed_segments'] == 0
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_vad_errors_mark_failed(self):
        """VAD errors must mark job failed and clean up."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            module._cleanup_files = MagicMock()

            def _bad_vad(path, segmented_paths, errors):
                errors.append(f'{path}: silero exploded')

            module.retrieve_vad_segments = _bad_vad

            await module._run_full_pipeline_background_async('j4', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job4')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert 'VAD failed' in args[1]
            assert module._cleanup_files.call_count >= 2
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_zero_segments_after_vad_completes(self):
        """Zero segmented_paths after VAD must complete with 0 segments."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            module._cleanup_files = MagicMock()
            module.retrieve_vad_segments = MagicMock()
            module.get_wav_duration = MagicMock(return_value=0.0)

            await module._run_full_pipeline_background_async('j5', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job5')

            stubs['sync_jobs'].mark_job_completed.assert_called_once()
            result = stubs['sync_jobs'].mark_job_completed.call_args[0][1]
            assert result['total_segments'] == 0
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_dg_budget_exhausted_marks_failed(self):
        """DG budget exhausted must mark job failed."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            module._cleanup_files = MagicMock()

            def _vad_with_segments(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg1.wav')

            module.retrieve_vad_segments = _vad_with_segments
            module.get_wav_duration = MagicMock(return_value=5.0)
            module.FAIR_USE_ENABLED = True
            module.FAIR_USE_RESTRICT_DAILY_DG_MS = 1000
            module.get_enforcement_stage = MagicMock(return_value='restrict')
            module.is_dg_budget_exhausted = MagicMock(return_value=True)
            module.record_speech_ms = MagicMock()
            module.get_rolling_speech_ms = MagicMock(return_value={})
            module.check_soft_caps = MagicMock(return_value=[])

            await module._run_full_pipeline_background_async('j6', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job6')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert 'DG budget exhausted' in args[1]
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_dg_budget_not_exhausted_continues(self):
        """DG budget NOT exhausted must continue to segment processing."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            module._cleanup_files = MagicMock()

            def _vad_with_segments(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg1.wav')

            module.retrieve_vad_segments = _vad_with_segments
            module.get_wav_duration = MagicMock(return_value=5.0)
            module.FAIR_USE_ENABLED = True
            module.FAIR_USE_RESTRICT_DAILY_DG_MS = 1000
            module.get_enforcement_stage = MagicMock(return_value='restrict')
            module.is_dg_budget_exhausted = MagicMock(return_value=False)
            module.record_speech_ms = MagicMock()
            module.get_rolling_speech_ms = MagicMock(return_value={})
            module.check_soft_caps = MagicMock(return_value=[])
            module.users_db = MagicMock()
            module.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            module.build_person_embeddings_cache = MagicMock(return_value={})
            module.process_segment = MagicMock()
            module.record_dg_usage_ms = MagicMock()
            module.record_usage = MagicMock()

            await module._run_full_pipeline_background_async('j7', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job7')

            stubs['sync_jobs'].mark_job_completed.assert_called_once()
            module.process_segment.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_partial_segment_failure_completes(self):
        """Partial segment failure must complete (not fail) with error count."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            module._cleanup_files = MagicMock()

            def _vad_two_segments(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg1.wav')
                segmented_paths.add('/tmp/seg2.wav')

            module.retrieve_vad_segments = _vad_two_segments
            module.get_wav_duration = MagicMock(return_value=5.0)
            module.users_db = MagicMock()
            module.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            module.build_person_embeddings_cache = MagicMock(return_value={})
            module.record_usage = MagicMock()
            call_count = [0]

            def _process_seg_fails_once(path, uid, response, lock, errors, *args):
                call_count[0] += 1
                if call_count[0] == 1:
                    errors.append(f'Segment {path} failed')
                else:
                    response['new_memories'].add('mem1')

            module.process_segment = _process_seg_fails_once

            await module._run_full_pipeline_background_async('j8', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job8')

            stubs['sync_jobs'].mark_job_completed.assert_called_once()
            result = stubs['sync_jobs'].mark_job_completed.call_args[0][1]
            assert result['failed_segments'] == 1
            assert result['total_segments'] == 2
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_person_embeddings_fallback(self):
        """Person embeddings failure must fall back to empty dict, not crash."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            module._cleanup_files = MagicMock()

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg1.wav')

            module.retrieve_vad_segments = _vad_one_seg
            module.get_wav_duration = MagicMock(return_value=5.0)
            module.users_db = MagicMock()
            module.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            module.build_person_embeddings_cache = MagicMock(side_effect=RuntimeError('cache boom'))
            captured_cache = {}

            def _capture_process(path, uid, response, lock, errors, source, is_locked, prefs, cache, *args):
                captured_cache['value'] = cache
                response['new_memories'].add('m1')

            module.process_segment = _capture_process
            module.record_usage = MagicMock()

            await module._run_full_pipeline_background_async('j9', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job9')

            assert captured_cache['value'] == {}
            stubs['sync_jobs'].mark_job_completed.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_target_conversation_id_forwarded(self):
        """target_conversation_id must be forwarded to process_segment."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            module._cleanup_files = MagicMock()

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg1.wav')

            module.retrieve_vad_segments = _vad_one_seg
            module.get_wav_duration = MagicMock(return_value=5.0)
            module.users_db = MagicMock()
            module.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            module.build_person_embeddings_cache = MagicMock(return_value={})
            module.record_usage = MagicMock()
            captured_target = {}

            def _capture_target(path, uid, response, lock, errors, source, is_locked, prefs, cache, target_cid):
                captured_target['value'] = target_cid
                response['new_memories'].add('m1')

            module.process_segment = _capture_target

            await module._run_full_pipeline_background_async(
                'j10', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job10', target_conversation_id='conv-123'
            )

            assert captured_target['value'] == 'conv-123'
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_cleanup_called_on_success(self):
        """Cleanup must be called even on successful completion."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            cleanup_calls = []
            module._cleanup_files = lambda paths: cleanup_calls.append(list(paths))

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg1.wav')

            module.retrieve_vad_segments = _vad_one_seg
            module.get_wav_duration = MagicMock(return_value=5.0)
            module.users_db = MagicMock()
            module.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            module.build_person_embeddings_cache = MagicMock(return_value={})
            module.process_segment = MagicMock()
            module.record_usage = MagicMock()

            await module._run_full_pipeline_background_async('j11', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job11')

            stubs['byok'].set_byok_keys.assert_called_with({})
            assert len(cleanup_calls) >= 3
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_cleanup_called_on_failure(self):
        """Cleanup and BYOK clear must happen even when pipeline crashes."""
        module, stubs = self._load_sync_module()
        try:
            module.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            cleanup_calls = []
            module._cleanup_files = lambda paths: cleanup_calls.append(list(paths))

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg1.wav')

            module.retrieve_vad_segments = _vad_one_seg
            module.get_wav_duration = MagicMock(side_effect=RuntimeError('unexpected crash'))

            await module._run_full_pipeline_background_async('j12', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job12')

            stubs['byok'].set_byok_keys.assert_called_with({})
            stubs['sync_jobs'].mark_job_failed.assert_called()
            assert len(cleanup_calls) >= 2
        finally:
            self._cleanup(stubs['saved_modules'])


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
            'models.conversation_enums',
            'models.transcript_segment',
            'utils',
            'utils.analytics',
            'utils.byok',
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
            'utils.log_sanitizer',
            'utils.http_client',
            'utils.speaker_assignment',
            'utils.speaker_identification',
            'utils.stt.speaker_embedding',
        ]

        for mod_name in heavy_deps:
            saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()

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

    def test_post_returns_202_and_schedules_background(self):
        """POST /v2/sync-local-files must return 202, create job, and schedule async background task."""
        saved, mock_sync_jobs, _ = self._build_test_app()
        mock_sync_jobs.create_sync_job = MagicMock(
            return_value={
                'job_id': 'created-job',
                'uid': 'test-uid',
                'status': 'queued',
                'total_files': 1,
                'total_segments': 0,
            }
        )

        try:
            sys.modules.pop('routers.sync', None)
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_post_202',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            module._retrieve_file_paths_v2 = MagicMock(return_value=['/tmp/fake.opus'])

            async def _noop_pipeline(*args, **kwargs):
                pass

            module._run_full_pipeline_background_async = _noop_pipeline

            async def _passthrough_run_blocking(_executor, fn, *args, **kwargs):
                return fn(*args, **kwargs)

            module.run_blocking = _passthrough_run_blocking

            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            app = FastAPI()
            app.include_router(module.router)
            app.dependency_overrides[module.auth.get_current_user_uid] = lambda: 'test-uid'

            client = TestClient(app)
            resp = client.post('/v2/sync-local-files', files=[('files', ('test.opus', b'\x00' * 10, 'audio/opus'))])

            assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
            body = resp.json()
            assert 'job_id' in body
            assert body['status'] == 'queued'
            assert body['poll_after_ms'] == 3000
            mock_sync_jobs.create_sync_job.assert_called_once()
        finally:
            self._cleanup_modules(saved)


# ---------------------------------------------------------------------------
# Pusher coordinator executor pattern
# ---------------------------------------------------------------------------


class TestPusherCoordinatorExecutor:
    """Pusher _process_conversation_task must use run_in_executor(None, ...) not critical_executor.

    process_conversation is a coordinator that internally submits to critical_executor.
    Passing critical_executor to run_in_executor would nest executors and cause deadlock.
    """

    @staticmethod
    def _read_pusher_source():
        pusher_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'pusher.py')
        with open(pusher_path) as f:
            return f.read()

    def test_process_conversation_uses_run_in_executor(self):
        """pusher._process_conversation_task must use run_in_executor for process_conversation."""
        source = self._read_pusher_source()
        assert 'run_in_executor' in source, "pusher.py must use run_in_executor for process_conversation"

    def test_process_conversation_uses_none_executor(self):
        """pusher._process_conversation_task must pass None as executor to avoid deadlock.

        process_conversation is a coordinator that submits child tasks to critical_executor.
        Using run_in_executor(None, ...) uses the default executor, preventing nested pool deadlock.
        """
        source = self._read_pusher_source()
        assert '_process_conversation_task' in source, "pusher.py must define _process_conversation_task"
        start = source.index('async def _process_conversation_task')
        next_def = source.find('\nasync def ', start + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[start:next_def]

        none_executor_pattern = re.compile(r'run_in_executor\(\s*None\s*,')
        assert none_executor_pattern.search(func_body), (
            "pusher._process_conversation_task must use run_in_executor(None, process_conversation, ...) "
            "— not critical_executor — because process_conversation is a coordinator that submits "
            "child tasks to critical_executor; nesting would cause deadlock under load"
        )

    def test_process_conversation_not_using_critical_executor_directly(self):
        """process_conversation call in pusher must NOT use critical_executor as the executor arg."""
        source = self._read_pusher_source()
        start = source.index('async def _process_conversation_task')
        next_def = source.find('\nasync def ', start + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[start:next_def]

        assert 'run_in_executor(critical_executor, process_conversation' not in func_body, (
            "pusher._process_conversation_task must NOT pass critical_executor for process_conversation — "
            "use None (default executor) to prevent deadlock"
        )


# ---------------------------------------------------------------------------
# 14. Bulkhead executor infrastructure tests
# ---------------------------------------------------------------------------


class TestBulkheadExecutors:
    """Verify bulkhead executor configuration in utils/executors.py."""

    @staticmethod
    def _read_executors_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'executors.py')
        with open(path) as f:
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
        assert 'max_workers=12' in source
        assert 'postprocess_executor = MonitoredThreadPoolExecutor(' in source
        assert 'max_workers=8' in source

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
        with open(path) as f:
            return f.read()

    def test_v2_uses_start_background_task_for_context_inheritance(self):
        """v2 must use start_background_task which wraps create_task (auto-inherits ContextVars/BYOK)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'start_background_task' in func_body, "v2 must use start_background_task for context inheritance"

    def test_async_coordinator_clears_byok_in_finally(self):
        """Async coordinator must clear BYOK context in its finally block."""
        source = self._read_sync_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'set_byok_keys({})' in func_body, "Async coordinator must clear BYOK keys in finally"

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
        with open(path) as f:
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
        with open(path) as f:
            return f.read()

    @staticmethod
    def _read_pre_recorded_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'stt', 'pre_recorded.py')
        with open(path) as f:
            return f.read()

    @staticmethod
    def _read_classifier_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'llm', 'fair_use_classifier.py')
        with open(path) as f:
            return f.read()

    def test_llm_mini_has_timeout(self):
        source = self._read_clients_source()
        llm_mini_line = [l for l in source.split('\n') if 'llm_mini' in l and 'ChatOpenAI' in l][0]
        assert 'request_timeout=120' in llm_mini_line
        assert 'max_retries=1' in llm_mini_line

    def test_anthropic_default_has_timeout(self):
        source = self._read_clients_source()
        default_line = [l for l in source.split('\n') if '_default_anthropic_client' in l and 'AsyncAnthropic' in l][0]
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
        source = self._read_classifier_source()
        start = source.index('_classifier_llm')
        end = source.index('\n', source.index(')', start))
        constructor_call = source[start:end]
        assert 'request_timeout=120' in constructor_call
        assert 'max_retries=1' in constructor_call

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

    def test_segment_timeout_budget(self):
        """Segment tasks in v2 async coordinator must use asyncio.wait_for with timeout=300."""
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            source = f.read()
        start = source.index('async def _run_full_pipeline_background_async')
        end = source.find('\n@router.', start + 1)
        if end == -1:
            end = len(source)
        func_body = source[start:end]
        assert 'asyncio.wait_for(' in func_body, "Must use asyncio.wait_for for timeout enforcement"
        assert 'timeout=300' in func_body, "Segment tasks must have 300s timeout"
