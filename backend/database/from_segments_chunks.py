"""Bounded point cleanup for encrypted continuation staging."""

from typing import Any


def purge_chunks(uid: str, conversation_id: str, count: int = 128, *, firestore_client: Any = None) -> None:
    if firestore_client is None:
        from database.account_deletion_marker import account_deletion_firestore_client

        firestore_client = account_deletion_firestore_client()
    client: Any = firestore_client
    chunks = client.collection('users').document(uid).collection('from_segments_chunks')
    # One commit, not one RPC per slot: every conversation delete runs this, and
    # 128 sequential deletes cost seconds even when no chunk was ever staged.
    batch = client.batch()
    for index in range(min(count, 128)):
        batch.delete(chunks.document(f'{conversation_id}-{index:03d}'))
    batch.commit()
