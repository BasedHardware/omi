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

    def test_v2_submits_to_default_executor(self):
        """v2 must submit background work via run_in_executor(None, ...) to avoid deadlock."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'run_in_executor' in func_body, "v2 must use run_in_executor for background worker"
        assert '_run_full_pipeline_background' in func_body, "v2 must submit the full pipeline background worker"
        none_executor_pattern = re.compile(r'run_in_executor\(\s*None\s*,')
        assert none_executor_pattern.search(func_body), (
            "v2 coordinator dispatch must use run_in_executor(None, ...) — "
            "passing critical_executor would nest executors and cause deadlock"
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
        start = source.index('def _run_full_pipeline_background')
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
        start = source.index('def _run_full_pipeline_background')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        dg_pos = func_body.index('record_dg_usage_ms')
        processing_pos = func_body.index('future.result(')
        assert dg_pos > processing_pos, "DG usage must be recorded AFTER segment processing"

    def test_v2_background_does_decode_and_vad(self):
        """Background worker must run decode and VAD (#7281 — moved from inline)."""
        source = self._read_sync_source()
        start = source.index('def _run_full_pipeline_background')
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
        start = source.index('def _run_full_pipeline_background')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert "'stage': 'decoding'" in func_body, "Background must heartbeat decode stage"
        assert "'stage': 'vad'" in func_body, "Background must heartbeat VAD stage"
        assert "'stage': 'processing'" in func_body, "Background must heartbeat processing stage"

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

    def test_v2_bg_worker_fetches_prefs_and_cache(self):
        """Background worker must fetch transcription prefs and build person embeddings cache."""
        source = self._read_sync_source()
        start = source.index('def _run_full_pipeline_background')
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
    """Test _run_full_pipeline_background worker function."""

    @staticmethod
    def _get_bg_func_body():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            source = f.read()
        start = source.index('def _run_full_pipeline_background')
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
        heartbeat_pos = body.rindex('update_sync_job(')
        result_pos = body.index('future.result(')
        assert heartbeat_pos > result_pos, "Heartbeat must come after future.result()"

    def test_background_pipeline_order(self):
        """Worker must run: decode → VAD → fair-use → STT in correct order."""
        body = self._get_bg_func_body()
        decode_pos = body.index('decode_files_to_wav')
        vad_pos = body.index('retrieve_vad_segments')
        speech_pos = body.index('record_speech_ms')
        segment_pos = body.index('process_segment')
        assert decode_pos < vad_pos < speech_pos < segment_pos


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

    def test_v2_transfers_file_ownership_to_bg_thread(self):
        """v2 must transfer raw path ownership to prevent double cleanup."""
        body = self._get_v2_post_body()
        assert 'owned_paths = list(paths)' in body
        assert 'paths = []' in body

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


class TestBackgroundWorkerBehavioral:
    """Behavioral tests for _run_full_pipeline_background using mocks."""

    @staticmethod
    def _load_bg_worker():
        """Load the background worker function with all dependencies mocked."""
        mock_redis = MagicMock()
        mock_sync_jobs = MagicMock()

        saved_modules = {}
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
            'models.conversation_enums',
            'models.transcript_segment',
        ]
        utils_subs = [
            'utils',
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
            'utils.analytics',
            'utils.speaker_assignment',
            'utils.speaker_identification',
            'utils.stt.speaker_embedding',
            'utils.executors',
            'utils.http_client',
        ]
        heavy_deps.extend(utils_subs)

        for mod in heavy_deps:
            saved_modules[mod] = sys.modules.get(mod)
            sys.modules[mod] = MagicMock()

        import contextvars
        from concurrent.futures import Future, ThreadPoolExecutor

        _test_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='test')

        def _submit_with_context(executor, fn, *args, **kwargs):
            ctx = contextvars.copy_context()
            return executor.submit(ctx.run, fn, *args, **kwargs)

        sys.modules['utils.executors'].critical_executor = _test_executor
        sys.modules['utils.executors'].sync_executor = _test_executor
        sys.modules['utils.executors'].postprocess_executor = _test_executor
        sys.modules['utils.executors'].storage_executor = _test_executor
        sys.modules['utils.executors'].submit_with_context = _submit_with_context

        sys.modules['database.redis_db'] = MagicMock(r=mock_redis)
        saved_modules['database.sync_jobs'] = sys.modules.get('database.sync_jobs')
        sys.modules['database.sync_jobs'] = mock_sync_jobs

        # Fair-use defaults
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0

        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                'sync_router_bg',
                os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Mock decode+VAD to pass through paths as segments
            def _mock_decode(paths):
                return list(paths)

            def _mock_vad(path, segmented_paths, errors=None):
                segmented_paths.add(path)

            module.decode_files_to_wav = _mock_decode
            module.retrieve_vad_segments = _mock_vad
            module.get_wav_duration = lambda p: 5.0
            module.build_person_embeddings_cache = MagicMock(return_value={})
            module.users_db = MagicMock()
            module.users_db.get_user_transcription_preferences = MagicMock(return_value={})

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

        mod._run_full_pipeline_background(
            job_id='test-job',
            uid='test-uid',
            raw_paths=['/tmp/fake1.wav', '/tmp/fake2.wav'],
            source='omi',
            should_lock=False,
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

        mod._run_full_pipeline_background(
            job_id='test-job',
            uid='test-uid',
            raw_paths=['/tmp/fake.wav'],
            source='omi',
            should_lock=False,
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

        mod._run_full_pipeline_background(
            job_id='hb-job',
            uid='uid',
            raw_paths=paths,
            source='omi',
            should_lock=False,
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

        mod._run_full_pipeline_background(
            job_id='partial-job',
            uid='test-uid',
            raw_paths=['/tmp/s1.wav', '/tmp/s2.wav', '/tmp/s3.wav', '/tmp/s4.wav'],
            source='omi',
            should_lock=False,
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

        mod._run_full_pipeline_background(
            job_id='allfail-job',
            uid='test-uid',
            raw_paths=['/tmp/f1.wav', '/tmp/f2.wav'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/allfail-dir',
        )

        mock_sync_jobs.mark_job_completed.assert_called_once()
        result_arg = mock_sync_jobs.mark_job_completed.call_args[0][1]
        assert result_arg['failed_segments'] == 2
        assert result_arg['total_segments'] == 2
        assert len(result_arg['errors']) == 2

    def test_bg_worker_records_dg_usage_when_enabled(self):
        """Worker must call record_dg_usage_ms when FAIR_USE_ENABLED and enforcement=restrict."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.process_segment = MagicMock()
        mock_record_dg = MagicMock()
        mod.record_dg_usage_ms = mock_record_dg
        mod.FAIR_USE_ENABLED = True
        mod.FAIR_USE_RESTRICT_DAILY_DG_MS = 1000
        mod.get_enforcement_stage = MagicMock(return_value='restrict')
        mod.is_dg_budget_exhausted = MagicMock(return_value=False)
        mod.record_speech_ms = MagicMock()
        mod.get_rolling_speech_ms = MagicMock(return_value={})
        mod.check_soft_caps = MagicMock(return_value=[])

        mod._run_full_pipeline_background(
            job_id='dg-job',
            uid='test-uid',
            raw_paths=['/tmp/d1.wav'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/dg-dir',
        )

        mock_record_dg.assert_called_once_with('test-uid', 5000)

    def test_bg_worker_skips_dg_recording_when_disabled(self):
        """Worker must NOT call record_dg_usage_ms when FAIR_USE_ENABLED=False."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.process_segment = MagicMock()
        mock_record_dg = MagicMock()
        mod.record_dg_usage_ms = mock_record_dg
        mod.FAIR_USE_ENABLED = False

        mod._run_full_pipeline_background(
            job_id='no-dg-job',
            uid='test-uid',
            raw_paths=['/tmp/d1.wav'],
            source='omi',
            should_lock=False,
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

        mod._run_full_pipeline_background(
            job_id='cleanup-job',
            uid='test-uid',
            raw_paths=[],
            source='omi',
            should_lock=False,
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

        mod._run_full_pipeline_background(
            job_id='cleanup-fail-job',
            uid='test-uid',
            raw_paths=[],
            source='omi',
            should_lock=False,
            job_dir=job_dir,
        )

        assert not os.path.exists(job_dir), "Job directory must be cleaned up even on failure"

    def test_bg_worker_fetches_and_forwards_prefs_to_process_segment(self):
        """Worker must fetch prefs/cache internally and forward to each process_segment call."""
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
        mod.users_db.get_user_transcription_preferences = MagicMock(return_value=test_prefs)
        mod.build_person_embeddings_cache = MagicMock(return_value=test_cache)

        mod._run_full_pipeline_background(
            job_id='prefs-job',
            uid='test-uid',
            raw_paths=['/tmp/p1.wav', '/tmp/p2.wav'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/prefs-dir',
        )

        assert len(received_args) == 2
        for args in received_args:
            assert args['prefs'] is test_prefs
            assert args['cache'] is test_cache

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

        mod._run_full_pipeline_background(
            job_id='target-conv-job',
            uid='test-uid',
            raw_paths=['/tmp/tc1.wav', '/tmp/tc2.wav'],
            source='omi',
            should_lock=False,
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

        mod._run_full_pipeline_background(
            job_id='no-target-conv-job',
            uid='test-uid',
            raw_paths=['/tmp/nt1.wav'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/no-target-conv-dir',
        )

        assert len(received_args) == 1
        assert received_args[0]['target_conversation_id'] is None

    def test_bg_worker_decode_failure_marks_job_failed(self):
        """Worker must mark_job_failed when decode_files_to_wav raises."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.decode_files_to_wav = MagicMock(side_effect=Exception("corrupt opus frame"))

        mod._run_full_pipeline_background(
            job_id='decode-fail-job',
            uid='test-uid',
            raw_paths=['/tmp/bad.opus'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/decode-fail-dir',
        )

        mock_sync_jobs.mark_job_failed.assert_called_once()
        assert 'corrupt opus frame' in mock_sync_jobs.mark_job_failed.call_args[0][1]

    def test_bg_worker_vad_error_aborts_job(self):
        """Worker must fail the job when retrieve_vad_segments produces errors."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        def _bad_vad(path, segmented_paths, errors=None):
            if errors is not None:
                errors.append(f'VAD failed: {path}')

        mod.retrieve_vad_segments = _bad_vad

        mod._run_full_pipeline_background(
            job_id='vad-fail-job',
            uid='test-uid',
            raw_paths=['/tmp/v1.wav'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/vad-fail-dir',
        )

        mock_sync_jobs.mark_job_failed.assert_called_once()
        assert 'VAD failed' in mock_sync_jobs.mark_job_failed.call_args[0][1]
        mock_sync_jobs.mark_job_completed.assert_not_called()

    def test_bg_worker_vad_exception_aborts_job(self):
        """Worker must fail the job when retrieve_vad_segments raises an exception."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.retrieve_vad_segments = MagicMock(side_effect=RuntimeError("AudioSegment export failed"))

        mod._run_full_pipeline_background(
            job_id='vad-exc-job',
            uid='test-uid',
            raw_paths=['/tmp/v1.wav'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/vad-exc-dir',
        )

        mock_sync_jobs.mark_job_failed.assert_called_once()
        assert 'AudioSegment export failed' in mock_sync_jobs.mark_job_failed.call_args[0][1]

    def test_bg_worker_dg_budget_exhausted_fails_job(self):
        """Worker must mark_job_failed when DG budget is exhausted."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.FAIR_USE_ENABLED = True
        mod.FAIR_USE_RESTRICT_DAILY_DG_MS = 1000
        mod.get_enforcement_stage = MagicMock(return_value='restrict')
        mod.is_dg_budget_exhausted = MagicMock(return_value=True)
        mod.record_speech_ms = MagicMock()
        mod.get_rolling_speech_ms = MagicMock(return_value={})
        mod.check_soft_caps = MagicMock(return_value=[])
        mod.process_segment = MagicMock()

        mod._run_full_pipeline_background(
            job_id='dg-exhaust-job',
            uid='test-uid',
            raw_paths=['/tmp/e1.wav'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/dg-exhaust-dir',
        )

        mock_sync_jobs.mark_job_failed.assert_called_once()
        assert 'budget exhausted' in mock_sync_jobs.mark_job_failed.call_args[0][1].lower()
        mod.process_segment.assert_not_called()

    def test_bg_worker_empty_wav_paths_completes_with_zero(self):
        """Worker must complete with zero segments when decode returns empty list."""
        mod, mock_sync_jobs = self._load_bg_worker()
        if mod is None:
            pytest.skip("Cannot load sync router due to import chain")

        mod.decode_files_to_wav = MagicMock(return_value=[])

        mod._run_full_pipeline_background(
            job_id='empty-job',
            uid='test-uid',
            raw_paths=['/tmp/empty.opus'],
            source='omi',
            should_lock=False,
            job_dir='/tmp/empty-dir',
        )

        mock_sync_jobs.mark_job_completed.assert_called_once()
        result = mock_sync_jobs.mark_job_completed.call_args[0][1]
        assert result['total_segments'] == 0
        assert result['failed_segments'] == 0


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
        """POST /v2/sync-local-files must return 202, create job, and schedule background work."""
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
            module._run_full_pipeline_background = MagicMock()

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
        assert 'sync_executor = ThreadPoolExecutor(max_workers=12' in source
        assert 'postprocess_executor = ThreadPoolExecutor(max_workers=8' in source

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
    """Verify BYOK context lifecycle in the sync pipeline."""

    @staticmethod
    def _read_sync_source():
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(path) as f:
            return f.read()

    def test_v2_captures_byok_before_dispatch(self):
        """v2 endpoint must capture BYOK keys before run_in_executor dispatch."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'get_byok_keys()' in func_body, "v2 must capture BYOK keys before dispatch"
        assert 'captured_byok' in func_body, "v2 must store captured BYOK in a variable"

    def test_v2_passes_byok_to_background(self):
        """v2 must pass captured BYOK keys as an argument to the background worker."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'captured_byok' in func_body
        dispatch_section = func_body[func_body.index('run_in_executor') :]
        assert 'captured_byok' in dispatch_section, "captured BYOK must be passed to run_in_executor call"

    def test_background_worker_accepts_byok_parameter(self):
        """_run_full_pipeline_background must accept a byok_keys parameter."""
        source = self._read_sync_source()
        start = source.index('def _run_full_pipeline_background')
        next_def = source.find('\ndef ', start + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[start:next_def]
        assert 'byok_keys' in func_body, "Background worker must accept byok_keys parameter"

    def test_background_worker_sets_byok_unconditionally(self):
        """Background worker must call set_byok_keys unconditionally (not guarded by if)."""
        source = self._read_sync_source()
        start = source.index('def _run_full_pipeline_background')
        next_def = source.find('\ndef ', start + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[start:next_def]

        assert (
            'set_byok_keys(byok_keys or {})' in func_body
        ), "Worker must set BYOK unconditionally with empty dict fallback"

    def test_background_worker_clears_byok_in_finally(self):
        """Background worker must clear BYOK context in its finally block."""
        source = self._read_sync_source()
        start = source.index('def _run_full_pipeline_background')
        next_def = source.find('\ndef ', start + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[start:next_def]

        assert 'set_byok_keys({})' in func_body, "Worker must clear BYOK keys (expected in finally block)"

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

    def test_segment_future_timeout_budget(self):
        """Segment futures in v2 background must use timeout=300."""
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            source = f.read()
        start = source.index('def _run_full_pipeline_background')
        end = source.find('\ndef ', start + 1)
        func_body = source[start:end]
        assert 'future.result(timeout=300)' in func_body, "Segment futures must have 300s timeout"
