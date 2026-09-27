"""Cheap, conservative stored-audio bounds for prompt clips.

Legacy file durations are estimates, not proof of speech or continuous audio.
They only reject windows clearly outside the listed chunks; transcription is
still required before a prompt can be offered.
"""

import math
from datetime import datetime, timezone
from typing import Any, Mapping

from utils.audio_timeline import coverage_outcome, is_audio_timeline_v2


def _seconds(value: Any) -> float | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if isinstance(value, datetime):
        value = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def prompt_window_covered(conversation: Mapping[str, Any], start: float, end: float) -> bool:
    """Require v2 span coverage or legacy file bounds for the complete window."""
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        return False
    if is_audio_timeline_v2(conversation):
        return coverage_outcome(conversation, start, end) == 'covered'
    origin = _seconds(conversation.get('started_at') or conversation.get('created_at'))
    if origin is None:
        return False
    absolute_start, absolute_end = origin + start, origin + end
    for audio_file in conversation.get('audio_files') or []:
        if not isinstance(audio_file, Mapping):
            continue
        timestamps = [_seconds(ts) for ts in audio_file.get('chunk_timestamps') or []]
        duration = _seconds(audio_file.get('duration'))
        if not timestamps or any(ts is None for ts in timestamps) or duration is None or duration <= 0:
            continue
        first = min(ts for ts in timestamps if ts is not None)
        if absolute_start >= first and absolute_end <= first + duration:
            return True
    return False
