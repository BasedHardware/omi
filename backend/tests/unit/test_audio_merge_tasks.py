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

BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', '..')


def _read_source(rel_path):
    with open(os.path.join(BACKEND_DIR, rel_path), encoding='utf-8') as f:
        return f.read()


def _load_cloud_tasks():
    import importlib.util

    saved = sys.modules.get('google.cloud.tasks_v2')
    sys.modules['google.cloud.tasks_v2'] = MagicMock()
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
        src = _read_source(os.path.join('routers', 'sync.py'))
        fn = src[src.index('def _get_audio_urls_via_artifacts') : src.index('def get_audio_signed_urls_endpoint')]
        assert '_precache_audio_file' not in fn
        assert 'get_or_create_merged_audio' not in fn
        assert 'download_audio_chunks_and_merge' not in fn
        assert 'enqueue_conversation_audio_merge' in fn
        assert 'poll_after_ms' in fn

    def test_urls_endpoint_gated(self):
        src = _read_source(os.path.join('routers', 'sync.py'))
        fn = src[src.index('def get_audio_signed_urls_endpoint') :]
        assert 'is_audio_merge_dispatch_enabled()' in fn[:1500]

    def test_download_endpoint_returns_202_on_miss(self):
        src = _read_source(os.path.join('routers', 'sync.py'))
        start = (
            src.index('def download_audio_file_endpoint')
            if 'def download_audio_file_endpoint' in src
            else src.index('format == "wav" and is_audio_merge_dispatch_enabled()')
        )
        section = src[start : start + 4000]
        assert 'download_playback_artifact' in section
        assert 'status_code=202' in section

    def test_mp3_export_settings(self):
        src = _read_source(os.path.join('routers', 'sync.py'))
        fn = src[src.index('def _build_playback_artifact') : src.index('async def run_audio_merge_job')]
        assert "format='mp3'" in fn
        assert "bitrate='48k'" in fn
        assert 'fill_gaps=True' in fn

    def test_handler_timeout_override_wired(self):
        src = _read_source('main.py')
        assert '"/v2/audio-merge-jobs/run"' in src
        assert 'HTTP_AUDIO_MERGE_RUN_TIMEOUT' in src


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


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
