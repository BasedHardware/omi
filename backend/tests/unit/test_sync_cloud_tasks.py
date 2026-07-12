"""
Tests for Cloud Tasks dispatch of the v2 sync pipeline.

Covers the new primitives in database/sync_jobs.py (run lock, queued-reset,
processed-segment ledger, metering once-guards), the OIDC verification in
utils/cloud_tasks.py, and the structural contract of the /v2/sync-jobs/run
handler in routers/sync.py.
"""

import hashlib
import json
import os
import sys
import time
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

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


def _load_sync_jobs():
    mock_redis = MagicMock()
    module = _load_module_with_stubs(
        os.path.join('database', 'sync_jobs.py'),
        'sync_jobs_under_test',
        {
            'database': MagicMock(),
            'database.redis_db': MagicMock(r=mock_redis),
        },
    )
    return module, mock_redis


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

    def test_lock_ttl_exceeds_handler_timeout(self):
        """Invariant: a run-lock can never expire under a live run (request
        timeout HTTP_SYNC_JOBS_RUN_TIMEOUT=1500 < lock TTL)."""
        sync_jobs, _ = _load_sync_jobs()
        assert sync_jobs.RUN_LOCK_TTL_SECONDS > 1500


# ---------------------------------------------------------------------------
# Queued-reset, ledger, once-guards
# ---------------------------------------------------------------------------


class TestRetryPrimitives:
    def test_mark_job_queued_for_retry_resets_status(self):
        import json

        sync_jobs, mock_redis = _load_sync_jobs()
        mock_redis.get.return_value = json.dumps({'job_id': 'job-1', 'status': 'processing'})
        sync_jobs.mark_job_queued_for_retry('job-1', attempt=2, error='boom')
        written = json.loads(mock_redis.set.call_args[0][1])
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

    def test_enqueue_account_deletion_task_is_named_by_uid(self):
        cloud_tasks = _load_cloud_tasks()
        env = {
            'SYNC_TASKS_PROJECT': 'proj',
            'SYNC_TASKS_LOCATION': 'us-central1',
            'ACCOUNT_DELETION_TASKS_QUEUE': 'account-delete',
            'ACCOUNT_DELETION_HANDLER_URL': 'https://backend-sync.example.com/v1/users/account-deletion-wipes/run',
            'SYNC_TASKS_INVOKER_SA': 'invoker@proj.iam.gserviceaccount.com',
        }
        uid_hash = hashlib.sha256(b'uid1').hexdigest()[:32]
        task_id = f'account-delete-{uid_hash}-abc123'
        with patch.dict(os.environ, env):
            client = MagicMock()
            client.task_path.return_value = f'projects/proj/locations/us-central1/queues/account-delete/tasks/{task_id}'
            with patch.object(cloud_tasks, '_get_tasks_client', return_value=client), patch.object(
                cloud_tasks.uuid, 'uuid4', return_value=MagicMock(hex='abc123')
            ):
                cloud_tasks.enqueue_account_deletion_wipe('uid1')
        client.task_path.assert_called_once_with('proj', 'us-central1', 'account-delete', task_id)
        client.create_task.assert_called_once()

    def test_account_deletion_dispatch_flag_default_inline(self):
        cloud_tasks = _load_cloud_tasks()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('ACCOUNT_DELETION_DISPATCH_MODE', None)
            assert cloud_tasks.is_account_deletion_dispatch_enabled() is False
        with patch.dict(os.environ, {'ACCOUNT_DELETION_DISPATCH_MODE': 'cloud_tasks'}):
            assert cloud_tasks.is_account_deletion_dispatch_enabled() is True


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

    def test_handler_respects_terminal_statuses(self):
        source = self._read(os.path.join('routers', 'sync.py'))
        handler = source[source.index('async def run_sync_job') :]
        assert 'TERMINAL_STATUSES' in handler
        assert 'mark_job_queued_for_retry' in handler
        assert 'status_code=409' in handler

    def test_fast_path_gates_on_env_and_byok(self):
        source = self._read(os.path.join('routers', 'sync.py'))
        assert 'is_cloud_tasks_dispatch_enabled() and not has_byok_keys()' in source

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
        assert 'Depends(verify_cloud_tasks_oidc)' in handler[:200]
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

        assert 'post-enqueue local cleanup failed' in func_body
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

    saved_modules = {}
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
    sys.modules['database.sync_jobs'] = mock_sync_jobs

    sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
    sys.modules['utils.fair_use'].get_hard_restriction_status = MagicMock(return_value=(False, None))
    sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
    sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
    sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
    sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
    sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)
    sys.modules['utils.request_validation'].parse_sync_filename_timestamp = MagicMock(return_value=time.time())
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
    sys.modules['utils.observability'] = obs_pkg
    sys.modules['utils.observability.fallback'] = fallback_mod
    obs_pkg.fallback = fallback_mod
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

    return module, saved_modules, mock_sync_jobs, BytesIO, sync_dispatch_fallback_calls, sync_dispatch_attempt_modes


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
async def test_sync_dispatch_enqueue_failed_records_degraded_inline(monkeypatch):
    from starlette.datastructures import UploadFile

    module, saved_modules, _, BytesIO, fallback_calls, attempt_modes = _load_sync_router_for_fast_path()
    module.start_background_task = MagicMock()
    module.enqueue_sync_job = MagicMock(side_effect=RuntimeError('enqueue boom'))
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
        assert fallback_calls == [
            {
                'component': 'sync_dispatch',
                'from_mode': 'cloud_tasks',
                'to_mode': 'inline',
                'reason': 'enqueue_failed',
                'outcome': 'degraded',
            }
        ]
        assert attempt_modes == ['inline']
        assert module.start_background_task.call_count == 2
        pipeline_call = module.start_background_task.call_args_list[-1]
        assert pipeline_call.kwargs.get('name', '').startswith('sync_pipeline:')
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

        assert response.status_code == 503
        assert response.headers['x-omi-rate-limit-reason'] == 'backfill_capacity'
        module.start_background_task.assert_not_called()
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
