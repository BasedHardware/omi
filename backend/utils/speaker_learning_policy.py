"""Pure planning for pooled person voice-learning clips.

Decides which transcript segments may teach a person, and how much clean speech
they contribute, without touching storage, STT or Firestore. Capture scopes
(`speaker_id_scope`) isolate competing transcripts of the same audio: purity is
judged only inside the candidate's own scope, while pooled wall time is counted
as the union of selected intervals across whatever scopes were authorized.
"""

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

TEACHING_MIN_TOTAL_SECONDS = 10.0
TEACHING_MAX_TOTAL_SECONDS = 30.0
TEACHING_MAX_INTERVALS = 12
TEACHING_CANDIDATE_LIMIT = 200
TEACHING_CLIP_MAX_SECONDS = 10.0
TEACHING_CLIP_MIN_SECONDS = 1.0

_OUTCOME_STATES = {
    'stored': 'learned',
    'disabled': 'disabled',
    'insufficient_speech': 'needs_more_speech',
}


def learning_state_for_outcome(outcome: str) -> str:
    return _OUTCOME_STATES.get(outcome, 'pending')


def segment_scope(segment: Mapping[str, Any]) -> Optional[str]:
    return segment.get('speaker_id_scope')


def segment_identity(segment: Mapping[str, Any]) -> Tuple[Any, Any, bool]:
    return (segment.get('speaker_id'), segment.get('person_id'), bool(segment.get('is_user')))


def segment_group(segment: Mapping[str, Any]) -> Tuple[Any, Any]:
    return (segment_scope(segment), segment.get('speaker_id'))


def _placed(segment: Mapping[str, Any]) -> bool:
    return (
        segment.get('audio_alignment') != 'unplaced'
        and segment.get('start') is not None
        and segment.get('end') is not None
    )


def _overlaps(segment: Mapping[str, Any], start: float, end: float) -> bool:
    return segment.get('start', 0) < end and segment.get('end', 0) > start


def clip_window(segment: Mapping[str, Any]) -> Optional[Tuple[float, float]]:
    start = segment.get('start')
    end = segment.get('end')
    if start is None or end is None or end <= start:
        return None
    if end - start > TEACHING_CLIP_MAX_SECONDS:
        center = (start + end) / 2
        start, end = center - TEACHING_CLIP_MAX_SECONDS / 2, center + TEACHING_CLIP_MAX_SECONDS / 2
    if end - start < TEACHING_CLIP_MIN_SECONDS:
        return None
    return (start, end)


def merge_intervals(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    merged: List[Tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def union_seconds(intervals: List[Tuple[float, float]]) -> float:
    return sum(end - start for start, end in merge_intervals(intervals))


def winning_receipt_decision(receipt: Mapping[str, Any], segment: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """The receipt decision that governs teaching from ``segment``, or None.

    A merged conversation reuses numeric speaker ids across capture scopes, so a
    speaker-level entry stamped with a scope covers only segments in that scope:
    without this a label carried into one scope would authorize another scope's audio.
    Conversation-wide resolution rewrites every segment to a ``conversation:`` scope
    while keeping the explicit label, so a hand-made entry (never a carried one) still
    governs there; the segment's own label is rechecked by every caller.
    """
    by_speaker = (receipt.get('speakers') or {}).get(str(segment.get('speaker_id')))
    if isinstance(by_speaker, Mapping) and by_speaker.get('speaker_id_scope') is not None:
        segment_scope = segment.get('speaker_id_scope')
        resolved = isinstance(segment_scope, str) and segment_scope.startswith('conversation:')
        if by_speaker.get('speaker_id_scope') != segment_scope and (
            by_speaker.get('source') == 'carried' or not resolved
        ):
            by_speaker = None
    decisions = [
        decision
        for decision in ((receipt.get('segments') or {}).get(segment.get('id')), by_speaker)
        if isinstance(decision, Mapping)
    ]
    if not decisions:
        return None
    return max(decisions, key=lambda decision: decision.get('generation', 0))


def _decision_authorizes(decision: Mapping[str, Any], person_id: str) -> bool:
    return (
        decision.get('person_id') == person_id
        and not decision.get('is_user')
        and decision.get('use_for_speech_training', True) is not False
    )


def decision_authorizes_training(decision: Optional[Mapping[str, Any]], person_id: str) -> bool:
    return isinstance(decision, Mapping) and _decision_authorizes(decision, person_id)


def authorized_teaching_segments(conversation: Mapping[str, Any], person_id: str) -> List[Mapping[str, Any]]:
    """Segments the winning manual receipt decision currently authorizes for teaching ``person_id``."""
    receipt = conversation.get('manual_speaker_assignments') or {}
    authorized: List[Mapping[str, Any]] = []
    for segment in conversation.get('transcript_segments') or []:
        decision = winning_receipt_decision(receipt, segment)
        if decision is None or not _decision_authorizes(decision, person_id):
            continue
        if segment.get('person_id') != person_id or segment.get('is_user'):
            continue
        authorized.append(segment)
    return authorized


def receipt_names_person(receipt: Mapping[str, Any], person_id: str) -> bool:
    for group in ('segments', 'speakers'):
        entries = receipt.get(group)
        if not isinstance(entries, Mapping):
            continue
        for decision in entries.values():
            if isinstance(decision, Mapping) and _decision_authorizes(decision, person_id):
                return True
    return False


@dataclass(frozen=True)
class PooledClipPlan:
    """Chronological clip windows (conversation-relative seconds) for one teaching attempt."""

    intervals: List[Tuple[float, float]]
    contributors: List[List[Mapping[str, Any]]]
    total_seconds: float
    contaminated: bool


def plan_pooled_intervals(
    candidates: List[Mapping[str, Any]],
    all_segments: List[Mapping[str, Any]],
    allowed_source_ids: Optional[set] = None,
) -> PooledClipPlan:
    """Select disjoint clean windows for one voice, longest candidates first.

    A candidate is dropped when a genuinely different identity overlaps its
    window inside the same capture scope, or when ``allowed_source_ids`` is
    given and an overlapping same-identity segment's id is not authorized
    (a same-voice turn without a training receipt may not ride along as
    source audio). Intervals are center-cropped to the clip cap; clean time
    is the union of selected windows (overlaps counted once, gaps never
    counted).
    """
    ranked = sorted(
        (segment for segment in candidates if _placed(segment)),
        key=lambda segment: float(segment.get('end', 0)) - float(segment.get('start', 0)),
        reverse=True,
    )[:TEACHING_CANDIDATE_LIMIT]
    selected: List[Tuple[float, float]] = []
    contributors: List[List[Mapping[str, Any]]] = []
    contaminated = False
    total = 0.0
    for segment in ranked:
        if len(selected) >= TEACHING_MAX_INTERVALS or total >= TEACHING_MAX_TOTAL_SECONDS:
            break
        window = clip_window(segment)
        if window is None:
            continue
        start, end = window
        scope = segment_scope(segment)
        identity = segment_identity(segment)
        foreign = any(
            other is not segment
            and _placed(other)
            and segment_scope(other) == scope
            and segment_identity(other) != identity
            and _overlaps(other, start, end)
            for other in all_segments
        )
        if foreign or (
            allowed_source_ids is not None
            and any(
                _placed(other)
                and segment_scope(other) == scope
                and segment_identity(other) == identity
                and _overlaps(other, start, end)
                and other.get('id') not in allowed_source_ids
                for other in all_segments
            )
        ):
            contaminated = True
            continue
        overlapping = sorted(
            (
                other
                for other in all_segments
                if _placed(other)
                and segment_scope(other) == scope
                and segment_identity(other) == identity
                and _overlaps(other, start, end)
            ),
            key=lambda other: (other.get('start', 0), other.get('end', 0)),
        )
        selected.append((start, end))
        contributors.append(overlapping)
        total = union_seconds(selected)
        if total >= TEACHING_MIN_TOTAL_SECONDS:
            break
    order = sorted(range(len(selected)), key=lambda index: selected[index][0])
    return PooledClipPlan(
        intervals=[selected[index] for index in order],
        contributors=[contributors[index] for index in order],
        total_seconds=total,
        contaminated=contaminated,
    )
