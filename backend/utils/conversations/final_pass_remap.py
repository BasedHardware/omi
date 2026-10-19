"""Fail-closed speaker-only promotion; stored text and annotations are immutable."""

from copy import deepcopy
from typing import Any

from utils.conversations.segment_remap import plan_segment_remap
from utils.manual_speaker_assignments import (
    apply_manual_assignments,
    manual_assignment_decision,
    manual_rejected_speakers,
)

SPEAKER_FIELDS = (
    'speaker',
    'speaker_id',
    'speaker_id_scope',
    'speaker_identity_status',
    'is_user',
    'person_id',
    'speaker_label_source',
    'speaker_match_source',
)


def remap_final_record(old, new, receipt, structured, *, clock_offset, protect_legacy_owner=True) -> dict[str, Any]:
    plan = plan_segment_remap(old, new, offset_seconds=clock_offset)
    if not plan.safe:
        raise ValueError('unsafe final record remap')
    # Preserve persisted IDs, text, clocks, translations and every non-speaker
    # field. A stored segment cannot safely split text without edited word clocks.
    # Refuse a projection spanning different candidate speakers.
    targets = {s['id']: s for s in new}
    stored = deepcopy(old)
    rejected = manual_rejected_speakers(receipt)
    current_receipt = {k: deepcopy(v) for k, v in receipt.items() if k not in {'segments', 'speakers'}}
    current_receipt['segments'] = {
        source['id']: decision
        for source in old
        if (decision := manual_assignment_decision(source, receipt, rejected)) is not None
    }
    for source, destination in zip(old, stored):
        candidates = [targets[target] for target in plan.ids[source['id']]]
        identities = {tuple(s.get(field) for field in SPEAKER_FIELDS) for s in candidates}
        if len(identities) != 1:
            raise ValueError('conflicting speakers within stored segment')
        candidate = candidates[0]
        # Bare legacy owner edits have no reliable provenance. Conservatively
        # protect either direction of an is_user disagreement, including False.
        protected = (
            (protect_legacy_owner and source.get('is_user', False) != candidate.get('is_user', False))
            or source.get('speaker_label_source') in {'manual', 'carried'}
            or (not source.get('speaker_match_source') and source.get('person_id'))
        )
        destination.update({field: candidate.get(field) for field in SPEAKER_FIELDS})
        if protected:
            destination.update(
                is_user=source.get('is_user', False),
                person_id=source.get('person_id'),
                speaker_label_source=source.get('speaker_label_source') or 'manual',
                speaker_match_source=None,
                speaker_identity_status=source.get('speaker_identity_status', 'unknown'),
            )
    return {
        'transcript_segments': apply_manual_assignments(stored, current_receipt),
        'manual_speaker_assignments': current_receipt,
        'structured': deepcopy(structured),
    }
