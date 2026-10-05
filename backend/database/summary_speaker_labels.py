"""Lower-layer persistence for note-inferred speaker labels.

Admission orchestration lives in ``utils/conversations/summary_speaker_labels``:
the import hierarchy (``database/ -> utils/ -> routers/ -> main.py``) keeps this
module free of ``utils/`` imports. The note is already durable when these run; a
failed transaction changes neither people nor labels.
"""

import hashlib
import logging
import unicodedata
from datetime import datetime, timezone

from database._client import get_firestore_client
from database.read_boundary import parse_payload_strict
from models.transcript_segment import TranscriptSegment

logger = logging.getLogger(__name__)
CATALOG_LIMIT = 500


def _normalized_name(name: str) -> str:
    # Mirrors utils.conversations.summary_speaker_labels.normalized_name; kept
    # local so this module never imports utils/.
    return ' '.join(unicodedata.normalize('NFKC', name).replace('\u2019', "'").casefold().split())


def read_summary_people_catalog(uid: str, transaction, *, firestore_client=None):
    """Read one bounded, unfiltered catalog inside the assignment transaction."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return list(
        client.collection('users')
        .document(uid)
        .collection('people')
        .limit(CATALOG_LIMIT + 1)
        .stream(transaction=transaction)
    )


def summary_inferred_person_id(name: str) -> str:
    """Deterministic person id for a note-inferred creation (uniqueness fenced by the caller)."""
    return 'summary-' + hashlib.sha256(_normalized_name(name).encode()).hexdigest()[:32]


def stage_summary_person_creation(transaction, people_ref, person_id: str, name: str) -> None:
    """Stage one person creation inside the transaction; the caller fenced absence."""
    now = datetime.now(timezone.utc)
    transaction.create(
        people_ref.document(person_id),
        dict(
            id=person_id,
            name=name,
            created_at=now,
            updated_at=now,
            speech_samples=[],
            speech_samples_version=3,
            creation_source='summary_inferred',
        ),
    )


def apply_summary_segment_updates(
    uid: str,
    conversation_id: str,
    segments: list,
    assignments: dict,
    data_protection_level: str,
    encode_conversation_for_write,
) -> tuple:
    """Apply admitted assignments; validate and encode before any write is staged.

    A codec or model error therefore cannot leave orphan people documents.
    Returns ``(validated_segments, payload)``; the caller stages the update.
    """
    updated = [dict(s) for s in segments]
    for segment in updated:
        assigned = assignments.get(segment.get('id'))
        if assigned is None:
            continue
        speaker, person_id = assigned
        segment.update(
            person_id=person_id,
            is_user=speaker.is_owner,
            speaker_identity_status='user' if speaker.is_owner else 'not_user',
            speaker_label_source='auto',
            speaker_match_source='summary_inferred',
            summary_speaker_evidence={
                'confidence': 'high',
                'evidence_segment_ids': list(speaker.evidence_segment_ids),
                'speaker_id_scope': segment.get('speaker_id_scope'),
                'version': 2,
            },
        )
    validated = [
        parse_payload_strict(
            TranscriptSegment,
            s,
            document_path=f'users/{uid}/conversations/{conversation_id}/segments/{s.get("id", "unknown")}',
        )
        for s in updated
    ]
    payload = encode_conversation_for_write(uid, {'transcript_segments': updated}, data_protection_level)
    return validated, payload
