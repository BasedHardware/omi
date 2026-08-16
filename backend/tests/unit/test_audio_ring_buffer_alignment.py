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
