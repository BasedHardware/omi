"""Firestore state for the one first-summary push per account.

users/{uid}/notification_markers/first_summary_push (document, created once)
  ├── outcome: "claimed" | "sent" | "undelivered" | "failed" | "suppressed" | "in_app" | "not_first"
  ├── conversation_id: the conversation that decided it
  ├── language: copy language of a claimed push
  ├── delivered: devices FCM accepted ("sent" / "undelivered")
  ├── reason: why a push was suppressed, undelivered or failed
  ├── retryable: true on a failed dispatch
  ├── created_at: the decision (for a push, the atomic claim before dispatch)
  └── settled_at: when a claimed push recorded its dispatch result

A push stays "claimed" until its dispatch result is recorded, so a claim that never
settles is an interrupted attempt, not a sent push.
"""

from typing import Any, Dict, List, Optional

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ._client import get_firestore_client


def _marker_ref(uid: str, firestore_client: Any = None) -> Any:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid).collection('notification_markers').document('first_summary_push')


def get_decision(uid: str, *, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    """The account's recorded decision, or None while it is undecided."""
    snapshot = _marker_ref(uid, firestore_client).get()
    return (snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else None


def try_decide(uid: str, decision: Dict[str, Any], *, firestore_client: Any = None) -> bool:
    """Record the account's one decision; False when one already exists.

    ``create`` is atomic, so concurrent or retried decisions record exactly one and only its
    caller may send. Storage errors propagate; callers treat them as undecided.
    """
    try:
        _marker_ref(uid, firestore_client).create({**decision, 'created_at': firestore.SERVER_TIMESTAMP})
        return True
    except AlreadyExists:
        return False


def settle(uid: str, result: Dict[str, Any], *, firestore_client: Any = None) -> None:
    """Record a claimed push's dispatch result. The document stays, so it never sends again."""
    _marker_ref(uid, firestore_client).update({**result, 'settled_at': firestore.SERVER_TIMESTAMP})


def oldest_conversation_summaries(uid: str, limit: int, *, firestore_client: Any = None) -> List[Dict[str, Any]]:
    """The account's oldest completed, kept conversations: creation time, summary fields, last write.

    An account's summary history sits at its start, even when a fresh sync batch fills the newest
    rows with unprocessed recordings.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection('conversations')
        .where(filter=FieldFilter('discarded', '==', False))
        .where(filter=FieldFilter('status', '==', 'completed'))
        .order_by('created_at', direction=firestore.Query.ASCENDING)
        .select(['created_at', 'structured.overview', 'structured.sections'])
        .limit(limit)
    )
    return [
        {**(snapshot.to_dict() or {}), 'id': snapshot.id, 'updated_at': getattr(snapshot, 'update_time', None)}
        for snapshot in query.stream()
    ]
