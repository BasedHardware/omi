"""Tests for sync router audio endpoints soft-deleted conversation access guard.

Verifies that soft-deleted conversations (deleted=True / tombstone)
are properly guarded and return 404 Not Found across sync audio endpoints:
- POST /v1/sync/audio/{conversation_id}/precache
- GET /v1/sync/audio/{conversation_id}/urls
- GET /v1/sync/audio/{conversation_id}/{audio_file_id}
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv'
)

from database import conversations as conversations_db
from routers import sync as sync_routes


def _make_conversation(
    deleted: bool = False,
    locked: bool = False,
    conversation_id: str = 'conv-1',
    audio_files: list | None = None,
) -> dict:
    if audio_files is None:
        audio_files = [{'id': 'audio-1', 'status': 'ready'}]
    return {
        'id': conversation_id,
        'deleted': deleted,
        'is_locked': locked,
        'audio_files': audio_files,
        'structured': {
            'title': 'Test Conversation',
            'action_items': [],
        },
        'transcript_segments': [],
        'started_at': '2024-01-01T00:00:00',
        'finished_at': '2024-01-01T01:00:00',
        'created_at': 1704067200,
        'discarded': False,
    }


class TestPrecacheConversationAudio:
    """POST /v1/sync/audio/{conversation_id}/precache access guard tests."""

    def test_precache_audio_rejects_deleted_conversation(self, monkeypatch):
        """Precache audio endpoint must return 404 when conversation is soft-deleted."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: _make_conversation(deleted=True, conversation_id=cid),
        )

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.precache_conversation_audio_endpoint(
                conversation_id='conv-1',
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_precache_audio_rejects_nonexistent_conversation(self, monkeypatch):
        """Precache audio endpoint must return 404 when conversation does not exist."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: None,
        )

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.precache_conversation_audio_endpoint(
                conversation_id='nonexistent',
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_precache_audio_rejects_locked_conversation(self, monkeypatch):
        """Precache audio endpoint must return 402 when conversation is locked."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: _make_conversation(locked=True, conversation_id=cid),
        )

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.precache_conversation_audio_endpoint(
                conversation_id='conv-1',
                uid='user-1',
            )

        assert exc_info.value.status_code == 402

    def test_precache_audio_allows_active_conversation(self, monkeypatch):
        """Precache audio endpoint must succeed for active (non-deleted) conversation."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: _make_conversation(deleted=False, conversation_id=cid),
        )
        mock_precache = MagicMock(return_value={'status': 'caching_started', 'file_count': 1})
        monkeypatch.setattr(sync_routes.sync_playback, 'precache_audio_files', mock_precache)

        result = sync_routes.precache_conversation_audio_endpoint(
            conversation_id='conv-1',
            uid='user-1',
        )

        assert result['status'] == 'caching_started'
        mock_precache.assert_called_once_with('user-1', 'conv-1', [{'id': 'audio-1', 'status': 'ready'}])


class TestGetAudioSignedUrls:
    """GET /v1/sync/audio/{conversation_id}/urls access guard tests."""

    def test_get_audio_signed_urls_rejects_deleted_conversation(self, monkeypatch):
        """Signed URLs endpoint must return 404 when conversation is soft-deleted."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid, read_site=None: _make_conversation(deleted=True, conversation_id=cid),
        )

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.get_audio_signed_urls_endpoint(
                conversation_id='conv-1',
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_get_audio_signed_urls_rejects_nonexistent_conversation(self, monkeypatch):
        """Signed URLs endpoint must return 404 when conversation does not exist."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid, read_site=None: None,
        )

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.get_audio_signed_urls_endpoint(
                conversation_id='nonexistent',
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_get_audio_signed_urls_rejects_locked_conversation(self, monkeypatch):
        """Signed URLs endpoint must return 402 when conversation is locked."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid, read_site=None: _make_conversation(locked=True, conversation_id=cid),
        )

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.get_audio_signed_urls_endpoint(
                conversation_id='conv-1',
                uid='user-1',
            )

        assert exc_info.value.status_code == 402

    def test_get_audio_signed_urls_allows_active_conversation(self, monkeypatch):
        """Signed URLs endpoint must succeed for active (non-deleted) conversation."""
        conv = _make_conversation(deleted=False, conversation_id='conv-1')
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid, read_site=None: conv,
        )
        mock_get_urls = MagicMock(return_value={'files': [{'id': 'audio-1', 'status': 'ready'}]})
        monkeypatch.setattr(sync_routes.sync_playback, 'get_audio_signed_urls', mock_get_urls)

        result = sync_routes.get_audio_signed_urls_endpoint(
            conversation_id='conv-1',
            uid='user-1',
        )

        assert 'files' in result
        mock_get_urls.assert_called_once_with('user-1', 'conv-1', conv['audio_files'], conversation=conv)


class TestDownloadAudioFile:
    """GET /v1/sync/audio/{conversation_id}/{audio_file_id} access guard tests."""

    def test_download_audio_rejects_deleted_conversation(self, monkeypatch):
        """Download audio endpoint must return 404 when conversation is soft-deleted."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: _make_conversation(deleted=True, conversation_id=cid),
        )
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.download_audio_file_endpoint(
                conversation_id='conv-1',
                audio_file_id='audio-1',
                request=mock_request,
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_download_audio_rejects_nonexistent_conversation(self, monkeypatch):
        """Download audio endpoint must return 404 when conversation does not exist."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: None,
        )
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.download_audio_file_endpoint(
                conversation_id='nonexistent',
                audio_file_id='audio-1',
                request=mock_request,
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Conversation not found'

    def test_download_audio_rejects_locked_conversation(self, monkeypatch):
        """Download audio endpoint must return 402 when conversation is locked."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: _make_conversation(locked=True, conversation_id=cid),
        )
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.download_audio_file_endpoint(
                conversation_id='conv-1',
                audio_file_id='audio-1',
                request=mock_request,
                uid='user-1',
            )

        assert exc_info.value.status_code == 402

    def test_download_audio_rejects_nonexistent_audio_file_id(self, monkeypatch):
        """Download audio endpoint must return 404 when audio file id is not in conversation."""
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: _make_conversation(deleted=False, conversation_id=cid, audio_files=[]),
        )
        mock_request = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            sync_routes.download_audio_file_endpoint(
                conversation_id='conv-1',
                audio_file_id='unknown-audio',
                request=mock_request,
                uid='user-1',
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == 'Audio file not found in conversation'

    def test_download_audio_allows_active_conversation(self, monkeypatch):
        """Download audio endpoint must succeed for active (non-deleted) conversation."""
        conv = _make_conversation(deleted=False, conversation_id='conv-1')
        monkeypatch.setattr(
            sync_routes.conversations_db,
            'get_conversation',
            lambda uid, cid: conv,
        )
        mock_download = MagicMock(return_value='streaming-response-mock')
        monkeypatch.setattr(sync_routes.sync_playback, 'download_audio_file_response', mock_download)
        mock_request = MagicMock()

        result = sync_routes.download_audio_file_endpoint(
            conversation_id='conv-1',
            audio_file_id='audio-1',
            request=mock_request,
            format='wav',
            uid='user-1',
        )

        assert result == 'streaming-response-mock'
        mock_download.assert_called_once_with(
            'user-1', 'conv-1', 'audio-1', {'id': 'audio-1', 'status': 'ready'}, mock_request, 'wav'
        )
