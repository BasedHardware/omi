"""
Tests for the audio-merge Cloud Tasks pipeline (conversation playback).

Playback used to merge audio chunks inline in request paths (/urls merged the
first uncached file synchronously and unbounded; the app's pending fallback
hit /download which also merged in-request) — long conversations always timed
out. Merges now run as Cloud Tasks jobs building a 30-day MP3 artifact under
playback/; request paths are pure metadata reads.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import pytest

# routers.sync (imported inside TestV2HandlerRetrySemantics) constructs Typesense /
# OpenAI clients at import; provide hermetic dummy config so the import succeeds
# without network. Matches the OPENAI_API_KEY default that conftest already sets.
os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')

# Imported at module scope (not inside the test) so the heavy routers.sync import cost
# lands in collection, keeping the per-test call within the fast-unit duration guard.
import routers.sync as routers_sync  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', '..')


def _read_source(rel_path):
    with open(os.path.join(BACKEND_DIR, rel_path), encoding='utf-8') as f:
        return f.read()


def _load_cloud_tasks():
    import importlib.util

    mock = MagicMock()
    saved = sys.modules.get('google.cloud.tasks_v2')
    sys.modules['google.cloud.tasks_v2'] = mock
    # If another test already imported the real package, `from google.cloud
    # import tasks_v2` resolves via the parent-package ATTRIBUTE and bypasses
    # sys.modules — patch the attribute too so load order can't leak the real
    # client into this module.
    google_cloud_pkg = sys.modules.get('google.cloud')
    sentinel = object()
    saved_attr = getattr(google_cloud_pkg, 'tasks_v2', sentinel) if google_cloud_pkg else sentinel
    if google_cloud_pkg is not None:
        google_cloud_pkg.tasks_v2 = mock
    try:
        spec = importlib.util.spec_from_file_location(
            'cloud_tasks_audio_test', os.path.join(BACKEND_DIR, 'utils', 'cloud_tasks.py')
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if saved is None:
            sys.modules.pop('google.cloud.tasks_v2', None)
        else:
            sys.modules['google.cloud.tasks_v2'] = saved
        if google_cloud_pkg is not None:
            if saved_attr is sentinel:
                try:
                    delattr(google_cloud_pkg, 'tasks_v2')
                except AttributeError:
                    pass
            else:
                google_cloud_pkg.tasks_v2 = saved_attr


AUDIO_ENV = {
    'SYNC_TASKS_PROJECT': 'proj',
    'SYNC_TASKS_LOCATION': 'us-central1',
    'AUDIO_MERGE_TASKS_QUEUE': 'audio-merge',
    'AUDIO_MERGE_HANDLER_URL': 'https://backend-sync.example.com/v2/audio-merge-jobs/run',
    'SYNC_TASKS_INVOKER_SA': 'invoker@proj.iam.gserviceaccount.com',
}


class TestEnqueueAudioMergeJob:
    def test_task_named_by_conversation_and_file(self):
        ct = _load_cloud_tasks()
        with patch.dict(os.environ, AUDIO_ENV):
            client = MagicMock()
            with patch.object(ct, '_get_tasks_client', return_value=client):
                ct.enqueue_audio_merge_job(
                    {'conversation_id': 'conv1', 'audio_file_id': 'file1', 'uid': 'u', 'timestamps': [1.0]}
                )
            client.task_path.assert_called_once_with('proj', 'us-central1', 'audio-merge', 'am-conv1-file1')
            client.create_task.assert_called_once()

    def test_schema_v2_task_named_by_conversation_and_fingerprint(self):
        # Conversation-level artifact builds embed the audio_files fingerprint in
        # the task name so rebuilds after late chunks get a fresh name instead of
        # hitting the named-task tombstone.
        ct = _load_cloud_tasks()
        with patch.dict(os.environ, AUDIO_ENV):
            client = MagicMock()
            with patch.object(ct, '_get_tasks_client', return_value=client):
                ct.enqueue_audio_merge_job(
                    {'schema_version': 2, 'conversation_id': 'conv1', 'fingerprint': 'abc123def456', 'uid': 'u'}
                )
            client.task_path.assert_called_once_with('proj', 'us-central1', 'audio-merge', 'amc-conv1-abc123def456')
            client.create_task.assert_called_once()

    def test_incomplete_env_raises(self):
        ct = _load_cloud_tasks()
        env = dict(AUDIO_ENV)
        env.pop('AUDIO_MERGE_TASKS_QUEUE')
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop('AUDIO_MERGE_TASKS_QUEUE', None)
            with pytest.raises(RuntimeError):
                ct.enqueue_audio_merge_job({'conversation_id': 'c', 'audio_file_id': 'f'})

    def test_dispatch_flag_default_inline(self):
        ct = _load_cloud_tasks()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('AUDIO_MERGE_DISPATCH_MODE', None)
            assert ct.is_audio_merge_dispatch_enabled() is False
        with patch.dict(os.environ, {'AUDIO_MERGE_DISPATCH_MODE': 'cloud_tasks'}):
            assert ct.is_audio_merge_dispatch_enabled() is True


class TestPlaybackReadPathsStructure:
    """Request paths must never merge when artifact dispatch is enabled."""

    def test_handler_endpoint_exists_with_oidc(self):
        src = _read_source(os.path.join('routers', 'sync.py'))
        assert '"/v2/audio-merge-jobs/run"' in src
        handler = src[src.index('async def run_audio_merge_job') :]
        assert 'Depends(verify_cloud_tasks_oidc)' in handler[:200]
        assert 'try_acquire_job_run_lock' in handler
        assert 'status_code=409' in handler
        assert "reason': 'chunks_missing'" in handler
        assert 'audio_merge_failed_final' in handler

    def test_artifact_urls_path_never_merges(self):
        src = _read_source(os.path.join('utils', 'sync', 'playback.py'))
        fn = src[src.index('def _get_audio_urls_via_artifacts') : src.index('def _get_audio_urls_inline')]
        assert 'precache_audio_file' not in fn
        assert 'get_or_create_merged_audio' not in fn
        assert 'download_audio_chunks_and_merge' not in fn
        assert 'enqueue_conversation_audio_merge' in fn
        assert 'poll_after_ms' in fn

    def test_urls_endpoint_gated(self):
        src = _read_source(os.path.join('utils', 'sync', 'playback.py'))
        fn = src[src.index('def get_audio_signed_urls') :]
        assert 'is_audio_merge_dispatch_enabled()' in fn[:1500]

    def test_download_endpoint_returns_202_on_miss(self):
        src = _read_source(os.path.join('utils', 'sync', 'playback.py'))
        start = src.index('def _get_artifact_download_payload')
        section = src[start : src.index('def _get_inline_download_payload')]
        assert 'download_playback_artifact' in section
        response_fn = src[src.index('def download_audio_file_response') : src.index('def build_playback_artifact')]
        assert 'status_code=202' in response_fn

    def test_mp3_export_settings(self):
        src = _read_source(os.path.join('utils', 'sync', 'playback.py'))
        fn = src[src.index('def build_playback_artifact') :]
        assert "format='mp3'" in fn
        assert "bitrate='48k'" in fn
        assert 'fill_gaps=True' in fn

    def test_handler_timeout_override_wired(self):
        src = _read_source('main.py')
        assert '"/v2/audio-merge-jobs/run"' in src
        assert 'HTTP_AUDIO_MERGE_RUN_TIMEOUT' in src


class TestUnavailableContract:
    """Unbuildable audio (chunks gone) must surface as terminal 'unavailable',
    never as pending-forever (named-task tombstones block re-enqueues)."""

    def test_handler_marks_unavailable_on_chunks_missing(self):
        src = _read_source(os.path.join('routers', 'sync.py'))
        handler = src[src.index('async def run_audio_merge_job') :]
        missing = handler[handler.index('except FileNotFoundError') : handler.index("'chunks_missing'}")]
        assert 'mark_playback_unavailable' in missing

    def test_urls_reports_unavailable_without_enqueue(self):
        src = _read_source(os.path.join('utils', 'sync', 'playback.py'))
        fn = src[src.index('def _get_audio_urls_via_artifacts') : src.index('def get_audio_signed_urls')]
        unavailable = fn[fn.index('is_playback_unavailable') : fn.index('else:')]
        assert '"unavailable"' in unavailable
        assert 'to_enqueue.append' not in unavailable

    def test_storage_marker_helpers(self):
        src = _read_source(os.path.join('utils', 'other', 'storage.py'))
        assert 'def mark_playback_unavailable' in src
        assert 'def is_playback_unavailable' in src
        assert '.unavailable' in src

    def test_app_treats_unavailable_as_terminal(self):
        src = _read_source(os.path.join('..', 'app', 'lib', 'backend', 'http', 'api', 'audio.dart'))
        assert "f.status != 'unavailable'" in src


class TestStorageArtifactHelpers:
    def test_playback_prefix_and_helpers(self):
        src = _read_source(os.path.join('utils', 'other', 'storage.py'))
        assert "PLAYBACK_ARTIFACT_PREFIX = 'playback'" in src
        assert 'def get_playback_artifact_signed_url' in src
        assert 'def download_playback_artifact' in src
        assert 'def upload_playback_artifact' in src
        assert "content_type='audio/mpeg'" in src

    def test_precache_gates_to_enqueue(self):
        src = _read_source(os.path.join('utils', 'other', 'storage.py'))
        fn = src[src.index('def precache_conversation_audio') :]
        assert 'is_audio_merge_dispatch_enabled()' in fn[:1200]
        assert 'enqueue_conversation_audio_merge' in fn[:1200]


class TestV2HandlerRetrySemantics:
    """The v2 conversation-merge dispatch must NOT be masked by the invalid-payload
    catch-all. A transient GCS/Firestore failure has to propagate (500 -> Cloud Tasks
    retry); acking it 200 permanently loses the playback artifact because the named
    task's tombstone blocks re-enqueue.
    """

    class _FakeRequest:
        def __init__(self, payload=None, raise_on_json=None):
            self._payload = payload
            self._raise_on_json = raise_on_json

        async def json(self):
            if self._raise_on_json is not None:
                raise self._raise_on_json
            return self._payload

    async def test_v2_transient_error_propagates_for_retry(self):
        from unittest.mock import AsyncMock, patch

        payload = {'schema_version': 2, 'conversation_id': 'c1', 'uid': 'u1', 'fingerprint': 'fp'}
        with patch.object(
            routers_sync, '_run_conversation_merge_job', new=AsyncMock(side_effect=RuntimeError('gcs 503'))
        ):
            with pytest.raises(RuntimeError):
                await routers_sync.run_audio_merge_job(self._FakeRequest(payload), task_retry_count=0)

    async def test_malformed_payload_still_dropped_200(self):
        req = self._FakeRequest(raise_on_json=ValueError('bad json'))
        resp = await routers_sync.run_audio_merge_job(req, task_retry_count=0)
        assert resp.status_code == 200
        assert b'invalid_payload' in resp.body


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
