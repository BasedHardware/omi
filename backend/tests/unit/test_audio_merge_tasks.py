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
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from database import conversation_audio as conversation_audio_db
from utils.other import conversation_playback_storage as playback_storage
from utils.other import storage as storage_mod
from utils.sync import conversation_artifact_protocol as artifact_protocol
from utils.sync import conversation_artifact_worker as artifact_worker

# routers.sync (imported at module scope below) constructs Typesense / OpenAI
# clients at import; provide hermetic dummy config so the import succeeds without
# network. Matches the OPENAI_API_KEY default that conftest already sets.
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

    def test_schema_v2_task_name_uses_incarnation_generation_when_present(self):
        ct = _load_cloud_tasks()
        with patch.dict(os.environ, AUDIO_ENV):
            client = MagicMock()
            with patch.object(ct, '_get_tasks_client', return_value=client):
                ct.enqueue_audio_merge_job(
                    {
                        'schema_version': 2,
                        'conversation_id': 'conv1',
                        'fingerprint': 'abc123def456',
                        'artifact_generation_id': '0' * 32,
                        'uid': 'u',
                    }
                )
            client.task_path.assert_called_once_with(
                'proj',
                'us-central1',
                'audio-merge',
                f"amc-conv1-{'0' * 32}",
            )
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
        storage_source = _read_source(os.path.join('utils', 'other', 'storage.py'))
        conversation_source = _read_source(os.path.join('utils', 'other', 'conversation_playback_storage.py'))
        assert "PLAYBACK_ARTIFACT_PREFIX = 'playback'" in storage_source
        assert 'def get_playback_artifact_signed_url' in storage_source
        assert 'def download_playback_artifact' in storage_source
        assert 'def upload_playback_artifact' in storage_source
        assert "content_type='audio/mpeg'" in storage_source
        assert 'artifact_generation_id' in conversation_source
        assert 'def upload_conversation_playback_artifact' in conversation_source

    def test_precache_gates_to_enqueue(self):
        src = _read_source(os.path.join('utils', 'other', 'storage.py'))
        fn = src[src.index('def precache_conversation_audio') :]
        assert 'is_audio_merge_dispatch_enabled()' in fn[:1200]
        assert 'enqueue_conversation_audio_merge' in fn[:1200]

    def test_identical_audio_uses_distinct_incarnation_generations(self):
        fingerprint = 'abc123def456'
        first = artifact_protocol.conversation_playback_artifact_generation_id(
            fingerprint,
            ('incarnation-1', 'job-1', 1),
        )
        recreated = artifact_protocol.conversation_playback_artifact_generation_id(
            fingerprint,
            ('incarnation-2', 'job-2', 1),
        )

        assert first != recreated
        assert len(first) == 32
        assert len(recreated) == 32

    def test_generation_specific_artifact_path(self, monkeypatch):
        blob = MagicMock()
        get_blob = MagicMock(return_value=blob)
        monkeypatch.setattr(playback_storage, 'get_private_cloud_sync_blob', get_blob)

        playback_storage.upload_conversation_playback_artifact('u', 'c', b'mp3', 'a' * 32)

        get_blob.assert_called_once_with('playback/u/c/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/conversation.mp3')
        blob.upload_from_string.assert_called_once_with(b'mp3', content_type='audio/mpeg')

    def test_enqueue_payload_carries_identity_and_generation(self, monkeypatch):
        identity = ('incarnation-1', 'job-1', 1)
        payloads = []
        monkeypatch.setattr(artifact_protocol, 'enqueue_audio_merge_job', payloads.append)

        artifact_protocol.enqueue_conversation_artifact_build(
            'u',
            'c',
            'fingerprint',
            'process_conversation',
            expected_finalization_identity=identity,
            require_delivery=True,
        )

        expected_generation = artifact_protocol.conversation_playback_artifact_generation_id('fingerprint', identity)
        assert payloads == [
            {
                'schema_version': 2,
                'uid': 'u',
                'conversation_id': 'c',
                'fingerprint': 'fingerprint',
                'artifact_generation_id': expected_generation,
                'caller': 'process_conversation',
                'expected_finalization_identity': list(identity),
            }
        ]

    @pytest.mark.parametrize('require_delivery', [False, True])
    def test_enqueue_delivery_failure_is_observable_only_in_durable_mode(self, monkeypatch, require_delivery):
        def fail(_payload):
            raise RuntimeError('queue unavailable')

        monkeypatch.setattr(artifact_protocol, 'enqueue_audio_merge_job', fail)

        if require_delivery:
            with pytest.raises(RuntimeError, match='queue unavailable'):
                artifact_protocol.enqueue_conversation_artifact_build(
                    'u',
                    'c',
                    'fingerprint',
                    'process_conversation',
                    require_delivery=True,
                )
        else:
            artifact_protocol.enqueue_conversation_artifact_build(
                'u',
                'c',
                'fingerprint',
                'sync_urls',
            )


class TestDurablePrecacheDrain:
    def test_waiting_cache_upload_runs_inline_and_propagates(self, monkeypatch):
        upload_started = threading.Event()
        release_upload = threading.Event()
        blob = MagicMock()
        blob.exists.return_value = False

        def upload(*_args, **_kwargs):
            upload_started.set()
            assert release_upload.wait(timeout=5), 'test did not release cache upload'
            raise RuntimeError('cache upload failed')

        blob.upload_from_string.side_effect = upload
        bucket = MagicMock()
        bucket.blob.return_value = blob
        client = MagicMock()
        client.bucket.return_value = bucket
        nested_executor = MagicMock()
        monkeypatch.setattr(storage_mod, '_get_storage_client', lambda: client)
        monkeypatch.setattr(storage_mod, 'download_audio_chunks_and_merge', lambda *args, **kwargs: b'pcm')
        monkeypatch.setattr(storage_mod, 'storage_executor', nested_executor)

        with ThreadPoolExecutor(max_workers=1) as coordinator:
            result = coordinator.submit(
                storage_mod.get_or_create_merged_audio,
                'u',
                'c',
                'file-1',
                [1.0],
                lambda pcm: b'wav:' + pcm,
                wait_for_cache_upload=True,
            )
            assert upload_started.wait(timeout=5), 'cache upload did not start'
            assert not result.done(), 'durable merge returned while cache upload was blocked'
            release_upload.set()
            with pytest.raises(RuntimeError, match='cache upload failed'):
                result.result(timeout=5)

        nested_executor.submit.assert_not_called()

    def test_precache_drains_siblings_before_propagating_first_failure(self, monkeypatch):
        second_started = threading.Event()
        first_failed = threading.Event()
        release_second = threading.Event()
        calls = []

        def merge(*_args, audio_file_id, wait_for_cache_upload, **_kwargs):
            calls.append((audio_file_id, wait_for_cache_upload))
            if audio_file_id == 'file-1':
                assert second_started.wait(timeout=5), 'second file did not start'
                first_failed.set()
                raise RuntimeError('first merge failed')
            second_started.set()
            assert release_second.wait(timeout=5), 'test did not release second file'
            return b'wav', False

        monkeypatch.setattr(storage_mod, 'is_audio_merge_dispatch_enabled', lambda: False)
        monkeypatch.setattr(storage_mod, 'get_or_create_merged_audio', merge)
        with ThreadPoolExecutor(max_workers=2) as file_executor:
            monkeypatch.setattr(storage_mod, 'storage_executor', file_executor)
            with ThreadPoolExecutor(max_workers=1) as coordinator:
                result = coordinator.submit(
                    storage_mod.precache_conversation_audio,
                    'u',
                    'c',
                    [
                        {'id': 'file-1', 'chunk_timestamps': [1.0]},
                        {'id': 'file-2', 'chunk_timestamps': [2.0]},
                    ],
                    wait_for_completion=True,
                )
                assert first_failed.wait(timeout=5), 'first file did not fail'
                assert not result.done(), 'precache returned while a sibling merge was still blocked'
                release_second.set()
                with pytest.raises(RuntimeError, match='first merge failed'):
                    result.result(timeout=5)

        assert sorted(calls) == [('file-1', True), ('file-2', True)]


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

    @staticmethod
    async def _run_inline(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    @staticmethod
    def _payload(identity):
        audio_files = [{'id': 'file-1', 'chunk_timestamps': [1.0]}]
        fingerprint = storage_mod.compute_audio_files_fingerprint(audio_files)
        return (
            {
                'schema_version': 2,
                'conversation_id': 'c1',
                'uid': 'u1',
                'fingerprint': fingerprint,
                'artifact_generation_id': artifact_protocol.conversation_playback_artifact_generation_id(
                    fingerprint,
                    identity,
                ),
                'expected_finalization_identity': list(identity),
            },
            audio_files,
        )

    async def test_tampered_generation_is_dropped_before_lock(self, monkeypatch):
        payload, _audio_files = self._payload(('incarnation-1', 'job-1', 1))
        payload['artifact_generation_id'] = 'f' * 32
        acquire_lock = MagicMock()
        monkeypatch.setattr(artifact_worker, 'try_acquire_job_run_lock', acquire_lock)

        response = await artifact_worker.run_conversation_merge_job(payload, task_retry_count=0)

        assert response.status_code == 200
        assert b'invalid_payload' in response.body
        acquire_lock.assert_not_called()

    async def test_recreated_same_id_with_identical_audio_supersedes_stale_task(self, monkeypatch):
        old_identity = ('incarnation-1', 'job-1', 1)
        payload, audio_files = self._payload(old_identity)
        recreated = {
            'id': 'c1',
            'audio_files': audio_files,
            'started_at': datetime(2026, 7, 28, tzinfo=timezone.utc),
            'finalization_incarnation_id': 'incarnation-2',
            'finalization_job_id': 'job-2',
            'finalization_revision': 1,
        }
        build = MagicMock()
        upload = MagicMock()
        commit = MagicMock()
        monkeypatch.setattr(artifact_worker, 'run_blocking', self._run_inline)
        monkeypatch.setattr(artifact_worker, 'try_acquire_job_run_lock', lambda *_: 'lock-1')
        monkeypatch.setattr(artifact_worker, 'release_job_run_lock', lambda *_: None)
        monkeypatch.setattr(artifact_worker.conversations_db, 'get_conversation', lambda *_: recreated)
        monkeypatch.setattr(artifact_worker.sync_playback, 'build_conversation_playback_artifact', build)
        monkeypatch.setattr(artifact_worker, 'upload_conversation_playback_artifact', upload)
        monkeypatch.setattr(conversation_audio_db, 'commit_conversation_audio_if_source_current', commit)

        response = await artifact_worker.run_conversation_merge_job(payload, task_retry_count=0)

        assert response.status_code == 200
        assert b'superseded' in response.body
        build.assert_not_called()
        upload.assert_not_called()
        commit.assert_not_called()

    async def test_recreation_during_build_is_fenced_before_upload(self, monkeypatch):
        identity = ('incarnation-1', 'job-1', 1)
        payload, audio_files = self._payload(identity)
        current = {
            'id': 'c1',
            'audio_files': audio_files,
            'started_at': datetime(2026, 7, 28, tzinfo=timezone.utc),
            'finalization_incarnation_id': identity[0],
            'finalization_job_id': identity[1],
            'finalization_revision': identity[2],
        }
        recreated = {
            **current,
            'finalization_incarnation_id': 'incarnation-2',
            'finalization_job_id': 'job-2',
        }
        get_conversation = MagicMock(side_effect=[current, recreated])
        upload = MagicMock()
        commit = MagicMock()
        monkeypatch.setattr(artifact_worker, 'run_blocking', self._run_inline)
        monkeypatch.setattr(artifact_worker, 'try_acquire_job_run_lock', lambda *_: 'lock-1')
        monkeypatch.setattr(artifact_worker, 'release_job_run_lock', lambda *_: None)
        monkeypatch.setattr(artifact_worker.conversations_db, 'get_conversation', get_conversation)
        monkeypatch.setattr(
            artifact_worker.sync_playback,
            'build_conversation_playback_artifact',
            lambda *_: (
                b'mp3',
                [{'file_id': 'file-1', 'wall_offset': 0.0, 'artifact_offset': 0.0, 'len': 1.0}],
            ),
        )
        monkeypatch.setattr(artifact_worker, 'upload_conversation_playback_artifact', upload)
        monkeypatch.setattr(conversation_audio_db, 'commit_conversation_audio_if_source_current', commit)

        response = await artifact_worker.run_conversation_merge_job(payload, task_retry_count=0)

        assert response.status_code == 200
        assert b'superseded' in response.body
        upload.assert_not_called()
        commit.assert_not_called()

    async def test_identity_cas_rejects_recreation_after_generation_upload(self, monkeypatch):
        identity = ('incarnation-1', 'job-1', 1)
        payload, audio_files = self._payload(identity)
        current = {
            'id': 'c1',
            'audio_files': audio_files,
            'started_at': datetime(2026, 7, 28, tzinfo=timezone.utc),
            'finalization_incarnation_id': identity[0],
            'finalization_job_id': identity[1],
            'finalization_revision': identity[2],
        }
        upload = MagicMock()
        commit = MagicMock(return_value=False)
        monkeypatch.setattr(artifact_worker, 'run_blocking', self._run_inline)
        monkeypatch.setattr(artifact_worker, 'try_acquire_job_run_lock', lambda *_: 'lock-1')
        monkeypatch.setattr(artifact_worker, 'release_job_run_lock', lambda *_: None)
        monkeypatch.setattr(artifact_worker.conversations_db, 'get_conversation', lambda *_: current)
        monkeypatch.setattr(
            artifact_worker.sync_playback,
            'build_conversation_playback_artifact',
            lambda *_: (
                b'mp3',
                [{'file_id': 'file-1', 'wall_offset': 0.0, 'artifact_offset': 0.0, 'len': 1.0}],
            ),
        )
        monkeypatch.setattr(artifact_worker, 'upload_conversation_playback_artifact', upload)
        monkeypatch.setattr(conversation_audio_db, 'commit_conversation_audio_if_source_current', commit)

        response = await artifact_worker.run_conversation_merge_job(payload, task_retry_count=0)

        assert response.status_code == 200
        assert b'superseded' in response.body
        upload.assert_called_once_with('u1', 'c1', b'mp3', payload['artifact_generation_id'])
        commit.assert_called_once()
        assert commit.call_args.kwargs == {
            'expected_audio_files': audio_files,
            'expected_finalization_identity': identity,
        }

    async def test_current_generation_uploads_and_commits(self, monkeypatch):
        identity = ('incarnation-1', 'job-1', 1)
        payload, audio_files = self._payload(identity)
        current = {
            'id': 'c1',
            'audio_files': audio_files,
            'started_at': datetime(2026, 7, 28, tzinfo=timezone.utc),
            'finalization_incarnation_id': identity[0],
            'finalization_job_id': identity[1],
            'finalization_revision': identity[2],
        }
        spans = [{'file_id': 'file-1', 'wall_offset': 0.0, 'artifact_offset': 0.0, 'len': 1.25}]
        upload = MagicMock()
        commit = MagicMock(return_value=True)
        release = MagicMock()
        monkeypatch.setattr(artifact_worker, 'run_blocking', self._run_inline)
        monkeypatch.setattr(artifact_worker, 'try_acquire_job_run_lock', lambda *_: 'lock-1')
        monkeypatch.setattr(artifact_worker, 'release_job_run_lock', release)
        monkeypatch.setattr(artifact_worker.conversations_db, 'get_conversation', lambda *_: current)
        monkeypatch.setattr(
            artifact_worker.sync_playback,
            'build_conversation_playback_artifact',
            lambda *_: (b'mp3', spans),
        )
        monkeypatch.setattr(artifact_worker, 'upload_conversation_playback_artifact', upload)
        monkeypatch.setattr(conversation_audio_db, 'commit_conversation_audio_if_source_current', commit)

        response = await artifact_worker.run_conversation_merge_job(payload, task_retry_count=0)

        assert response.status_code == 200
        assert b'"status":"done"' in response.body
        upload.assert_called_once_with('u1', 'c1', b'mp3', payload['artifact_generation_id'])
        commit.assert_called_once()
        stamp = commit.call_args.args[2]
        assert stamp['audio_files_fingerprint'] == payload['fingerprint']
        assert stamp['artifact_generation_id'] == payload['artifact_generation_id']
        assert stamp['duration'] == 1.25
        assert stamp['captured_duration'] == 1.25
        assert stamp['spans'] == spans
        assert commit.call_args.kwargs == {
            'expected_audio_files': audio_files,
            'expected_finalization_identity': identity,
        }
        release.assert_called_once_with('audio:c1:conversation', 'lock-1')


@pytest.mark.parametrize(
    ('identity', 'audio_files'),
    [
        (('incarnation-2', 'job-2', 1), [{'id': 'file-1', 'chunk_timestamps': [1.0]}]),
        (('incarnation-1', 'job-1', 1), [{'id': 'file-1', 'chunk_timestamps': [2.0]}]),
    ],
    ids=('recreated-row-identical-audio', 'same-row-new-audio'),
)
def test_conversation_audio_commit_rejects_changed_source(monkeypatch, identity, audio_files):
    path = ('users', 'u1', 'conversations', 'c1')
    current_audio = [{'id': 'file-1', 'chunk_timestamps': [1.0]}]
    database = StrictFirestore(
        {
            path: {
                'id': 'c1',
                'audio_files': current_audio,
                'finalization_incarnation_id': 'incarnation-1',
                'finalization_job_id': 'job-1',
                'finalization_revision': 1,
            }
        }
    )
    monkeypatch.setattr(conversation_audio_db.firestore, 'transactional', lambda function: function)

    committed = conversation_audio_db.commit_conversation_audio_if_source_current(
        'u1',
        'c1',
        {'artifact_generation_id': 'a' * 32},
        expected_audio_files=audio_files,
        expected_finalization_identity=identity,
        firestore_client=database,
    )

    assert committed is False
    assert database.rows[path].get('conversation_audio') is None
    assert database.transactions[0].updates == []


def test_conversation_audio_commit_updates_matching_source(monkeypatch):
    path = ('users', 'u1', 'conversations', 'c1')
    identity = ('incarnation-1', 'job-1', 1)
    audio_files = [{'id': 'file-1', 'chunk_timestamps': [1.0]}]
    conversation_audio = {
        'audio_files_fingerprint': storage_mod.compute_audio_files_fingerprint(audio_files),
        'artifact_generation_id': 'a' * 32,
    }
    database = StrictFirestore(
        {
            path: {
                'id': 'c1',
                'audio_files': audio_files,
                'finalization_incarnation_id': identity[0],
                'finalization_job_id': identity[1],
                'finalization_revision': identity[2],
            }
        }
    )
    monkeypatch.setattr(conversation_audio_db.firestore, 'transactional', lambda function: function)

    committed = conversation_audio_db.commit_conversation_audio_if_source_current(
        'u1',
        'c1',
        conversation_audio,
        expected_audio_files=audio_files,
        expected_finalization_identity=identity,
        firestore_client=database,
    )

    assert committed is True
    assert database.rows[path]['conversation_audio'] == conversation_audio
    assert database.transactions[0].updates == [(path, {'conversation_audio': conversation_audio})]


def test_conversation_audio_source_read_includes_row_identity():
    identity = ('incarnation-1', 'job-1', 1)
    source = {
        'conversation_audio': {'audio_files_fingerprint': 'fp'},
        'finalization_incarnation_id': identity[0],
        'finalization_job_id': identity[1],
        'finalization_revision': identity[2],
    }
    snapshot = MagicMock(exists=True)
    snapshot.to_dict.return_value = source
    client = MagicMock()
    conversation_ref = (
        client.collection.return_value.document.return_value.collection.return_value.document.return_value
    )
    conversation_ref.get.return_value = snapshot

    result = conversation_audio_db.get_conversation_audio_source('u1', 'c1', firestore_client=client)

    assert result == source
    conversation_ref.get.assert_called_once_with(
        field_paths=[
            'conversation_audio',
            'finalization_incarnation_id',
            'finalization_job_id',
            'finalization_revision',
        ]
    )


def test_sync_finalize_enqueue_carries_current_row_identity(monkeypatch):
    from utils.sync import pipeline as sync_pipeline

    identity = ('incarnation-1', 'job-1', 1)
    audio_file = MagicMock()
    audio_file.model_dump.return_value = {'id': 'file-1', 'chunk_timestamps': [1.0]}
    source = {
        'audio_files': [audio_file.model_dump.return_value],
        'finalization_incarnation_id': identity[0],
        'finalization_job_id': identity[1],
        'finalization_revision': identity[2],
    }
    enqueues = []
    monkeypatch.setattr(sync_pipeline.conversations_db, 'create_audio_files_from_chunks', lambda *_: [audio_file])
    monkeypatch.setattr(sync_pipeline.conversations_db, 'update_conversation', lambda *_: None)
    monkeypatch.setattr(sync_pipeline.conversations_db, 'get_conversation', lambda *_: source)
    monkeypatch.setattr(sync_pipeline, 'precache_conversation_audio', lambda *_: None)
    monkeypatch.setattr(sync_pipeline, 'is_audio_merge_dispatch_enabled', lambda: True)
    monkeypatch.setattr(sync_pipeline, 'compute_audio_files_fingerprint', lambda _files: 'fp')
    monkeypatch.setattr(
        sync_pipeline,
        'enqueue_conversation_artifact_build',
        lambda *args, **kwargs: enqueues.append((args, kwargs)),
    )

    sync_pipeline._finalize_sync_audio_files('u1', {'new_memories': {'c1'}})

    assert enqueues == [
        (
            ('u1', 'c1', 'fp', 'sync_finalize'),
            {'expected_finalization_identity': identity},
        )
    ]


if __name__ == '__main__':
    sys.exit(pytest.main([__file__, '-v']))
