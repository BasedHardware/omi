"""Cut a short clip of a conversation's stored audio.

Audio exists only for conversations recorded with private cloud sync on; the
chunks live beside the conversation and are listed by ``audio_files``. Times
are seconds from ``conversation.started_at``, the same frame as transcript
segments.
"""

import io
import wave
from typing import Any, List, Mapping, Optional

from utils.other.storage import download_audio_chunks_and_merge

CLIP_SAMPLE_RATE = 16000
MAX_CLIP_REQUEST_SECONDS = 12.0


def _started_at_seconds(conversation: Mapping[str, Any]) -> Optional[float]:
    started_at = conversation.get('started_at')
    if started_at is None:
        return None
    return started_at.timestamp() if hasattr(started_at, 'timestamp') else float(started_at)


def _chunk_timestamps(conversation: Mapping[str, Any]) -> List[float]:
    timestamps: List[float] = []
    for audio_file in conversation.get('audio_files') or []:
        timestamps.extend(audio_file.get('chunk_timestamps') or [])
    return sorted(set(timestamps))


def conversation_clip_pcm(
    uid: str, conversation: Mapping[str, Any], start: float, end: float, sample_rate: int = CLIP_SAMPLE_RATE
) -> Optional[bytes]:
    """PCM16 mono for ``[start, end)``, or None when no stored audio covers it."""
    if end <= start or end - start > MAX_CLIP_REQUEST_SECONDS:
        raise ValueError('Clip window must be positive and at most 12 seconds')
    started_at = _started_at_seconds(conversation)
    timestamps = _chunk_timestamps(conversation)
    if started_at is None or not timestamps:
        return None
    abs_start = started_at + start
    abs_end = started_at + end

    first = 0
    for index, timestamp in enumerate(timestamps):
        if timestamp <= abs_start:
            first = index
        else:
            break
    relevant = [timestamp for timestamp in timestamps[first:] if timestamp <= abs_end]
    if not relevant:
        return None

    merged = download_audio_chunks_and_merge(uid, conversation['id'], relevant, fill_gaps=True, sample_rate=sample_rate)
    buffer_start = min(relevant)
    pcm = trim_pcm16(merged, sample_rate, abs_start - buffer_start, abs_end - buffer_start)
    return pcm or None


def trim_pcm16(pcm: bytes, sample_rate: int, start: float, end: float) -> bytes:
    """Sample-accurate cut of PCM16 mono: two bytes per sample, so the cut is byte arithmetic."""
    first = max(0, int(round(start * sample_rate))) * 2
    last = max(0, int(round(end * sample_rate))) * 2
    return pcm[first:last]


def pcm_to_wav(pcm: bytes, sample_rate: int = CLIP_SAMPLE_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()
