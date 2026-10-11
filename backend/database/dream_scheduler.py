"""Rotating owner pages plus weighted age avoid a permanent score-top-100 window."""

from datetime import datetime, timezone
from google.cloud import firestore
from database._client import get_firestore_client
from config.plan_catalog import PAID_PLAN_IDS

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def priority(row, now, *, weight=1):
    last = row.get('last_pass_at')
    if not isinstance(last, datetime) or last.tzinfo is None:
        last = EPOCH
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
        # Read current plans in one transaction-bound batch; idle owners and plan
        # changes must not depend on a later product write to refresh their weight.
        owners = (
            {
                snapshot.id: snapshot.to_dict() or {}
                for snapshot in database.get_all(
                    [database.collection('users').document(row.id) for row in rows],
                    transaction=tx,
                    timeout=3,
                    field_paths=['subscription.plan', 'plan'],
                )
            }
            if rows
            else {}
        )
        weights = {
            uid: 2 if (user.get('subscription') or {}).get('plan', user.get('plan', '')) in PAID_PLAN_IDS else 1
            for uid, user in owners.items()
        }
        # Advance atomically across competing drains. Leases still serialize owners.
        tx.set(cursor, {'after': rows[-1].id if rows else None})
        return [
            row.id
            for row in sorted(
                rows, key=lambda row: priority(row.to_dict() or {}, now, weight=weights.get(row.id, 1)), reverse=True
            )
        ]

    return select(database.transaction())
