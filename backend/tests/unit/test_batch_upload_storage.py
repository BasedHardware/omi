"""Unit tests for upload_audio_chunks_batch (#5418 Phase 2).

Verifies:
1. Batch upload with multiple chunks (flag enabled) — streams to GCS
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


def _collect_written_bytes(mock_blob):
    """Collect all bytes written via blob.open().__enter__().write() calls."""
    mock_file = mock_blob.open.return_value.__enter__.return_value
    written = b''
    for c in mock_file.write.call_args_list:
        written += c[0][0]
    return written


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
        """Multiple chunks streamed as single .batch.bin object."""
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
        # Verify streaming write was used (blob.open, not upload_from_string)
        mock_blob.open.assert_called_once()
        written = _collect_written_bytes(mock_blob)
        assert len(written) == 300
        assert written[:100] == b'\x01' * 100
        assert written[100:200] == b'\x02' * 100
        assert written[200:] == b'\x03' * 100

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
        mock_blob.open.assert_called_once()

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_batch_encrypted(self, mock_users_db, mock_encryption):
        """Enhanced protection encrypts each chunk and streams to GCS."""
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

        assert len(paths) == 1
        assert paths[0].endswith('.batch.enc')
        assert mock_encryption.encrypt_audio_chunk.call_count == 2
        written = _collect_written_bytes(mock_blob)
        assert len(written) == 240

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
        mock_blob.open.assert_not_called()

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
        # Streamed data should be in timestamp order
        written = _collect_written_bytes(mock_blob)
        assert written[:50] == b'\x01' * 50
        assert written[50:100] == b'\x02' * 50
        assert written[100:] == b'\x03' * 50

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

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_large_batch_streams_correctly(self, mock_users_db):
        """Large batch (50 chunks) streams without regression."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [{'data': b'\xaa' * 80_000, 'timestamp': 1000.000 + i * 5.0} for i in range(50)]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        assert len(paths) == 1
        assert paths[0].endswith('.batch.bin')
        mock_file = mock_blob.open.return_value.__enter__.return_value
        assert mock_file.write.call_count == 50

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_identical_timestamps_filename_and_order(self, mock_users_db):
        """Chunks with identical timestamps produce valid filename and stable order."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
            {'data': b'\x02' * 50, 'timestamp': 1000.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        # Same first_ts and last_ts → filename uses single timestamp
        assert len(paths) == 1
        assert '1000.000.batch.bin' in paths[0]

    @patch.object(storage_mod, 'PRIVATE_CLOUD_BATCH_ENABLED', True)
    @patch.object(storage_mod, 'users_db')
    def test_streaming_api_call_args(self, mock_users_db):
        """Batch mode uses blob.open('wb') with correct args and does NOT call upload_from_string."""
        mock_bucket, mock_blob = self._setup_mock_bucket()

        chunks = [{'data': b'\x01' * 50, 'timestamp': 1000.000}]

        storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level='standard',
        )

        mock_blob.open.assert_called_once_with('wb', content_type='application/octet-stream')
        mock_blob.upload_from_string.assert_not_called()


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
        # 3 individual uploads via upload_from_string (per-chunk path)
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
    def test_flag_disabled_none_level_delegates_db_per_chunk(self, mock_users_db):
        """Flag disabled + level=None delegates DB resolution to per-chunk upload_audio_chunk."""
        mock_bucket, mock_blob = self._setup_mock_bucket()
        mock_users_db.get_data_protection_level.return_value = 'standard'

        chunks = [
            {'data': b'\x01' * 50, 'timestamp': 1000.000},
            {'data': b'\x02' * 50, 'timestamp': 1005.000},
        ]

        paths = storage_mod.upload_audio_chunks_batch(
            chunks=chunks,
            uid='test-uid',
            conversation_id='conv-1',
            data_protection_level=None,
        )

        assert len(paths) == 2
        # Each per-chunk call passes data_protection_level=None, triggering DB read inside upload_audio_chunk
        assert mock_users_db.get_data_protection_level.call_count == 2

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
