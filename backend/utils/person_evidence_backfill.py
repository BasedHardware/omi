"""Seed ``people/{id}.label_evidence`` from existing manual-assignment receipts.

Receipts do not record whether a decision came from the transcript tag sheet or a
suggestion card, so every receipt conversation counts as one hand label. Counting is
keyed per conversation (``manual_labels:<conversation_id>``), so re-running, resuming,
or overlapping with live labels never counts a conversation twice.
"""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from google.cloud import firestore

from database._client import run_transactional
from utils.person_evidence import merge_backfill, receipt_person_ids

DecodeReceipt = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def receipt_conversations_by_person(
    conversations: Iterable[Tuple[str, Mapping[str, Any]]], decode: DecodeReceipt
) -> Dict[str, List[str]]:
    """person_id -> conversation ids whose receipt names them. Skips deleted and merged-away rows."""
    found: Dict[str, List[str]] = {}
    for conversation_id, data in conversations:
        if data.get('deleted') or not data.get('manual_speaker_assignments'):
            continue
        for person_id in receipt_person_ids(decode(data)):
            found.setdefault(person_id, []).append(conversation_id)
    return found


def backfill_person(
    client: Any,
    uid: str,
    person_id: str,
    conversation_ids: List[str],
    now: datetime,
    *,
    apply: bool,
) -> Optional[Dict[str, Any]]:
    """Merge one person's receipt conversations into their tally. Returns the new tally, or None when unchanged."""
    ref = client.collection('users').document(uid).collection('people').document(person_id)

    @firestore.transactional
    def merge(transaction: Any) -> Optional[Dict[str, Any]]:
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return None
        tally = merge_backfill((snapshot.to_dict() or {}).get('label_evidence'), conversation_ids, now)
        if tally is not None and apply:
            transaction.update(ref, {'label_evidence': tally})
        return tally

    return run_transactional(client, merge)
