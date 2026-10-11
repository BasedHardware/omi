"""Cut a short clip of a conversation's stored audio.

Audio exists only for conversations recorded with private cloud sync on; the
chunks live beside the conversation and are listed by ``audio_files``. Times
are seconds from ``conversation.started_at`` (``created_at`` when absent), the
same frame as transcript segments.

For audio-timeline v2 conversations the clip window must be *covered*: the
union of validated ``chunk_spans`` must contain it (1 ms tolerance). A known
uncovered window returns None — never a clip of the wrong audio. Legacy
conversations use strict authoritative spans or main timing behavior for
uncertain chunks/batches; text verification still guards original clock drift.
"""

import io
import wave
from typing import Any, List, Mapping, Optional

from database.audio_timeline import chunk_span_bounds
from utils.audio_timeline import coverage_outcome
from utils.conversations.audio_placement import capture_window, locate, provisional_window
from utils.speaker_tag_prompts.coverage import prompt_window_covered
from utils.metrics import OMI_AUDIO_TIMELINE_COVERAGE_TOTAL
from utils.other.storage import download_audio_chunks_and_merge
from utils.speaker_audio import legacy_speaker_clip_pcm

CLIP_SAMPLE_RATE = 16000
MAX_CLIP_REQUEST_SECONDS = 12.0


def _chunk_timestamps(conversation: Mapping[str, Any]) -> List[float]:
    timestamps: List[float] = []
    for audio_file in conversation.get('audio_files') or []:
        timestamps.extend(audio_file.get('chunk_timestamps') or [])
    return sorted(set(timestamps))


def v2_relevant_timestamps(conversation: Mapping[str, Any], abs_start: float, abs_end: float) -> List[float]:
    """Chunk timestamps whose validated span intersects the clip window."""
    relevant: List[float] = []
    for audio_file in conversation.get('audio_files') or []:
        spans = audio_file.get('chunk_spans') or []
        timestamps = audio_file.get('chunk_timestamps') or []
        if not spans or len(spans) != len(timestamps):
            return []
        for span, timestamp in zip(spans, timestamps):
            bounds = chunk_span_bounds(span)
            if bounds is None:
                return []
            start, end = bounds
            if start < abs_end and end > abs_start:
                relevant.append(float(timestamp))
    return sorted(set(relevant))


def conversation_clip_pcm(
    uid: str,
    conversation: Mapping[str, Any],
    start: float,
    end: float,
    sample_rate: int = CLIP_SAMPLE_RATE,
    *,
    caller: str = 'preview',
    prefer_capture: bool = False,
) -> Optional[bytes]:
    """PCM16 mono for ``[start, end)``, or None when no stored audio covers it.

    ``prefer_capture`` cuts where the live receiver heard the window instead of at the
    legacy origin; callers use it only as a retry and keep their transcript verification.
    """
    if end <= start or end - start > MAX_CLIP_REQUEST_SECONDS:
        raise ValueError('Clip window must be positive and at most 12 seconds')
    window = (
        capture_window(conversation, start, end) if prefer_capture else provisional_window(conversation, start, end)
    )
    if window is None:
        return None
    placement = locate(conversation, start, end)
    if placement.reason in ('unplaced', 'invalid_window'):
        return None
    normalized = dict(conversation)
    normalized['started_at'] = window[0] - start
    if not prompt_window_covered(normalized, start, end):
        return None
    marker = conversation.get('audio_timeline')
    if isinstance(marker, Mapping) and marker.get('version') == 2:
        if placement.reason != 'v2' or placement.window is None:
            return None
        outcome = coverage_outcome(normalized, start, end)
        OMI_AUDIO_TIMELINE_COVERAGE_TOTAL.labels(mode='v2', outcome=outcome).inc()
        if outcome != 'covered':
            # Uncovered windows never yield audio: missing/pending/unsupported
            # storage is unavailable, not a claim of aligned audio.
            return None
        abs_start, abs_end = placement.window
        relevant = v2_relevant_timestamps(conversation, abs_start, abs_end)
        if not relevant:
            return None
        try:
            merged = download_audio_chunks_and_merge(
                uid, conversation['id'], relevant, fill_gaps=True, sample_rate=sample_rate
            )
        except FileNotFoundError:
            # Listed chunks that storage cannot return are missing audio, not a
            # server error: callers answer 404 / "no sample".
            return None
        spans = [
            bounds
            for audio_file in conversation.get('audio_files') or []
            for bounds in (chunk_span_bounds(span) for span in (audio_file.get('chunk_spans') or []))
            if bounds is not None and bounds[0] < abs_end and bounds[1] > abs_start
        ]
        buffer_start = min(start for start, _ in spans)
        pcm = trim_pcm16(merged, sample_rate, abs_start - buffer_start, abs_end - buffer_start)
        return pcm or None
    timestamps = _chunk_timestamps(conversation)
    if not timestamps:
        return None
    abs_start, abs_end = placement.window if placement.window is not None else window

    return legacy_speaker_clip_pcm(
        uid, conversation['id'], abs_start, abs_end, sample_rate, timestamps=timestamps, caller=caller
    )


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
