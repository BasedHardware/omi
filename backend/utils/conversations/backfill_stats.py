"""Counts-only transcript triage; overlapping speech is counted once."""

from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any


def transcript_stats(segments: Any) -> dict[str, int | float]:
    if not isinstance(segments, list) or any(not isinstance(s, dict) for s in segments):
        raise ValueError('malformed_segments')
    intervals = []
    speakers = set()
    words = 0
    for segment in segments:
        text = segment.get('text') or ''
        if not isinstance(text, str):
            raise ValueError('malformed_text')
        words += len(re.findall(r'\w+', text))
        start, end = segment.get('start'), segment.get('end')
        if (
            isinstance(start, (int, float))
            and isinstance(end, (int, float))
            and math.isfinite(start)
            and math.isfinite(end)
            and 0 <= start < end
        ):
            intervals.append((start, end))
        if segment.get('speaker') is not None:
            speakers.add(str(segment['speaker']))
    seconds, cursor = 0.0, 0.0
    for start, end in sorted(intervals):
        seconds += max(0, end - max(cursor, start))
        cursor = max(cursor, end)
    return {
        'speech_seconds': seconds,
        'word_count': words,
        'segment_count': len(segments),
        'speaker_count': len(speakers),
    }


def classify(stats: dict[str, Any], has_audio: bool, *, seconds: float, words: int) -> str:
    if not stats['word_count'] and has_audio:
        return 'review_audio_without_transcript'
    if stats['speech_seconds'] >= seconds or stats['word_count'] >= words:
        return 'substantive'
    return 'noise'


def same_timestamp_revision(left: datetime, right: datetime) -> bool:
    """datetime equality alone drops Firestore's sub-microsecond revision precision."""
    return left == right and getattr(left, 'nanosecond', left.microsecond * 1000) == getattr(
        right, 'nanosecond', right.microsecond * 1000
    )
