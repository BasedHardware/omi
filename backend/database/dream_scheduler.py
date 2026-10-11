"""Rotating owner pages plus weighted age avoid a permanent score-top-100 window."""

from datetime import datetime, timezone
from google.cloud import firestore
from database._client import get_firestore_client

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def priority(row, now):
    last = row.get('last_pass_at')
    if not isinstance(last, datetime) or last.tzinfo is None:
        last = EPOCH
    weight = 2 if row.get('usage_weight') == 2 else 1
    return weight * max(0, (now - last).total_seconds()), weight


def candidate_page(*, after=None, limit=100, transaction=None, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    users = database.collection('dream_users')
    query = users.order_by('__name__')
    if after:
        query = query.start_after({'__name__': users.document(after)})
    return list(query.limit(max(1, min(limit, 100))).stream(transaction=transaction))


def candidates(*, limit=100, now=None, firestore_client=None):
    if limit <= 0:
        return []
    database = firestore_client if firestore_client is not None else get_firestore_client()
    cursor = database.collection('dream_scheduler').document('rotation')
    now = now or datetime.now(timezone.utc)

    @firestore.transactional
    def select(tx):
        after = (cursor.get(transaction=tx).to_dict() or {}).get('after')
        rows = candidate_page(after=after, limit=limit, transaction=tx, firestore_client=database)
        if not rows and after:
            rows = candidate_page(limit=limit, transaction=tx, firestore_client=database)
        # Advance atomically across competing drains. Leases still serialize owners.
        tx.set(cursor, {'after': rows[-1].id if rows else None})
        return [row.id for row in sorted(rows, key=lambda row: priority(row.to_dict() or {}, now), reverse=True)]

    return select(database.transaction())
