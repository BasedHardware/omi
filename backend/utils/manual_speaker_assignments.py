"""Manual identity policy shared by transactional transcript writers.

The receipt authorizes best-effort teaching; it is not an enrollment job.
Inference must never create or replace these explicit user decisions.
"""

from copy import deepcopy
from typing import Optional
import uuid


def apply_manual_assignments(segments: list[dict], receipt: dict) -> list[dict]:
    result = deepcopy(segments)
    for segment in result:
        by_segment = receipt.get('segments', {}).get(segment.get('id'))
        by_speaker = receipt.get('speakers', {}).get(str(segment.get('speaker_id')))
        decisions = [value for value in (by_segment, by_speaker) if value]
        if not decisions:
            continue
        decision = max(decisions, key=lambda value: value['generation'])
        segment.update(
            is_user=decision['is_user'],
            person_id=decision['person_id'],
            speaker_identity_status=(
                'user' if decision['is_user'] else 'not_user' if decision['person_id'] else 'unknown'
            ),
        )
    return result


def manual_assignment(
    conversation: dict,
    *,
    person_id: Optional[str],
    is_user: bool,
    segment_ids: Optional[list[str]] = None,
    speaker_id: Optional[int] = None,
    segment_index: Optional[int] = None,
    use_for_speech_training: bool = True,
) -> tuple[list[dict], dict, list[str], set[str]]:
    segments = deepcopy(conversation.get('transcript_segments', []))
    from models.transcript_segment import TranscriptSegment

    for segment in segments:
        if segment.get('speaker_id') is None:
            segment['speaker_id'] = TranscriptSegment(**segment).speaker_id
    if segment_index is not None:
        indices = [segment_index] if 0 <= segment_index < len(segments) else []
    elif speaker_id is not None:
        indices = [i for i, s in enumerate(segments) if s.get('speaker_id') == speaker_id]
    else:
        by_id = {s.get('id'): i for i, s in enumerate(segments) if s.get('id')}
        indices = []
        for target in segment_ids or []:
            index = by_id.get(target)
            if index is None and conversation.get('status') == 'completed' and target.startswith('#index:'):
                number = target.removeprefix('#index:')
                if number.isascii() and number.isdecimal() and int(number) < len(segments):
                    index = int(number)
            if index is None:
                raise ValueError('Unresolved transcript segment')
            if index not in indices:
                indices.append(index)
    if not indices:
        raise LookupError('Segment not found')
    receipt = deepcopy(conversation.get('manual_speaker_assignments') or {})
    generation = receipt.get('generation', 0) + 1
    receipt['generation'] = generation
    decision = dict(
        origin='MANUAL',
        generation=generation,
        person_id=person_id,
        is_user=is_user,
        use_for_speech_training=use_for_speech_training,
    )
    previous = set()
    resolved = []
    for index in indices:
        segment = segments[index]
        if segment.get('person_id') and segment['person_id'] != person_id:
            previous.add(segment['person_id'])
        if not segment.get('id'):
            segment['id'] = str(uuid.uuid4())
        resolved.append(segment['id'])
        receipt.setdefault('segments', {})[segment['id']] = dict(decision)
    if speaker_id is not None:
        receipt.setdefault('speakers', {})[str(speaker_id)] = dict(decision)
    return apply_manual_assignments(segments, receipt), receipt, resolved, previous


def acknowledged_teaching(conversation: dict, person_id: str, segment_ids: list[str]) -> bool:
    """Only a persisted manual decision can authorize the delayed socket attempt."""
    receipt = conversation.get('manual_speaker_assignments') or {}
    decisions = receipt.get('segments', {})
    current = {s.get('id'): s for s in conversation.get('transcript_segments', [])}
    return bool(segment_ids) and all(
        decisions.get(sid, {}).get('person_id') == person_id
        and decisions[sid].get('use_for_speech_training', False)
        and current.get(sid, {}).get('person_id') == person_id
        and not current[sid].get('is_user')
        for sid in segment_ids
    )
