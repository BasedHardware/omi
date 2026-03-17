"""Unit tests for upload_audio_chunk data_protection_level caching.

Verifies that when data_protection_level is passed to upload_audio_chunk(),
the per-chunk Firestore read (users_db.get_data_protection_level) is skipped.
When not provided, falls back to the DB read for backward compatibility.
"""

import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# Mock heavy dependencies at sys.modules level before importing storage
sys.modules.setdefault("database._client", MagicMock())

# We need the real storage module but with mocked GCS client
_mock_gcs_storage = MagicMock()
_mock_gcs_client_instance = MagicMock()
_mock_gcs_storage.Client.return_value = _mock_gcs_client_instance
sys.modules.setdefault("google.cloud.storage", _mock_gcs_storage)
sys.modules.setdefault("google.cloud.storage.transfer_manager", MagicMock())
sys.modules.setdefault("google.cloud.exceptions", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.service_account", MagicMock())

# Now import the module under test
from utils.other import storage as storage_mod


class TestUploadAudioChunkDataProtectionCache:
    """Tests for the data_protection_level caching in upload_audio_chunk."""

    def _setup_mock_bucket(self):
        """Set up mock bucket and blob for upload tests."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket, mock_blob

    @patch.object(storage_mod, 'users_db')
    def test_skips_db_read_when_level_provided(self, mock_users_db):
        """When data_protection_level is passed, should NOT call Firestore."""
        self._setup_mock_bucket()

        storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='standard',
        )

        mock_users_db.get_data_protection_level.assert_not_called()

    @patch.object(storage_mod, 'users_db')
    def test_falls_back_to_db_when_level_not_provided(self, mock_users_db):
        """When data_protection_level is None (default), should read from Firestore."""
        self._setup_mock_bucket()
        mock_users_db.get_data_protection_level.return_value = 'standard'

        storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
        )

        mock_users_db.get_data_protection_level.assert_called_once_with('test-uid')

    @patch.object(storage_mod, 'users_db')
    def test_standard_level_uploads_unencrypted(self, mock_users_db):
        """Standard protection level should upload .bin (no encryption)."""
        _, mock_blob = self._setup_mock_bucket()

        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='standard',
        )

        assert path.endswith('.bin')
        mock_blob.upload_from_string.assert_called_once()

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_enhanced_level_uploads_encrypted(self, mock_users_db, mock_encryption):
        """Enhanced protection level should encrypt and upload .enc."""
        _, mock_blob = self._setup_mock_bucket()
        mock_encryption.encrypt_audio_chunk.return_value = b'\x01' * 120

        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='enhanced',
        )

        assert path.endswith('.enc')
        mock_encryption.encrypt_audio_chunk.assert_called_once_with(b'\x00' * 100, 'test-uid')

    @patch.object(storage_mod, 'users_db')
    def test_explicit_none_falls_back_to_db(self, mock_users_db):
        """Explicitly passing None should still fall back to DB read."""
        self._setup_mock_bucket()
        mock_users_db.get_data_protection_level.return_value = 'standard'

        storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 100,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level=None,
        )

        mock_users_db.get_data_protection_level.assert_called_once_with('test-uid')
