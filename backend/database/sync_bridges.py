"""Revision-fenced completion receipts for retained sync bridge tombstones."""

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional


def mark_sync_bridge_cleaned(uid, source_id, revision, audio_target, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(source_id)

    @firestore.transactional
    def mark(transaction):
        row = ref.get(transaction=transaction).to_dict()
        if not row or not row.get('deleted') or not row.get('sync_merged_into'):
            return False
        if row.get('sync_content_revision') != revision:
            return False
        transaction.update(ref, {'sync_bridge_cleaned_revision': revision, 'sync_bridge_audio_target': audio_target})
        return True

    return run_transactional(client, mark)
