"""Revision-fenced completion receipts for retained sync bridge tombstones."""

import logging
from google.api_core.exceptions import NotFound
from google.cloud import firestore

from database._client import get_firestore_client, run_transactional

logger = logging.getLogger(__name__)


def mark_sync_bridge_cleaned(uid, source_id, revision, audio_target, *, firestore_client=None):
    if not uid or not isinstance(uid, str) or not uid.strip():
        return False
    if not source_id or not isinstance(source_id, str) or not source_id.strip():
        return False

    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(source_id)

    @firestore.transactional
    def mark(transaction):
        snapshot = ref.get(transaction=transaction)
        if not getattr(snapshot, "exists", False):
            return False
        row = snapshot.to_dict()
        if not row or not row.get('deleted') or not row.get('sync_merged_into'):
            return False
        if row.get('sync_content_revision') != revision:
            return False
        transaction.update(ref, {'sync_bridge_cleaned_revision': revision, 'sync_bridge_audio_target': audio_target})
        return True

    try:
        return run_transactional(client, mark)
    except NotFound:
        return False
    except Exception as e:
        logger.warning(f"mark_sync_bridge_cleaned failed for {uid}/{source_id}: {e}")
        return False
