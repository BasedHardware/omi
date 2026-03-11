"""Unit tests for upload_audio_chunks_batch (#5418 Phase 2).

Verifies:
1. Batch upload with multiple chunks (flag enabled)
2. Single chunk fallback (flag enabled)
3. Encrypted batch upload (flag enabled, enhanced protection)
4. Flag disabled behavior (falls back to per-chunk upload_audio_chunk)
5. Empty batch returns empty list
6. DB lookup count — only one fetch per batch when level is None
7. Unsorted input produces correctly ordered upload
"""

import os
import sys
from unittest.mock import MagicMock, patch, call

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

# Mock heavy dependencies at sys.modules level before importing storage
sys.modules.setdefault("database._client", MagicMock())

_mock_gcs_storage = MagicMock()
_mock_gcs_client_instance = MagicMock()
_mock_gcs_storage.Client.return_value = _mock_gcs_client_instance
sys.modules.setdefault("google.cloud.storage", _mock_gcs_storage)
sys.modules.setdefault("google.cloud.storage.transfer_manager", MagicMock())
sys.modules.setdefault("google.cloud.exceptions", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.service_account", MagicMock())

from utils.other import storage as storage_mod


class TestBatchUploadFlagEnabled:
    """Tests with PRIVATE_CLOUD_BATCH_ENABLED = True."""

    def _setup_mock_bucket(self):
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket, mock_blob

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_batch_multiple_chunks_standard(self, mock_users_db):
        """Multiple chunks uploaded as single concatenated .batch.bin object."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [
            {'data': b'\x01' * 100, 'timestamp': 1000.000},
            {'data': b'\x02' * 100, 'timestamp': 1005.000},
            {'data': b'\x03' * 100, 'timestamp': 1010.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        assert len(paths) == 1
        assert paths[0].endswith('.batch.bin')
        assert '1000.000-1010.000' in paths[0]
        mock_blob.upload_from_string.assert_called_once()
        # Verify concatenated data is 300 bytes
        uploaded_data = mock_blob.upload_from_string.call_args[0][0]
        assert len(uploaded_data) == 300
        assert uploaded_data[:100] == b'\x01' * 100
        assert uploaded_data[100:200] == b'\x02' * 100
        assert uploaded_data[200:] == b'\x03' * 100

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_single_chunk_batch(self, mock_users_db):
        """Single chunk batch uses single timestamp in filename."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [{'data': b'\x01' * 50, 'timestamp': 1000.000}]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        assert len(paths) == 1
        assert '1000.000.batch.bin' in paths[0]
        mock_blob.upload_from_string.assert_called_once()

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_batch_encrypted(self, mock_users_db, mock_encryption):
        """Enhanced protection encrypts each chunk and concatenates."""
        mock_bucket, mock_blob = self._setup_mock_bucket()
        # Each encrypted chunk returns 120 bytes (simulating length-prefix + nonce + ciphertext)
        mock_encryption.encrypt_audio_chunk.return_value = b'\xee' * 120

        chunks = [
            {'data': b'\x01' * 100, 'timestamp': 1000.000},
            {'data': b'\x02' * 100, 'timestamp': 1005.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='enhanced',
        )

        assert len(paths) == 1
        assert paths[0].endswith('.batch.enc')
        assert mock_encryption.encrypt_audio_chunk.call_count == 2
        # Verify concatenated encrypted data is 240 bytes
        uploaded_data = mock_blob.upload_from_string.call_args[0][0]
        assert len(uploaded_data) == 240

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_empty_batch_returns_empty(self, mock_users_db):
        """Empty chunk list returns empty list without any GCS ops."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=[],
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        assert paths == []
        mock_blob.upload_from_string.assert_not_called()

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_db_lookup_once_per_batch(self, mock_users_db):
        """When data_protection_level is None, DB is queried exactly once per batch."""
        mock_bucket, mock_blob = self._setup_mock_bucket()
        mock_users_db.get_data_protection_level.return_value = 'standard'

        chunks = [
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
            {'data': b'\x02' * 50, 'timestamp': 1005.000},
            {'data': b'\x03' * 50, 'timestamp': 1010.000},
        ]

        storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
        )

        mock_users_db.get_data_protection_level.assert_called_once_with('test-uid')

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_unsorted_input_produces_ordered_upload(self, mock_users_db):
        """Chunks provided out of order are sorted by timestamp before upload."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [
            {'data': b'\x03' * 50, 'timestamp': 1010.000},
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
            {'data': b'\x02' * 50, 'timestamp': 1005.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        # Filename should reflect sorted order: first_ts-last_ts
        assert '1000.000-1010.000' in paths[0]
        # Uploaded data should be in timestamp order
        uploaded_data = mock_blob.upload_from_string.call_args[0][0]
        assert uploaded_data[:50] == b'\x01' * 50
        assert uploaded_data[50:100] == b'\x02' * 50
        assert uploaded_data[100:] == b'\x03' * 50

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_skips_db_when_level_provided(self, mock_users_db):
        """When data_protection_level is explicitly provided, no DB read."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        storage_mod.upload_audio_chunks_batch(
            chunks=[{'data': b'\x01' * 50, 'timestamp': 1000.000}],
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        mock_users_db.get_data_protection_level.assert_not_called()


class TestBatchUploadFlagDisabled:
    """Tests with PRIVATE_CLOUD_BATCH_ENABLED = False (default)."""

    def _setup_mock_bucket(self):
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket, mock_blob

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', False)
    @patch.object(storage_mod, 'users_db')
    def test_flag_disabled_falls_back_to_per_chunk(self, mock_users_db):
        """When flag is disabled, each chunk is uploaded individually via upload_audio_chunk."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [
            {'data': b'\x01' * 100, 'timestamp': 1000.000},
            {'data': b'\x02' * 100, 'timestamp': 1005.000},
            {'data': b'\x03' * 100, 'timestamp': 1010.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        # Should return 3 individual paths (one per chunk)
        assert len(paths) == 3
        for p in paths:
            assert p.endswith('.bin')
            assert '.batch.' not in p
        # 3 individual uploads
        assert mock_blob.upload_from_string.call_count == 3

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', False)
    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_flag_disabled_encrypted_falls_back(self, mock_users_db, mock_encryption):
        """When flag is disabled with enhanced protection, falls back to per-chunk encrypted uploads."""
        mock_bucket, mock_blob = self._setup_mock_bucket()
        mock_encryption.encrypt_audio_chunk.return_value = b'\xee' * 120

        chunks = [
            {'data': b'\x01' * 100, 'timestamp': 1000.000},
            {'data': b'\x02' * 100, 'timestamp': 1005.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='enhanced',
        )

        assert len(paths) == 2
        for p in paths:
            assert p.endswith('.enc')
            assert '.batch.' not in p

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', False)
    @patch.object(storage_mod, 'users_db')
    def test_flag_disabled_empty_batch(self, mock_users_db):
        """Empty batch with flag disabled returns empty list."""
        self._setup_mock_bucket()

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=[],
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        assert paths == []

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', False)
    @patch.object(storage_mod, 'users_db')
    def test_flag_disabled_preserves_timestamp_order(self, mock_users_db):
        """Even in fallback mode, chunks are uploaded in timestamp order."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [
            {'data': b'\x03' * 50, 'timestamp': 1010.000},
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        # First path should have the earlier timestamp
        assert '1000.000' in paths[0]
        assert '1010.000' in paths[1]
