"""Unit tests for Opus encoding/decoding + audio-chunk storage in private cloud sync.

Verifies:
- PCM→Opus→PCM roundtrip produces same-length output
- Compression ratio is significant (>5x for 5s chunks)
- Extension handling for .opus, .opus.enc, .bin, .enc (+ batch variants)
- Timestamp parsing works for double-extension filenames
- Upload produces correct extensions when Opus is enabled
- Download decodes Opus back to PCM, with fallback across extensions

Storage-backed tests run against the neutral object-store port via an in-memory FakeObjectStore
(ADR-0032); storage.py migrated off the raw GCS client, so the old ``storage_client`` MagicMock seam
is gone and these exercise the real port path.
"""

import struct
from unittest.mock import patch

import pytest

from utils.other import storage as storage_mod
from tests.object_store_fakes import FakeObjectStore

requires_native_opus = pytest.mark.skipif(storage_mod.opuslib is None, reason="native libopus is not installed")


@pytest.fixture(autouse=True)
def store(monkeypatch):
    """Point storage.py's object-store seam at a fresh in-memory FakeObjectStore per test."""
    fake = FakeObjectStore()
    monkeypatch.setattr(storage_mod, "_object_store", lambda: fake)
    return fake


def _bucket() -> str:
    return storage_mod.private_cloud_sync_bucket


@requires_native_opus
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


@requires_native_opus
class TestUploadOpusEncoding:
    """Tests for upload_audio_chunk with always-on Opus encoding."""

    @patch.object(storage_mod, 'users_db')
    def test_opus_standard_extension(self, mock_users_db, store):
        """Standard upload uses .opus extension."""
        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 640,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='standard',
        )

        assert path.endswith('.opus')
        assert '.opus.enc' not in path
        assert store.exists(_bucket(), path)

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_opus_enhanced_extension(self, mock_users_db, mock_encryption, store):
        """Enhanced upload uses .opus.enc extension."""
        mock_encryption.encrypt_audio_chunk.return_value = b'\x01' * 50

        path = storage_mod.upload_audio_chunk(
            chunk_data=b'\x00' * 640,
            uid='test-uid',
            conversation_id='conv-1',
            timestamp=1234567890.123,
            data_protection_level='enhanced',
        )

        assert path.endswith('.opus.enc')
        assert store.exists(_bucket(), path)

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_opus_data_passed_to_encryption(self, mock_users_db, mock_encryption, store):
        """Encrypted upload passes Opus data (not raw PCM) to encryption."""
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

    def test_lists_all_extension_types(self, store):
        """list_audio_chunks recognizes .bin, .enc, .opus, .opus.enc."""
        for name in (
            'chunks/uid/conv/1000.000.bin',
            'chunks/uid/conv/1005.000.enc',
            'chunks/uid/conv/1010.000.opus',
            'chunks/uid/conv/1015.000.opus.enc',
        ):
            store.put(_bucket(), name, b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 4
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[1]['timestamp'] == 1005.0
        assert chunks[2]['timestamp'] == 1010.0
        assert chunks[3]['timestamp'] == 1015.0

    def test_opus_enc_timestamp_parsing(self, store):
        """Double extension .opus.enc correctly extracts timestamp."""
        store.put(_bucket(), 'chunks/uid/conv/1234567890.123.opus.enc', b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1234567890.123

    def test_ignores_unknown_extensions(self, store):
        """Unknown extensions are skipped."""
        store.put(_bucket(), 'chunks/uid/conv/1000.000.bin', b'x')
        store.put(_bucket(), 'chunks/uid/conv/1005.000.txt', b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1


class TestDeleteAudioChunksExtensions:
    """Tests for delete_audio_chunks with all extension types."""

    def test_tries_all_extensions(self, store):
        """delete_audio_chunks removes every single-chunk extension for the timestamp."""
        for ext in ('.opus.enc', '.enc', '.opus', '.bin'):
            store.put(_bucket(), f'chunks/uid/conv/1000.000{ext}', b'x')

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0])

        assert store.list(_bucket(), 'chunks/uid/conv/') == []


class TestDownloadFallbackPath:
    """Tests for download_audio_chunks_and_merge fallback behavior."""

    def test_fallback_opus_corrupt_to_legacy_bin(self, store):
        """When .opus.enc exists but decrypt fails, falls back to .bin."""
        pcm_data = b'\x00' * 640
        store.put(_bucket(), 'chunks/uid/conv/1000.000.opus.enc', b'corrupt-opus-data')
        store.put(_bucket(), 'chunks/uid/conv/1000.000.bin', pcm_data)

        with patch.object(storage_mod, 'encryption') as mock_encryption:
            mock_encryption.decrypt_audio_file.side_effect = Exception("decrypt failed")
            result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)

        assert result == pcm_data

    def test_fallback_all_not_found_raises(self, store):
        """When no extension exists for a timestamp, raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)

    @requires_native_opus
    def test_opus_decode_success_no_fallback(self, store):
        """When .opus chunk is valid, uses it and does not fall through to .bin."""
        pcm_data = b'\x00' * 640
        opus_data = storage_mod.encode_pcm_to_opus(pcm_data)
        store.put(_bucket(), 'chunks/uid/conv/1000.000.opus', opus_data)
        store.put(_bucket(), 'chunks/uid/conv/1000.000.bin', b'\xff' * 640)  # different: proves opus won

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)

        # decoded from .opus (lossy ~silence), NOT the distinctive .bin bytes -> opus short-circuited bin
        assert len(result) == len(pcm_data)
        assert result != b'\xff' * 640

    def test_fallback_opus_decode_error_to_bin(self, store):
        """When .opus data is malformed (decode raises), falls back to .bin."""
        pcm_data = b'\x00' * 640
        bad_opus = b'\x01\x00\x00\x00\x80\x02\x00\x00\xff\xff'  # 1 pkt, pcm_len=640, bad pkt_len
        store.put(_bucket(), 'chunks/uid/conv/1000.000.opus', bad_opus)
        store.put(_bucket(), 'chunks/uid/conv/1000.000.bin', pcm_data)

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

    def test_lists_batch_bin_blobs(self, store):
        """list_audio_chunks recognizes .batch.bin with range timestamp."""
        store.put(_bucket(), 'chunks/uid/conv/1000.000-1010.000.batch.bin', b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True
        assert chunks[0]['path'] == 'chunks/uid/conv/1000.000-1010.000.batch.bin'

    def test_lists_batch_enc_blobs(self, store):
        """list_audio_chunks recognizes .batch.enc with range timestamp."""
        store.put(_bucket(), 'chunks/uid/conv/1000.000-1010.000.batch.enc', b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True

    def test_single_timestamp_batch(self, store):
        """Batch blob with single timestamp (short conversation)."""
        store.put(_bucket(), 'chunks/uid/conv/1000.000.batch.bin', b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True

    def test_mixed_single_and_batch_blobs(self, store):
        """Conversation with both single-chunk and batch blobs (migration period)."""
        for name in (
            'chunks/uid/conv/1000.000.opus',
            'chunks/uid/conv/1005.000.opus',
            'chunks/uid/conv/1010.000-1025.000.batch.bin',
        ):
            store.put(_bucket(), name, b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 3
        assert chunks[0]['is_batch'] is False
        assert chunks[1]['is_batch'] is False
        assert chunks[2]['is_batch'] is True
        assert chunks[2]['timestamp'] == 1010.0

    def test_is_batch_false_for_single_blobs(self, store):
        """Single-chunk blobs have is_batch=False."""
        store.put(_bucket(), 'chunks/uid/conv/1000.000.opus.enc', b'x')

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['is_batch'] is False


class TestDeleteAudioChunksBatch:
    """Tests for delete_audio_chunks with batch blobs."""

    def test_deletes_single_timestamp_batch(self, store):
        """Finds and deletes batch blob with single timestamp."""
        path = 'chunks/uid/conv/1000.000.batch.bin'
        store.put(_bucket(), path, b'x')

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0])

        assert not store.exists(_bucket(), path)

    def test_deletes_range_named_batch_via_scan(self, store):
        """Finds and deletes range-named batch blob by scanning."""
        path = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        store.put(_bucket(), path, b'x')

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0, 1005.0, 1010.0])

        assert not store.exists(_bucket(), path)


class TestDownloadBatchBlobs:
    """Tests for download_audio_chunks_and_merge with batch blobs."""

    def test_downloads_batch_blob_once(self, store, monkeypatch):
        """Batch blob covering multiple timestamps is downloaded once."""
        pcm_data = b'\x00' * 480000
        store.put(_bucket(), 'chunks/uid/conv/1000.000-1010.000.batch.bin', pcm_data)

        downloads = []
        orig_get = store.get_bytes
        monkeypatch.setattr(store, 'get_bytes', lambda b, k: (downloads.append(k), orig_get(b, k))[1])

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0, 1005.0, 1010.0], fill_gaps=False)

        assert result == pcm_data
        assert len([p for p in downloads if 'batch' in p]) == 1

    @requires_native_opus
    def test_mixed_single_and_batch_download(self, store):
        """Mix of single-chunk and batch blobs downloads correctly."""
        single_pcm = b'\x01' * 160000
        batch_pcm = b'\x02' * 320000
        store.put(_bucket(), 'chunks/uid/conv/1000.000.opus', storage_mod.encode_pcm_to_opus(single_pcm))
        store.put(_bucket(), 'chunks/uid/conv/1005.000-1015.000.batch.bin', batch_pcm)

        result = storage_mod.download_audio_chunks_and_merge(
            'uid', 'conv', [1000.0, 1005.0, 1010.0, 1015.0], fill_gaps=False
        )

        assert len(result) == len(single_pcm) + len(batch_pcm)
