"""Unit tests for Opus encoding/decoding in private cloud sync.

Verifies:
- PCM→Opus→PCM roundtrip produces same-length output
- Compression ratio is significant (>5x for 5s chunks)
- Feature flag controls whether Opus encoding is used
- Extension handling for .opus, .opus.enc, .bin, .enc
- Timestamp parsing works for double-extension filenames
- Upload produces correct extensions when Opus is enabled
- Download decodes Opus back to PCM
"""

import os
import struct
import sys
from unittest.mock import MagicMock, patch

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


class TestOpusEncodeDecode:
    """Tests for encode_pcm_to_opus and decode_opus_to_pcm."""

    def test_roundtrip_preserves_length(self):
        """Encode→decode produces same number of bytes as input."""
        # 5 seconds of PCM16 at 16kHz mono = 160000 bytes
        pcm_data = b'\x00' * 160000
        opus_data = storage_mod.encode_pcm_to_opus(pcm_data)
        decoded = storage_mod.decode_opus_to_pcm(opus_data)
        assert len(decoded) == len(pcm_data)

    def test_compression_ratio(self):
        """Opus should achieve at least 5x compression on 5s PCM chunks."""
        # Silence compresses very well; real audio ~10-12x
        pcm_data = b'\x00' * 160000
        opus_data = storage_mod.encode_pcm_to_opus(pcm_data)
        ratio = len(pcm_data) / len(opus_data)
        assert ratio > 5.0, f"Compression ratio {ratio:.1f}x is below 5x minimum"

    def test_small_input_padded(self):
        """Input smaller than one frame is padded but trimmed to original length on decode."""
        # 100 bytes = less than one 20ms frame (640 bytes)
        pcm_data = b'\x80' * 100
        opus_data = storage_mod.encode_pcm_to_opus(pcm_data)
        decoded = storage_mod.decode_opus_to_pcm(opus_data)
        # Decoded length equals original input (trimmed from padded frame)
        assert len(decoded) == len(pcm_data)

    def test_exact_frame_boundary(self):
        """Input exactly on frame boundary has no padding."""
        frame_bytes = storage_mod.OPUS_FRAME_SIZE * storage_mod.OPUS_CHANNELS * 2  # 640
        pcm_data = b'\x00' * (frame_bytes * 10)  # exactly 10 frames
        opus_data = storage_mod.encode_pcm_to_opus(pcm_data)
        decoded = storage_mod.decode_opus_to_pcm(opus_data)
        assert len(decoded) == len(pcm_data)

    def test_packet_count_header(self):
        """Opus output starts with correct packet count and original PCM length."""
        frame_bytes = storage_mod.OPUS_FRAME_SIZE * storage_mod.OPUS_CHANNELS * 2
        pcm_data = b'\x00' * (frame_bytes * 5)  # 5 frames
        opus_data = storage_mod.encode_pcm_to_opus(pcm_data)
        packet_count = struct.unpack_from('<I', opus_data, 0)[0]
        original_pcm_len = struct.unpack_from('<I', opus_data, 4)[0]
        assert packet_count == 5
        assert original_pcm_len == len(pcm_data)

    def test_empty_input(self):
        """Empty PCM produces zero packets."""
        opus_data = storage_mod.encode_pcm_to_opus(b'')
        packet_count = struct.unpack_from('<I', opus_data, 0)[0]
        original_pcm_len = struct.unpack_from('<I', opus_data, 4)[0]
        assert packet_count == 0
        assert original_pcm_len == 0
        decoded = storage_mod.decode_opus_to_pcm(opus_data)
        assert decoded == b''


class TestOpusDecodeErrorHandling:
    """Tests for decode_opus_to_pcm error handling with malformed data."""

    def test_truncated_header_raises(self):
        """Data shorter than 8 bytes raises ValueError."""
        with pytest.raises(ValueError, match="too short"):
            storage_mod.decode_opus_to_pcm(b'\x00' * 4)

    def test_truncated_packet_length_raises(self):
        """Truncated data missing packet length raises ValueError."""
        # Header says 1 packet but no packet data follows
        bad_data = struct.pack('<I', 1) + struct.pack('<I', 100)  # pkt_count=1, pcm_len=100
        with pytest.raises(ValueError, match="Truncated"):
            storage_mod.decode_opus_to_pcm(bad_data)

    def test_truncated_packet_body_raises(self):
        """Packet length claims more bytes than available."""
        # Header: 1 packet, pcm_len=640; packet length says 100 but only 5 bytes follow
        bad_data = struct.pack('<I', 1) + struct.pack('<I', 640) + struct.pack('<H', 100) + b'\x00' * 5
        with pytest.raises(ValueError, match="Truncated"):
            storage_mod.decode_opus_to_pcm(bad_data)

    def test_zero_byte_input_raises(self):
        """Completely empty input raises ValueError."""
        with pytest.raises(ValueError, match="too short"):
            storage_mod.decode_opus_to_pcm(b'')


class TestExtensionHelpers:
    """Tests for _get_extension_for_path and _strip_extension."""

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("chunks/uid/conv/1234567890.123.bin", "bin"),
            ("chunks/uid/conv/1234567890.123.enc", "enc"),
            ("chunks/uid/conv/1234567890.123.opus", "opus"),
            ("chunks/uid/conv/1234567890.123.opus.enc", "opus.enc"),
        ],
    )
    def test_get_extension_for_path(self, path, expected):
        assert storage_mod._get_extension_for_path(path) == expected

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("1234567890.123.bin", "1234567890.123"),
            ("1234567890.123.enc", "1234567890.123"),
            ("1234567890.123.opus", "1234567890.123"),
            ("1234567890.123.opus.enc", "1234567890.123"),
        ],
    )
    def test_strip_extension(self, filename, expected):
        assert storage_mod._strip_extension(filename) == expected

    def test_strip_extension_unknown_falls_back(self):
        """Unknown extension falls back to rsplit behavior."""
        assert storage_mod._strip_extension("file.unknown") == "file"


class TestUploadOpusEncoding:
    """Tests for upload_audio_chunk with always-on Opus encoding."""

    def _setup_mock_bucket(self):
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket
        return mock_bucket, mock_blob

    @patch.object(storage_mod, 'users_db')
    def test_opus_standard_extension(self, mock_users_db):
        """Standard upload uses .opus extension."""
        _, mock_blob = self._setup_mock_bucket()

        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 640,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='standard',
        )

        assert path.endswith('.opus')
        assert '.opus.enc' not in path

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_opus_enhanced_extension(self, mock_users_db, mock_encryption):
        """Enhanced upload uses .opus.enc extension."""
        _, mock_blob = self._setup_mock_bucket()
        mock_encryption.encrypt_audio_chunk.return_value = b'\x01' * 50

        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 640,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='enhanced',
        )

        assert path.endswith('.opus.enc')

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_opus_data_passed_to_encryption(self, mock_users_db, mock_encryption):
        """Encrypted upload passes Opus data (not raw PCM) to encryption."""
        _, mock_blob = self._setup_mock_bucket()
        mock_encryption.encrypt_audio_chunk.return_value = b'\x01' * 50

        pcm_data = b'\x00' * 160000
        storage_mod.upload_audio_chunk(
            chunk_data=pcm_data,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='enhanced',
        )

        # The data passed to encrypt should be Opus-encoded (much smaller than 160000)
        call_args = mock_encryption.encrypt_audio_chunk.call_args[0]
        assert len(call_args[0]) < len(pcm_data)


class TestListAudioChunksExtensions:
    """Tests for list_audio_chunks with all extension types."""

    def _make_mock_blob(self, name, size=1000):
        blob = MagicMock()
        blob.name = name
        blob.size = size
        return blob

    def test_lists_all_extension_types(self):
        """list_audio_chunks recognizes .bin, .enc, .opus, .opus.enc."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000.bin', 160000),
            self._make_mock_blob('chunks/uid/conv/1005.000.enc', 160100),
            self._make_mock_blob('chunks/uid/conv/1010.000.opus', 8000),
            self._make_mock_blob('chunks/uid/conv/1015.000.opus.enc', 8100),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 4
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[1]['timestamp'] == 1005.0
        assert chunks[2]['timestamp'] == 1010.0
        assert chunks[3]['timestamp'] == 1015.0

    def test_opus_enc_timestamp_parsing(self):
        """Double extension .opus.enc correctly extracts timestamp."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1234567890.123.opus.enc', 8000),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1234567890.123

    def test_ignores_unknown_extensions(self):
        """Unknown extensions are skipped."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000.bin', 160000),
            self._make_mock_blob('chunks/uid/conv/1005.000.txt', 500),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1


class TestDeleteAudioChunksExtensions:
    """Tests for delete_audio_chunks with all extension types."""

    def test_tries_all_extensions(self):
        """delete_audio_chunks tries .enc, .bin, .opus.enc, .opus."""
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.exists.return_value = False
        mock_bucket.blob.return_value = mock_blob
        storage_mod.storage_client.bucket.return_value = mock_bucket

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0])

        # Should have tried all 4 extensions
        paths_tried = [call[0][0] for call in mock_bucket.blob.call_args_list]
        assert any('.enc' in p and '.opus' not in p for p in paths_tried)
        assert any('.bin' in p for p in paths_tried)
        assert any('.opus.enc' in p for p in paths_tried)
        assert any('.opus' in p and '.enc' not in p for p in paths_tried)


class _FakeNotFound(Exception):
    """Fake NotFound exception for testing (storage_mod.NotFound is mocked)."""

    pass


class TestDownloadFallbackPath:
    """Tests for download_audio_chunks_and_merge fallback behavior."""

    def _blob_factory(self, ext_data_map):
        """Return a blob factory. ext_data_map: dict of ext -> bytes.
        Missing extensions raise _FakeNotFound."""

        def factory(path):
            mock_blob = MagicMock()
            for ext, data in ext_data_map.items():
                if path.endswith(f'.{ext}'):
                    mock_blob.download_as_bytes.return_value = data
                    return mock_blob
            mock_blob.download_as_bytes.side_effect = _FakeNotFound('not found')
            return mock_blob

        return factory

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    @patch.object(storage_mod, 'encryption')
    def test_fallback_opus_corrupt_to_legacy_bin(self, mock_encryption):
        """When .opus.enc exists but decrypt fails, falls back to .bin."""
        mock_bucket = MagicMock()
        pcm_data = b'\x00' * 640

        mock_bucket.blob.side_effect = self._blob_factory(
            {
                'opus.enc': b'corrupt-opus-data',
                'bin': pcm_data,
            }
        )
        storage_mod.storage_client.bucket.return_value = mock_bucket
        mock_encryption.decrypt_audio_file.side_effect = Exception("decrypt failed")

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)
        assert result == pcm_data

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    def test_fallback_all_not_found_raises(self):
        """When no extension exists for a timestamp, raises FileNotFoundError."""
        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = self._blob_factory({})  # nothing available
        storage_mod.storage_client.bucket.return_value = mock_bucket

        with pytest.raises(FileNotFoundError):
            storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    def test_opus_decode_success_no_fallback(self):
        """When .opus chunk is valid, uses it without trying .bin."""
        mock_bucket = MagicMock()
        pcm_data = b'\x00' * 640
        opus_data = storage_mod.encode_pcm_to_opus(pcm_data)

        call_log = []
        original_factory = self._blob_factory({'opus': opus_data})

        def tracking_factory(path):
            call_log.append(path)
            return original_factory(path)

        mock_bucket.blob.side_effect = tracking_factory
        storage_mod.storage_client.bucket.return_value = mock_bucket

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)
        assert len(result) == len(pcm_data)
        # Should NOT have tried .bin after .opus succeeded
        assert not any(p.endswith('.bin') for p in call_log)

    @patch.object(storage_mod, 'NotFound', _FakeNotFound)
    def test_fallback_opus_decode_error_to_bin(self):
        """When .opus data is malformed (decode raises), falls back to .bin."""
        mock_bucket = MagicMock()
        pcm_data = b'\x00' * 640
        bad_opus = b'\x01\x00\x00\x00\x80\x02\x00\x00\xff\xff'  # 1 pkt, pcm_len=640, bad pkt_len

        mock_bucket.blob.side_effect = self._blob_factory(
            {
                'opus': bad_opus,
                'bin': pcm_data,
            }
        )
        storage_mod.storage_client.bucket.return_value = mock_bucket

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)
        assert result == pcm_data


class TestBatchExtensionHelpers:
    """Tests for batch extension support in helpers and PRIVATE_CLOUD_EXTENSIONS."""

    def test_private_cloud_extensions_includes_batch(self):
        """PRIVATE_CLOUD_EXTENSIONS includes .batch.bin and .batch.enc."""
        assert '.batch.bin' in storage_mod.PRIVATE_CLOUD_EXTENSIONS
        assert '.batch.enc' in storage_mod.PRIVATE_CLOUD_EXTENSIONS

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("chunks/uid/conv/1000.000-1010.000.batch.bin", "batch.bin"),
            ("chunks/uid/conv/1000.000-1010.000.batch.enc", "batch.enc"),
            ("chunks/uid/conv/1000.000.batch.bin", "batch.bin"),
        ],
    )
    def test_get_extension_for_batch_path(self, path, expected):
        assert storage_mod._get_extension_for_path(path) == expected

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("1000.000-1010.000.batch.bin", "1000.000-1010.000"),
            ("1000.000-1010.000.batch.enc", "1000.000-1010.000"),
            ("1000.000.batch.bin", "1000.000"),
            ("1000.000.batch.enc", "1000.000"),
        ],
    )
    def test_strip_batch_extension(self, filename, expected):
        assert storage_mod._strip_extension(filename) == expected


class TestListAudioChunksBatch:
    """Tests for list_audio_chunks with batch blobs."""

    def _make_mock_blob(self, name, size=1000):
        blob = MagicMock()
        blob.name = name
        blob.size = size
        return blob

    def test_lists_batch_bin_blobs(self):
        """list_audio_chunks recognizes .batch.bin with range timestamp."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000-1010.000.batch.bin', 480000),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True
        assert chunks[0]['path'] == 'chunks/uid/conv/1000.000-1010.000.batch.bin'

    def test_lists_batch_enc_blobs(self):
        """list_audio_chunks recognizes .batch.enc with range timestamp."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000-1010.000.batch.enc', 500000),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True

    def test_single_timestamp_batch(self):
        """Batch blob with single timestamp (short conversation)."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000.batch.bin', 160000),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True

    def test_mixed_single_and_batch_blobs(self):
        """Conversation with both single-chunk and batch blobs (migration period)."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000.opus', 8000),
            self._make_mock_blob('chunks/uid/conv/1005.000.opus', 8000),
            self._make_mock_blob('chunks/uid/conv/1010.000-1025.000.batch.bin', 480000),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 3
        assert chunks[0]['is_batch'] is False
        assert chunks[1]['is_batch'] is False
        assert chunks[2]['is_batch'] is True
        assert chunks[2]['timestamp'] == 1010.0

    def test_is_batch_false_for_single_blobs(self):
        """Single-chunk blobs have is_batch=False."""
        mock_bucket = MagicMock()
        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000.opus.enc', 8000),
        ]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['is_batch'] is False


class TestDeleteAudioChunksBatch:
    """Tests for delete_audio_chunks with batch blobs."""

    def test_deletes_single_timestamp_batch(self):
        """Finds and deletes batch blob with single timestamp."""
        mock_bucket = MagicMock()
        blob_map = {}

        def blob_factory(path):
            if path not in blob_map:
                b = MagicMock()
                b.name = path
                b.exists.return_value = path.endswith('.batch.bin')
                blob_map[path] = b
            return blob_map[path]

        mock_bucket.blob.side_effect = blob_factory
        mock_bucket.list_blobs.return_value = []
        storage_mod.storage_client.bucket.return_value = mock_bucket

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0])

        batch_path = 'chunks/uid/conv/1000.000.batch.bin'
        assert batch_path in blob_map
        blob_map[batch_path].delete.assert_called_once()

    def test_deletes_range_named_batch_via_scan(self):
        """Finds and deletes range-named batch blob by scanning."""
        mock_bucket = MagicMock()

        single_blob = MagicMock()
        single_blob.exists.return_value = False
        mock_bucket.blob.return_value = single_blob

        batch_blob = MagicMock()
        batch_blob.name = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        mock_bucket.list_blobs.return_value = [batch_blob]
        storage_mod.storage_client.bucket.return_value = mock_bucket

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0, 1005.0, 1010.0])

        batch_blob.delete.assert_called_once()


class TestDownloadBatchBlobs:
    """Tests for download_audio_chunks_and_merge with batch blobs."""

    def _make_mock_blob(self, name, size=1000):
        blob = MagicMock()
        blob.name = name
        blob.size = size
        return blob

    @patch.object(storage_mod, 'NotFound', type('FakeNotFound', (Exception,), {}))
    def test_downloads_batch_blob_once(self):
        """Batch blob covering multiple timestamps is downloaded once."""
        mock_bucket = MagicMock()
        pcm_data = b'\x00' * 480000

        batch_blob_listed = self._make_mock_blob('chunks/uid/conv/1000.000-1010.000.batch.bin', 480000)
        mock_bucket.list_blobs.return_value = [batch_blob_listed]

        download_calls = []

        def blob_factory(path):
            b = MagicMock()
            download_calls.append(path)
            if path == 'chunks/uid/conv/1000.000-1010.000.batch.bin':
                b.download_as_bytes.return_value = pcm_data
            else:
                b.download_as_bytes.side_effect = storage_mod.NotFound('not found')
            return b

        mock_bucket.blob.side_effect = blob_factory
        storage_mod.storage_client.bucket.return_value = mock_bucket

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0, 1005.0, 1010.0], fill_gaps=False)

        assert result == pcm_data
        batch_downloads = [p for p in download_calls if 'batch' in p]
        assert len(batch_downloads) == 1

    @patch.object(storage_mod, 'NotFound', type('FakeNotFound', (Exception,), {}))
    def test_mixed_single_and_batch_download(self):
        """Mix of single-chunk and batch blobs downloads correctly."""
        mock_bucket = MagicMock()
        single_pcm = b'\x01' * 160000
        batch_pcm = b'\x02' * 320000

        mock_bucket.list_blobs.return_value = [
            self._make_mock_blob('chunks/uid/conv/1000.000.opus', 8000),
            self._make_mock_blob('chunks/uid/conv/1005.000-1015.000.batch.bin', 320000),
        ]

        opus_encoded_single = storage_mod.encode_pcm_to_opus(single_pcm)

        def blob_factory(path):
            b = MagicMock()
            if path == 'chunks/uid/conv/1005.000-1015.000.batch.bin':
                b.download_as_bytes.return_value = batch_pcm
            elif path.endswith('.opus') and '1000.000' in path:
                b.download_as_bytes.return_value = opus_encoded_single
            else:
                b.download_as_bytes.side_effect = storage_mod.NotFound('not found')
            return b

        mock_bucket.blob.side_effect = blob_factory
        storage_mod.storage_client.bucket.return_value = mock_bucket

        result = storage_mod.download_audio_chunks_and_merge(
            'uid', 'conv', [1000.0, 1005.0, 1010.0, 1015.0], fill_gaps=False
        )

        assert len(result) == len(single_pcm) + len(batch_pcm)
