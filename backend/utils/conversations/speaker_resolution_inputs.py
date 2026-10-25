"""Pure receipt and measured-audio inputs for conversation speaker resolution."""

import math
from typing import Any, Dict, Mapping

from utils.manual_speaker_assignments import manual_rejected_speakers
from utils.stt.conversation_speakers import Identity


def manual_speakers(receipt: Mapping[str, Any]) -> Dict[int, Identity]:
    """A receipt key labeled neither owner nor person stays its own voice."""
    speakers: Dict[int, Identity] = {}
    for key, entry in (receipt.get('speakers') or {}).items():
        try:
            speaker_id = int(key)
        except (TypeError, ValueError):
            continue
        if not isinstance(entry, Mapping):
            continue
        if entry.get('is_user'):
            speakers[speaker_id] = Identity(is_user=True, person_id=None)
        elif entry.get('person_id'):
            speakers[speaker_id] = Identity(is_user=False, person_id=str(entry['person_id']))
        else:
            speakers[speaker_id] = Identity(is_user=False, person_id=None, anonymous_key=speaker_id)
    for speaker_id in manual_rejected_speakers(receipt):
        speakers[speaker_id] = Identity(is_user=False, person_id=None, anonymous_key=speaker_id)
    return speakers


def measured_embedding_seconds(segments, vectors, keys, clip_seconds, placements, max_clip_seconds):
    """Old unmeasured cache entries and reused PCM add no owner evidence."""
    durations = {}
    covered_windows = []
    for segment in segments:
        sid = segment.id
        if sid not in vectors:
            continue
        key = keys.get(sid, sid)
        seconds = clip_seconds.get(key, 0.0)
        if not math.isfinite(seconds) or seconds < 0:
            seconds = 0.0
        seconds = min(seconds, max(0.0, float(segment.end) - float(segment.start)), max_clip_seconds)
        window = placements[sid].window if sid in placements else None
        if window is not None:
            low, high = window
            if high - low > max_clip_seconds:
                center = (low + high) / 2
                low, high = center - max_clip_seconds / 2, center + max_clip_seconds / 2
            fresh = [(low, high)]
            for used_low, used_high in covered_windows:
                fresh = [
                    part
                    for a, b in fresh
                    for part in ((a, min(b, used_low)), (max(a, used_high), b))
                    if part[1] > part[0]
                ]
            seconds = min(seconds, sum(b - a for a, b in fresh))
            covered_windows.append((low, high))
        durations[sid] = seconds
    return durations
