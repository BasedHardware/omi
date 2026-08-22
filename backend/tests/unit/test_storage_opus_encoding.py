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

import struct
from unittest.mock import MagicMock, patch

import pytest

from utils.other import storage as storage_mod
from tests.object_store_fakes import FakeObjectStore

requires_native_opus = pytest.mark.skipif(storage_mod.opuslib is None, reason="native libopus is not installed")


class _RecordingObjectStore(FakeObjectStore):
    """FakeObjectStore that records delete/get_bytes keys, so tests can assert which extensions the
    delete/download fallback tried (was the GCS ``mock_bucket.blob.call_args_list`` inspection)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deleted: list[str] = []
        self.fetched: list[str] = []

    def delete(self, bucket, key):
        self.deleted.append(key)
        return super().delete(bucket, key)

    def get_bytes(self, bucket, key):
        self.fetched.append(key)
        return super().get_bytes(bucket, key)


@pytest.fixture(autouse=True)
def _object_store(monkeypatch):
    """storage.py reads/writes through the neutral object-store port (_object_store()), not a raw
    GCS storage_client. Inject a fresh in-memory recording FakeObjectStore per test so upload/list/
    delete/download run against it; tests seed and assert on it via ``storage_mod._object_store()``."""
    store = _RecordingObjectStore()
    monkeypatch.setattr(storage_mod, "_object_store", lambda: store)
    return store


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
    def test_opus_standard_extension(self, mock_users_db):
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

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_opus_enhanced_extension(self, mock_users_db, mock_encryption):
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

    @patch.object(storage_mod, 'encryption')
    @patch.object(storage_mod, 'users_db')
    def test_opus_data_passed_to_encryption(self, mock_users_db, mock_encryption):
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

    def _seed(self, name, size=1000):
        # list_audio_chunks reads _object_store().list(bucket, prefix); seed keys into the fake store.
        storage_mod._object_store().put(storage_mod.private_cloud_sync_bucket, name, b'\x00' * size)

    def test_lists_all_extension_types(self):
        """list_audio_chunks recognizes .bin, .enc, .opus, .opus.enc."""
        self._seed('chunks/uid/conv/1000.000.bin', 160000)
        self._seed('chunks/uid/conv/1005.000.enc', 160100)
        self._seed('chunks/uid/conv/1010.000.opus', 8000)
        self._seed('chunks/uid/conv/1015.000.opus.enc', 8100)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 4
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[1]['timestamp'] == 1005.0
        assert chunks[2]['timestamp'] == 1010.0
        assert chunks[3]['timestamp'] == 1015.0

    def test_opus_enc_timestamp_parsing(self):
        """Double extension .opus.enc correctly extracts timestamp."""
        self._seed('chunks/uid/conv/1234567890.123.opus.enc', 8000)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1234567890.123

    def test_ignores_unknown_extensions(self):
        """Unknown extensions are skipped."""
        self._seed('chunks/uid/conv/1000.000.bin', 160000)
        self._seed('chunks/uid/conv/1005.000.txt', 500)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1


class TestDeleteAudioChunksExtensions:
    """Tests for delete_audio_chunks with all extension types."""

    def test_tries_all_extensions(self):
        """delete_audio_chunks deletes every single-chunk extension present (.enc, .bin, .opus.enc, .opus)."""
        store = storage_mod._object_store()
        bucket = storage_mod.private_cloud_sync_bucket
        for ext in ('.enc', '.bin', '.opus.enc', '.opus'):
            store.put(bucket, f'chunks/uid/conv/1000.000{ext}', b'\x00' * 100)

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0])

        # every seeded extension was deleted (recorded delete keys, was mock_bucket.blob.call_args_list)
        paths_tried = store.deleted
        assert any('.enc' in p and '.opus' not in p for p in paths_tried)
        assert any('.bin' in p for p in paths_tried)
        assert any('.opus.enc' in p for p in paths_tried)
        assert any('.opus' in p and '.enc' not in p for p in paths_tried)


class TestDownloadFallbackPath:
    """Tests for download_audio_chunks_and_merge fallback behavior."""

    def _seed(self, ext, data):
        # download reads _object_store().get_bytes(bucket, path); an absent ext raises ObjectNotFound.
        storage_mod._object_store().put(
            storage_mod.private_cloud_sync_bucket, f'chunks/uid/conv/1000.000.{ext}', data
        )

    @patch.object(storage_mod, 'encryption')
    def test_fallback_opus_corrupt_to_legacy_bin(self, mock_encryption):
        """When .opus.enc exists but decrypt fails, falls back to .bin."""
        pcm_data = b'\x00' * 640
        self._seed('opus.enc', b'corrupt-opus-data')
        self._seed('bin', pcm_data)
        mock_encryption.decrypt_audio_file.side_effect = Exception("decrypt failed")

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)
        assert result == pcm_data

    def test_fallback_all_not_found_raises(self):
        """When no extension exists for a timestamp, raises FileNotFoundError."""
        # nothing seeded -> every get_bytes raises ObjectNotFound
        with pytest.raises(FileNotFoundError):
            storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)

    @requires_native_opus
    def test_opus_decode_success_no_fallback(self):
        """When .opus chunk is valid, uses it without trying .bin."""
        pcm_data = b'\x00' * 640
        self._seed('opus', storage_mod.encode_pcm_to_opus(pcm_data))

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0], fill_gaps=False)
        assert len(result) == len(pcm_data)
        # Should NOT have fetched .bin after .opus succeeded (recorded get_bytes keys)
        assert not any(p.endswith('.bin') for p in storage_mod._object_store().fetched)

    def test_fallback_opus_decode_error_to_bin(self):
        """When .opus data is malformed (decode raises), falls back to .bin."""
        pcm_data = b'\x00' * 640
        bad_opus = b'\x01\x00\x00\x00\x80\x02\x00\x00\xff\xff'  # 1 pkt, pcm_len=640, bad pkt_len
        self._seed('opus', bad_opus)
        self._seed('bin', pcm_data)

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

    def _seed(self, name, size=1000):
        storage_mod._object_store().put(storage_mod.private_cloud_sync_bucket, name, b'\x00' * size)

    def test_lists_batch_bin_blobs(self):
        """list_audio_chunks recognizes .batch.bin with range timestamp."""
        self._seed('chunks/uid/conv/1000.000-1010.000.batch.bin', 480000)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True
        assert chunks[0]['path'] == 'chunks/uid/conv/1000.000-1010.000.batch.bin'

    def test_lists_batch_enc_blobs(self):
        """list_audio_chunks recognizes .batch.enc with range timestamp."""
        self._seed('chunks/uid/conv/1000.000-1010.000.batch.enc', 500000)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True

    def test_single_timestamp_batch(self):
        """Batch blob with single timestamp (short conversation)."""
        self._seed('chunks/uid/conv/1000.000.batch.bin', 160000)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['timestamp'] == 1000.0
        assert chunks[0]['is_batch'] is True

    def test_mixed_single_and_batch_blobs(self):
        """Conversation with both single-chunk and batch blobs (migration period)."""
        self._seed('chunks/uid/conv/1000.000.opus', 8000)
        self._seed('chunks/uid/conv/1005.000.opus', 8000)
        self._seed('chunks/uid/conv/1010.000-1025.000.batch.bin', 480000)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 3
        assert chunks[0]['is_batch'] is False
        assert chunks[1]['is_batch'] is False
        assert chunks[2]['is_batch'] is True
        assert chunks[2]['timestamp'] == 1010.0

    def test_is_batch_false_for_single_blobs(self):
        """Single-chunk blobs have is_batch=False."""
        self._seed('chunks/uid/conv/1000.000.opus.enc', 8000)

        chunks = storage_mod.list_audio_chunks('uid', 'conv')

        assert len(chunks) == 1
        assert chunks[0]['is_batch'] is False


class TestDeleteAudioChunksBatch:
    """Tests for delete_audio_chunks with batch blobs."""

    def _seed(self, name, size=1000):
        storage_mod._object_store().put(storage_mod.private_cloud_sync_bucket, name, b'\x00' * size)

    def test_deletes_single_timestamp_batch(self):
        """Finds and deletes batch blob with single timestamp."""
        store = storage_mod._object_store()
        batch_path = 'chunks/uid/conv/1000.000.batch.bin'
        self._seed(batch_path, 160000)

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0])

        assert batch_path in store.deleted
        assert not store.exists(storage_mod.private_cloud_sync_bucket, batch_path)

    def test_deletes_range_named_batch_via_scan(self):
        """Finds and deletes range-named batch blob by scanning."""
        store = storage_mod._object_store()
        batch_path = 'chunks/uid/conv/1000.000-1010.000.batch.bin'
        self._seed(batch_path, 480000)

        storage_mod.delete_audio_chunks('uid', 'conv', [1000.0, 1005.0, 1010.0])

        assert not store.exists(storage_mod.private_cloud_sync_bucket, batch_path)


class TestDownloadBatchBlobs:
    """Tests for download_audio_chunks_and_merge with batch blobs."""

    def _seed(self, name, data):
        storage_mod._object_store().put(storage_mod.private_cloud_sync_bucket, name, data)

    def test_downloads_batch_blob_once(self):
        """Batch blob covering multiple timestamps is downloaded once."""
        store = storage_mod._object_store()
        pcm_data = b'\x00' * 480000
        self._seed('chunks/uid/conv/1000.000-1010.000.batch.bin', pcm_data)

        result = storage_mod.download_audio_chunks_and_merge('uid', 'conv', [1000.0, 1005.0, 1010.0], fill_gaps=False)

        assert result == pcm_data
        batch_downloads = [p for p in store.fetched if 'batch' in p]
        assert len(batch_downloads) == 1

    @requires_native_opus
    def test_mixed_single_and_batch_download(self):
        """Mix of single-chunk and batch blobs downloads correctly."""
        single_pcm = b'\x01' * 160000
        batch_pcm = b'\x02' * 320000
        self._seed('chunks/uid/conv/1000.000.opus', storage_mod.encode_pcm_to_opus(single_pcm))
        self._seed('chunks/uid/conv/1005.000-1015.000.batch.bin', batch_pcm)

        result = storage_mod.download_audio_chunks_and_merge(
            'uid', 'conv', [1000.0, 1005.0, 1010.0, 1015.0], fill_gaps=False
        )

        assert len(result) == len(single_pcm) + len(batch_pcm)
