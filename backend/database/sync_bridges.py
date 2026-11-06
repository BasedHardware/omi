"""Revision-fenced completion receipts for retained sync bridge tombstones."""

from google.api_core.exceptions import NotFound
from google.cloud import firestore

from database._client import get_firestore_client, run_transactional


def mark_sync_bridge_cleaned(uid, source_id, revision, audio_target, *, firestore_client=None):
    if (
        not uid
        or not isinstance(uid, str)
        or not uid.strip()
        or not source_id
        or not isinstance(source_id, str)
        or not source_id.strip()
    ):
        return False
    clean_uid = uid.strip()
    clean_source_id = source_id.strip()
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(clean_uid).collection('conversations').document(clean_source_id)

    @firestore.transactional
    def mark(transaction):
        try:
            snapshot = ref.get(transaction=transaction)
            if hasattr(snapshot, 'exists') and not snapshot.exists:
                return False
            row = snapshot.to_dict()
            if not row or not row.get('deleted') or not row.get('sync_merged_into'):
                return False
            if row.get('sync_content_revision') != revision:
                return False
            transaction.update(
                ref, {'sync_bridge_cleaned_revision': revision, 'sync_bridge_audio_target': audio_target}
            )
            return True
        except NotFound:
            return False

    # The body re-reads and refuses a moved revision, so it meets the
    # ``transient=True`` idempotency contract. The default path only restarts an
    # expired transaction id; a contended commit exhausts the SDK's same-id
    # replay and surfaces as a bare ValueError, failing finalize after intake
    # already persisted. A fresh transaction with bounded backoff re-reads and
    # converges instead.
    try:
        return run_transactional(client, mark, transient=True)
    except NotFound:
        return False
