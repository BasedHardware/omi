"""Tests for sync router audio playback and download tombstone guards.

Contract:
- Soft-deleted conversations (``deleted: True``) must be rejected with HTTP 404
  across all audio playback and download endpoints:
  1. POST /v1/sync/audio/{conversation_id}/precache
  2. GET /v1/sync/audio/{conversation_id}/urls
  3. GET /v1/sync/audio/{conversation_id}/{audio_file_id}
- Live, active conversations proceed normally.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

os.environ.setdefault('TYPESENSE_API_KEY', 'test-typesense-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')
os.environ.setdefault('TYPESENSE_PROTOCOL', 'http')
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import database.conversations as conversations_db
import routers.sync as routers_sync

UID = "test-uid-1"
CONV_ID = "test-conv-1"
AUDIO_FILE_ID = "audio-file-1"


def _make_conversation(deleted: bool = False, is_locked: bool = False) -> dict:
    return {
        "id": CONV_ID,
        "uid": UID,
        "deleted": deleted,
        "is_locked": is_locked,
        "audio_files": [{"id": AUDIO_FILE_ID, "chunk_timestamps": [100.0, 101.0]}],
    }


class TestSyncAudioPrecacheTombstoneGuard:
    def test_precache_rejects_soft_deleted_tombstone(self):
        conv = _make_conversation(deleted=True)
        with patch.object(conversations_db, "get_conversation", return_value=conv), patch(
            "utils.sync.playback.precache_audio_files"
        ) as mock_precache:
            with pytest.raises(HTTPException) as exc_info:
                routers_sync.precache_conversation_audio_endpoint(CONV_ID, uid=UID)
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "Conversation not found"
            mock_precache.assert_not_called()

    def test_precache_succeeds_for_live_conversation(self):
        conv = _make_conversation(deleted=False)
        sentinel = {"status": "ok", "cached_files": 1}
        with patch.object(conversations_db, "get_conversation", return_value=conv), patch(
            "utils.sync.playback.precache_audio_files", return_value=sentinel
        ) as mock_precache:
            res = routers_sync.precache_conversation_audio_endpoint(CONV_ID, uid=UID)
            assert res == sentinel
            mock_precache.assert_called_once_with(UID, CONV_ID, conv["audio_files"])


class TestSyncAudioSignedUrlsTombstoneGuard:
    def test_urls_rejects_soft_deleted_tombstone(self):
        conv = _make_conversation(deleted=True)
        with patch.object(conversations_db, "get_conversation", return_value=conv), patch(
            "utils.sync.playback.get_audio_signed_urls"
        ) as mock_urls:
            with pytest.raises(HTTPException) as exc_info:
                routers_sync.get_audio_signed_urls_endpoint(CONV_ID, uid=UID)
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "Conversation not found"
            mock_urls.assert_not_called()

    def test_urls_succeeds_for_live_conversation(self):
        conv = _make_conversation(deleted=False)
        sentinel = {"files": [{"id": AUDIO_FILE_ID, "status": "ready"}]}
        with patch.object(conversations_db, "get_conversation", return_value=conv), patch(
            "utils.sync.playback.get_audio_signed_urls", return_value=sentinel
        ) as mock_urls:
            res = routers_sync.get_audio_signed_urls_endpoint(CONV_ID, uid=UID)
            assert res == sentinel
            mock_urls.assert_called_once_with(UID, CONV_ID, conv["audio_files"], conversation=conv)


class TestSyncAudioDownloadTombstoneGuard:
    def test_download_rejects_soft_deleted_tombstone(self):
        conv = _make_conversation(deleted=True)
        req = MagicMock()
        with patch.object(conversations_db, "get_conversation", return_value=conv), patch(
            "utils.sync.playback.download_audio_file_response"
        ) as mock_download:
            with pytest.raises(HTTPException) as exc_info:
                routers_sync.download_audio_file_endpoint(CONV_ID, AUDIO_FILE_ID, request=req, uid=UID)
            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == "Conversation not found"
            mock_download.assert_not_called()

    def test_download_succeeds_for_live_conversation(self):
        conv = _make_conversation(deleted=False)
        req = MagicMock()
        sentinel_resp = MagicMock()
        with patch.object(conversations_db, "get_conversation", return_value=conv), patch(
            "utils.sync.playback.download_audio_file_response", return_value=sentinel_resp
        ) as mock_download:
            res = routers_sync.download_audio_file_endpoint(CONV_ID, AUDIO_FILE_ID, request=req, format="wav", uid=UID)
            assert res is sentinel_resp
            mock_download.assert_called_once_with(UID, CONV_ID, AUDIO_FILE_ID, conv["audio_files"][0], req, "wav")
