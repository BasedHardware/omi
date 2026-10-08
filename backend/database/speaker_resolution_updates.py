"""Revision-fenced identity-only persistence after late capture audio arrives."""

import copy
from google.cloud import firestore
import config.speaker_match_scores as match_scores
from database import conversations
from database.conversations import (
    _prepare_conversation_for_write as prepare_conversation_for_identity_write,
    _reapply_current_manual_assignments as reapply_manual_identity,
    _sync_conversation_search_index as sync_identity_search_projection,
)
from database._client import get_data_plane_firestore_client as get_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.conversation_revisions import firestore_revision_datetime
from database.helpers import prepare_for_write


@prepare_for_write(
    data_arg_name='conversation_data', prepare_func=prepare_conversation_for_identity_write, preserve_result=True
)
def persist_speaker_resolution_if_current(uid: str, conversation_data: dict, *, expected_updated_at) -> bool:
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
        reapply_manual_identity(uid, patch, current)
        transaction.update(ref, patch)
        return True

    written = persist(client.transaction())
    if written:
        conversations.invalidate_people_stats_cache(uid)
        sync_identity_search_projection(uid, conversation_data['id'])
    return written
