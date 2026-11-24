"""One quality-repair attempt per effective input, reserved before any paid call."""

from typing import Any
from google.cloud import firestore
from database._client import get_firestore_client
from utils.conversations.fragment_visibility import (
    is_relevance_discarded,
    is_completed_rule_discard,
    is_settling_fragment,
)
from utils.sync import bridge_pending


def visible(row: dict[str, Any]) -> bool:
    """Use the existing default-read admission predicates, never speaker identity."""
    return bool(row) and not (
        row.get('deleted')
        or row.get('dream_duplicate_of')
        or row.get('merged_into')
        or getattr(row.get('status'), 'value', row.get('status')) == 'failed'
        or is_relevance_discarded(row)
        or is_completed_rule_discard(row)
        or is_settling_fragment(row)
        or bridge_pending.hidden(row)
    )


def claim(
    uid: str,
    conversation_id: str,
    key: str,
    *,
    expected_revision: Any,
    expected_input: str | None,
    expected_output: str | None,
    firestore_client: Any = None
) -> bool:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() if snapshot.exists else None
        if not row or not visible(row):
            return False
        if (
            row.get('sync_content_revision') != expected_revision
            or row.get('notes_llm_input_hash') != expected_input
            or row.get('notes_llm_output_hash') != expected_output
            or row.get('notes_quality_repair_input_hash') == key
        ):
            return False
        transaction.update(ref, {'notes_quality_repair_input_hash': key})
        return True

    return commit(client.transaction())
