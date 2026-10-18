"""Real encoder/decoder path, bounded size and sample-exact clocks."""

import math
import struct
import wave

import pytest

from utils.sync import live_cap_codec as codec


@pytest.mark.parametrize('rate', [8000, 16000, 24000, 48000])
@pytest.mark.parametrize('frames', [1, 1001, 6000])
def test_opus_roundtrip_preserves_short_tail_clock_and_format(tmp_path, rate, frames):
    pcm = b''.join(struct.pack('<h', int(6000 * math.sin(2 * math.pi * 220 * i / rate))) for i in range(frames))
    compressed, decoded = str(tmp_path / 'capture.opus'), str(tmp_path / 'capture.wav')
    codec.encode(compressed, pcm, rate)
    codec.decode(compressed, decoded, rate, frames)
    with wave.open(decoded) as audio:
        assert audio.getnframes() == frames
        assert audio.getframerate() == rate
        assert audio.getnchannels() == 1 and audio.getsampwidth() == 2
    assert (tmp_path / 'capture.opus').stat().st_size < codec.MAX_OBJECT_BYTES


def test_full_minute_of_noise_obeys_encoded_size_ceiling(tmp_path):
    import random

    noise = random.Random(12).randbytes(60 * 16000 * 2)
    path = str(tmp_path / 'noise.opus')
    codec.encode(path, noise, 16000)
    assert (tmp_path / 'noise.opus').stat().st_size <= codec.MAX_OBJECT_BYTES
