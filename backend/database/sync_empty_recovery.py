"""Owner-scoped, non-expiring paid intent; payloads are encrypted by the caller."""

import hashlib
import time

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore

from database._client import get_firestore_client
from database.legal_holds import external_write_fence


def claim(uid, segment_id, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    key = hashlib.sha256(segment_id.encode()).hexdigest()
    ref = client.collection('users').document(uid).collection('sync_empty_recovery').document(key)
    with external_write_fence(uid):
        try:
            receipt = ref.create({'state': 'running', 'created_at': time.time(), 'provider': 'modulate'})
            return ref, receipt.update_time, None
        except AlreadyExists:
            row = ref.get().to_dict() or {}
            if row.get('state') == 'completed' and isinstance(row.get('response'), str):
                return ref, None, row['response']
            # A crash/network uncertainty spends the intent. Reconciliation must
            # resolve it; task retries and reuploads cannot buy another call.
            raise RuntimeError('sync empty recovery intent unresolved') from None


def settle(uid, ref, version, response):
    with external_write_fence(uid):
        ref.update(
            {'state': 'completed', 'response': response, 'settled_at': time.time()},
            option=firestore.LastUpdateOption(version),
        )
