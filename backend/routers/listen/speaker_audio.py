"""Metadata interval pooling and bounded live embedding WAV encoding."""

import io
from typing import Any

import av
import numpy as np

from routers.listen.speaker_queue import subtract_audio_ranges
from utils.audio import AudioRingBuffer
from utils.observability.speaker_embedding_budget import PCM_WINDOWS_RESTORED

MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS = 10.0


def fresh_audio_ranges(
    pending: list[tuple[float, float]],
    incoming: list[tuple[float, float]],
    covered: list[tuple[float, float]],
    bounds: tuple[float, float],
) -> list[tuple[float, float]]:
    fresh = []
    for start, end in sorted(pending + incoming):
        start, end = max(start, bounds[0]), min(end, bounds[1])
        if end <= start:
            continue
        if fresh and start <= fresh[-1][1]:
            fresh[-1] = (fresh[-1][0], max(fresh[-1][1], end))
        else:
            fresh.append((start, end))
    return subtract_audio_ranges(fresh, covered)[-128:]


def encode_query(pcm: bytes, sample_rate: int) -> bytes:
    samples = np.frombuffer(pcm, dtype=np.int16)
    buffer = io.BytesIO()
    container = av.open(buffer, mode='w', format='wav')
    stream: Any = container.add_stream('pcm_s16le', rate=sample_rate)
    stream.layout = 'mono'
    frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='mono')
    frame.rate = sample_rate
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    return buffer.getvalue()


def select_query_audio(
    ring: AudioRingBuffer,
    fresh: list[tuple[float, float]],
    *,
    prefer_recent: bool,
    sample_rate: int,
    capture_watermark: float | None = None,
    minimum_seconds: float = 0.5,
) -> tuple[bytes, list[tuple[float, float]]]:
    if capture_watermark is not None:
        newer = [(max(start, capture_watermark), end) for start, end in fresh if end > capture_watermark]
        pcm, selected = select_query_audio(
            ring, newer, prefer_recent=True, sample_rate=sample_rate, minimum_seconds=minimum_seconds
        )
        if len(pcm) / (sample_rate * 2) >= minimum_seconds:
            return pcm, selected
        # Only insufficient new physical evidence permits older pending speech.
    selected, chunks = [], []
    uncorrected_bytes = 0
    remaining_seconds = MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS
    ordered = sorted(fresh, key=lambda r: (-min(10.0, r[1] - r[0]), -r[1])) if prefer_recent else fresh
    for start, end in ordered:
        if remaining_seconds <= 0:
            break
        if end - start > remaining_seconds:
            center = end - remaining_seconds / 2 if prefer_recent else (start + end) / 2
            start, end = center - remaining_seconds / 2, center + remaining_seconds / 2
        chunk = ring.extract(start, end)
        if not chunk:
            continue
        # Timestamp-overlapping spans can return more PCM than the wall window.
        # Bound physical samples too, including when provider timing is malformed.
        byte_limit = int(remaining_seconds * sample_rate) * 2
        uncorrected_bytes += min(len(chunk) - 2 * getattr(chunk, 'restored_samples', 0), byte_limit)
        chunk = chunk[:byte_limit]
        chunks.append(chunk)
        selected.append((start, end))
        remaining_seconds -= max(end - start, len(chunk) / (sample_rate * 2))
    pcm = b''.join(chunks)
    if uncorrected_bytes < minimum_seconds * sample_rate * 2 <= len(pcm):
        PCM_WINDOWS_RESTORED.labels(reason='full_span_rounding').inc()
    return pcm, selected
