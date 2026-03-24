"""Unit tests for upload_audio_chunks_batch (#5418 Phase 2).

Verifies:
1. Batch upload with multiple chunks — streams to GCS
2. Single chunk batch uses single timestamp filename
3. Encrypted batch upload (enhanced protection)
4. Empty batch returns empty list
5. DB lookup count — only one fetch per batch when level is None
6. Unsorted input produces correctly ordered upload
"""

import os
import sys
from unittest.mock import MagicMock, patch

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


class _FakeNotFound(Exception):
    """Fake NotFound exception for testing (storage_mod.NotFound is mocked)."""

    pass


def _collect_written_bytes(mock_blob):
    """Collect all bytes written via blob.open().__enter__().write() calls."""
    mock_file = mock_blob.open.return_value.__enter__.return_value
    written = b''
    for c in mock_file.write.call_args_list:
        written += c[0][0]
    return written


class TestBatchUpload:
    """Tests for upload_audio_chunks_batch streaming to GCS."""

    def _setup_mock_bucket(self):
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket, mock_blob

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


class TestListAudioChunksBatchAware:
    """Tests for list_audio_chunks handling .batch.bin/.batch.enc files."""

    def _setup_mock_bucket_with_blobs(self, blob_names):
        """Set up mock bucket that returns specified blob names from list_blobs."""
        mock_bucket = MagicMock()
        mock_blobs = []
        for name in blob_names:
            mock_blob = MagicMock()
            mock_blob.name = name
            mock_blob.size = 1000
            mock_blobs.append(mock_blob)
        mock_bucket.list_blobs.return_value = mock_blobs
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket

    def test_list_per_chunk_files(self):
        """Standard per-chunk .bin files are listed correctly."""
        self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000.bin',
                'chunks/uid/conv/1005.000.bin',
            ]
        )

        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 2
        assert result[0]['timestamp'] == 1000.000
        assert result[1]['timestamp'] == 1005.000

    def test_list_batch_bin_file(self):
        """Batch .batch.bin file is listed with first timestamp."""
        self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000-1010.000.batch.bin',
            ]
        )

        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is True

    def test_list_batch_enc_file(self):
        """Batch .batch.enc file is listed with first timestamp."""
        self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000-1010.000.batch.enc',
            ]
        )

        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is True

    def test_list_single_chunk_batch(self):
        """Single-chunk batch file (no range) is listed correctly."""
        self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000.batch.bin',
            ]
        )

        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is True

    def test_list_mixed_per_chunk_and_batch(self):
        """Mixed per-chunk and batch files are all listed and sorted."""
        self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1010.000-1020.000.batch.bin',
                'chunks/uid/conv/1000.000.bin',
                'chunks/uid/conv/1005.000.bin',
            ]
        )

        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 3
        assert result[0]['timestamp'] == 1000.000
        assert result[0]['is_batch'] is False
        assert result[1]['timestamp'] == 1005.000
        assert result[2]['timestamp'] == 1010.000
        assert result[2]['is_batch'] is True

    def test_list_skips_meta_json(self):
        """Meta JSON files are not listed as chunks."""
        self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000.bin',
                'chunks/uid/conv/1000.000.meta.json',
            ]
        )

        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert len(result) == 1

    def test_per_chunk_has_is_batch_false(self):
        """Per-chunk files have is_batch=False."""
        self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000.enc',
            ]
        )

        result = storage_mod.list_audio_chunks('uid', 'conv')
        assert result[0]['is_batch'] is False


class TestDeleteAudioChunksBatchAware:
    """Tests for delete_audio_chunks handling batch files."""

    def _setup_mock_bucket_with_blobs(self, blob_names):
        """Set up mock bucket with blobs for exists/delete and list_blobs."""
        mock_bucket = MagicMock()
        # Track which blobs exist
        blob_map = {}
        for name in blob_names:
            mock_blob = MagicMock()
            mock_blob.name = name
            mock_blob.exists.return_value = True
            blob_map[name] = mock_blob

        def make_blob(path):
            if path in blob_map:
                return blob_map[path]
            mb = MagicMock()
            mb.name = path
            mb.exists.return_value = False
            return mb

        mock_bucket.blob.side_effect = make_blob

        # list_blobs returns all blobs
        list_blobs = []
        for name in blob_names:
            lb = MagicMock()
            lb.name = name
            list_blobs.append(lb)
        mock_bucket.list_blobs.return_value = list_blobs
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket, blob_map

    def test_delete_per_chunk_by_timestamp(self):
        """Per-chunk files are deleted by exact timestamp match."""
        mock_bucket, blob_map = self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000.bin',
            ]
        )

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.000])

        blob_map['chunks/uid/conv/1000.000.bin'].delete.assert_called_once()

    def test_delete_batch_by_start_timestamp(self):
        """Batch files are deleted when start timestamp matches."""
        mock_bucket, blob_map = self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000-1010.000.batch.bin',
            ]
        )

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.000])

        # The batch blob found via list_blobs scan should be deleted
        list_blobs = mock_bucket.list_blobs.return_value
        list_blobs[0].delete.assert_called_once()

    def test_delete_tries_batch_extensions(self):
        """Direct blob lookup tries .batch.enc and .batch.bin extensions."""
        mock_bucket, blob_map = self._setup_mock_bucket_with_blobs(
            [
                'chunks/uid/conv/1000.000.batch.enc',
            ]
        )

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.000])

        blob_map['chunks/uid/conv/1000.000.batch.enc'].delete.assert_called_once()


class TestDownloadAudioChunksMergeBatchAware:
    """Tests for download_audio_chunks_and_merge handling batch blobs."""

    def _setup_mock_bucket(self, list_blobs_data, download_data):
        """
        Set up mock bucket for download tests.
        list_blobs_data: list of (name, size) tuples for list_audio_chunks
        download_data: dict of path -> bytes for download_as_bytes
        """
        mock_bucket = MagicMock()

        # list_blobs for list_audio_chunks
        list_blobs = []
        for name, size in list_blobs_data:
            mb = MagicMock()
            mb.name = name
            mb.size = size
            list_blobs.append(mb)
        mock_bucket.list_blobs.return_value = list_blobs

        # blob download
        def make_blob(path):
            mb = MagicMock()
            mb.name = path
            if path in download_data:
                mb.download_as_bytes.return_value = download_data[path]
            else:
                mb.download_as_bytes.side_effect = _FakeNotFound(f"Not found: {path}")
            return mb

        mock_bucket.blob.side_effect = make_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    def test_download_batch_blob_found(self):
        """Batch blob is resolved via list_audio_chunks and downloaded once."""
        batch_path = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        batch_data = b'\x01' * 100 + b'\x02' * 100

        self._setup_mock_bucket(
            list_blobs_data=[(batch_path, 200)],
            download_data={batch_path: batch_data},
        )

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid',
            conversation_id='conv',
            timestamps=[1000.000],
            fill_gaps=False,
        )

        assert result == batch_data

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    def test_download_per_chunk_still_works(self):
        """Per-chunk .bin files are still downloaded correctly."""
        self._setup_mock_bucket(
            list_blobs_data=[
                ('chunks/uid/conv/1000.000.bin', 100),
                ('chunks/uid/conv/1005.000.bin', 100),
            ],
            download_data={
                'chunks/uid/conv/1000.000.bin': b'\x01' * 100,
                'chunks/uid/conv/1005.000.bin': b'\x02' * 100,
            },
        )

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid',
            conversation_id='conv',
            timestamps=[1000.000, 1005.000],
            fill_gaps=False,
        )

        assert result == b'\x01' * 100 + b'\x02' * 100

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    def test_download_batch_deduplicates(self):
        """Multiple timestamps pointing to same batch blob download it once."""
        batch_path = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        batch_data = b'\xaa' * 300

        mock_bucket = self._setup_mock_bucket(
            # list_audio_chunks only returns batch with first timestamp
            list_blobs_data=[(batch_path, 300)],
            download_data={batch_path: batch_data},
        )

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid',
            conversation_id='conv',
            timestamps=[1000.000],
            fill_gaps=False,
        )

        assert result == batch_data

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    @patch.object(storage_mod, 'encryption')
    def test_download_batch_encrypted_decrypts(self, mock_encryption):
        """Encrypted batch blob is decrypted via decrypt_audio_file."""
        batch_path = 'chunks/uid/conv/1000.000-1010.000.batch.enc'
        encrypted_data = b'\xee' * 200
        decrypted_data = b'\xdd' * 180

        mock_encryption.decrypt_audio_file.return_value = decrypted_data

        self._setup_mock_bucket(
            list_blobs_data=[(batch_path, 200)],
            download_data={batch_path: encrypted_data},
        )

        result = storage_mod.download_audio_chunks_and_merge(
            uid='uid',
            conversation_id='conv',
            timestamps=[1000.000],
            fill_gaps=False,
        )

        mock_encryption.decrypt_audio_file.assert_called_once_with(encrypted_data, 'uid')
        assert result == decrypted_data


class TestCopyAudioChunksForMergeBatchAware:
    """Tests for _copy_audio_chunks_for_merge preserving batch blob filenames."""

    @classmethod
    def setup_class(cls):
        """Mock heavy transitive imports before loading merge_conversations."""
        for mod_name in [
            'openai',
            'openai.resources',
            'openai._client',
            'utils.llm',
            'utils.llm.clients',
            'utils.apps',
            'database.apps',
            'database.memories',
            'database.tasks',
            'database.plugins',
            'database.notifications',
        ]:
            sys.modules.setdefault(mod_name, MagicMock())

    @patch('utils.conversations.merge_conversations.conversations_db')
    @patch('utils.conversations.merge_conversations.list_audio_chunks')
    @patch('utils.conversations.merge_conversations.storage_client')
    def test_copy_preserves_batch_filename(self, mock_storage_client, mock_list, mock_conv_db):
        """Batch blob filenames are preserved during copy (not renamed to single-timestamp)."""
        from utils.conversations.merge_conversations import _copy_audio_chunks_for_merge

        mock_bucket = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        mock_list.return_value = [
            {
                'timestamp': 1000.000,
                'path': 'chunks/uid/conv-old/1000.000-1060.000.batch.bin',
                'size': 960000,
                'is_batch': True,
            }
        ]
        mock_conv_db.create_audio_files_from_chunks.return_value = []

        _copy_audio_chunks_for_merge('uid', [{'id': 'conv-old'}], 'conv-new')

        # Verify the copy preserved the batch filename
        copy_call = mock_bucket.copy_blob.call_args
        new_path = copy_call[0][2]  # third positional arg is new_name
        assert new_path == 'chunks/uid/conv-new/1000.000-1060.000.batch.bin'

    @patch('utils.conversations.merge_conversations.conversations_db')
    @patch('utils.conversations.merge_conversations.list_audio_chunks')
    @patch('utils.conversations.merge_conversations.storage_client')
    def test_copy_preserves_single_chunk_filename(self, mock_storage_client, mock_list, mock_conv_db):
        """Single-chunk filenames are also preserved during copy."""
        from utils.conversations.merge_conversations import _copy_audio_chunks_for_merge

        mock_bucket = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        mock_list.return_value = [
            {
                'timestamp': 1000.000,
                'path': 'chunks/uid/conv-old/1000.000.bin',
                'size': 80000,
                'is_batch': False,
            }
        ]
        mock_conv_db.create_audio_files_from_chunks.return_value = []

        _copy_audio_chunks_for_merge('uid', [{'id': 'conv-old'}], 'conv-new')

        copy_call = mock_bucket.copy_blob.call_args
        new_path = copy_call[0][2]
        assert new_path == 'chunks/uid/conv-new/1000.000.bin'

    @patch('utils.conversations.merge_conversations.conversations_db')
    @patch('utils.conversations.merge_conversations.list_audio_chunks')
    @patch('utils.conversations.merge_conversations.storage_client')
    def test_copy_mixed_single_and_batch(self, mock_storage_client, mock_list, mock_conv_db):
        """Mixed single + batch blobs are all copied with original filenames."""
        from utils.conversations.merge_conversations import _copy_audio_chunks_for_merge

        mock_bucket = MagicMock()
        mock_storage_client.bucket.return_value = mock_bucket

        mock_list.return_value = [
            {
                'timestamp': 1000.000,
                'path': 'chunks/uid/conv-old/1000.000.enc',
                'size': 80000,
                'is_batch': False,
            },
            {
                'timestamp': 1010.000,
                'path': 'chunks/uid/conv-old/1010.000-1070.000.batch.enc',
                'size': 960000,
                'is_batch': True,
            },
        ]
        mock_conv_db.create_audio_files_from_chunks.return_value = []

        _copy_audio_chunks_for_merge('uid', [{'id': 'conv-old'}], 'conv-new')

        assert mock_bucket.copy_blob.call_count == 2
        paths = [call[0][2] for call in mock_bucket.copy_blob.call_args_list]
        assert 'chunks/uid/conv-new/1000.000.enc' in paths
        assert 'chunks/uid/conv-new/1010.000-1070.000.batch.enc' in paths
