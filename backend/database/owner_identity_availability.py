"""Durable, idempotent observations of the latest committed identity revision.

A bounded shard counter and a row-local digest commit atomically. These are
revision observations, not a census, unique-recording counts or accuracy.
"""

import hashlib
import logging

from google.cloud import firestore

from database._client import get_data_plane_firestore_client
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database import conversations, transcript_pointer
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)
SHARDS = 16
FIELD = 'owner_identity_observation_sha256'


def collection(client):
    return client.collection(f'owner_identity_availability_{current_stage()}')


def observe(uid, conversation_id, *, client=None):
    """Called after canonical persistence. Re-read current authority; never the caller's snapshot."""
    from utils.observability.owner_recognition import identity_availability_snapshot

    client = client or get_data_plane_firestore_client()
    ref = (
        client.collection('users')
        .document(uid)
        .collection(conversations.conversations_collection)
        .document(conversation_id)
    )
    shard = str(int(hashlib.sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest()[:8], 16) % SHARDS)
    counter = collection(client).document(shard)

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction, retry=None, timeout=3)
        marker = account_deletion_document(uid, firestore_client=client).get(
            transaction=transaction, retry=None, timeout=3
        )
        raw = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or any(raw.get(k) for k in ('deleted', 'discarded', 'is_locked', 'sync_merged_into'))
            or raw.get('status') != 'completed'
            or account_deletion_marker_blocks_access(
                marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
            )
        ):
            return False
        segments = conversations.decode_transcript_segments_verified(
            uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
        )
        digest, amounts = identity_availability_snapshot({**raw, 'transcript_segments': segments})
        if raw.get(FIELD) == digest:
            return False
        counts = counter.get(transaction=transaction, retry=None, timeout=3).to_dict() or {}
        for key, amount in amounts.items():
            counts[key] = counts.get(key, 0) + amount
        transaction.update(ref, {FIELD: digest})
        transaction.set(counter, counts)
        return True

    return transcript_pointer.run_preloaded_transactional(
        client, commit, attempts=1, initial_transaction=client.transaction(max_attempts=1)
    )


def observe_safely(uid, conversation_id):
    try:
        return observe(uid, conversation_id)
    except Exception as error:
        logger.warning(
            'event=owner_identity_availability outcome=observation_unavailable exception_type=%s', type(error).__name__
        )
        return False


def refresh(now, *, client=None):
    from utils.observability.owner_recognition import IDENTITY_AVAILABILITY

    client = client or get_data_plane_firestore_client()
    references = [collection(client).document(str(i)) for i in range(SHARDS)]
    rows = {s.id: s.to_dict() or {} for s in client.get_all(references, retry=None, timeout=3)}
    if set(rows) != set(map(str, range(SHARDS))):
        raise ValueError('identity counter snapshot incomplete')
    IDENTITY_AVAILABILITY.publish(rows, observed_at=now)
