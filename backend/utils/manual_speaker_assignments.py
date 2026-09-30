"""Manual identity policy shared by transactional transcript writers.

The receipt authorizes best-effort teaching; it is not an enrollment job.
Inference must never create or replace these explicit user decisions.
"""

from dataclasses import dataclass
from typing import Optional
import uuid

from models.transcript_segment import TranscriptSegment, legacy_conversation_segment_id

TEACHING_CANDIDATE_LIMIT = 3


def teaching_segment_ids(segments: list[dict], resolved: list[str], limit: int = TEACHING_CANDIDATE_LIMIT) -> list[str]:
    """Longest labeled clips first, capped so extraction never walks the whole speaker cluster."""
    by_id = {segment.get('id'): segment for segment in segments if segment.get('id')}
    ranked = []
    for sid in resolved:
        segment = by_id.get(sid)
        if not segment:
            continue
        duration = float(segment.get('end') or 0) - float(segment.get('start') or 0)
        ranked.append((duration, sid))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [sid for _, sid in ranked[:limit]]


def apply_manual_assignments(segments: list[dict], receipt: dict) -> list[dict]:
    speakers = receipt.get('speakers') or {}
    overrides = receipt.get('segments') or {}
    if not speakers and not overrides:
        return segments
    result = None
    for index, segment in enumerate(segments):
        by_segment = overrides.get(segment.get('id'))
        by_speaker = speakers.get(str(segment.get('speaker_id')))
        decisions = [value for value in (by_segment, by_speaker) if value]
        if not decisions:
            continue
        decision = max(decisions, key=lambda value: value.get('generation', 0))
        is_user = decision['is_user']
        person_id = decision['person_id']
        status = 'user' if is_user else 'not_user' if person_id else 'unknown'
        if (
            segment.get('is_user') == is_user
            and segment.get('person_id') == person_id
            and segment.get('speaker_identity_status') == status
            and segment.get('speaker_match_source') is None
        ):
            continue
        if result is None:
            result = list(segments)
        copied = dict(segment)
        copied.update(is_user=is_user, person_id=person_id, speaker_identity_status=status, speaker_match_source=None)
        result[index] = copied
    return result if result is not None else segments


def remap_absorbed_receipt(receipt: dict, absorbed_into: dict[str, str]) -> dict:
    """Move segment overrides from absorbed ids onto the surviving segment."""
    if not absorbed_into:
        return receipt
    survivors: dict[str, str] = {}
    for absorbed_id in absorbed_into:
        path: list[str] = []
        seen: set[str] = set()
        current = absorbed_id
        while current in absorbed_into and current not in survivors:
            if current in seen:
                raise ValueError('Cyclic transcript segment absorption')
            seen.add(current)
            path.append(current)
            current = absorbed_into[current]
        survivor_id = survivors.get(current, current)
        for sid in path:
            survivors[sid] = survivor_id

    segments = dict(receipt.get('segments') or {})
    changed = False
    for absorbed_id, survivor_id in survivors.items():
        entry = segments.pop(absorbed_id, None)
        if entry is None:
            continue
        changed = True
        existing = segments.get(survivor_id)
        if existing is None or entry.get('generation', 0) >= existing.get('generation', 0):
            segments[survivor_id] = entry
    if not changed:
        return receipt
    updated = dict(receipt)
    if segments:
        updated['segments'] = segments
    else:
        updated.pop('segments', None)
    return updated


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
    segments = [dict(segment) for segment in conversation.get('transcript_segments', [])]

    for index, segment in enumerate(segments):
        if not segment.get('id') and conversation.get('id'):
            segment['id'] = legacy_conversation_segment_id(conversation['id'], index)
        if segment.get('speaker_id') is None:
            segment['speaker_id'] = TranscriptSegment(**segment).speaker_id
    if segment_index is not None:
        indices = [segment_index] if 0 <= segment_index < len(segments) else []
    elif speaker_id is not None:
        indices = [i for i, s in enumerate(segments) if s.get('speaker_id') == speaker_id]
    else:
        by_id = {s.get('id'): i for i, s in enumerate(segments) if s.get('id')}
        indices = []
        unresolved = []
        for target in segment_ids or []:
            index = by_id.get(target)
            if index is None and conversation.get('status') == 'completed' and target.startswith('#index:'):
                number = target.removeprefix('#index:')
                if number.isascii() and number.isdecimal() and int(number) < len(segments):
                    index = int(number)
            if index is None:
                unresolved.append(target)
            elif index not in indices:
                indices.append(index)
        if unresolved:
            raise ValueError('Unable to resolve transcript segment assignment target(s): ' + ', '.join(unresolved))
    if not indices:
        raise LookupError('Segment not found')
    receipt = dict(conversation.get('manual_speaker_assignments') or {})
    receipt['segments'] = dict(receipt.get('segments') or {})
    receipt['speakers'] = dict(receipt.get('speakers') or {})
    generation = receipt.get('generation', 0) + 1
    receipt['generation'] = generation
    identity = dict(generation=generation, person_id=person_id, is_user=is_user)
    if not use_for_speech_training:
        identity['use_for_speech_training'] = False
    previous = set()
    resolved = []
    for index in indices:
        segment = segments[index]
        if segment.get('person_id') and segment['person_id'] != person_id:
            previous.add(segment['person_id'])
        if not segment.get('id'):
            segment['id'] = str(uuid.uuid4())
        resolved.append(segment['id'])
        if speaker_id is None:
            receipt['segments'][segment['id']] = dict(identity)
    if speaker_id is not None:
        receipt['speakers'][str(speaker_id)] = dict(identity)
        by_id = {segment.get('id'): segment for segment in segments}
        for sid in list(receipt['segments']):
            owner = by_id.get(sid)
            if sid in resolved or (owner and owner.get('speaker_id') == speaker_id):
                receipt['segments'].pop(sid, None)
    if not receipt['segments']:
        receipt.pop('segments', None)
    if not receipt['speakers']:
        receipt.pop('speakers', None)
    return apply_manual_assignments(segments, receipt), receipt, resolved, previous


def acknowledged_teaching(conversation: dict, person_id: str, segment_ids: list[str]) -> bool:
    """Only a persisted manual decision can authorize the delayed socket attempt."""
    if not person_id or not segment_ids:
        return False
    receipt = conversation.get('manual_speaker_assignments') or {}
    current = {segment.get('id'): segment for segment in conversation.get('transcript_segments', [])}
    speakers = receipt.get('speakers') or {}
    overrides = receipt.get('segments') or {}
    for sid in segment_ids:
        segment = current.get(sid) or {}
        override = overrides.get(sid)
        covering = speakers.get(str(segment.get('speaker_id')))
        decisions = [value for value in (override, covering) if value]
        if not decisions:
            return False
        decision = max(decisions, key=lambda value: value.get('generation', 0))
        if (
            decision.get('person_id') != person_id
            or decision.get('is_user')
            or not decision.get('use_for_speech_training', True)
            or segment.get('person_id') != person_id
            or segment.get('is_user')
        ):
            return False
    return True


@dataclass(frozen=True)
class LiveTranscriptMerge:
    """Accepted storage payload and client delta from one transaction attempt."""

    segments: list[dict]
    updated_ids: set[str]
    removed_ids: list[str]
    absorbed_into: dict[str, str]


def merge_live_segments(persisted: list[dict], fresh: list[dict], receipt: dict) -> LiveTranscriptMerge:
    """Plan only the mutable tail and fresh batch against the transaction's receipt.

    Reconstruct models on every attempt: combine_segments mutates its inputs.
    Historical segments stay dictionaries, avoiding full model hydration per tick.
    """
    tail = [TranscriptSegment(**persisted[-1])] if persisted else []
    incoming = [TranscriptSegment(**segment) for segment in fresh]
    covered = set(receipt.get('segments') or {})
    speakers = receipt.get('speakers') or {}
    covered.update(s.id for s in [*tail, *incoming] if str(s.speaker_id) in speakers and s.id)
    combined = TranscriptSegment.combine_segments(tail, incoming, protected_segment_ids=covered)
    result = persisted[:-1] + [segment.model_dump() for segment in combined.segments]
    result.sort(key=lambda s: (s.get('start', 0), s.get('end', 0)))
    return LiveTranscriptMerge(
        result,
        {s.id for s in combined.joined if s.id},
        combined.removed_ids,
        combined.absorbed_into,
    )
