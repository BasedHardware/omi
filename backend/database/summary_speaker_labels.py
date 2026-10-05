"""Atomic note-inferred people and labels, strictly below existing assignments.

The note is already durable when this runs. A failed transaction changes neither
people nor labels; it never fails note processing and never schedules teaching.
"""

import hashlib
import logging
from datetime import datetime, timezone

from google.cloud import firestore

from config.summary_speaker_labels import summary_speaker_labels_enabled
from database.read_boundary import parse_payload_strict
from models.transcript_segment import TranscriptSegment
from utils.conversations.summary_speaker_labels import (
    full_real_name,
    normalized_name,
    select_candidates,
    transcript_identity,
)
from utils.speaker_permissions import named_speaker_prompts_allowed

logger = logging.getLogger(__name__)
CATALOG_LIMIT = 500


def read_summary_people_catalog(uid: str, transaction, *, firestore_client=None):
    """Read one bounded, unfiltered catalog inside the assignment transaction."""
    from database._client import get_firestore_client

    client = firestore_client if firestore_client is not None else get_firestore_client()
    return list(
        client.collection('users')
        .document(uid)
        .collection('people')
        .limit(CATALOG_LIMIT + 1)
        .stream(transaction=transaction)
    )


def apply_summary_speaker_labels(uid: str, conversation, *, firestore_client=None) -> int:
    if not summary_speaker_labels_enabled():
        return 0
    candidates = getattr(conversation.structured, '_summary_speaker_candidates', [])
    roster = getattr(conversation.structured, '_summary_speaker_roster', None)
    if not candidates or not roster or conversation.discarded:
        return 0
    try:
        from database import conversations as conversations_db
        from database._client import get_firestore_client

        # A subscription read failure declines the entire stage, including owner;
        # never infer paid eligibility and never touch manual endpoints.
        allow_named = named_speaker_prompts_allowed(uid) if any(not c.is_owner for c in candidates) else False
        client = firestore_client if firestore_client is not None else get_firestore_client()
        user_ref = client.collection('users').document(uid)
        conversation_ref = user_ref.collection('conversations').document(conversation.id)
        expected = transcript_identity([s.model_dump() for s in conversation.transcript_segments])

        @firestore.transactional
        def commit(transaction):
            if not summary_speaker_labels_enabled():
                return None
            snapshot = conversation_ref.get(transaction=transaction)
            if not snapshot.exists:
                return None
            current = snapshot.to_dict() or {}
            if (
                current.get('deleted')
                or current.get('discarded')
                or current.get('is_locked')
                or current.get('status') != 'completed'
                or current.get('merged_into')
            ):
                return None
            note = current.get('structured') or {}
            if (note.get('title'), note.get('overview')) != (
                conversation.structured.title,
                conversation.structured.overview,
            ):
                return None
            segments = conversations_db.decode_transcript_segments_verified(
                uid, current.get('transcript_segments'), bool(current.get('transcript_segments_compressed'))
            )
            if transcript_identity(segments) != expected:
                return None
            receipt = conversations_db.decode_manual_speaker_assignments(
                uid,
                current.get('manual_speaker_assignments'),
                bool(current.get('manual_speaker_assignments_compressed')),
            )
            selected = select_candidates(candidates, segments, receipt, roster, allow_named=allow_named)
            if not selected:
                return None
            people_ref = user_ref.collection('people')
            # Bounded catalog, no speech-profile/learning projection or N+1 reads.
            # A truncated catalog cannot establish uniqueness, so decline all names.
            people = []
            if any(not s.is_owner for s in selected):
                docs = read_summary_people_catalog(uid, transaction, firestore_client=client)
                if len(docs) > CATALOG_LIMIT:
                    return None
                people = [{**d.to_dict(), 'id': d.id} for d in docs]
            staged_people = {}
            assignments = {}
            now = datetime.now(timezone.utc)
            for speaker in selected:
                person_id = None
                if not speaker.is_owner:
                    proposed_name = normalized_name(speaker.name)
                    matches = [
                        p
                        for p in people
                        if normalized_name(p.get('name') or '') == proposed_name
                        or (
                            full_real_name(proposed_name)
                            and proposed_name in [normalized_name(a) for a in p.get('aliases', [])]
                        )
                    ]
                    if speaker.person_id:
                        matches = [p for p in people if p['id'] == speaker.person_id]
                    if len(matches) > 1:
                        continue
                    if matches:
                        person = matches[0]
                        if (
                            person.get('deleted')
                            or person.get('status') in {'merged', 'dismissed'}
                            or person.get('is_ai_agent')
                        ):
                            continue
                        person_id = person['id']
                    elif speaker.person_id or not speaker.may_create:
                        continue
                    else:
                        person_id = 'summary-' + hashlib.sha256(normalized_name(speaker.name).encode()).hexdigest()[:32]
                        # The catalog read fenced absence. Transaction create cannot
                        # overwrite a concurrent create/rename of this deterministic ID.
                        staged_people[person_id] = dict(
                            id=person_id,
                            name=speaker.name,
                            created_at=now,
                            updated_at=now,
                            speech_samples=[],
                            speech_samples_version=3,
                            creation_source='summary_inferred',
                        )
                for sid in speaker.segment_ids:
                    assignments[sid] = (speaker, person_id)
            if not assignments:
                return None
            updated = [dict(s) for s in segments]
            for segment in updated:
                if segment.get('id') not in assignments:
                    continue
                speaker, person_id = assignments[segment['id']]
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
            # Encode before staging any write: a codec error cannot leave people.
            validated = [
                parse_payload_strict(
                    TranscriptSegment,
                    s,
                    document_path=f'users/{uid}/conversations/{conversation.id}/segments/{s.get("id", "unknown")}',
                )
                for s in updated
            ]
            payload = conversations_db.encode_conversation_for_write(
                uid, {'transcript_segments': updated}, current.get('data_protection_level', 'standard')
            )
            for pid, person in staged_people.items():
                transaction.create(people_ref.document(pid), person)
            transaction.update(conversation_ref, payload)
            return validated, len(assignments)

        committed = commit(client.transaction())
        if committed:
            segments, count = committed
            conversation.transcript_segments = segments
            conversations_db.invalidate_people_stats_cache(uid)
            logger.info('summary_speaker_labels outcome=applied segments=%d', count)
            return count
        logger.info('summary_speaker_labels outcome=declined')
    except Exception as error:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_notes',
            from_mode='summary_speaker_labels',
            to_mode='saved_note',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        logger.warning('summary_speaker_labels outcome=error exception_type=%s', type(error).__name__)
    return 0
