"""Bounded point cleanup for encrypted continuation staging."""

from typing import Any


def purge_chunks(uid: str, conversation_id: str, count: int = 128, *, firestore_client: Any = None) -> None:
    if firestore_client is None:
        from database.account_deletion_marker import account_deletion_firestore_client

        firestore_client = account_deletion_firestore_client()
    client: Any = firestore_client
    chunks = client.collection('users').document(uid).collection('from_segments_chunks')
    for index in range(min(count, 128)):
        chunks.document(f'{conversation_id}-{index:03d}').delete()
