import pytest
from utils.audio import AudioRingBuffer

@pytest.mark.parametrize(
    "capacity, writes, expected_buffer, expected_pos, expected_total, expected_ts",
    [
        # capacity 4: empty write
        (4, [], b"\x00\x00\x00\x00", 0, 0, None),

        # capacity 4: partial fill
        (4, [(b"AB", 1.0)], b"AB\x00\x00", 2, 2, 1.0),

        # capacity 4: exact fill
        (4, [(b"ABCD", 1.0)], b"ABCD", 0, 4, 1.0),

        # capacity 4: wrap around by 1
        (4, [(b"ABCDE", 2.0)], b"EBCD", 1, 5, 2.0),

        # capacity 4: wrap around by 1 in multiple writes
        (4, [(b"AB", 1.0), (b"CDE", 2.0)], b"EBCD", 1, 5, 2.0),

        # capacity 4: wrap around multiple times
        (4, [(b"ABCDEFGHI", 3.0)], b"IFGH", 1, 9, 3.0),

        # capacity 6: wrap around multiple times
        (6, [(b"ABC", 1.0), (b"DEFGH", 2.0)], b"GHCDEF", 2, 8, 2.0),

        # capacity 0: should not crash, ignores writes
        (0, [(b"A", 1.0)], b"", 0, 0, None),
    ]
)
def test_audio_ring_buffer_write_wrap_around(capacity, writes, expected_buffer, expected_pos, expected_total, expected_ts):
    """Test that AudioRingBuffer.write correctly wraps around and updates stats."""
    # To get a specific capacity, we set duration_seconds = capacity / 2.0 and sample_rate = 1
    # bytes_per_second = sample_rate * 2 = 2
    # capacity = max(0, int(duration_seconds * 2))
    buf = AudioRingBuffer(duration_seconds=capacity / 2.0, sample_rate=1)

    assert buf.capacity == capacity
    assert len(buf.buffer) == capacity

    for data, ts in writes:
        buf.write(data, ts)

    assert bytes(buf.buffer) == expected_buffer
    assert buf.write_pos == expected_pos
    assert buf.total_bytes_written == expected_total
    assert buf.last_write_timestamp == expected_ts
