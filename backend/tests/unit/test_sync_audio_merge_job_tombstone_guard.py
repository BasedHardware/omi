"""Tests for sync router audio merge Cloud Tasks job soft-deleted conversation access guard.

Verifies that soft-deleted conversations (deleted=True / tombstone)
are properly guarded and dropped without executing heavy audio merge processing
or mutating Firestore documents in:
- POST /v2/audio-merge-jobs/run (schema_version 2: conversation-level dense MP3 merge)
- POST /v2/audio-merge-jobs/run (schema_version 1: legacy single-file merge)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv'
)

import routers.sync as routers_sync


def _make_conversation(
    deleted: bool = False,
    conversation_id: str = 'conv-1',
    audio_files: list | None = None,
) -> dict:
    if audio_files is None:
        audio_files = [{'id': 'af1', 'chunk_timestamps': [100.0, 101.0]}]
    return {
        'id': conversation_id,
        'uid': 'user-1',
        'deleted': deleted,
        'audio_files': audio_files,
        'started_at': '2026-01-01T00:00:00+00:00',
    }


class TestV2ConversationAudioMergeTombstoneGuard:
    """Tests for _run_conversation_merge_job (schema_version 2) tombstone handling."""

    @pytest.mark.anyio
    async def test_v2_merge_drops_soft_deleted_conversation(self):
        """Job must immediately drop and ack task when conversation is soft-deleted."""
        deleted_conv = _make_conversation(deleted=True, conversation_id='conv-del-1')
        payload = {
            'schema_version': 2,
            'uid': 'user-1',
            'conversation_id': 'conv-del-1',
            'fingerprint': 'fp1',
        }
        mock_build = MagicMock()
        mock_upload = MagicMock()
        mock_update = MagicMock()

        with patch.object(routers_sync, 'try_acquire_job_run_lock', return_value='token-1'), \
             patch.object(routers_sync, 'release_job_run_lock'), \
             patch.object(routers_sync, 'should_skip_background_account_mutation', return_value=False), \
             patch.object(routers_sync.conversations_db, 'get_conversation', return_value=deleted_conv), \
             patch.object(routers_sync.sync_playback, 'build_conversation_playback_artifact', mock_build), \
             patch.object(routers_sync, 'upload_conversation_playback_artifact', mock_upload), \
             patch.object(routers_sync.conversations_db, 'update_conversation', mock_update):

            resp = await routers_sync._run_conversation_merge_job(payload, task_retry_count=0)

        assert resp.status_code == 200
        assert b'"status":"dropped"' in resp.body
        assert b'"reason":"deleted_conversation"' in resp.body
        mock_build.assert_not_called()
        mock_upload.assert_not_called()
        mock_update.assert_not_called()

    @pytest.mark.anyio
    async def test_v2_merge_drops_nonexistent_conversation(self):
        """Job must drop and ack task when conversation does not exist."""
        payload = {
            'schema_version': 2,
            'uid': 'user-1',
            'conversation_id': 'conv-nonexistent',
            'fingerprint': 'fp1',
        }
        mock_build = MagicMock()

        with patch.object(routers_sync, 'try_acquire_job_run_lock', return_value='token-1'), \
             patch.object(routers_sync, 'release_job_run_lock'), \
             patch.object(routers_sync, 'should_skip_background_account_mutation', return_value=False), \
             patch.object(routers_sync.conversations_db, 'get_conversation', return_value=None), \
             patch.object(routers_sync.sync_playback, 'build_conversation_playback_artifact', mock_build):

            resp = await routers_sync._run_conversation_merge_job(payload, task_retry_count=0)

        assert resp.status_code == 200
        assert b'"status":"dropped"' in resp.body
        assert b'"reason":"deleted_conversation"' in resp.body
        mock_build.assert_not_called()

    @pytest.mark.anyio
    async def test_v2_merge_drops_conversation_without_audio_files(self):
        """Job must drop when conversation has no audio files."""
        conv_no_audio = _make_conversation(deleted=False, conversation_id='conv-no-audio', audio_files=[])
        payload = {
            'schema_version': 2,
            'uid': 'user-1',
            'conversation_id': 'conv-no-audio',
            'fingerprint': 'fp1',
        }
        mock_build = MagicMock()

        with patch.object(routers_sync, 'try_acquire_job_run_lock', return_value='token-1'), \
             patch.object(routers_sync, 'release_job_run_lock'), \
             patch.object(routers_sync, 'should_skip_background_account_mutation', return_value=False), \
             patch.object(routers_sync.conversations_db, 'get_conversation', return_value=conv_no_audio), \
             patch.object(routers_sync.sync_playback, 'build_conversation_playback_artifact', mock_build):

            resp = await routers_sync._run_conversation_merge_job(payload, task_retry_count=0)

        assert resp.status_code == 200
        assert b'"status":"dropped"' in resp.body
        assert b'"reason":"no_audio_files"' in resp.body
        mock_build.assert_not_called()

    @pytest.mark.anyio
    async def test_v2_merge_proceeds_for_active_conversation(self):
        """Job must proceed and build artifact when conversation is active."""
        active_conv = _make_conversation(deleted=False, conversation_id='conv-active')
        payload = {
            'schema_version': 2,
            'uid': 'user-1',
            'conversation_id': 'conv-active',
            'fingerprint': 'fp-active',
        }
        mock_build = MagicMock(return_value=(b'fake_mp3', [{'len': 1.0, 'wall_offset': 0.0}]))
        mock_upload = MagicMock()
        mock_update = MagicMock()

        with patch.object(routers_sync, 'try_acquire_job_run_lock', return_value='token-1'), \
             patch.object(routers_sync, 'release_job_run_lock'), \
             patch.object(routers_sync, 'should_skip_background_account_mutation', return_value=False), \
             patch.object(routers_sync.conversations_db, 'get_conversation', return_value=active_conv), \
             patch.object(routers_sync, 'compute_audio_files_fingerprint', return_value='fp-active'), \
             patch.object(routers_sync, 'get_conversation_playback_signed_url', return_value=None), \
             patch.object(routers_sync.sync_playback, 'build_conversation_playback_artifact', mock_build), \
             patch.object(routers_sync, 'upload_conversation_playback_artifact', mock_upload), \
             patch.object(routers_sync.conversations_db, 'update_conversation', mock_update):

            resp = await routers_sync._run_conversation_merge_job(payload, task_retry_count=0)

        assert resp.status_code == 200
        assert b'"status":"done"' in resp.body
        mock_build.assert_called_once()
        mock_upload.assert_called_once()
        mock_update.assert_called_once()


class TestV1SingleFileAudioMergeTombstoneGuard:
    """Tests for run_audio_merge_job (schema_version != 2 legacy) tombstone handling."""

    class _FakeRequest:
        def __init__(self, payload: dict):
            self._payload = payload

        async def json(self):
            return self._payload

    @pytest.mark.anyio
    async def test_v1_merge_drops_soft_deleted_conversation(self):
        """Legacy merge must drop and ack when conversation is soft-deleted."""
        deleted_conv = _make_conversation(deleted=True, conversation_id='conv-del-v1')
        payload = {
            'uid': 'user-1',
            'conversation_id': 'conv-del-v1',
            'audio_file_id': 'file-1',
            'timestamps': [100.0],
        }
        mock_build = MagicMock()

        with patch.object(routers_sync, 'try_acquire_job_run_lock', return_value='token-1'), \
             patch.object(routers_sync, 'release_job_run_lock'), \
             patch.object(routers_sync, 'should_skip_background_account_mutation', return_value=False), \
             patch.object(routers_sync.conversations_db, 'get_conversation', return_value=deleted_conv), \
             patch.object(routers_sync.sync_playback, 'build_playback_artifact', mock_build):

            resp = await routers_sync.run_audio_merge_job(self._FakeRequest(payload), task_retry_count=0)

        assert resp.status_code == 200
        assert b'"status":"dropped"' in resp.body
        assert b'"reason":"deleted_conversation"' in resp.body
        mock_build.assert_not_called()

    @pytest.mark.anyio
    async def test_v1_merge_drops_nonexistent_conversation(self):
        """Legacy merge must drop and ack when conversation does not exist."""
        payload = {
            'uid': 'user-1',
            'conversation_id': 'conv-nonexistent',
            'audio_file_id': 'file-1',
            'timestamps': [100.0],
        }
        mock_build = MagicMock()

        with patch.object(routers_sync, 'try_acquire_job_run_lock', return_value='token-1'), \
             patch.object(routers_sync, 'release_job_run_lock'), \
             patch.object(routers_sync, 'should_skip_background_account_mutation', return_value=False), \
             patch.object(routers_sync.conversations_db, 'get_conversation', return_value=None), \
             patch.object(routers_sync.sync_playback, 'build_playback_artifact', mock_build):

            resp = await routers_sync.run_audio_merge_job(self._FakeRequest(payload), task_retry_count=0)

        assert resp.status_code == 200
        assert b'"status":"dropped"' in resp.body
        assert b'"reason":"deleted_conversation"' in resp.body
        mock_build.assert_not_called()
