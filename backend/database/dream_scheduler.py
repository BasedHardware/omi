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
    return list(query.limit(max(1, min(limit, 100))).stream(transaction=transaction, timeout=3))


class CandidatePage(list):
    def __init__(self, owners, *, ordered, after):
        super().__init__(owners)
        self.ordered = ordered
        self.after = after


def candidates(*, limit=100, now=None, firestore_client=None):
    if limit <= 0:
        return CandidatePage([], ordered=[], after=None)
    database = firestore_client if firestore_client is not None else get_firestore_client()
    cursor = database.collection('dream_scheduler').document('rotation')
    now = now or datetime.now(timezone.utc)
    after = (cursor.get(timeout=3).to_dict() or {}).get('after')
    rows = candidate_page(after=after, limit=limit, firestore_client=database)
    if not rows and after:
        rows = candidate_page(limit=limit, firestore_client=database)
    # Entitlements are a projected read outside a transaction, with no user locks.
    owners = (
        {
            snapshot.id: snapshot.to_dict() or {}
            for snapshot in database.get_all(
                [database.collection('users').document(row.id) for row in rows],
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
    return CandidatePage(
        [
            row.id
            for row in sorted(
                rows, key=lambda row: priority(row.to_dict() or {}, now, weight=weights.get(row.id, 1)), reverse=True
            )
        ],
        ordered=[row.id for row in rows],
        after=after,
    )


def advance(page, tried, *, firestore_client=None):
    # Priority order can differ from document order. Only advance over a contiguous
    # prefix of attempted owners so capacity waits never skip anyone.
    after = page.after
    for uid in page.ordered:
        if uid not in tried:
            break
        after = uid
    if after == page.after:
        return
    database = firestore_client if firestore_client is not None else get_firestore_client()
    cursor = database.collection('dream_scheduler').document('rotation')

    @firestore.transactional
    def finish(tx):
        current = (cursor.get(transaction=tx).to_dict() or {}).get('after')
        if current == page.after:
            tx.set(cursor, {'after': after})

    finish(database.transaction())
