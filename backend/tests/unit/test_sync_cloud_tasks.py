"""
Tests for Cloud Tasks dispatch of the v2 sync pipeline.

Covers the new primitives in database/sync_jobs.py (run lock, queued-reset,
processed-segment ledger, metering once-guards), the OIDC verification in
utils/cloud_tasks.py, and the structural contract of the /v2/sync-jobs/run
handler in routers/sync.py.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

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
        source = self._read(os.path.join('routers', 'sync.py'))
        assert 'task_mode: bool = False' in source
        # Catch-all must re-raise in task mode so the handler controls retry
        assert 'if task_mode:' in source

    def test_timeout_override_wired(self):
        main_src = self._read('main.py')
        assert 'paths_timeout' in main_src
        assert 'HTTP_SYNC_JOBS_RUN_TIMEOUT' in main_src
        timeout_src = self._read(os.path.join('utils', 'other', 'timeout.py'))
        assert 'paths_timeout' in timeout_src

    def test_v1_endpoint_unchanged(self):
        source = self._read(os.path.join('routers', 'sync.py'))
        assert '"/v1/sync-local-files"' in source


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
