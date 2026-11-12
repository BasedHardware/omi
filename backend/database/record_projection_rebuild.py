"""Content-free playback repair debt; no seal, producer-token or object authority."""

import hashlib
import json
from datetime import datetime, timezone

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason, assert_batch_write_allowed

COLLECTION = 'record_projection_rebuild_jobs'
KIND = 'record_projection_rebuild_due'
MAX_MARKERS_PER_BATCH = 256


def marker_id(uid, cid):
    for value in (uid, cid):
        if not isinstance(value, str) or not value or '/' in value or len(value.encode()) > 256:
            raise ValueError('bounded projection owner required')
    return hashlib.sha256(json.dumps([uid, cid], separators=(',', ':')).encode()).hexdigest()


def mark_due(uid, cid, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    client.collection(COLLECTION).document(marker_id(uid, cid)).set(
        {'kind': KIND, 'owner_id': uid, 'conversation_id': cid, 'requested_at': datetime.now(timezone.utc)},
        timeout=5,
        retry=None,
    )


def mark_many(uid, conversation_ids, *, firestore_client=None):
    """One bounded cleanup RPC, rather than one timeout per socket obligation."""
    owners = set(conversation_ids)
    if not 0 < len(owners) <= MAX_MARKERS_PER_BATCH:
        raise ValueError('bounded projection marker batch required')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    batch = client.batch()
    requested_at = datetime.now(timezone.utc)
    for cid in owners:
        ref = client.collection(COLLECTION).document(marker_id(uid, cid))
        batch.set(ref, {'kind': KIND, 'owner_id': uid, 'conversation_id': cid, 'requested_at': requested_at})
    batch.commit(timeout=1, retry=None)


def retire_empty(uid, cid, *, observed_update_time, firestore_client=None):
    """Retire only observed empty debt with a transactionally clear producer map.

    An absent or malformed map is unknown, not proof of quiescence. Reading
    both documents makes a producer mint or marker replacement before commit
    conflict with deletion. This never clears or interprets producer tokens.
    """
    if observed_update_time is None:
        raise ValueError('observed projection marker version required')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    marker = client.collection(COLLECTION).document(marker_id(uid, cid))
    owner = client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def commit(tx):
        observed = marker.get(transaction=tx)
        if not observed.exists or observed.update_time != observed_update_time:
            return 'changed'
        snapshot = owner.get(transaction=tx)
        sessions = (snapshot.to_dict() or {}).get('record_upload_sessions')
        if not snapshot.exists or not isinstance(sessions, dict) or sessions:
            return 'producer_fenced'
        tx.delete(marker)
        return 'retired_no_objects'

    return run_transactional(client, commit, transient=True)


def apply_projection(uid, cid, payload, *, expected_audio_files, firestore_client=None):
    """Cold repair only: deletion intent and projection CAS share the commit."""
    from database.conversations import AudioFilesChanged, audio_files_revision, retain_aliases

    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def commit(tx):
        snapshot = ref.get(transaction=tx)
        if not snapshot.exists:
            return False
        row = snapshot.to_dict() or {}
        if row.get('deleted') or row.get('discarded') or row.get('private_cloud_sync_enabled') is False:
            return False
        try:
            assert_batch_write_allowed(client, tx, uid, conversation_ids=(cid,))
        except BatchPrivacyBlocked as blocked:
            if blocked.reason in {
                BatchPrivacyReason.ACCOUNT_DELETED,
                BatchPrivacyReason.ACCOUNT_MISSING,
                BatchPrivacyReason.CONVERSATION_DELETED,
            }:
                return False
            return None  # Migration, generation holds and unknown refusals retain debt without a write.
        if audio_files_revision(row.get('audio_files') or []) != audio_files_revision(expected_audio_files):
            raise AudioFilesChanged('audio projection changed')
        tx.update(ref, {'audio_files': retain_aliases(payload['audio_files'], row.get('audio_files') or [])})
        # A retained socket worker may still publish a later tail. Its existing
        # producer fence is read-only here: repair never clears or seals it.
        return None if row.get('record_upload_sessions') else True

    return run_transactional(client, commit, transient=True)
