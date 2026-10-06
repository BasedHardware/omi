"""Manual identity policy shared by transactional transcript writers.

The receipt authorizes best-effort teaching; it is not an enrollment job.
Inference must never create or replace these explicit user decisions.
"""

from dataclasses import dataclass, field, replace
from typing import Annotated, Any, Mapping, Optional
import uuid

from pydantic import BaseModel, Field, StrictStr

from config.live_capture import capture_window_reason
from config.audio_timeline import (
    live_capture_window_merge_preservation_enabled,
    live_capture_window_merge_union_enabled,
)
from models.capture_window_proof import CaptureWindowProof
from database.read_boundary import parse_payload_strict
from models.speaker_label_provenance import project_source
from models.transcript_segment import TranscriptSegment, legacy_conversation_segment_id

TEACHING_CANDIDATE_LIMIT = 3
LIVE_TRANSCRIPT_REPLAY_RECEIPT_COMMIT_LIMIT = 2
LIVE_TRANSCRIPT_REPLAY_RECEIPT_BATCH_LIMIT = 128
LIVE_TRANSCRIPT_REPLAY_RECEIPT_LIMIT = (
    LIVE_TRANSCRIPT_REPLAY_RECEIPT_COMMIT_LIMIT * LIVE_TRANSCRIPT_REPLAY_RECEIPT_BATCH_LIMIT
)


class LiveTranscriptReplayReceipt(BaseModel):
    model_config = {'extra': 'forbid'}

    commits: list[Annotated[list[StrictStr], Field(max_length=LIVE_TRANSCRIPT_REPLAY_RECEIPT_BATCH_LIMIT)]] = Field(
        max_length=LIVE_TRANSCRIPT_REPLAY_RECEIPT_COMMIT_LIMIT
    )


def _receipt_section(receipt: object, key: str) -> Mapping:
    """A stored receipt is user data: a wrong-typed section must not crash the reader."""
    if not isinstance(receipt, Mapping):
        return {}
    section = receipt.get(key)
    return section if isinstance(section, Mapping) else {}


def manual_owner_reserved(receipt: Mapping) -> bool:
    """An explicit owner decision reserves the owner even without a voiceprint."""
    return any(
        isinstance(entry, dict) and entry.get('is_user') is True
        for entries in (_receipt_section(receipt, 'speakers'), _receipt_section(receipt, 'segments'))
        for entry in entries.values()
    )


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
    speakers = _receipt_section(receipt, 'speakers')
    overrides = _receipt_section(receipt, 'segments')
    if not speakers and not overrides:
        return segments
    rejected = manual_rejected_speakers(receipt)
    result = None
    for index, segment in enumerate(segments):
        by_segment = overrides.get(segment.get('id'))
        by_speaker = speakers.get(str(segment.get('speaker_id')))
        negative = rejected.get(segment.get('speaker_id'))
        if not isinstance(by_segment, dict):
            by_segment = None
        if not isinstance(by_speaker, dict):
            by_speaker = None
        if not isinstance(negative, dict):
            negative = None
        if (
            by_speaker is not None
            and by_speaker.get('source') == 'carried'
            and by_speaker.get('speaker_id_scope') != segment.get('speaker_id_scope')
        ):
            by_speaker = None
        if negative is not None and negative.get('speaker_id_scope') is not None:
            if negative['speaker_id_scope'] != segment.get('speaker_id_scope'):
                negative = None
        decisions = [value for value in (by_segment, by_speaker, negative) if value]
        if not decisions:
            continue
        decision = max(decisions, key=lambda value: value.get('generation', 0))
        is_user = bool(decision.get('is_user', False))
        person_id = decision.get('person_id')
        status = 'user' if is_user else 'not_user' if person_id else 'unknown'
        source = project_source({'person_id': person_id, 'is_user': is_user}, decision)
        if (
            segment.get('is_user') == is_user
            and segment.get('person_id') == person_id
            and segment.get('speaker_identity_status') == status
            and segment.get('speaker_match_source') is None
            and segment.get('speaker_label_source') == source
        ):
            continue
        if result is None:
            result = list(segments)
        copied = dict(segment)
        copied.update(
            is_user=is_user,
            person_id=person_id,
            speaker_identity_status=status,
            speaker_match_source=None,
            speaker_label_source=source,
        )
        result[index] = copied
    return result if result is not None else segments


def manual_rejected_speakers(receipt: Mapping) -> dict:
    """speaker_id -> its winning rejection decision, per the manual receipt.

    Speaker entries carry the speaker id in their key; selected-segment
    rejections carry the voice they were written against in ``speaker_id``.
    A rejection only stands while no newer explicit positive decision
    (an entry without ``rejection``) covers the same voice.
    """
    decisions: dict = {}
    for key, entry in _receipt_section(receipt, 'speakers').items():
        if not isinstance(entry, dict):
            continue
        try:
            speaker_id = int(key)
        except (TypeError, ValueError):
            continue
        decisions.setdefault(speaker_id, []).append(entry)
    for entry in _receipt_section(receipt, 'segments').values():
        if isinstance(entry, dict) and isinstance(entry.get('speaker_id'), int):
            decisions.setdefault(entry['speaker_id'], []).append(entry)
    rejected: dict = {}
    for speaker_id, entries in decisions.items():
        rejection = None
        positive = -1
        for entry in entries:
            generation = entry.get('generation', 0)
            if entry.get('rejection'):
                if rejection is None or generation >= rejection.get('generation', 0):
                    rejection = entry
            else:
                positive = max(positive, generation)
        if rejection is not None and positive <= rejection.get('generation', 0):
            rejected[speaker_id] = rejection
    return rejected


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

    segments = dict(_receipt_section(receipt, 'segments'))
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


REJECTION_KINDS = ('not_me', 'not_person', 'not_a_person')


def normalize_rejection(rejection: Optional[dict]) -> Optional[dict]:
    """Validate the kind and keep ``person_id`` only where it binds a person."""
    if rejection is None:
        return None
    kind = rejection.get('kind')
    if kind not in REJECTION_KINDS:
        raise ValueError('Unknown speaker rejection kind')
    person_id = rejection.get('person_id') if kind == 'not_person' else None
    if kind == 'not_person' and not (person_id and str(person_id).strip()):
        raise ValueError('person_id is required when kind is not_person')
    return {'kind': kind, 'person_id': person_id}


def donor_selected_ids(
    source_segments: list, *, segment_ids=None, speaker_id=None, segment_index=None, strict_speaker=False
) -> list:
    """Translate ids targeted at a merged-away donor into surviving segment ids.

    Every requested id must exist on the donor, or the whole edit fails.
    Rejections additionally require the ids to be the donor's own records of the
    requested speaker; positive assigns tolerate the donor's stale numbering.
    """
    if segment_ids:
        by_id = {s.get('id'): s for s in source_segments if s.get('id')}
        missing = [sid for sid in segment_ids if sid not in by_id]
        if missing:
            raise ValueError('Unable to resolve transcript segment assignment target(s): ' + ', '.join(missing))
        selected = [by_id[sid] for sid in segment_ids]
        if strict_speaker and speaker_id is not None and any(s.get('speaker_id') != speaker_id for s in selected):
            raise ValueError('Selected segments do not belong to the requested speaker')
    elif segment_index is not None:
        selected = source_segments[segment_index : segment_index + 1]
    else:
        selected = [s for s in source_segments if s.get('speaker_id') == speaker_id]
    return [s['id'] for s in selected if s.get('id')]


def manual_assignment(
    conversation: dict,
    *,
    person_id: Optional[str],
    is_user: bool,
    segment_ids: Optional[list[str]] = None,
    speaker_id: Optional[int] = None,
    segment_index: Optional[int] = None,
    use_for_speech_training: bool = True,
    rejection: Optional[dict] = None,
) -> tuple[list[dict], dict, list[str], set[str]]:
    rejection = normalize_rejection(rejection)
    segments = [dict(segment) for segment in conversation.get('transcript_segments', [])]

    for index, segment in enumerate(segments):
        if not segment.get('id') and conversation.get('id'):
            segment['id'] = legacy_conversation_segment_id(conversation['id'], index)
        if segment.get('speaker_id') is None:
            segment['speaker_id'] = TranscriptSegment(**segment).speaker_id
    if segment_index is not None:
        indices = [segment_index] if 0 <= segment_index < len(segments) else []
    elif speaker_id is not None and not segment_ids:
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
        if speaker_id is not None and any(segments[i].get('speaker_id') != speaker_id for i in indices):
            raise ValueError('Selected segments do not belong to the requested speaker')
    if not indices:
        raise LookupError('Segment not found')
    receipt = dict(conversation.get('manual_speaker_assignments') or {})
    receipt['segments'] = dict(_receipt_section(receipt, 'segments'))
    receipt['speakers'] = dict(_receipt_section(receipt, 'speakers'))
    generation = receipt.get('generation', 0) + 1
    receipt['generation'] = generation
    identity: dict = dict(generation=generation, person_id=person_id, is_user=is_user)
    if not use_for_speech_training or rejection:
        identity['use_for_speech_training'] = False
    if rejection:
        identity['rejection'] = {'kind': rejection.get('kind'), 'person_id': rejection.get('person_id')}
    previous = set()
    resolved = []
    for index in indices:
        segment = segments[index]
        if segment.get('person_id') and segment['person_id'] != person_id:
            previous.add(segment['person_id'])
        if not segment.get('id'):
            segment['id'] = str(uuid.uuid4())
        resolved.append(segment['id'])
        if speaker_id is None or segment_ids:
            entry = dict(identity)
            entry['speaker_id'] = segment.get('speaker_id')
            if segment.get('speaker_id_scope') is not None:
                entry['speaker_id_scope'] = segment['speaker_id_scope']
            receipt['segments'][segment['id']] = entry
    if speaker_id is not None and not segment_ids:
        entry = dict(identity)
        scopes = {segments[i].get('speaker_id_scope') for i in indices}
        if len(scopes) == 1 and next(iter(scopes)) is not None:
            entry['speaker_id_scope'] = next(iter(scopes))
        receipt['speakers'][str(speaker_id)] = entry
        by_id = {segment.get('id'): segment for segment in segments}
        for sid in list(receipt['segments']):
            owner = by_id.get(sid)
            if sid in resolved or (owner and owner.get('speaker_id') == speaker_id):
                receipt['segments'].pop(sid, None)
    if not receipt['segments']:
        receipt.pop('segments', None)
    if not receipt['speakers']:
        receipt.pop('speakers', None)
    applied = apply_manual_assignments(segments, receipt)
    if rejection is not None:
        chosen = set(indices)
        rejected = manual_rejected_speakers(receipt)
        for index, segment in enumerate(segments):
            negative = rejected.get(segment.get('speaker_id'))
            if negative is None or negative.get('generation') != generation:
                continue
            if index in chosen or applied[index] is segment:
                continue
            scope = negative.get('speaker_id_scope')
            if scope is not None and scope != segment.get('speaker_id_scope'):
                continue
            if segment.get('person_id'):
                previous.add(segment['person_id'])
            resolved.append(segment['id'])
    return applied, receipt, resolved, previous


def acknowledged_teaching(conversation: dict, person_id: str, segment_ids: list[str]) -> bool:
    """Only a persisted manual decision can authorize the delayed socket attempt."""
    if not person_id or not segment_ids:
        return False
    receipt = conversation.get('manual_speaker_assignments') or {}
    current = {segment.get('id'): segment for segment in conversation.get('transcript_segments', [])}
    speakers = _receipt_section(receipt, 'speakers')
    overrides = _receipt_section(receipt, 'segments')
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
    capture_reasons: dict[str, str] = field(default_factory=dict)
    created_ids: set[str] = field(default_factory=set)
    capture_proofs: dict[str, CaptureWindowProof] = field(default_factory=dict)

    def with_segments(self, segments: list[dict]) -> 'LiveTranscriptMerge':
        return replace(self, segments=segments)


def replay_receipt_commits(payload: Mapping[str, Any], document_path: str) -> list[list[str]]:
    return parse_payload_strict(LiveTranscriptReplayReceipt, payload, document_path=document_path).commits


def merge_live_segments(
    persisted: list[dict],
    fresh: list[dict],
    receipt: dict,
    *,
    absorbed_ids: Optional[list[str]] = None,
    capture_reasons: Optional[dict[str, str]] = None,
    capture_proofs: Optional[dict[str, CaptureWindowProof]] = None,
) -> LiveTranscriptMerge:
    """Plan only the mutable tail and fresh batch against the transaction's receipt.

    Reconstruct models on every attempt: combine_segments mutates its inputs.
    Historical segments stay dictionaries, avoiding full model hydration per tick.
    """
    # The transaction's snapshot is the authority after an ambiguous write:
    # a commit may have succeeded even when its acknowledgement was lost.
    # Filter IDs before combine_segments, which otherwise merges/appends the
    # same words a second time. Also dedupe repeated IDs in one fresh batch.
    seen_ids = {str(segment['id']) for segment in persisted if segment.get('id')}
    seen_ids.update(str(absorbed_id) for absorbed_id in (absorbed_ids or []))
    prior_ids = set(seen_ids)
    unique_fresh = []
    replayed_commit = False
    for segment in fresh:
        segment_id = segment.get('id')
        if segment_id and str(segment_id) in seen_ids:
            replayed_commit = replayed_commit or str(segment_id) in prior_ids
            continue
        unique_fresh.append(segment)
        if segment_id:
            seen_ids.add(str(segment_id))
    # Plan against the identity the writer will store. Otherwise a fresh word
    # tagged by live inference never matches a manually decided tail's
    # speaker_match_source, and every word lands in its own segment.
    tail = [TranscriptSegment(**segment) for segment in apply_manual_assignments(persisted[-1:], receipt)]
    incoming = [TranscriptSegment(**segment) for segment in apply_manual_assignments(unique_fresh, receipt)]
    for segment in tail:
        if segment.audio_capture_start is None or segment.audio_capture_end is None:
            segment.capture_window_reason = 'inherited_unknown'
    for segment in incoming:
        segment.capture_window_reason = capture_window_reason((capture_reasons or {}).get(str(segment.id)))
    if live_capture_window_merge_union_enabled():
        for segment in [*tail, *incoming]:
            proof = (capture_proofs or {}).get(str(segment.id))
            if proof and proof.matches(segment.capture_window_bounds()):
                segment.capture_merge_proof = proof
    # Selected-segment decisions are keyed by ID, so those segments must keep it.
    # Speaker-wide decisions are keyed by speaker: same-speaker merges keep them.
    covered = set(_receipt_section(receipt, 'segments'))
    speakers = _receipt_section(receipt, 'speakers')
    speaker_bound = {
        s.speaker_id for s in [*tail, *incoming] if s.speaker_id is not None and str(s.speaker_id) in speakers
    }
    # Unplaced fallback IDs are the retry receipt. Never absorb one into the
    # preceding unplaced tail, or a committed retry would no longer find its
    # ID in the next transaction snapshot.
    covered.update(s.id for s in incoming if s.audio_alignment == 'unplaced' and s.id)
    if replayed_commit or len(incoming) > LIVE_TRANSCRIPT_REPLAY_RECEIPT_BATCH_LIMIT:
        covered.update(s.id for s in [*tail, *incoming] if s.id)
    combined = TranscriptSegment.combine_segments(
        tail,
        incoming,
        protected_segment_ids=covered,
        speaker_bound_ids=speaker_bound,
        preserve_capture_windows=live_capture_window_merge_preservation_enabled(),
    )
    result = persisted[:-1] + [segment.model_dump() for segment in combined.segments]
    result.sort(key=lambda s: (s.get('start', 0), s.get('end', 0)))
    return LiveTranscriptMerge(
        result,
        {s.id for s in combined.joined if s.id},
        combined.removed_ids,
        combined.absorbed_into,
        {str(s.id): s.capture_window_reason for s in combined.joined if s.id},
        {str(s.id) for s in combined.segments if s.id and str(s.id) not in prior_ids},
        {
            str(s.id): s.capture_merge_proof
            for s in combined.segments
            if result and s.id == result[-1].get('id') and s.capture_merge_proof is not None
        },
    )
