"""
Tests for memory leak prevention buffers in transcribe.py.
Covers: audio buffer capping, deque maxlen behavior, image chunk TTL.
"""
import time
from collections import deque


# Constants matching transcribe.py
MAX_AUDIO_BUFFER_SIZE = 1024 * 1024 * 10  # 10MB
MAX_SEGMENT_BUFFER_SIZE = 1000
MAX_IMAGE_CHUNKS = 50
IMAGE_CHUNK_TTL = 60.0


def audio_bytes_send_logic(audio_buffers: bytearray, audio_bytes: bytes, max_size: int) -> bytearray:
    """
    Extracted logic from audio_bytes_send for testing.
    Returns the updated buffer.
    """
    chunk = audio_bytes
    if len(chunk) > max_size:
        chunk = chunk[-max_size:]
    if len(audio_buffers) + len(chunk) > max_size:
        excess = len(audio_buffers) + len(chunk) - max_size
        audio_buffers = audio_buffers[excess:]
    audio_buffers.extend(chunk)
    return audio_buffers


class TestAudioBufferCapping:
    """Test audio buffer size limiting logic."""

    def test_normal_append_within_limit(self):
        """Normal append when buffer has room."""
        buffer = bytearray(b'existing')
        result = audio_bytes_send_logic(buffer, b'new', MAX_AUDIO_BUFFER_SIZE)
        assert result == bytearray(b'existingnew')

    def test_drops_oldest_when_exceeds_limit(self):
        """Drops oldest bytes when new data would exceed limit."""
        max_size = 10
        buffer = bytearray(b'12345678')  # 8 bytes
        result = audio_bytes_send_logic(buffer, b'abc', max_size)  # +3 = 11, need to drop 1
        assert len(result) == max_size
        assert result == bytearray(b'2345678abc')  # dropped '1'

    def test_trims_oversized_incoming_chunk(self):
        """Trims incoming chunk if it alone exceeds max size."""
        max_size = 5
        buffer = bytearray()
        result = audio_bytes_send_logic(buffer, b'1234567890', max_size)  # 10 bytes, max 5
        assert len(result) == max_size
        assert result == bytearray(b'67890')  # kept last 5 bytes

    def test_oversized_chunk_replaces_existing_buffer(self):
        """Oversized chunk after trimming replaces existing buffer."""
        max_size = 5
        buffer = bytearray(b'abc')
        result = audio_bytes_send_logic(buffer, b'1234567890', max_size)
        assert len(result) == max_size
        assert result == bytearray(b'67890')

    def test_exact_fit(self):
        """Chunk that exactly fills remaining space."""
        max_size = 10
        buffer = bytearray(b'12345')  # 5 bytes
        result = audio_bytes_send_logic(buffer, b'67890', max_size)  # +5 = 10
        assert len(result) == max_size
        assert result == bytearray(b'1234567890')

    def test_boundary_one_over(self):
        """One byte over the limit."""
        max_size = 10
        buffer = bytearray(b'12345')  # 5 bytes
        result = audio_bytes_send_logic(buffer, b'678901', max_size)  # +6 = 11, drop 1
        assert len(result) == max_size
        assert result == bytearray(b'2345678901')


class TestDequeMaxlen:
    """Test deque maxlen behavior for segment buffers."""

    def test_deque_drops_oldest_at_maxlen(self):
        """Deque with maxlen drops oldest when full."""
        d = deque(maxlen=3)
        d.extend([1, 2, 3])
        d.append(4)
        assert list(d) == [2, 3, 4]

    def test_deque_extend_drops_multiple(self):
        """Extend that exceeds capacity drops multiple oldest."""
        d = deque(maxlen=3)
        d.extend([1, 2, 3])
        d.extend([4, 5])
        assert list(d) == [3, 4, 5]

    def test_deque_clear_preserves_maxlen(self):
        """Clear preserves maxlen unlike reassignment."""
        d = deque(maxlen=3)
        d.extend([1, 2, 3])
        d.clear()
        assert d.maxlen == 3
        d.extend([1, 2, 3, 4])
        assert list(d) == [2, 3, 4]

    def test_list_conversion_preserves_order(self):
        """list() conversion preserves order for JSON serialization."""
        d = deque(maxlen=5)
        d.extend([1, 2, 3])
        assert list(d) == [1, 2, 3]


class TestImageChunksTTL:
    """Test image chunks TTL and max concurrent logic."""

    def test_cleanup_expired_chunks(self):
        """Expired chunks are removed."""
        image_chunks = {
            'old': {'chunks': [None], 'created_at': time.time() - 120},  # 2 min ago
            'new': {'chunks': [None], 'created_at': time.time()},
        }
        now = time.time()
        expired = [tid for tid, data in image_chunks.items() if now - data['created_at'] > IMAGE_CHUNK_TTL]
        for tid in expired:
            del image_chunks[tid]

        assert 'old' not in image_chunks
        assert 'new' in image_chunks

    def test_max_concurrent_drops_oldest(self):
        """When max concurrent reached, oldest is dropped."""
        image_chunks = {}
        base_time = time.time()

        # Fill to max
        for i in range(MAX_IMAGE_CHUNKS):
            image_chunks[f'id_{i}'] = {'chunks': [None], 'created_at': base_time + i}

        assert len(image_chunks) == MAX_IMAGE_CHUNKS

        # Add one more - should trigger drop of oldest
        if len(image_chunks) >= MAX_IMAGE_CHUNKS:
            oldest_id = min(image_chunks.keys(), key=lambda k: image_chunks[k]['created_at'])
            del image_chunks[oldest_id]

        image_chunks['new_id'] = {'chunks': [None], 'created_at': base_time + MAX_IMAGE_CHUNKS}

        assert len(image_chunks) == MAX_IMAGE_CHUNKS
        assert 'id_0' not in image_chunks  # oldest was dropped
        assert 'new_id' in image_chunks

    def test_chunk_within_limit_not_dropped(self):
        """Chunks within limit are not dropped."""
        image_chunks = {}
        for i in range(MAX_IMAGE_CHUNKS - 1):
            image_chunks[f'id_{i}'] = {'chunks': [None], 'created_at': time.time()}

        # Add one more - should not trigger drop
        image_chunks['new_id'] = {'chunks': [None], 'created_at': time.time()}

        assert len(image_chunks) == MAX_IMAGE_CHUNKS
        assert 'id_0' in image_chunks
        assert 'new_id' in image_chunks
