"""Real encoder/decoder path, bounded size and sample-exact clocks."""

import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace

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


def test_both_encoder_passes_allow_slow_encoding_with_original_twenty_second_timeout(tmp_path, monkeypatch):
    timeouts = []

    def slow_encoder(command, **kwargs):
        timeouts.append(kwargs['timeout'])
        if kwargs['timeout'] < 9:
            raise codec.subprocess.TimeoutExpired(command, kwargs['timeout'])
        # Model a nine-second encode without spending nine wall-clock seconds.
        Path(command[-1]).write_bytes(b'opus' * (10 if len(timeouts) == 1 else 1))
        return SimpleNamespace(stdout=b'')

    monkeypatch.setattr(codec.subprocess, 'run', slow_encoder)
    codec.encode(str(tmp_path / 'slow.opus'), b'\0' * 32000, 16000, max_bytes=16)
    assert timeouts == [20, 20]
