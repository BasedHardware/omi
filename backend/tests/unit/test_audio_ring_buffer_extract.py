import time

import pytest
from utils.audio import AudioRingBuffer


def test_extract_empty_buffer_returns_none():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=16000)
    assert buf.extract(0.0, 1.0) is None


def test_extract_completely_before_buffer_returns_none():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=16000)
    buf.write(b"\x00" * 32000, 10.0)
    assert buf.extract(5.0, 8.0) is None


def test_extract_completely_after_buffer_returns_none():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=16000)
    buf.write(b"\x00" * 32000, 10.0)
    assert buf.extract(11.0, 12.0) is None


def test_extract_inverted_timestamps_returns_none():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=16000)
    buf.write(b"\x00" * 32000, 10.0)
    assert buf.extract(9.5, 9.0) is None


def test_extract_less_than_one_sample_returns_none():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=16000)
    buf.write(b"\x00" * 32000, 10.0)
    # 1 sample is 2 bytes, 1/16000 seconds = 0.0000625s.
    # Requesting a range so small that it aligns to < 2 bytes.
    # e.g. 0.00001 seconds.
    assert buf.extract(9.5, 9.5 + 0.00001) is None


def test_extract_wraparound_buffer_boundaries():
    # Capacity is 10 bytes (5 samples) -> 1.0 seconds
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=5)

    # Write 8 bytes (4 samples)
    buf.write(b"\x01\x01\x02\x02\x03\x03\x04\x04", 0.8)

    # Write another 6 bytes (3 samples) -> total 14 bytes written > capacity (10)
    buf.write(b"\x05\x05\x06\x06\x07\x07", 1.4)

    out = buf.extract(0.4, 1.4)
    # 0.4s to 1.4s -> 5 samples -> 10 bytes
    # Written: \x01\x01 (overwritten), \x02\x02 (overwritten), \x03\x03 (overwritten by \x07\x07)
    # The buffer now contains the last 10 bytes (5 samples) written up to 1.4s
    # The buffer starts at time 0.4s (1.4 - 1.0).
    # Since total bytes written = 14, and capacity is 10.
    # 14 bytes total -> 7 samples -> last 5 samples are samples 3, 4, 5, 6, 7.
    # Sample 3: \x03\x03
    # Sample 4: \x04\x04
    # Sample 5: \x05\x05
    # Sample 6: \x06\x06
    # Sample 7: \x07\x07
    assert out == b"\x03\x03\x04\x04\x05\x05\x06\x06\x07\x07"


def test_extract_partial_overlap_before():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=5)
    buf.write(b"\x01\x01\x02\x02\x03\x03\x04\x04\x05\x05", 1.0)

    out = buf.extract(-0.5, 0.4)
    assert out == b"\x01\x01\x02\x02"


def test_extract_partial_overlap_after():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=5)
    buf.write(b"\x01\x01\x02\x02\x03\x03\x04\x04\x05\x05", 1.0)

    out = buf.extract(0.6, 1.5)
    assert out == b"\x04\x04\x05\x05"


def test_extract_zero_capacity_returns_none():
    buf = AudioRingBuffer(duration_seconds=0.0, sample_rate=16000)
    # Capacity is 0.
    buf.write(b"\x00" * 32000, 10.0)
    assert buf.extract(9.0, 10.0) is None


def test_extract_exact_buffer_boundaries():
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=5)
    buf.write(b"\x01\x01\x02\x02\x03\x03\x04\x04\x05\x05", 1.0)

    out = buf.extract(0.0, 1.0)
    assert out == b"\x01\x01\x02\x02\x03\x03\x04\x04\x05\x05"


def _reference_ring_state(capacity, chunks):
    buffer = bytearray(capacity)
    write_pos = 0
    total = 0
    for data in chunks:
        for byte in data:
            buffer[write_pos] = byte
            write_pos = (write_pos + 1) % capacity
        total += len(data)
    return buffer, write_pos, total


def _public_write(buf, write_mode, data, ts):
    if write_mode == "write":
        buf.write(data, ts)
    else:
        buf.write_positioned(data, ts - len(data) / buf.bytes_per_second)


@pytest.mark.parametrize("write_mode", ["write", "write_positioned"])
@pytest.mark.parametrize("capacity", [1, 2, 7, 10])
def test_ring_buffer_physical_state_matches_per_byte_reference(capacity, write_mode):
    buf = AudioRingBuffer(duration_seconds=capacity / 2, sample_rate=1)
    assert buf.capacity == capacity
    seed = capacity * 31
    chunks = [
        b"",
        bytes((seed + i) % 256 for i in range(max(1, capacity - 1))),
        bytes((seed + 17 + i) % 256 for i in range(capacity)),
        bytes((seed + 41 + i) % 256 for i in range(2 * capacity + 1)),
        bytes((seed + 71 + i) % 256 for i in range(3)),
        bytes((seed + 97 + i) % 256 for i in range(1)),
    ]
    ts = 0.0
    for data in chunks:
        ts += 1.0
        _public_write(buf, write_mode, data, ts)
    expected_buffer, expected_pos, expected_total = _reference_ring_state(capacity, chunks)
    assert buf.capacity == capacity
    assert bytes(buf.buffer) == bytes(expected_buffer)
    assert buf.write_pos == expected_pos
    assert buf.total_bytes_written == expected_total


@pytest.mark.parametrize("write_mode", ["write", "write_positioned"])
def test_extract_after_oversize_write_with_nonzero_start(write_mode):
    buf = AudioRingBuffer(duration_seconds=1.0, sample_rate=5)
    buf.write(b"\xaa" * 8, 0.8)
    payload = bytes(range(25))
    _public_write(buf, write_mode, payload, 4.5)

    assert buf.write_pos == 3
    assert buf.total_bytes_written == 33
    assert bytes(buf.buffer) == bytes(list(range(22, 25)) + list(range(15, 22)))
    assert buf.get_time_range() == (3.5, 4.5)
    assert buf.extract(3.5, 4.5) == bytes(range(15, 25))
    assert buf.extract(4.0, 4.4) == bytes(range(19, 23))
    assert buf.extract(2.0, 3.0) is None


@pytest.mark.parametrize("write_mode", ["write", "write_positioned"])
def test_ring_buffer_single_large_write_performance(write_mode):
    buf = AudioRingBuffer(duration_seconds=135.0, sample_rate=16000)
    payload = bytes(range(256)) * (4_320_000 // 256)
    assert len(payload) == 4_320_000
    _public_write(buf, write_mode, b"\x00\x00", 0.0)

    start = time.process_time()
    _public_write(buf, write_mode, payload, 145.0)
    elapsed = time.process_time() - start

    assert elapsed < 0.10
    assert buf.capacity == 4_320_000
    assert buf.total_bytes_written == 4_320_002
    assert buf.write_pos == 2
    assert buf.get_time_range() == (10.0, 145.0)
    assert buf.extract(10.0, 145.0) == payload


@pytest.mark.parametrize("write_mode", ["write", "write_positioned"])
def test_ring_buffer_live_packet_writes_performance(write_mode):
    buf = AudioRingBuffer(duration_seconds=135.0, sample_rate=16000)
    packet = bytes(range(256)) * (960 // 256) + bytes(960 % 256)
    assert len(packet) == 960

    start = time.process_time()
    for i in range(4500):
        _public_write(buf, write_mode, packet, (i + 1) * 0.03)
    elapsed = time.process_time() - start

    assert elapsed < 0.10
    assert buf.capacity == 4_320_000
    assert buf.total_bytes_written == 4_320_000
    assert buf.write_pos == 0
    assert bytes(buf.buffer) == packet * 4500
    assert buf.get_time_range() == (0.0, 135.0)
    out = buf.extract(0.0, 135.0)
    assert out is not None
    assert out[:960] == packet
