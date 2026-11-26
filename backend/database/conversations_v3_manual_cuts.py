"""Owner-level manual end instants for v3 conversations (reliability experiment ``end_open_conversation``).

A cut is the server time at which the wearer asked to end the conversation in
progress. It holds no content. The builder reads the cuts that fall inside the
span it loaded and starts a new conversation at each one.
"""

from datetime import datetime, timezone

from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client

COLLECTION = 'conversation_v3_manual_cuts'
READ_LIMIT = 200


def _cuts(client, uid):
    return client.collection('users').document(uid).collection(COLLECTION)


def record(uid, at, *, firestore_client=None) -> str:
    """Store one cut and return its id."""
    client = firestore_client or get_firestore_client()
    ref = _cuts(client, uid).document()
    ref.set({'at': at, 'created_at': datetime.now(timezone.utc), 'source': 'client_finalize'})
    return ref.id


def around(uid, at, *, firestore_client=None) -> tuple[datetime | None, datetime | None]:
    """The last cut at or before ``at`` and the first cut after it (two one-row reads)."""
    client = firestore_client or get_firestore_client()

    def one(query):
        for row in query.limit(1).stream():
            value = (row.to_dict() or {}).get('at')
            return value if isinstance(value, datetime) else None
        return None

    cuts = _cuts(client, uid)
    before = one(cuts.where(filter=FieldFilter('at', '<=', at)).order_by('at', direction='DESCENDING'))
    after = one(cuts.where(filter=FieldFilter('at', '>', at)).order_by('at'))
    return before, after


def load(uid, since, *, firestore_client=None) -> list[datetime]:
    """Cuts at or after ``since``, oldest first."""
    client = firestore_client or get_firestore_client()
    rows = _cuts(client, uid).where(filter=FieldFilter('at', '>=', since)).order_by('at').limit(READ_LIMIT).stream()
    return [at for at in ((row.to_dict() or {}).get('at') for row in rows) if isinstance(at, datetime)]
