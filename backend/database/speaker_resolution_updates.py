"""Revision-fenced identity-only persistence after late capture audio arrives."""

import copy
import logging
from typing import Callable, Optional
from google.cloud import firestore
import config.speaker_match_scores as match_scores
from database import conversations
from database._client import get_data_plane_firestore_client as get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.conversation_revisions import firestore_revision_datetime

logger = logging.getLogger(__name__)


def persist_speaker_resolution_if_current(
    uid: str,
    conversation_data: dict,
    *,
    expected_updated_at,
    on_committed_identity: Optional[Callable[[dict, dict], None]] = None,
) -> bool:
    """Identity-only commit: refuse every intervening write, including manual edits.

    No lifecycle, summary, task, or processing admission is owned by this path.
    Protection is copied from the read snapshot and a migration defeats its CAS.
    """
    if expected_updated_at is None:
        return False
    client = get_firestore_client()
    ref = (
        client.collection('users')
        .document(uid)
        .collection(conversations.conversations_collection)
        .document(conversation_data['id'])
    )

    @firestore.transactional
    def persist(transaction):
        snapshot = ref.get(transaction=transaction)
        deleting = account_deletion_document(uid, firestore_client=client).get(transaction=transaction)
        current = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or deleting.exists
            or conversations.is_soft_deleted(current)
            or current.get('discarded')
            or current.get('is_locked')
            or current.get('status') != 'completed'
            or firestore_revision_datetime(getattr(snapshot, 'update_time', None)) != expected_updated_at
        ):
            return False
        fields = ('transcript_segments', 'transcript_segments_compressed', 'speaker_resolution', match_scores.FIELD)
        patch = {key: copy.deepcopy(conversation_data[key]) for key in fields if key in conversation_data}
        receipt = conversations.decode_manual_speaker_assignments(
            uid, current.get('manual_speaker_assignments'), bool(current.get('manual_speaker_assignments_compressed'))
        )
        patch['transcript_segments'] = conversations.apply_manual_assignments(patch['transcript_segments'], receipt)
        prepared = conversations.encode_conversation_for_write(
            uid, patch, current.get('data_protection_level') or 'standard'
        )
        identities = None
        if on_committed_identity is not None:
            # Decode the actual transaction snapshots, including protection and
            # the current manual receipt. Never observe the speculative payload.
            def readable(data):
                return {
                    'id': conversation_data['id'],
                    'transcript_segments': copy.deepcopy(
                        conversations.decode_transcript_segments_verified(
                            uid, data.get('transcript_segments', []), bool(data.get('transcript_segments_compressed'))
                        )
                    ),
                }

            identities = (readable(current), readable(prepared))
        transaction.update(ref, {key: prepared[key] for key in fields if key in prepared})
        return (identities,)

    written = persist(client.transaction())
    if written:
        if on_committed_identity is not None:
            try:
                on_committed_identity(*written[0])
            except Exception as error:
                # Observability cannot turn an authoritative commit into failure.
                logger.warning(
                    'event=owner_identity_repair_metrics outcome=failed exception_type=%s', type(error).__name__
                )
        conversations.invalidate_people_stats_cache(uid)
        # Typesense explicitly excludes transcript/identity fields. This update
        # changes none of its allow-listed projection inputs.
    return bool(written)
