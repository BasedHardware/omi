"""
Tests for v2 async sync-local-files endpoints (#5941, #7281).

v2 saves raw files and returns 202 immediately, then runs the full pipeline
(decode → VAD → fair-use → STT → LLM) in a background thread. The app
polls GET /v2/sync-local-files/{job_id} until the job reaches a terminal status.

v1 remains completely unchanged.
"""

import asyncio
import json
import os
import re
import sys
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.routing import APIRoute
from models.users import PlanType
from utils.executors import run_blocking as _production_run_blocking

PIPELINE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'pipeline.py')


def _read_pipeline_source():
    with open(PIPELINE_PATH, encoding='utf-8') as f:
        return f.read()


def _get_pipeline_async_function_body(function_name):
    source = _read_pipeline_source()
    start = source.index(f'async def {function_name}')
    next_boundary = source.find('\nasync def ', start + 1)
    if next_boundary == -1:
        next_boundary = source.find('\ndef ', start + 1)
    if next_boundary == -1:
        next_boundary = len(source)
    return source[start:next_boundary]


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

    def test_v2_uses_job_specific_directory(self):
        """v2 must use syncing/{uid}/{job_id}/ to avoid concurrency conflicts."""
        source = _read_pipeline_source()
        assert '_retrieve_file_paths_v2' in _read_pipeline_source()
        start = _read_pipeline_source().index('def _retrieve_file_paths_v2')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert (
            'syncing/{uid}/{job_id}' in func_body or "f'syncing/{uid}/{job_id}/'" in func_body
        ), "v2 must use job-specific directory"

    def test_v2_background_has_cleanup(self):
        """Background worker must clean up files in finally block."""
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'finally:' in func_body, "Background worker must have finally for cleanup"
        assert '_cleanup_files' in func_body, "Background worker must call _cleanup_files"
        assert 'rmtree' in func_body, "Background worker must clean up job directory"

    def test_v2_background_records_dg_after_processing(self):
        """DG usage must be recorded after processing, not before."""
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        dg_pos = func_body.index('_record_restricted_sync_dg_usage')
        processing_pos = func_body.index('run_blocking(sync_executor, _process_one_segment')
        assert dg_pos > processing_pos, "DG usage must be recorded AFTER segment processing"
        assert 'record_dg_usage_ms' in _get_pipeline_async_function_body('_record_restricted_sync_dg_usage')

    def test_v2_background_does_decode_and_vad(self):
        """Background worker must run decode and VAD (#7281 — moved from inline)."""
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'decode_files_to_wav' in func_body, "Background must decode files"
        assert '_run_sync_vad_phase' in func_body, "Background must run the VAD phase"
        assert 'retrieve_vad_segments' in _get_pipeline_async_function_body('_run_sync_vad_phase')
        assert '_load_sync_segment_context' in func_body, "Background must load segment context"
        assert 'build_person_embeddings_cache' in _get_pipeline_async_function_body('_load_sync_segment_context')
        assert 'is_dg_budget_exhausted' in func_body, "Background must check DG budget"

    def test_v2_background_has_stage_heartbeats(self):
        """Background worker must heartbeat with stage info during decode and VAD."""
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
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
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'get_user_transcription_preferences' in func_body, "bg worker must fetch prefs"
        assert '_load_sync_segment_context' in func_body, "bg worker must load segment context"
        assert 'build_person_embeddings_cache' in _get_pipeline_async_function_body('_load_sync_segment_context')

    def test_v2_bg_worker_forwards_private_cloud_sync_enabled(self):
        """Background worker must forward private cloud sync intent into process_segment."""
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert '_load_sync_segment_context' in func_body
        assert 'get_user_private_cloud_sync_enabled' in _get_pipeline_async_function_body('_load_sync_segment_context')
        assert 'private_cloud_sync_enabled=private_cloud_sync_enabled' in func_body

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

    def test_device_provenance_survives_inline_and_cloud_task_dispatch(self):
        """Offline sync must stamp the conversation that canonical extraction reads."""
        source = self._read_sync_source()
        v1_start = source.index('async def sync_local_files(')
        v2_start = source.index('async def sync_local_files_v2')
        v1 = source[v1_start:v2_start]
        v2_end = source.find('\n@router.', v2_start + 1)
        v2 = source[v2_start:v2_end]
        task_handler = source[source.index('async def run_sync_job') :]
        # process_segment was extracted to utils/sync/pipeline.py (W4 refactor)
        pipeline_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'pipeline.py')
        with open(pipeline_path, encoding='utf-8') as f:
            pipeline_source = f.read()
        segment = pipeline_source[
            pipeline_source.index('def process_segment(') : pipeline_source.index('\ndef _store_sync_audio_chunk')
        ]

        assert 'resolve_client_device_from_request(request)' in v1
        assert 'resolve_client_device(' in v2
        assert "'client_device_id': client_device_context.client_device_id" in v2
        assert 'client_device_id=client_device_context.client_device_id' in v2
        assert 'client_device_id=client_device_id' in task_handler
        assert 'client_device_id=client_device_id' in segment


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

    def test_get_sync_job_self_heals_stale_processing_job(self):
        """A dead worker's job is finalized to failed on read so the client re-uploads."""
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
        assert result['error']
        mock_redis.set.assert_called()

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


class TestFullPipelineBackground:
    """Test _run_full_pipeline_background_async async coordinator function."""

    @staticmethod
    def _get_bg_func_body():
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        return source[start:next_boundary]

    def test_background_calls_mark_job_processing(self):
        """Worker must transition job to processing status."""
        assert '_mark_job_processing_for_run, job_id' in self._get_bg_func_body()

    def test_background_calls_finalize_sync_job(self):
        """Worker must call finalize_sync_job with result."""
        body = self._get_bg_func_body()
        assert '_finalize_sync_job_for_run' in body and 'job_id' in body

    def test_background_uses_chunk_pattern(self):
        """Worker must batch segments in chunks of 5."""
        assert 'chunk_size = 5' in self._get_bg_func_body()

    def test_background_result_matches_v1_shape(self):
        """Worker result must include new_memories, updated_memories, failed_segments, total_segments, errors."""
        body = self._get_bg_func_body()
        for field in ['new_memories', 'updated_memories', 'failed_segments', 'total_segments', 'errors']:
            assert f"'{field}'" in body, f"Worker result must include {field}"

    def test_background_has_heartbeat(self):
        """Worker must heartbeat through the run-token-fenced updater."""
        body = self._get_bg_func_body()
        assert '_update_sync_job_for_run' in body, "Worker must fence its progress updates"

    def test_background_pipeline_order(self):
        """Worker must run: decode → VAD → fair-use → STT in correct order."""
        body = self._get_bg_func_body()
        decode_pos = body.index('decode_files_to_wav')
        vad_pos = body.index('_run_sync_vad_phase')
        speech_pos = body.index('record_speech_ms')
        segment_pos = body.index('process_segment')
        assert decode_pos < vad_pos < speech_pos < segment_pos

    def test_background_is_async_coordinator(self):
        """Background pipeline must be an async def, not a sync function (#7361)."""
        body = self._get_bg_func_body()
        assert body.startswith('async def'), "Pipeline must be async — coordinator runs on event loop"
        assert 'await run_blocking(' in body, "Async coordinator must offload blocking work to pools"
        assert '_get_sync_pipeline_semaphore' in body, "Async coordinator must use loop-scoped semaphore"

    def test_background_does_not_abandon_mutating_executor_workers(self):
        """Cancelling an executor Future must not let its thread outlive job finalization."""
        body = self._get_bg_func_body()
        vad_body = _get_pipeline_async_function_body('_run_sync_vad_phase')
        assert '_run_sync_vad_phase' in body
        assert 'asyncio.wait_for(run_blocking(sync_executor, _run_vad_bg' not in vad_body
        assert 'asyncio.wait_for(run_blocking(sync_executor, _process_one_segment' not in body
        assert 'run_blocking(sync_executor, _run_vad_bg' in vad_body
        assert 'run_blocking(sync_executor, _process_one_segment' in body


# ---------------------------------------------------------------------------
# 4. v1 regression tests — v1 must be completely unchanged
# ---------------------------------------------------------------------------


class TestV1Unchanged:
    """Verify v1 endpoint behavior is not modified by v2 addition."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path, encoding='utf-8') as f:
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
        with open(sync_path, encoding='utf-8') as f:
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

    def test_stale_just_over_threshold_self_heals(self):
        """A job one second past the stale bound is finalized to failed on read."""
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

    def test_stale_read_persists_failure(self):
        """The self-heal is durable — the failed status is written back, not just returned."""
        mod, mock_redis = self._load_sync_jobs_module()
        job = {
            'job_id': 'j',
            'uid': 'u',
            'status': 'processing',
            'updated_at': time.time() - 700,
        }
        mock_redis.get.return_value = json.dumps(job).encode()
        result = mod.get_sync_job('j')
        assert result['status'] == 'failed'
        mock_redis.set.assert_called()

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


class TestAsyncCoordinatorStructure:
    """Structural tests for _run_full_pipeline_background_async async coordinator (#7361).

    The function is now async and cannot be called from sync test context.
    These tests verify structure via source inspection.
    """

    @staticmethod
    def _get_bg_func_body():
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        return source[start:next_boundary]

    def test_async_coordinator_offloads_all_db_calls(self):
        """All DB calls must go through run_blocking(db_executor, ...)."""
        body = self._get_bg_func_body()
        assert '_mark_job_processing_for_run' in body and 'db_executor' in body
        assert '_finalize_sync_job_for_run' in body and 'db_executor' in body
        assert '_update_sync_job_for_run' in body

    def test_async_coordinator_offloads_decode(self):
        """Decode must be offloaded to sync_executor via run_blocking."""
        body = self._get_bg_func_body()
        assert 'run_blocking(sync_executor, decode_files_to_wav' in body

    def test_async_coordinator_offloads_vad(self):
        """VAD must be offloaded to sync_executor via run_blocking + asyncio.gather."""
        body = self._get_bg_func_body()
        vad_body = _get_pipeline_async_function_body('_run_sync_vad_phase')
        assert '_run_sync_vad_phase' in body
        assert 'run_blocking(sync_executor, _run_vad_bg' in vad_body
        assert 'asyncio.gather(*vad_tasks' in vad_body

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

    def test_async_coordinator_clears_byok_in_finally(self):
        """Async coordinator must clear BYOK keys in finally block."""
        body = self._get_bg_func_body()
        finally_idx = body.rindex('finally:')
        after_finally = body[finally_idx:]
        assert 'set_byok_keys({})' in after_finally
        assert 'set_byok_uid(None)' in after_finally

    def test_async_coordinator_sets_byok_uid_from_context(self):
        """Async coordinator must attach uid when inherited BYOK keys are present."""
        body = self._get_bg_func_body()
        setup_section = body[body.index('concurrency_gate =') : body.index('segmented_paths = set()')]
        assert 'set_byok_uid(uid if get_byok_keys() else None)' in setup_section

    def test_async_coordinator_rejects_empty_decode(self):
        """An admitted batch cannot infer silence from an empty decode result."""
        body = self._get_bg_func_body()
        assert 'if not wav_paths:' in body
        empty_section = body[body.index('if not wav_paths:') : body.index('Phase 2: VAD')]
        assert "error_code='sync_invalid_audio'" in empty_section
        assert 'TranscriptionOutcome.INVALID_INPUT' in empty_section

    def test_async_coordinator_chunks_segments(self):
        """Async coordinator must process segments in chunks of 5."""
        body = self._get_bg_func_body()
        assert 'chunk_size = 5' in body
        assert 'range(0, len(segment_list), chunk_size)' in body

    def test_async_coordinator_records_dg_usage_after_processing(self):
        """DG usage must be recorded after segment processing, not before."""
        body = self._get_bg_func_body()
        dg_pos = body.index('_record_restricted_sync_dg_usage')
        processing_pos = body.index('_process_one_segment')
        assert dg_pos > processing_pos
        assert 'record_dg_usage_ms' in _get_pipeline_async_function_body('_record_restricted_sync_dg_usage')

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
        assert '_load_sync_segment_context' in body
        assert 'build_person_embeddings_cache' in _get_pipeline_async_function_body('_load_sync_segment_context')

    def test_no_thread_pool_slot_held_for_coordinator(self):
        """Async coordinator must not submit itself to a thread pool slot."""
        body = self._get_bg_func_body()
        assert 'submit_with_context' not in body, "Async coordinator must not use submit_with_context"
        assert body.count('.result(') == 1, "Only the sync-worker fence callback may synchronously await a future"
        assert 'asyncio.run_coroutine_threadsafe(' in body


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

    def test_semaphore_delegates_to_http_client(self):
        """Semaphore must use http_client._get_semaphore (CLAUDE.md rule 4)."""
        source = _read_pipeline_source()
        assert '_get_sync_pipeline_semaphore(sync_lane)' in source, "Must use the lane-specific loop-scoped semaphore"
        assert '_get_semaphore' in source, "Must delegate to http_client._get_semaphore"

    def test_semaphore_limit_is_16(self):
        """Semaphore cap must be 16 (2x the old 8-slot postprocess_executor)."""
        source = _read_pipeline_source()
        start = source.index('def _get_sync_pipeline_semaphore')
        end = source.find('\ndef ', start + 1)
        if end == -1:
            end = source.find('\nasync def ', start + 1)
        func_body = source[start:end]
        assert "'sync_pipeline_fresh', 16" in func_body
        assert "'sync_pipeline_backfill'" in func_body

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
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\nasync def ', start + 1)
        if next_boundary == -1:
            next_boundary = source.find('\ndef ', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        return source[start:next_boundary]

    def test_decode_failure_returns_early(self):
        """Decode failure must return immediately, not fall through to VAD."""
        body = self._get_bg_func_body()
        decode_section = body[body.index('decode_files_to_wav') : body.index('Phase 2')]
        return_count = decode_section.count('return')
        assert return_count >= 2, "Decode failure paths must return early (HTTPException + generic)"

    # --- Empty decode ---

    def test_empty_decode_fails_as_invalid_input(self):
        """Empty wav_paths must not be acknowledged as expected silence."""
        body = self._get_bg_func_body()
        empty_check_idx = body.index('if not wav_paths:')
        vad_phase_idx = body.index('Phase 2: VAD')
        section = body[empty_check_idx:vad_phase_idx]
        assert "error_code='sync_invalid_audio'" in section
        assert 'TranscriptionOutcome.INVALID_INPUT' in section

    def test_empty_decode_does_not_run_vad(self):
        """Empty wav_paths must return before VAD phase."""
        body = self._get_bg_func_body()
        empty_check_idx = body.index('if not wav_paths:')
        vad_phase_idx = body.index('Phase 2: VAD')
        return_after_empty = body[empty_check_idx:vad_phase_idx]
        assert 'return' in return_after_empty

    # --- VAD errors ---

    def test_vad_workers_complete_before_cleanup(self):
        """Mutating VAD workers must finish before segmented paths are cleaned."""
        body = _get_pipeline_async_function_body('_run_sync_vad_phase')
        gather_idx = body.index('vad_results = await asyncio.gather')
        cleanup_idx = body.index('run_blocking(storage_executor, _cleanup_files, wav_paths)')
        assert gather_idx < cleanup_idx
        assert 'asyncio.wait_for(run_blocking(sync_executor, _run_vad_bg' not in body

    def test_vad_clears_segmented_paths_on_error(self):
        """On VAD failure, segmented_paths must be cleared after cleanup."""
        body = self._get_bg_func_body()
        vad_error_section = body[body.index('if vad_errors:') : body.index('Phase 3')]
        assert 'segmented_paths = set()' in vad_error_section

    # --- Zero segments after VAD ---

    def test_zero_segments_completes_not_fails(self):
        """Zero segments after VAD (all silence) must complete with 0 segments."""
        body = self._get_bg_func_body()
        zero_check_idx = body.index('if total_segments == 0:')
        fair_use_idx = body.index('FAIR_USE_ENABLED')
        section = body[zero_check_idx:fair_use_idx]
        assert 'finalize_sync_job' in section
        assert "'total_segments': 0" in section
        assert 'return' in section

    # --- DG budget ---

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

    def test_dg_usage_recorded_after_processing(self):
        """DG usage recording must happen after segment processing, not before."""
        body = self._get_bg_func_body()
        processing_end = body.index("stage_timings['stt_llm_ms']")
        record_dg_idx = body.index('_record_restricted_sync_dg_usage')
        assert record_dg_idx > processing_end
        assert 'record_dg_usage_ms' in _get_pipeline_async_function_body('_record_restricted_sync_dg_usage')

    # --- Partial / all segment failure ---

    def test_segment_workers_complete_before_reprocessing(self):
        """Mutating segment workers must finish before merged conversations are reprocessed."""
        body = self._get_bg_func_body()
        gather_idx = body.index('seg_results = await asyncio.gather')
        reprocess_idx = body.index('_reprocess_merged_conversations')
        assert gather_idx < reprocess_idx
        assert 'asyncio.wait_for(run_blocking(sync_executor, _process_one_segment' not in body

    def test_segment_errors_included_in_result(self):
        """segment_errors must be included in the final result sent to finalize_sync_job."""
        body = self._get_bg_func_body()
        result_section = body[body.index("# Build result") :]
        assert 'failed_segments' in result_section
        assert 'segment_errors' in result_section
        assert 'segment_errors[:10]' in result_section

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
        body = _get_pipeline_async_function_body('_load_sync_segment_context')
        assert 'except Exception' in body
        assert 'person_embeddings_cache = {}' in body

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
        process_segment_call = process_segment_section[:800]
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
    sys.modules['utils.observability'] = obs_pkg
    sys.modules['utils.observability.fallback'] = fallback_mod
    sys.modules['utils.observability.transcription'] = transcription_mod
    obs_pkg.fallback = fallback_mod
    obs_pkg.transcription = transcription_mod
    sys.modules['utils.metrics'] = MagicMock(OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL=MagicMock())
    return fallback_mod


class TestAsyncCoordinatorBehavioral:
    """Behavioral tests that invoke _run_full_pipeline_background_async with
    mocked dependencies. Verifies actual call sequences and outcomes."""

    @staticmethod
    def _load_sync_module():
        """Load routers/sync.py with all heavy deps stubbed, return (module, stubs)."""
        saved_modules = {}
        stubs = {}
        from database.sync_jobs import SyncLedgerFenceMode

        prior_utils = sys.modules.get('utils')
        prior_utils_sync = sys.modules.get('utils.sync')
        prior_utils_stt = sys.modules.get('utils.stt')
        prior_outcomes = sys.modules.get('utils.stt.outcomes')
        from utils.stt import outcomes as actual_outcomes

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
            'google.cloud.firestore_v1',
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
            'utils.observability.transcription',
            'utils.metrics',
            'utils.log_sanitizer',
            'utils.http_client',
            'utils.multipart',
            'utils.request_validation',
            'utils.sync.files',
            'utils.sync.playback',
            'utils.sync.backfill',
            'utils.sync.content_id',
            'utils.speaker_assignment',
            'utils.speaker_identification',
            'utils.stt.speaker_embedding',
            'python_multipart',
            'python_multipart.multipart',
        ]

        for mod_name in heavy_deps:
            saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()

        # Keep the outcome contract real; the coordinator tests exercise its
        # enum values while every heavyweight provider dependency stays stubbed.
        saved_modules['utils'] = prior_utils
        saved_modules['utils.sync'] = prior_utils_sync
        saved_modules['utils.stt'] = prior_utils_stt
        saved_modules['utils.stt.outcomes'] = prior_outcomes
        sys.modules['utils.stt.outcomes'] = actual_outcomes
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

        class _AudioPrecacheResponse(BaseModel):
            pass

        class _AudioUrlsResponse(BaseModel):
            pass

        sys.modules['models.sync_audio'].AudioPrecacheResponse = _AudioPrecacheResponse
        sys.modules['models.sync_audio'].AudioUrlsResponse = _AudioUrlsResponse
        sys.modules['utils.other.endpoints'].get_current_user_uid = MagicMock(return_value='test-uid')
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)

        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            'sync_behavioral',
            os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py'),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        pipeline_mod = sys.modules['utils.sync.pipeline']

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
        sys.modules.pop('utils.sync.pipeline', None)
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

    @pytest.mark.asyncio
    async def test_durable_completion_offloads_epoch_and_terminal_metric(self, fenced_worker_module):
        """Redis-backed fencing and telemetry never run on the async coordinator loop."""
        module, stubs = fenced_worker_module
        pipeline = stubs['pipeline']
        pipeline._cleanup_files = MagicMock()
        pipeline.bind_or_converge_sync_ledger_completion = MagicMock(
            return_value={'outcome': 'success', 'provider': 'deepgram', 'model': 'nova-3'}
        )
        offloads = []

        async def tracking_run_blocking(executor, fn, *args, **kwargs):
            offloads.append((executor, fn))
            return fn(*args, **kwargs)

        pipeline.run_blocking = tracking_run_blocking

        await module._run_full_pipeline_background_async(
            'job-durable-metric',
            'uid',
            [],
            'omi',
            False,
            '/tmp/job-durable-metric',
            task_mode=True,
            content_id='content-durable-metric',
            run_lock_token='1:owner-token',
        )

        def was_offloaded(fn):
            return any(executor is pipeline.db_executor and candidate is fn for executor, candidate in offloads)

        assert was_offloaded(pipeline.get_sync_job_run_lock_epoch)
        assert was_offloaded(pipeline._record_sync_job_outcome)
        pipeline.record_sync_transcription_outcome.assert_called_once()

    @pytest.mark.asyncio
    async def test_first_fenced_worker_mutation_stops_before_decode_or_cleanup(self, fenced_worker_module):
        """A stale run token cannot begin provider work or free retry material."""
        module, stubs = fenced_worker_module
        pipeline = stubs['pipeline']
        pipeline._cleanup_files = MagicMock()
        pipeline.release_sync_content_claim = MagicMock()
        stubs['sync_jobs'].fenced_mark_job_processing.return_value = types.SimpleNamespace(
            applied=False,
            outcome=types.SimpleNamespace(value='stale_owner'),
        )

        with pytest.raises(pipeline.SyncJobRunLeaseLost):
            await module._run_full_pipeline_background_async(
                'job-old',
                'uid',
                ['/tmp/input.opus'],
                'omi',
                False,
                '/tmp/job-old',
                task_mode=True,
                content_id='content-old',
                run_lock_token='owner-old',
            )

        stubs['sync_jobs'].fenced_mark_job_processing.assert_called_once_with('job-old', 'owner-old')
        pipeline.decode_files_to_wav.assert_not_called()
        pipeline.release_sync_content_claim.assert_not_called()
        pipeline._cleanup_files.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejected_terminal_fence_never_releases_content_claim(self):
        """A stale owner cannot turn an already-built result into a retry release."""
        module, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline.retrieve_vad_segments = MagicMock()
            pipeline._cleanup_files = MagicMock()
            pipeline.mark_sync_content_completed = MagicMock(return_value=True)
            pipeline.release_sync_content_claim = MagicMock()
            stubs['sync_jobs'].fenced_finalize_sync_job.return_value = types.SimpleNamespace(
                applied=False,
                outcome=types.SimpleNamespace(value='stale_owner'),
            )

            with pytest.raises(pipeline.SyncJobRunLeaseLost):
                await module._run_full_pipeline_background_async(
                    'job-old',
                    'uid',
                    ['/tmp/input.opus'],
                    'omi',
                    False,
                    '/tmp/job-old',
                    task_mode=True,
                    content_id='content-old',
                    run_lock_token='owner-old',
                )

            stubs['sync_jobs'].fenced_finalize_sync_job.assert_called_once()
            pipeline.release_sync_content_claim.assert_not_called()
            pipeline.release_sync_content_claim_after_job_retired.assert_not_called()
            pipeline.delete_sync_job_run_lock_epoch.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_lost_content_ledger_owner_stops_before_completed_job_publication(self):
        """A newer ledger owner cannot be acknowledged by an old worker's Redis result."""
        module, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline.retrieve_vad_segments = MagicMock()
            pipeline._cleanup_files = MagicMock()
            pipeline.mark_sync_content_completed = MagicMock(return_value=False)
            pipeline.release_sync_content_claim = MagicMock()

            with pytest.raises(pipeline.SyncJobRunLeaseLost):
                await module._run_full_pipeline_background_async(
                    'job-old',
                    'uid',
                    ['/tmp/input.opus'],
                    'omi',
                    False,
                    '/tmp/job-old',
                    task_mode=True,
                    content_id='content-old',
                    run_lock_token='owner-old',
                )

            stubs['sync_jobs'].fenced_finalize_sync_job.assert_not_called()
            pipeline.release_sync_content_claim.assert_not_called()
            pipeline.release_sync_content_claim_after_job_retired.assert_not_called()
            pipeline.delete_sync_job_run_lock_epoch.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_inline_lease_renews_until_the_coordinator_stops(self):
        """A healthy inline run refreshes its token rather than job-state timestamps."""
        _, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.RUN_LOCK_HEARTBEAT_SECONDS = 0.001
            pipeline.renew_job_run_lock = MagicMock(return_value=True)
            stop_event = asyncio.Event()
            lease_lost_event = asyncio.Event()

            lease_task = asyncio.create_task(
                pipeline._maintain_inline_run_lease('job-lease', 'token-lease', stop_event, lease_lost_event, None)
            )
            for _ in range(20):
                if pipeline.renew_job_run_lock.called:
                    break
                await asyncio.sleep(0.005)
            stop_event.set()
            await lease_task

            pipeline.renew_job_run_lock.assert_called_with('job-lease', 'token-lease')
            assert not lease_lost_event.is_set()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_inline_lease_loss_marks_event_and_cancels_owner(self):
        """Token loss is a coordinator cancellation, never a normal completion."""
        _, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.RUN_LOCK_HEARTBEAT_SECONDS = 0.001
            pipeline.renew_job_run_lock = MagicMock(return_value=False)
            stop_event = asyncio.Event()
            lease_lost_event = asyncio.Event()
            owner_task = MagicMock()

            await pipeline._maintain_inline_run_lease(
                'job-lease', 'stale-token', stop_event, lease_lost_event, owner_task
            )

            assert lease_lost_event.is_set()
            owner_task.cancel.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_inline_lease_renew_errors_fail_closed_before_token_expiry(self):
        """Redis renewal errors cannot keep an inline owner alive past its lease."""
        _, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.RUN_LOCK_HEARTBEAT_SECONDS = 0.001
            pipeline.RUN_LOCK_TTL_SECONDS = 0.006
            pipeline.RUN_LOCK_RENEWAL_SAFETY_SECONDS = 0.001
            # Drive the lease deadline explicitly. A 6 ms wall-clock window can
            # legitimately expire after one scheduler turn on a busy CI worker,
            # even though the retry behavior under test is correct.
            pipeline.time = types.SimpleNamespace(
                monotonic=MagicMock(side_effect=[0.0, 0.0, 0.001, 0.001, 0.002, 0.006])
            )
            pipeline.renew_job_run_lock = MagicMock(side_effect=ConnectionError('redis unavailable'))
            stop_event = asyncio.Event()
            lease_lost_event = asyncio.Event()
            owner_task = MagicMock()

            await pipeline._maintain_inline_run_lease(
                'job-lease', 'token-lease', stop_event, lease_lost_event, owner_task
            )

            assert pipeline.renew_job_run_lock.call_count >= 2
            assert lease_lost_event.is_set()
            owner_task.cancel.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_inline_lease_renew_timeout_fails_closed_before_token_expiry(self):
        """A hung Redis executor cannot silently outlive the last known-good token."""
        _, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.RUN_LOCK_HEARTBEAT_SECONDS = 0.001
            pipeline.RUN_LOCK_TTL_SECONDS = 0.006
            pipeline.RUN_LOCK_RENEWAL_SAFETY_SECONDS = 0.001
            renewal_started = asyncio.Event()

            async def _hanging_run_blocking(_executor, _fn, *_args, **_kwargs):
                renewal_started.set()
                await asyncio.Event().wait()

            pipeline.run_blocking = _hanging_run_blocking
            stop_event = asyncio.Event()
            lease_lost_event = asyncio.Event()
            owner_task = MagicMock()

            await pipeline._maintain_inline_run_lease(
                'job-lease', 'token-lease', stop_event, lease_lost_event, owner_task
            )

            assert renewal_started.is_set()
            assert lease_lost_event.is_set()
            owner_task.cancel.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_inline_lease_renews_while_waiting_for_pipeline_capacity(self):
        """A saturated semaphore cannot let an already-owned token expire."""
        module, stubs = self._load_sync_module()
        gate = asyncio.Semaphore(1)
        await gate.acquire()
        lease_tasks = []
        try:
            pipeline = stubs['pipeline']
            pipeline._get_sync_pipeline_semaphore = lambda _lane: gate
            pipeline.RUN_LOCK_HEARTBEAT_SECONDS = 0.001
            pipeline.renew_job_run_lock = MagicMock(return_value=True)
            pipeline._cleanup_files = MagicMock()
            pipeline.release_sync_content_claim = MagicMock()
            pipeline.release_job_run_lock = MagicMock()

            def _start_task(coro, *, name):
                task = asyncio.create_task(coro, name=name)
                lease_tasks.append(task)
                return task

            pipeline.start_background_task = _start_task
            coordinator = asyncio.create_task(
                module._run_full_pipeline_background_async(
                    'job-wait',
                    'uid',
                    ['/tmp/file.opus'],
                    'omi',
                    False,
                    '/tmp/job-wait',
                    content_id='content-wait',
                    inline_run_lock_token='token-wait',
                )
            )
            for _ in range(20):
                if pipeline.renew_job_run_lock.called:
                    break
                await asyncio.sleep(0.005)

            pipeline.renew_job_run_lock.assert_called_with('job-wait', 'token-wait')
            assert not coordinator.done()

            coordinator.cancel()
            with pytest.raises(asyncio.CancelledError):
                await coordinator
            await asyncio.gather(*lease_tasks, return_exceptions=True)

            pipeline._cleanup_files.assert_not_called()
            pipeline.release_sync_content_claim.assert_not_called()
            pipeline.release_job_run_lock.assert_not_called()
        finally:
            gate.release()
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_inline_renew_errors_cancel_before_capacity_admission_without_releasing_retry_material(self):
        """A broken Redis lease aborts queued inline work before its token expires."""
        module, stubs = self._load_sync_module()
        gate = asyncio.Semaphore(1)
        await gate.acquire()
        lease_tasks = []
        try:
            pipeline = stubs['pipeline']
            pipeline._get_sync_pipeline_semaphore = lambda _lane: gate
            pipeline.RUN_LOCK_HEARTBEAT_SECONDS = 0.001
            pipeline.RUN_LOCK_TTL_SECONDS = 0.006
            pipeline.RUN_LOCK_RENEWAL_SAFETY_SECONDS = 0.001
            pipeline.renew_job_run_lock = MagicMock(side_effect=ConnectionError('redis unavailable'))
            pipeline._cleanup_files = MagicMock()
            pipeline.release_sync_content_claim = MagicMock()
            pipeline.release_job_run_lock = MagicMock()

            def _start_task(coro, *, name):
                task = asyncio.create_task(coro, name=name)
                lease_tasks.append(task)
                return task

            pipeline.start_background_task = _start_task
            coordinator = asyncio.create_task(
                module._run_full_pipeline_background_async(
                    'job-renew-error',
                    'uid',
                    ['/tmp/file.opus'],
                    'omi',
                    False,
                    '/tmp/job-renew-error',
                    content_id='content-renew-error',
                    inline_run_lock_token='token-renew-error',
                )
            )

            with pytest.raises(asyncio.CancelledError):
                await coordinator
            await asyncio.gather(*lease_tasks, return_exceptions=True)

            assert pipeline.renew_job_run_lock.call_count >= 2
            pipeline._cleanup_files.assert_not_called()
            pipeline.release_sync_content_claim.assert_not_called()
            pipeline.release_job_run_lock.assert_not_called()
        finally:
            gate.release()
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_lost_inline_lease_during_teardown_preserves_retry_material(self):
        """A lease loss racing normal teardown cannot be swallowed into cleanup."""
        module, stubs = self._load_sync_module()
        lease_tasks = []
        cleanup_calls_at_loss = []
        try:
            pipeline = stubs['pipeline']
            pipeline._get_sync_pipeline_semaphore = lambda _lane: asyncio.Semaphore(1)
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline.retrieve_vad_segments = MagicMock()
            pipeline.get_wav_duration = MagicMock(return_value=0.0)
            pipeline._cleanup_files = MagicMock()
            pipeline.release_sync_content_claim = MagicMock()
            pipeline.release_job_run_lock = MagicMock()

            async def _lose_when_teardown_starts(_job_id, _token, stop_event, lease_lost_event, owner_task):
                await stop_event.wait()
                # Raw and decoded intermediates are intentionally consumed by
                # earlier successful phases. The invariant here is that the
                # *teardown* adds no cleanup after the ownership loss.
                cleanup_calls_at_loss.append(pipeline._cleanup_files.call_count)
                lease_lost_event.set()
                owner_task.cancel()

            def _start_task(coro, *, name):
                task = asyncio.create_task(coro, name=name)
                lease_tasks.append(task)
                return task

            pipeline._maintain_inline_run_lease = _lose_when_teardown_starts
            pipeline.start_background_task = _start_task

            with pytest.raises(asyncio.CancelledError):
                await module._run_full_pipeline_background_async(
                    'job-teardown',
                    'uid',
                    ['/tmp/file.opus'],
                    'omi',
                    False,
                    '/tmp/job-teardown',
                    content_id='content-teardown',
                    inline_run_lock_token='token-teardown',
                )
            await asyncio.gather(*lease_tasks, return_exceptions=True)

            assert pipeline._cleanup_files.call_count == cleanup_calls_at_loss[0]
            pipeline.release_sync_content_claim.assert_not_called()
            pipeline.release_job_run_lock.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_cancellation_during_decode_keeps_raw_retry_material(self):
        """Cancelling a coordinator cannot delete input a decoder leaf may still read."""
        module, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline._get_sync_pipeline_semaphore = lambda _lane: asyncio.Semaphore(1)
            pipeline._cleanup_files = MagicMock()
            pipeline.release_sync_content_claim = MagicMock()
            pipeline.release_job_run_lock = MagicMock()
            decode_started = asyncio.Event()

            async def _run_blocking_with_hung_decode(_executor, fn, *args, **kwargs):
                if fn is pipeline.decode_files_to_wav:
                    decode_started.set()
                    await asyncio.Event().wait()
                return fn(*args, **kwargs)

            pipeline.run_blocking = _run_blocking_with_hung_decode
            coordinator = asyncio.create_task(
                module._run_full_pipeline_background_async(
                    'job-decode-cancel',
                    'uid',
                    ['/tmp/raw-retry.opus'],
                    'omi',
                    False,
                    '/tmp/job-decode-cancel',
                    content_id='content-decode-cancel',
                )
            )
            await decode_started.wait()

            coordinator.cancel()
            with pytest.raises(asyncio.CancelledError):
                await coordinator

            pipeline._cleanup_files.assert_not_called()
            pipeline.release_sync_content_claim.assert_not_called()
            pipeline.release_job_run_lock.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_cancellation_during_vad_keeps_inflight_audio_and_retry_material(self):
        """A cancelled coordinator cannot clean audio still owned by a VAD worker."""
        module, stubs = self._load_sync_module()
        release_vad = threading.Event()
        vad_finished = threading.Event()
        vad_started = asyncio.Event()
        vad_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='test-vad-cancel')
        try:
            pipeline = stubs['pipeline']
            raw_path = '/tmp/raw-vad-retry.opus'
            wav_path = '/tmp/vad-inflight.wav'
            segment_path = '/tmp/vad-inflight-segment.wav'
            pipeline._get_sync_pipeline_semaphore = lambda _lane: asyncio.Semaphore(1)
            pipeline.decode_files_to_wav = MagicMock(return_value=[wav_path])
            pipeline._cleanup_files = MagicMock()
            pipeline._finalize_sync_job_failure = AsyncMock()
            pipeline._finalize_sync_job_for_run = MagicMock()
            pipeline.release_sync_content_claim = MagicMock()
            pipeline.release_sync_content_claim_after_job_retired = MagicMock()
            loop = asyncio.get_running_loop()

            def _blocking_vad(_path, segmented_paths, _errors):
                segmented_paths.add(segment_path)
                loop.call_soon_threadsafe(vad_started.set)
                assert release_vad.wait(timeout=2)
                vad_finished.set()

            async def _routing_run_blocking(executor, fn, *args, **kwargs):
                if executor is pipeline.sync_executor:
                    return await _production_run_blocking(vad_worker, fn, *args, **kwargs)
                return fn(*args, **kwargs)

            pipeline.retrieve_vad_segments = _blocking_vad
            pipeline.run_blocking = _routing_run_blocking
            with patch.object(pipeline.os.path, 'isdir', return_value=True), patch.object(
                pipeline.shutil, 'rmtree'
            ) as rmtree:
                coordinator = asyncio.create_task(
                    module._run_full_pipeline_background_async(
                        'job-vad-cancel',
                        'uid',
                        [raw_path],
                        'omi',
                        False,
                        '/tmp/job-vad-cancel',
                        content_id='content-vad-cancel',
                    )
                )
                await asyncio.wait_for(vad_started.wait(), timeout=1)

                coordinator.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await coordinator

                # Decode already consumed the raw input. Cancellation while VAD
                # is still mutating must not also clean its WAV/segment inputs.
                assert pipeline._cleanup_files.call_count == 1
                assert pipeline._cleanup_files.call_args.args[0] == [raw_path]
                rmtree.assert_not_called()
                pipeline._finalize_sync_job_failure.assert_not_awaited()
                pipeline._finalize_sync_job_for_run.assert_not_called()
                pipeline.release_sync_content_claim.assert_not_called()
                pipeline.release_sync_content_claim_after_job_retired.assert_not_called()

                release_vad.set()
                await asyncio.wait_for(asyncio.to_thread(vad_finished.wait), timeout=1)
                assert vad_finished.is_set()
        finally:
            release_vad.set()
            await asyncio.to_thread(vad_worker.shutdown, wait=True)
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_decode_http_exception_marks_failed(self):
        """Decode raising HTTPException must mark job failed."""
        from fastapi import HTTPException as _HTTPException

        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(
                side_effect=_HTTPException(status_code=400, detail='bad format')
            )
            stubs['pipeline']._cleanup_files = MagicMock()

            await module._run_full_pipeline_background_async('j1', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job1')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert args[0] == 'j1'
            assert args[1] == 'sync_invalid_audio'
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_decode_generic_exception_marks_failed(self):
        """Decode raising generic Exception must mark job failed."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(side_effect=RuntimeError('corrupt file'))
            stubs['pipeline']._cleanup_files = MagicMock()

            await module._run_full_pipeline_background_async('j2', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job2')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert args[1] == 'sync_decode_failed'
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_empty_decode_marks_failed_and_releases_retry_claim(self):
        """Empty decoder output is invalid input, not authoritative silence."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=[])
            stubs['pipeline']._cleanup_files = MagicMock()
            stubs['pipeline'].get_sync_job = MagicMock(return_value={'status': 'failed'})

            await module._run_full_pipeline_background_async(
                'j3', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job3', content_id='content-3'
            )

            stubs['sync_jobs'].mark_job_failed.assert_called_once()
            assert stubs['sync_jobs'].mark_job_failed.call_args.args[1] == 'sync_invalid_audio'
            stubs['pipeline'].release_sync_content_claim.assert_called_once_with('uid', 'content-3', 'j3')
            stubs['pipeline'].release_sync_content_claim_after_job_retired.assert_not_called()
            stubs['sync_jobs'].finalize_sync_job.assert_not_called()
            stubs['pipeline'].mark_sync_content_completed.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_vad_errors_mark_failed(self):
        """VAD errors must mark job failed and clean up."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _bad_vad(path, segmented_paths, errors):
                errors.append(f'{path}: silero exploded')

            stubs['pipeline'].retrieve_vad_segments = _bad_vad

            await module._run_full_pipeline_background_async('j4', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job4')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert args[1] == 'sync_vad_failed'
            assert stubs['pipeline']._cleanup_files.call_count >= 2
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_zero_segments_after_vad_completes(self):
        """Zero segmented_paths after VAD must complete with 0 segments."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()
            stubs['pipeline'].retrieve_vad_segments = MagicMock()
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=0.0)

            await module._run_full_pipeline_background_async(
                'j5', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job5', content_id='content-5'
            )

            stubs['sync_jobs'].finalize_sync_job.assert_called_once()
            result = stubs['sync_jobs'].finalize_sync_job.call_args[0][1]
            assert result['total_segments'] == 0
            assert result['outcome'] == 'expected_silence'
            stubs['pipeline'].mark_sync_content_completed.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_provider_empty_after_vad_releases_content_for_retry(self):
        """VAD-positive empty STT must fail and leave the content ledger retryable."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_one_segment(_path, segmented_paths, _errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_one_segment
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=False)
            stubs['pipeline'].users_db.get_data_protection_level = MagicMock(return_value=None)
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline'].get_prerecorded_service = MagicMock(return_value=('deepgram', 'multi', 'nova-3'))
            stubs['pipeline'].prerecorded = MagicMock(return_value=([], 'en'))
            terminal_events = []
            stubs['pipeline'].release_sync_content_claim_after_job_retired.side_effect = (
                lambda *_args: terminal_events.append('claim_released')
            )
            stubs['sync_jobs'].finalize_sync_job.side_effect = lambda *_args: (
                terminal_events.append('job_finalized') or {'status': 'partial_failure'}
            )

            await module._run_full_pipeline_background_async(
                'j-empty',
                'uid',
                ['/tmp/f.opus'],
                'omi',
                False,
                '/tmp/job-empty',
                content_id='content-empty',
            )

            result = stubs['sync_jobs'].finalize_sync_job.call_args[0][1]
            assert result['failed_segments'] == 1
            assert result['errors'] == ['stt_empty_unexpected']
            assert result['outcome'] == 'empty_unexpected'
            stubs['pipeline'].mark_sync_content_completed.assert_not_called()
            stubs['pipeline'].release_sync_content_claim_after_job_retired.assert_called_once_with(
                'uid', 'content-empty', 'j-empty'
            )
            stubs['pipeline'].release_sync_content_claim.assert_not_called()
            assert terminal_events[:2] == ['job_finalized', 'claim_released']
            stubs['sync_jobs'].add_processed_segment.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_tokenized_partial_terminal_releases_retired_claim_before_deleting_epoch(self):
        """A winning terminal fence orders retry release and epoch retirement after Redis publication."""
        module, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline._cleanup_files = MagicMock()
            pipeline.get_wav_duration = MagicMock(return_value=5.0)
            pipeline.get_processed_sync_segment_ids = MagicMock(return_value=set())
            pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            pipeline.users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=False)
            pipeline.users_db.get_data_protection_level = MagicMock(return_value=None)
            pipeline.build_person_embeddings_cache = MagicMock(return_value={})
            pipeline.get_prerecorded_service = MagicMock(return_value=('deepgram', 'multi', 'nova-3'))

            def _one_speech_segment(_path, segmented_paths, _errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            def _failed_segment(_path, _uid, _response, lock, errors, *_args, **_kwargs):
                with lock:
                    errors.append('stt_empty_unexpected')
                return False

            pipeline.retrieve_vad_segments = _one_speech_segment
            pipeline.process_segment = _failed_segment
            terminal_events = []
            pipeline.fenced_finalize_sync_job = MagicMock(
                side_effect=lambda *_args, **_kwargs: (
                    terminal_events.append('fenced_terminal')
                    or types.SimpleNamespace(applied=True, job={'status': 'partial_failure'})
                )
            )
            pipeline.release_sync_content_claim_after_job_retired = MagicMock(
                side_effect=lambda *_args: terminal_events.append('retired_release')
            )
            pipeline.delete_sync_job_run_lock_epoch = MagicMock(
                side_effect=lambda *_args: terminal_events.append('epoch_delete')
            )

            await module._run_full_pipeline_background_async(
                'job-tokenized',
                'uid',
                ['/tmp/f.opus'],
                'omi',
                False,
                '/tmp/job-tokenized',
                task_mode=True,
                content_id='content-tokenized',
                run_lock_token='1:owner-token',
                content_run_bound=True,
                ledger_fence_active=True,
            )

            pipeline.fenced_finalize_sync_job.assert_called_once()
            pipeline.release_sync_content_claim_after_job_retired.assert_called_once_with(
                'uid', 'content-tokenized', 'job-tokenized'
            )
            pipeline.delete_sync_job_run_lock_epoch.assert_called_once_with('job-tokenized')
            pipeline.release_sync_content_claim.assert_not_called()
            assert terminal_events == ['fenced_terminal', 'retired_release', 'epoch_delete']
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_success_metric_waits_for_durable_segment_checkpoint(self):
        """A checkpoint failure must not advertise a successful transcription."""
        module, stubs = self._load_sync_module()
        try:
            segmented_path = '/tmp/seg_1700000001.wav'
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()
            stubs['pipeline'].retrieve_vad_segments = lambda _path, paths, _errors: paths.add(segmented_path)
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=False)
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline'].get_sync_content_partial_result = MagicMock(return_value={})
            stubs['pipeline'].get_processed_sync_segment_ids = MagicMock(return_value=set())
            stubs['pipeline'].compute_sync_segment_id = MagicMock(return_value='segment-1')
            stubs['pipeline'].process_segment = MagicMock(return_value=True)
            stubs['pipeline'].checkpoint_sync_content_partial_result.side_effect = RuntimeError('ledger unavailable')

            await module._run_full_pipeline_background_async(
                'checkpoint-job',
                'uid',
                ['/tmp/f.opus'],
                'omi',
                False,
                '/tmp/checkpoint-job',
                content_id='content-checkpoint',
            )

            segment_outcomes = [
                call.kwargs['outcome']
                for call in stubs['pipeline'].record_sync_transcription_outcome.call_args_list
                if call.kwargs['kind'] == 'segment'
            ]
            assert 'success' not in segment_outcomes
            assert segment_outcomes == ['upstream_error']
            stubs['pipeline'].add_processed_sync_segment_id.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_content_completion_failure_cannot_publish_completed_job(self):
        """A durable-ledger failure must retry before the client sees completed."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()
            stubs['pipeline'].retrieve_vad_segments = MagicMock()
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=0.0)
            stubs['pipeline'].mark_sync_content_completed.side_effect = RuntimeError('ledger unavailable')

            with pytest.raises(RuntimeError, match='ledger unavailable'):
                await module._run_full_pipeline_background_async(
                    'j-ledger',
                    'uid',
                    ['/tmp/f.opus'],
                    'omi',
                    False,
                    '/tmp/job-ledger',
                    task_mode=True,
                    content_id='content-ledger',
                )

            stubs['sync_jobs'].finalize_sync_job.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_dg_budget_exhausted_marks_failed(self):
        """DG budget exhausted must mark job failed."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_with_segments(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_with_segments
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].FAIR_USE_ENABLED = True
            stubs['pipeline'].FAIR_USE_RESTRICT_DAILY_DG_MS = 1000
            stubs['pipeline'].get_enforcement_stage = MagicMock(return_value='restrict')
            stubs['pipeline'].is_dg_budget_exhausted = MagicMock(return_value=True)
            module.record_speech_ms = MagicMock()
            module.get_rolling_speech_ms = MagicMock(return_value={})
            module.check_soft_caps = MagicMock(return_value=[])

            await module._run_full_pipeline_background_async('j6', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job6')

            stubs['sync_jobs'].mark_job_failed.assert_called()
            args = stubs['sync_jobs'].mark_job_failed.call_args[0]
            assert args[1] == 'sync_transcription_budget_exhausted'
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_dg_budget_not_exhausted_continues(self):
        """DG budget NOT exhausted must continue to segment processing."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_with_segments(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_with_segments
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].FAIR_USE_ENABLED = True
            stubs['pipeline'].FAIR_USE_RESTRICT_DAILY_DG_MS = 1000
            stubs['pipeline'].get_enforcement_stage = MagicMock(return_value='restrict')
            stubs['pipeline'].is_dg_budget_exhausted = MagicMock(return_value=False)
            stubs['pipeline'].record_speech_ms = MagicMock()
            stubs['pipeline'].get_rolling_speech_ms = MagicMock(return_value={})
            stubs['pipeline'].check_soft_caps = MagicMock(return_value=[])
            stubs['pipeline'].users_db = MagicMock()
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline'].process_segment = MagicMock()
            stubs['pipeline'].record_dg_usage_ms = MagicMock()
            stubs['pipeline'].record_usage = MagicMock()

            await module._run_full_pipeline_background_async('j7', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job7')

            stubs['sync_jobs'].finalize_sync_job.assert_called_once()
            stubs['pipeline'].process_segment.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ('subscription', 'expected_plan', 'lookup_error'),
        [
            (types.SimpleNamespace(plan=PlanType.unlimited_v2), PlanType.unlimited_v2, None),
            (types.SimpleNamespace(plan=PlanType.basic), PlanType.basic, None),
            (None, None, None),
            (None, None, RuntimeError('subscription store unavailable')),
        ],
        ids=['unlimited', 'basic', 'missing-subscription', 'subscription-read-failure'],
    )
    async def test_fresh_soft_caps_use_the_current_subscription_plan(self, subscription, expected_plan, lookup_error):
        """Queued fresh work applies the persisted plan instead of the default cap tier."""
        module, stubs = self._load_sync_module()
        try:
            pipeline = stubs['pipeline']
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline._cleanup_files = MagicMock()

            def _vad_with_segments(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            speech_totals = {'daily_ms': 5_000, 'three_day_ms': 5_000, 'weekly_ms': 5_000}
            pipeline.retrieve_vad_segments = _vad_with_segments
            pipeline.get_wav_duration = MagicMock(return_value=5.0)
            pipeline.FAIR_USE_ENABLED = True
            pipeline.FAIR_USE_RESTRICT_DAILY_DG_MS = 0
            pipeline.record_speech_ms = MagicMock()
            pipeline.get_rolling_speech_ms = MagicMock(return_value=speech_totals)
            pipeline.check_soft_caps = MagicMock(return_value=[])
            pipeline.users_db = MagicMock()
            pipeline.users_db.get_existing_user_subscription = MagicMock(return_value=subscription)
            if lookup_error:
                pipeline.users_db.get_existing_user_subscription.side_effect = lookup_error
            pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            pipeline.users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=False)
            pipeline.users_db.get_data_protection_level = MagicMock(return_value=None)
            pipeline.build_person_embeddings_cache = MagicMock(return_value={})
            pipeline.process_segment = MagicMock()
            pipeline.record_dg_usage_ms = MagicMock()
            pipeline.record_usage = MagicMock()

            await module._run_full_pipeline_background_async('j-plan', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job')

            pipeline.users_db.get_existing_user_subscription.assert_called_once_with('uid')
            pipeline.check_soft_caps.assert_called_once_with('uid', speech_totals=speech_totals, plan=expected_plan)
            stubs['sync_jobs'].finalize_sync_job.assert_called_once()
            if lookup_error:
                pipeline.record_fallback.assert_called_once_with(
                    component='other',
                    from_mode='subscription_plan',
                    to_mode='default_cap',
                    reason='policy',
                    outcome='degraded',
                    log=pipeline.logger,
                )
            else:
                pipeline.record_fallback.assert_not_called()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_partial_segment_failure_completes(self):
        """Partial segment failure must complete (not fail) with error count."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_two_segments(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')
                segmented_paths.add('/tmp/seg_1700000002.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_two_segments
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db = MagicMock()
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=False)
            stubs['pipeline'].users_db.get_data_protection_level = MagicMock(return_value=None)
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline']._reprocess_merged_conversations = MagicMock()
            stubs['pipeline'].record_usage = MagicMock()
            stubs['pipeline'].get_timestamp_from_path = MagicMock(
                side_effect=lambda p: int(p.split('_')[-1].split('.')[0])
            )
            call_count = [0]

            def _process_seg_fails_once(path, uid, response, lock, errors, *args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    errors.append('stt_timeout')
                else:
                    response['new_memories'].add('mem1')

            stubs['pipeline'].process_segment = _process_seg_fails_once

            await module._run_full_pipeline_background_async('j8', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job8')

            stubs['sync_jobs'].finalize_sync_job.assert_called_once()
            result = stubs['sync_jobs'].finalize_sync_job.call_args[0][1]
            assert result['failed_segments'] == 1
            assert result['total_segments'] == 2
            assert result['outcome'] == 'timeout'
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_generic_segment_task_exception_counts_as_failed_segment(self):
        """A task-level segment exception must not complete with failed_segments=0."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_one_segment(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_one_segment
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db = MagicMock()
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=False)
            stubs['pipeline'].users_db.get_data_protection_level = MagicMock(return_value=None)
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            module._reprocess_merged_conversations = MagicMock()
            stubs['pipeline'].record_usage = MagicMock()
            module.get_timestamp_from_path = MagicMock(return_value=1700000001)
            module.sanitize = lambda value: value
            stubs['pipeline'].process_segment = MagicMock(side_effect=RuntimeError('executor exploded'))

            await module._run_full_pipeline_background_async(
                'j-generic-segment-error', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-generic'
            )

            stubs['sync_jobs'].finalize_sync_job.assert_called_once()
            result = stubs['sync_jobs'].finalize_sync_job.call_args[0][1]
            assert result['failed_segments'] == 1
            assert result['total_segments'] == 1
            assert result['errors'] == ['stt_upstream_error']
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_retry_skips_segment_already_committed_by_prior_attempt(self):
        """Cloud Tasks retry must not re-transcribe a segment with a durable job marker."""
        module, stubs = self._load_sync_module()
        try:
            segment_path = '/tmp/seg_1700000001.wav'
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_one_segment(_path, segmented_paths, _errors):
                segmented_paths.add(segment_path)

            stubs['pipeline'].retrieve_vad_segments = _vad_one_segment
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=False)
            stubs['pipeline'].users_db.get_data_protection_level = MagicMock(return_value=None)
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline'].process_segment = MagicMock()
            stubs['sync_jobs'].get_processed_segments.return_value = {segment_path}

            await module._run_full_pipeline_background_async(
                'j-retry',
                'uid',
                ['/tmp/f.opus'],
                'omi',
                False,
                '/tmp/job-retry',
                task_mode=True,
            )

            stubs['pipeline'].process_segment.assert_not_called()
            result = stubs['sync_jobs'].finalize_sync_job.call_args[0][1]
            assert result['failed_segments'] == 0
            assert result['total_segments'] == 1
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_retry_hydration_excludes_durably_fenced_conversation_from_audio_finalization(self):
        """A fence recorded before a retry cannot let its stale checkpoint finalize audio."""
        module, stubs = self._load_sync_module()
        try:
            segment_path = '/tmp/seg_1700000001.wav'
            pipeline = stubs['pipeline']
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline._cleanup_files = MagicMock()
            pipeline.retrieve_vad_segments = lambda _path, paths, _errors: paths.add(segment_path)
            pipeline.get_wav_duration = MagicMock(return_value=5.0)
            pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            pipeline.users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=True)
            pipeline.users_db.get_data_protection_level = MagicMock(return_value=None)
            pipeline.build_person_embeddings_cache = MagicMock(return_value={})
            pipeline.get_sync_job = MagicMock(
                return_value={
                    'partial_result': {
                        'updated_memories': ['fenced-conversation', 'current-conversation'],
                        'new_memories': ['fenced-conversation'],
                    }
                }
            )
            pipeline.get_sync_content_partial_result = MagicMock(
                return_value={'fenced_conversation_ids': ['fenced-conversation']}
            )
            pipeline.get_processed_sync_segment_ids = MagicMock(return_value={'segment-1'})
            pipeline.compute_sync_segment_id = MagicMock(return_value='segment-1')
            pipeline.process_segment = MagicMock()
            pipeline._reprocess_merged_conversations = MagicMock()
            pipeline._finalize_sync_audio_files = MagicMock()

            await module._run_full_pipeline_background_async(
                'job-retry-fenced',
                'uid',
                ['/tmp/f.opus'],
                'omi',
                False,
                '/tmp/job-retry-fenced',
                task_mode=True,
                content_id='content-retry-fenced',
                content_run_bound=True,
                ledger_fence_active=False,
            )

            pipeline.process_segment.assert_not_called()
            pipeline._finalize_sync_audio_files.assert_called_once()
            finalized_response = pipeline._finalize_sync_audio_files.call_args.args[1]
            assert finalized_response['updated_memories'] == {'current-conversation'}
            assert 'fenced-conversation' not in finalized_response['updated_memories']
            assert 'fenced-conversation' not in finalized_response['new_memories']
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_fence_checkpoint_handoffs_to_db_executor_before_audio_finalization(self):
        """A sync-worker fence persists ledger then job state through the coordinator loop."""
        module, stubs = self._load_sync_module()
        sync_worker = ThreadPoolExecutor(max_workers=1)
        try:
            segment_path = '/tmp/seg_1700000001.wav'
            pipeline = stubs['pipeline']
            checkpoint_events = []
            db_offload_calls = []
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline._cleanup_files = MagicMock()
            pipeline.retrieve_vad_segments = lambda _path, paths, _errors: paths.add(segment_path)
            pipeline.get_wav_duration = MagicMock(return_value=5.0)
            pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            pipeline.users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=True)
            pipeline.users_db.get_data_protection_level = MagicMock(return_value=None)
            pipeline.build_person_embeddings_cache = MagicMock(return_value={})
            pipeline.get_sync_job = MagicMock(return_value={'partial_result': {}})
            pipeline.get_sync_content_partial_result = MagicMock(return_value={})
            pipeline.get_processed_sync_segment_ids = MagicMock(return_value=set())
            pipeline.compute_sync_segment_id = MagicMock(return_value='segment-1')
            pipeline.process_segment = MagicMock(return_value=False)
            pipeline.checkpoint_sync_content_partial_result = MagicMock(
                side_effect=lambda *_args, **_kwargs: checkpoint_events.append('durable') or True
            )

            def _record_job_partial(*args):
                if 'partial_result' in args[2]:
                    checkpoint_events.append('job')

            pipeline._update_sync_job_for_run = MagicMock(side_effect=_record_job_partial)

            def _fence_in_sync_worker(_uid, response, on_fenced):
                response['_fenced_conversation_ids'].add('fenced-conversation')
                on_fenced()

            pipeline._reprocess_merged_conversations = _fence_in_sync_worker
            pipeline._finalize_sync_audio_files = MagicMock()

            async def _threaded_run_blocking(executor, fn, *args, **kwargs):
                if executor is pipeline.sync_executor:
                    return await _production_run_blocking(sync_worker, fn, *args, **kwargs)
                if executor is pipeline.db_executor and (
                    fn is pipeline.checkpoint_sync_content_partial_result
                    or (fn is pipeline._update_sync_job_for_run and 'partial_result' in args[2])
                ):
                    db_offload_calls.append(fn)
                return fn(*args, **kwargs)

            pipeline.run_blocking = _threaded_run_blocking

            await module._run_full_pipeline_background_async(
                'job-fence-checkpoint',
                'uid',
                ['/tmp/f.opus'],
                'omi',
                False,
                '/tmp/job-fence-checkpoint',
                task_mode=True,
                content_id='content-fence-checkpoint',
                content_run_bound=True,
            )

            assert db_offload_calls == [
                pipeline.checkpoint_sync_content_partial_result,
                pipeline._update_sync_job_for_run,
            ]
            assert checkpoint_events == ['durable', 'job']
            pipeline._finalize_sync_audio_files.assert_called_once()
        finally:
            sync_worker.shutdown(wait=True)
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_fence_checkpoint_lease_loss_stops_audio_finalization(self):
        """A durable fence checkpoint failure reaches the sync callback before side effects."""
        module, stubs = self._load_sync_module()
        sync_worker = ThreadPoolExecutor(max_workers=1)
        try:
            segment_path = '/tmp/seg_1700000001.wav'
            pipeline = stubs['pipeline']
            pipeline.decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            pipeline._cleanup_files = MagicMock()
            pipeline.retrieve_vad_segments = lambda _path, paths, _errors: paths.add(segment_path)
            pipeline.get_wav_duration = MagicMock(return_value=5.0)
            pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
            pipeline.users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=True)
            pipeline.users_db.get_data_protection_level = MagicMock(return_value=None)
            pipeline.build_person_embeddings_cache = MagicMock(return_value={})
            pipeline.get_sync_job = MagicMock(return_value={'partial_result': {}})
            pipeline.get_sync_content_partial_result = MagicMock(return_value={})
            pipeline.get_processed_sync_segment_ids = MagicMock(return_value=set())
            pipeline.compute_sync_segment_id = MagicMock(return_value='segment-1')
            pipeline.process_segment = MagicMock(return_value=False)
            pipeline.checkpoint_sync_content_partial_result = MagicMock(return_value=False)

            def _fence_in_sync_worker(_uid, response, on_fenced):
                response['_fenced_conversation_ids'].add('fenced-conversation')
                on_fenced()

            pipeline._reprocess_merged_conversations = _fence_in_sync_worker
            pipeline._finalize_sync_audio_files = MagicMock()

            async def _threaded_run_blocking(executor, fn, *args, **kwargs):
                if executor is pipeline.sync_executor:
                    return await _production_run_blocking(sync_worker, fn, *args, **kwargs)
                return fn(*args, **kwargs)

            pipeline.run_blocking = _threaded_run_blocking

            with pytest.raises(pipeline.SyncJobRunLeaseLost):
                await module._run_full_pipeline_background_async(
                    'job-fence-lease-lost',
                    'uid',
                    ['/tmp/f.opus'],
                    'omi',
                    False,
                    '/tmp/job-fence-lease-lost',
                    task_mode=True,
                    content_id='content-fence-lease-lost',
                    content_run_bound=True,
                )

            pipeline._finalize_sync_audio_files.assert_not_called()
        finally:
            sync_worker.shutdown(wait=True)
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_person_embeddings_fallback(self):
        """Person embeddings failure must fall back to empty dict, not crash."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_one_seg
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db = MagicMock()
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(side_effect=RuntimeError('cache boom'))
            captured_cache = {}

            def _capture_process(path, uid, response, lock, errors, source, is_locked, prefs, cache, *args, **kwargs):
                captured_cache['value'] = cache
                response['new_memories'].add('m1')

            stubs['pipeline'].process_segment = _capture_process
            stubs['pipeline'].record_usage = MagicMock()

            await module._run_full_pipeline_background_async('j9', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job9')

            assert captured_cache['value'] == {}
            stubs['sync_jobs'].finalize_sync_job.assert_called_once()
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_target_conversation_id_forwarded(self):
        """target_conversation_id must be forwarded to process_segment."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_one_seg
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db = MagicMock()
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline'].record_usage = MagicMock()
            captured_target = {}

            def _capture_target(
                path, uid, response, lock, errors, source, is_locked, prefs, cache, target_cid, *args, **kwargs
            ):
                captured_target['value'] = target_cid
                response['new_memories'].add('m1')

            stubs['pipeline'].process_segment = _capture_target

            await module._run_full_pipeline_background_async(
                'j10', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job10', target_conversation_id='conv-123'
            )

            assert captured_target['value'] == 'conv-123'
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_private_cloud_sync_enabled_forwarded(self):
        """private_cloud_sync_enabled must be forwarded to process_segment."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            stubs['pipeline']._cleanup_files = MagicMock()

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_one_seg
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db = MagicMock()
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].users_db.get_user_private_cloud_sync_enabled = MagicMock(return_value=True)
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline'].record_usage = MagicMock()
            captured = {}

            def _capture_private_sync(path, uid, response, lock, errors, *args, **kwargs):
                captured['value'] = kwargs['private_cloud_sync_enabled']
                response['new_memories'].add('m1')

            stubs['pipeline'].process_segment = _capture_private_sync

            await module._run_full_pipeline_background_async(
                'j-private', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-private'
            )

            assert captured['value'] is True
        finally:
            self._cleanup(stubs['saved_modules'])

    @pytest.mark.asyncio
    async def test_cleanup_called_on_success(self):
        """Cleanup must be called even on successful completion."""
        module, stubs = self._load_sync_module()
        try:
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            cleanup_calls = []
            stubs['pipeline']._cleanup_files = lambda paths: cleanup_calls.append(list(paths))

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_one_seg
            stubs['pipeline'].get_wav_duration = MagicMock(return_value=5.0)
            stubs['pipeline'].users_db = MagicMock()
            stubs['pipeline'].users_db.get_user_transcription_preferences = MagicMock(return_value={})
            stubs['pipeline'].build_person_embeddings_cache = MagicMock(return_value={})
            stubs['pipeline'].process_segment = MagicMock()
            stubs['pipeline'].record_usage = MagicMock()

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
            stubs['pipeline'].decode_files_to_wav = MagicMock(return_value=['/tmp/w.wav'])
            cleanup_calls = []
            stubs['pipeline']._cleanup_files = lambda paths: cleanup_calls.append(list(paths))

            def _vad_one_seg(path, segmented_paths, errors):
                segmented_paths.add('/tmp/seg_1700000001.wav')

            stubs['pipeline'].retrieve_vad_segments = _vad_one_seg
            stubs['pipeline'].get_wav_duration = MagicMock(side_effect=RuntimeError('unexpected crash'))

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
        prior_utils = sys.modules.get('utils')
        prior_utils_sync = sys.modules.get('utils.sync')
        prior_utils_stt = sys.modules.get('utils.stt')
        prior_outcomes = sys.modules.get('utils.stt.outcomes')
        from utils.stt import outcomes as actual_outcomes

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
            'google.cloud.firestore_v1',
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
            'utils.observability.transcription',
            'utils.metrics',
            'utils.log_sanitizer',
            'utils.http_client',
            'utils.multipart',
            'utils.request_validation',
            'utils.sync.files',
            'utils.sync.playback',
            'utils.sync.backfill',
            'utils.sync.content_id',
            'utils.speaker_assignment',
            'utils.speaker_identification',
            'utils.stt.speaker_embedding',
            'python_multipart',
            'python_multipart.multipart',
        ]

        for mod_name in heavy_deps:
            saved_modules[mod_name] = sys.modules.get(mod_name)
            sys.modules[mod_name] = MagicMock()

        saved_modules['utils'] = prior_utils
        saved_modules['utils.sync'] = prior_utils_sync
        saved_modules['utils.stt'] = prior_utils_stt
        saved_modules['utils.stt.outcomes'] = prior_outcomes
        sys.modules['utils.stt.outcomes'] = actual_outcomes
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

        # Mock auth to return test uid
        sys.modules['utils.other.endpoints'].get_current_user_uid = MagicMock(return_value='test-uid')

        return saved_modules, mock_sync_jobs, mock_fair_use

    @staticmethod
    def _cleanup_modules(saved_modules):
        sys.modules.pop('routers.sync', None)
        sys.modules.pop('utils.sync.pipeline', None)
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
            sys.modules.pop('utils.sync.pipeline', None)
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
            sys.modules.pop('utils.sync.pipeline', None)
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
            sys.modules.pop('utils.sync.pipeline', None)
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
            sys.modules.pop('utils.sync.pipeline', None)
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
            sys.modules.pop('utils.sync.pipeline', None)
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
            sys.modules.pop('utils.sync.pipeline', None)
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
            scheduled_tasks = []

            def _capture_background_task(coro, *, name):
                scheduled_tasks.append(name)
                coro.close()

            module.start_background_task = _capture_background_task

            async def _passthrough_run_blocking(_executor, fn, *args, **kwargs):
                return fn(*args, **kwargs)

            module.run_blocking = _passthrough_run_blocking
            module.classify_sync_lane = MagicMock(
                return_value=types.SimpleNamespace(
                    lane=module.SyncLane.FRESH,
                    trust=types.SimpleNamespace(value='legacy'),
                    reason='recent_capture',
                    maximum_age_seconds=60,
                    automatic_recovery_allowed=True,
                )
            )

            import asyncio
            from starlette.datastructures import UploadFile

            upload = UploadFile(filename='test.opus', file=BytesIO(b'\x00' * 10))
            resp = asyncio.run(module.sync_local_files_v2(files=[upload], uid='test-uid'))

            assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
            body = json.loads(resp.body)
            assert 'job_id' in body
            assert body['status'] == 'queued'
            assert body['poll_after_ms'] == 3000
            mock_sync_jobs.create_sync_job.assert_called_once()
            assert scheduled_tasks == [f"sync_pipeline:{body['job_id']}"]
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
        assert re.search(r'run_blocking\(\s+postprocess_executor,\s+process_conversation', source)


# ---------------------------------------------------------------------------
# 14. Bulkhead executor infrastructure tests
# ---------------------------------------------------------------------------


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
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'set_byok_keys({})' in func_body, "Async coordinator must clear BYOK keys in finally"
        assert 'set_byok_uid(None)' in func_body, "Async coordinator must clear BYOK uid in finally"

    def test_async_coordinator_sets_byok_uid_before_work(self):
        """Async coordinator must attach the uid to inherited BYOK key context."""
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        next_boundary = source.find('\n@router.', start + 1)
        if next_boundary == -1:
            next_boundary = len(source)
        func_body = source[start:next_boundary]

        assert 'set_byok_uid(uid if get_byok_keys() else None)' in func_body

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

    def test_segment_workers_are_not_detached_by_async_timeout(self):
        """Executor threads must not outlive the coordinator after an asyncio timeout."""
        source = _read_pipeline_source()
        start = source.index('async def _run_full_pipeline_background_async')
        end = source.find('\nasync def ', start + 1)
        if end == -1:
            end = source.find('\ndef ', start + 1)
        if end == -1:
            end = len(source)
        func_body = source[start:end]
        assert 'asyncio.wait_for(run_blocking(sync_executor, _process_one_segment' not in func_body
        assert 'run_blocking(sync_executor, _process_one_segment' in func_body
