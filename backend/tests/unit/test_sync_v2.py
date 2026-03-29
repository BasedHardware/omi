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

    def test_v2_starts_daemon_thread(self):
        """v2 must start a daemon background thread."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files_v2')
        next_section = source.find('\n@router.', start + 1)
        if next_section == -1:
            next_section = len(source)
        func_body = source[start:next_section]

        assert 'daemon=True' in func_body, "Background thread must be daemon"
        assert 'bg_thread.start()' in func_body, "Background thread must be started"

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

        # record_dg_usage_ms must come after chunk_threads_bg
        dg_pos = func_body.index('record_dg_usage_ms')
        thread_pos = func_body.index('chunk_threads_bg(threads)')
        assert dg_pos > thread_pos, "DG usage must be recorded AFTER segment processing"

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
        assert 'mark_job_completed(job_id' in self._get_bg_func_body()

    def test_background_calls_mark_job_failed_on_exception(self):
        """Worker must call mark_job_failed on unexpected exception."""
        assert 'mark_job_failed(job_id' in self._get_bg_func_body()

    def test_background_uses_chunk_threads_pattern(self):
        """Worker must batch threads in chunks of 5 (same as v1)."""
        assert 'chunk_size = 5' in self._get_bg_func_body()

    def test_background_result_matches_v1_shape(self):
        """Worker result must include new_memories, updated_memories, failed_segments, total_segments, errors."""
        body = self._get_bg_func_body()
        for field in ['new_memories', 'updated_memories', 'failed_segments', 'total_segments', 'errors']:
            assert f"'{field}'" in body, f"Worker result must include {field}"


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

    def test_v1_uses_synchronous_chunk_threads(self):
        """v1 must still join threads synchronously (no background)."""
        body = self._get_v1_body()
        assert 'chunk_threads(threads)' in body, "v1 must still use synchronous chunk_threads"

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
