"""Create a missing list head under the existing destructive-operation fence."""

from typing import Any
from uuid import uuid4

from google.cloud import firestore

from config.list_projection import STATE_COLLECTION
from database.legal_holds import external_write_fence


def initialize_head(uid: str, family: str, *, firestore_client: Any) -> str | None:
    reference = firestore_client.collection('users').document(uid).collection(STATE_COLLECTION).document(family)

    @firestore.transactional
    def initialize(transaction: Any) -> str | None:
        # Reuse the existing authority policy without changing its reads or
        # locks. Deletion starting after this read conflicts with the commit.
        with external_write_fence(uid, firestore_client=firestore_client, transaction=transaction):
            snapshot = reference.get(transaction=transaction)
            if snapshot.exists:
                value = (snapshot.to_dict() or {}).get('version')
                return value if isinstance(value, str) and len(value) == 32 else None
            initial = uuid4().hex
            transaction.create(reference, {'version': initial})
            return initial

    # Optional optimization: contention falls back to the source reader;
    # another poll can retry, rather than spending a GET's latency on retries.
    return initialize(firestore_client.transaction(max_attempts=1))
