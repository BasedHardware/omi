"""Immutable per-device clock offsets in the existing sync-assignment metadata.

One direct document transaction per decoded request/run; the first writer
creates the anchor and every later request only reads it. No query or TTL can
forget an offset while retained audio might still be retried.
"""

import math
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client


def frozen_offset(uid: str, scope: str, raw_end: float, received_at: float, *, firestore_client: Any = None) -> float:
    client = firestore_client or get_firestore_client()
    ref = client.collection('users').document(uid).collection('sync_assignment').document(f'capture-clock-{scope}')

    @firestore.transactional
    def anchor(transaction):
        row = ref.get(transaction=transaction).to_dict()
        if row is not None:
            offset = row.get('offset')
            if row.get('version') != 1 or type(offset) not in (int, float) or not math.isfinite(offset):
                raise ValueError('invalid retained capture-clock anchor')
            return float(offset)
        offset = raw_end - received_at
        transaction.set(ref, {'version': 1, 'offset': offset, 'raw_end': raw_end, 'received_at': received_at})
        return offset

    return anchor(client.transaction())
