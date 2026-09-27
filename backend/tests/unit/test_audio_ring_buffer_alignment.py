"""Regression test: AudioRingBuffer.extract must start on a PCM16 sample boundary.

utils.audio.AudioRingBuffer stores PCM16 mono audio. extract() computed start_offset as
int((actual_start - buffer_start_ts) * bytes_per_second), which is odd about half the time
because actual_start is an arbitrary float timestamp. An odd byte offset begins the copy on a
sample's high byte, so every returned int16 sample is byte-shifted into noise. This audio feeds
speaker-embedding cuts, so the misalignment intermittently corrupts speaker identification.
extract() now floors start_offset to the 2-byte sample boundary.
"""

import struct

from utils.audio import AudioRingBuffer


def _decode(pcm: bytes):
    return list(struct.unpack("<" + "h" * (len(pcm) // 2), pcm))


def _buffer_with_ascending_samples(sample_rate: int) -> AudioRingBuffer:
    buf = AudioRingBuffer(1.0, sample_rate)
    # 100 known ascending samples: 1000, 1001, ... 1099
    buf.write(b"".join(struct.pack("<h", 1000 + i) for i in range(100)), 10.0)
    return buf


def test_extract_with_odd_start_offset_returns_aligned_samples():
    sample_rate = 16000
    buf = _buffer_with_ascending_samples(sample_rate)

    time_range = buf.get_time_range()
    assert time_range is not None
    buffer_start_ts, buffer_end_ts = time_range

    # 3.5 bytes worth of time -> start_offset computes to int(3.5) = 3 (odd).
    out = buf.extract(buffer_start_ts + 3.5 / (sample_rate * 2), buffer_end_ts)
    assert out is not None

    samples = _decode(out)
    assert samples  # non-empty
    # Odd offset floored to 2 -> first whole sample is index 1 (value 1001), not byte-shifted noise.
    assert samples[0] == 1001, samples[:5]
    assert all(1000 <= s <= 1099 for s in samples), samples[:5]


def test_extract_with_even_start_offset_still_correct():
    sample_rate = 16000
    buf = _buffer_with_ascending_samples(sample_rate)

    time_range = buf.get_time_range()
    assert time_range is not None
    buffer_start_ts, buffer_end_ts = time_range

    # 4.5 bytes worth of time -> start_offset computes to int(4.5) = 4 (already even).
    out = buf.extract(buffer_start_ts + 4.5 / (sample_rate * 2), buffer_end_ts)
    assert out is not None

    samples = _decode(out)
    assert samples[0] == 1002  # byte 4 = sample index 2
    assert all(1000 <= s <= 1099 for s in samples), samples[:5]


def _marker_pcm(marker: int, samples: int) -> bytes:
    """PCM16 where every sample encodes (marker, index): byte-exact expectations."""
    return b''.join(((marker << 8) | (i & 0xFF)).to_bytes(2, 'little') for i in range(samples))


def test_extract_skips_wall_gap_after_client_stall():
    """A >2 s arrival stall inside the buffer must not be read as audio.

    write_positioned records per-chunk first-sample walls; extract used to
    convert the whole wall delta into one byte offset, reading past the end of
    the retained bytes (or wrapping the ring) instead of the post-stall audio.
    """
    sample_rate = 16000
    buf = AudioRingBuffer(60.0, sample_rate)
    before = _marker_pcm(1, sample_rate)  # 1 s ending at wall 101.0
    buf.write_positioned(before, 100.0)
    after = _marker_pcm(2, sample_rate)  # 1 s starting at wall 106.0 (5 s stall)
    buf.write_positioned(after, 106.0)

    # Window spans the stall: exactly the last 0.5 s of `before` and the first
    # 0.5 s of `after`, with the 5 s gap skipped.
    out = buf.extract(100.5, 106.5)
    assert out == before[sample_rate // 2 * 2 :] + after[: sample_rate // 2 * 2]


def test_extract_across_stall_with_ring_wraparound():
    """Same stall shape, but the buffer wrapped: the span walk must still be exact."""
    sample_rate = 16000
    buf = AudioRingBuffer(2.0, sample_rate)  # exactly 2 s of bytes
    first = _marker_pcm(3, sample_rate)
    buf.write_positioned(first, 200.0)
    second = _marker_pcm(4, sample_rate)
    buf.write_positioned(second, 205.0)  # wraps the ring

    out = buf.extract(200.5, 205.5)
    assert out == first[sample_rate // 2 * 2 :] + second[: sample_rate // 2 * 2]


def test_extract_before_first_span_and_past_last_span():
    sample_rate = 16000
    buf = AudioRingBuffer(10.0, sample_rate)
    buf.write_positioned(_marker_pcm(5, sample_rate), 300.0)

    assert buf.extract(298.0, 299.0) is None  # entirely before the retained audio
    assert buf.extract(301.5, 302.5) is None  # entirely past it
    # A window that only partially overlaps returns the overlap.
    assert buf.extract(300.25, 300.75) == _marker_pcm(5, sample_rate)[8000:24000]
