"""Cut a short clip of a conversation's stored audio.

Audio exists only for conversations recorded with private cloud sync on; the
chunks live beside the conversation and are listed by ``audio_files``. Times
are seconds from ``conversation.started_at`` (``created_at`` when absent), the
same frame as transcript segments.

For audio-timeline v2 conversations the clip window must be *covered*: the
union of validated ``chunk_spans`` must contain it (1 ms tolerance). A known
uncovered window returns None — never a clip of the wrong audio. Legacy
conversations keep the timestamp-based best-effort behavior.
"""

from datetime import datetime, timezone
import io
import wave
from typing import Any, List, Mapping, Optional

from database.audio_timeline import chunk_span_bounds
from utils.audio_timeline import coverage_outcome, segment_wall_window
from utils.speaker_tag_prompts.coverage import prompt_window_covered
from utils.metrics import OMI_AUDIO_TIMELINE_COVERAGE_TOTAL
from utils.other.storage import download_audio_chunks_and_merge

CLIP_SAMPLE_RATE = 16000
MAX_CLIP_REQUEST_SECONDS = 12.0


def _started_at_seconds(conversation: Mapping[str, Any]) -> Optional[float]:
    raw: Any = conversation.get('started_at') or conversation.get('created_at')
    if isinstance(raw, str) and raw.strip():
        try:
            raw = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
        except ValueError:
            pass
    if isinstance(raw, datetime):
        return (raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)).timestamp()
    ts_fn: Any = getattr(raw, 'timestamp', None)
    return (
        float(ts_fn())
        if ts_fn is not None
        else (float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool) else None)
    )


def _chunk_timestamps(conversation: Mapping[str, Any]) -> List[float]:
    timestamps: List[float] = []
    for audio_file in conversation.get('audio_files') or []:
        timestamps.extend(audio_file.get('chunk_timestamps') or [])
    return sorted(set(timestamps))


def _v2_relevant_timestamps(conversation: Mapping[str, Any], abs_start: float, abs_end: float) -> List[float]:
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
    uid: str, conversation: Mapping[str, Any], start: float, end: float, sample_rate: int = CLIP_SAMPLE_RATE
) -> Optional[bytes]:
    """PCM16 mono for ``[start, end)``, or None when no stored audio covers it."""
    if end <= start or end - start > MAX_CLIP_REQUEST_SECONDS:
        raise ValueError('Clip window must be positive and at most 12 seconds')
    started_at = _started_at_seconds(conversation)
    if started_at is None:
        return None
    if not prompt_window_covered(conversation, start, end):
        return None
    marker = conversation.get('audio_timeline')
    if isinstance(marker, Mapping) and marker.get('version') == 2:
        window = segment_wall_window(conversation, start, end)
        if window is None:
            return None
        outcome = coverage_outcome(conversation, start, end)
        OMI_AUDIO_TIMELINE_COVERAGE_TOTAL.labels(mode='v2', outcome=outcome).inc()
        if outcome != 'covered':
            # Uncovered windows never yield audio: missing/pending/unsupported
            # storage is unavailable, not a claim of aligned audio.
            return None
        abs_start, abs_end = window
        relevant = _v2_relevant_timestamps(conversation, abs_start, abs_end)
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
    abs_start = started_at + start
    abs_end = started_at + end

    first = max((i for i, ts in enumerate(timestamps) if ts <= abs_start), default=0)
    relevant = [timestamp for timestamp in timestamps[first:] if timestamp <= abs_end]
    if not relevant:
        return None

    try:
        merged = download_audio_chunks_and_merge(
            uid, conversation['id'], relevant, fill_gaps=True, sample_rate=sample_rate
        )
    except FileNotFoundError:
        return None
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
