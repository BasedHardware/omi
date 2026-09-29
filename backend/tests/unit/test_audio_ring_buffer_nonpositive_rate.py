"""AudioRingBuffer must not crash on a non-positive sample_rate or duration, nor over-allocate.

sample_rate reaches AudioRingBuffer from the /v4/listen WebSocket query parameter
(routers/transcribe.py: `sample_rate: int = 8000`, no gt=0). validate_audio_format now restricts it
to standard rates for every codec, but it used to range-check only the opus codecs, so a pcm client
could send 0, a negative value, or a huge one. The buffer keeps its own guards in case a caller
skips validation. When speaker identification is enabled (a normal state for a user with an
enrolled speech profile or private-cloud sync), routers/listen/runtime.py builds
AudioRingBuffer(duration, request.sample_rate), and receiver.py writes to it on the first audio
frame.

Before the guard:
- sample_rate=0 -> capacity 0 -> bytearray(0); the first write() did buffer[0] = byte, raising
  IndexError (and % capacity would raise ZeroDivisionError), which was uncaught in the WS receive
  loop and killed the live-transcription session on its first audio frame.
- a negative sample_rate -> negative capacity -> bytearray(negative) raised ValueError during
  session bootstrap.
- sample_rate=30000000 -> bytearray(60 * 30e6 * 2), ~3.6 GB zero-filled at bootstrap, which
  exceeded the listen pod's memory limit and OOM-killed every live session on it.

The non-positive guard mirrors resample_pcm, which already treats a non-positive rate as a no-op.
"""

from utils.audio import MAX_RING_BUFFER_SAMPLE_RATE, AudioRingBuffer


def test_zero_sample_rate_write_does_not_raise():
    buf = AudioRingBuffer(duration_seconds=30.0, sample_rate=0)

    # The first audio frame must not crash the session.
    buf.write(b"\x01\x02\x03\x04", timestamp=100.0)

    # Nothing is buffered, which the extraction/speaker path already treats as "no audio".
    assert buf.get_time_range() is None
    assert buf.extract(0.0, 1000.0) is None


def test_negative_sample_rate_construction_does_not_raise():
    buf = AudioRingBuffer(duration_seconds=30.0, sample_rate=-16000)

    buf.write(b"\x01\x02", timestamp=100.0)
    assert buf.get_time_range() is None


def test_zero_duration_does_not_raise():
    buf = AudioRingBuffer(duration_seconds=0.0, sample_rate=16000)

    buf.write(b"\x01\x02", timestamp=100.0)
    assert buf.get_time_range() is None


def test_normal_positive_rate_still_buffers_and_extracts():
    rate = 16000
    buf = AudioRingBuffer(duration_seconds=30.0, sample_rate=rate)

    # One second of PCM16 mono at 16 kHz is 32000 bytes.
    one_second = bytes(rate * 2)
    buf.write(one_second, timestamp=100.0)

    time_range = buf.get_time_range()
    assert time_range is not None
    start_ts, end_ts = time_range
    assert end_ts == 100.0
    assert abs((end_ts - start_ts) - 1.0) < 1e-6

    extracted = buf.extract(99.5, 100.0)
    assert extracted is not None
    assert len(extracted) > 0


def test_oversized_sample_rate_capacity_is_capped():
    # sample_rate=30000000 used to allocate 60 * 30e6 * 2 bytes (~3.6 GB) up front and OOM-kill the
    # listen pod. The buffer caps its own capacity even if validation is bypassed.
    buf = AudioRingBuffer(duration_seconds=60.0, sample_rate=30_000_000)

    assert buf.capacity == 60 * MAX_RING_BUFFER_SAMPLE_RATE * 2
    assert len(buf.buffer) == buf.capacity

    # Still writable; spans are timed against the requested rate.
    buf.write(bytes(4), timestamp=100.0)
    assert buf.get_time_range() is not None


def test_supported_rates_keep_full_capacity():
    for rate in (8000, 16000, 48000):
        buf = AudioRingBuffer(duration_seconds=60.0, sample_rate=rate)
        assert buf.capacity == 60 * rate * 2
