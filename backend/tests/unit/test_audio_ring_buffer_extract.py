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
