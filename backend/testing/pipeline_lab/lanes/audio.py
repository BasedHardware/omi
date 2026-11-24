"""Load a corpus clip as canonical 16 kHz mono PCM16LE (the cassette audio basis)."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

RATE = 16000


def load_pcm16(path: str | Path, entry: Any = None) -> bytes:
    path = Path(path)
    codec = (getattr(entry, 'codec', None) or '').lower()
    rate = getattr(entry, 'sample_rate', None)
    suffix = path.suffix.lower()
    if codec in {'pcm16', 'pcm', 'linear16'} or suffix in {'.pcm', '.raw'}:
        pcm = path.read_bytes()
        return pcm if (rate or RATE) == RATE else _resample(pcm, rate)
    if suffix == '.wav':
        with wave.open(str(path), 'rb') as handle:
            if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (1, 2, RATE):
                return handle.readframes(handle.getnframes())
    from pydub import AudioSegment  # lazy; product dependency (ffmpeg for compressed codecs)

    segment = AudioSegment.from_file(str(path))
    return segment.set_frame_rate(RATE).set_channels(1).set_sample_width(2).raw_data


def _resample(pcm: bytes, rate: int) -> bytes:
    from pydub import AudioSegment

    return AudioSegment(pcm, sample_width=2, frame_rate=rate, channels=1).set_frame_rate(RATE).raw_data


def seconds(pcm16: bytes) -> float:
    return len(pcm16) / (2 * RATE)


def slice_pcm(pcm16: bytes, start: float, end: float) -> bytes:
    left, right = int(round(start * RATE)) * 2, int(round(end * RATE)) * 2
    return pcm16[left:right]
