"""Authoritative meeting-treatment policy for finalized conversations."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, Literal, NamedTuple

MIN_MEETING_DURATION_SECONDS = 5 * 60
MIN_TRANSCRIBED_SPEECH_SECONDS = 60

MeetingTreatmentReason = Literal[
    'eligible',
    'too_short',
    'insufficient_speech',
    'rotation',
    'discarded',
    'not_desktop_meeting',
]


class MeetingTreatmentVerdict(NamedTuple):
    eligible: bool
    reason: MeetingTreatmentReason
    duration_s: float
    dedup_speech_s: float


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def deduplicated_transcribed_speech_seconds(segments: Iterable[Any]) -> float:
    """Return the union of non-empty transcript intervals.

    Desktop can transcribe the remote party through both the microphone and the
    system-audio tap. Those streams frequently emit twins at the same start
    time, so summing segment durations would count the same speech twice.
    Taking the interval union also handles partially overlapping twins.
    """

    intervals: list[tuple[float, float]] = []
    for segment in segments:
        text = _value(segment, 'text', '')
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            start = float(_value(segment, 'start'))
            end = float(_value(segment, 'end'))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start) or not math.isfinite(end):
            continue
        start = max(0.0, start)
        if end <= start:
            continue
        intervals.append((start, end))

    if not intervals:
        return 0.0

    intervals.sort()
    total = 0.0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start
        current_start, current_end = start, end
    return total + current_end - current_start


def meeting_treatment_verdict(conversation: Any) -> MeetingTreatmentVerdict:
    """Return the auditable final meeting-treatment decision and its inputs."""

    source = _value(conversation, 'source')
    source_value = getattr(source, 'value', source)
    external_data = _value(conversation, 'external_data') or {}
    if not isinstance(external_data, Mapping):
        external_data = {}

    segments = _value(conversation, 'transcript_segments', []) or []
    dedup_speech_s = deduplicated_transcribed_speech_seconds(segments)

    started_at = _value(conversation, 'started_at')
    finished_at = _value(conversation, 'finished_at')
    duration_s = 0.0
    if isinstance(started_at, datetime) and isinstance(finished_at, datetime):
        try:
            duration_s = max(0.0, (finished_at - started_at).total_seconds())
        except TypeError:
            pass

    if source_value != 'desktop' or external_data.get('conversation_role') != 'meeting':
        return MeetingTreatmentVerdict(False, 'not_desktop_meeting', duration_s, dedup_speech_s)
    if external_data.get('conversation_finalization_reason') == 'max_duration_rotation':
        return MeetingTreatmentVerdict(False, 'rotation', duration_s, dedup_speech_s)
    if bool(_value(conversation, 'discarded', False)):
        return MeetingTreatmentVerdict(False, 'discarded', duration_s, dedup_speech_s)
    if duration_s < MIN_MEETING_DURATION_SECONDS:
        return MeetingTreatmentVerdict(False, 'too_short', duration_s, dedup_speech_s)
    if dedup_speech_s < MIN_TRANSCRIBED_SPEECH_SECONDS:
        return MeetingTreatmentVerdict(False, 'insufficient_speech', duration_s, dedup_speech_s)
    return MeetingTreatmentVerdict(True, 'eligible', duration_s, dedup_speech_s)


def is_meeting_treatment_eligible(conversation: Any) -> bool:
    """Compatibility wrapper around the single auditable verdict policy."""

    return meeting_treatment_verdict(conversation).eligible
