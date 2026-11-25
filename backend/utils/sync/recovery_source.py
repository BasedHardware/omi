"""Same-owner deletion authority for an ignored recovery target; no chronology proof."""

from typing import Any

from google.cloud import firestore


def recovery_source_conversation(uid: str, conversation_id: str | None) -> str | None:
    """Return only a live same-account source, preserving all existing privacy denials."""
    if (
        not isinstance(conversation_id, str)
        or not conversation_id
        or '/' in conversation_id
        or len(conversation_id) > 128
    ):
        return None
    from database import _client
    from database.batch_pipeline_privacy import assert_batch_write_allowed

    client = _client.get_firestore_client()

    @firestore.transactional
    def read(transaction: Any) -> str | None:
        snapshots: dict[str, Any] = {}
        assert_batch_write_allowed(client, transaction, uid, conversation_ids=[conversation_id], snapshots=snapshots)
        return conversation_id if snapshots.get('conversations', {}).get(conversation_id) else None

    return read(client.transaction())
