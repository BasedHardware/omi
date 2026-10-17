"""Durable due-work queue: bootstrap discovery is independent from admission."""

from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from database._client import get_firestore_client
from config.dream_agent import allowlist_uids, eligibility, eligible, enabled, hunt_interval

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def priority(row, now, *, weight=1):
    last = row.get('last_pass_at')
    if not isinstance(last, datetime) or last.tzinfo is None:
        last = EPOCH
    return max(0, (now - last).total_seconds()) + min(500, row.get('score', 0)) * 60, row.get('score', 0)


def due_time(state, now):
    last = state.get('last_attempt_at') or state.get('last_pass_at') or EPOCH
    if not isinstance(last, datetime) or last.tzinfo is None:
        last = EPOCH
    if state.get('score', 0) > 0:
        return last - timedelta(minutes=min(500, state['score']))
    return last + hunt_interval(state.get('size_bucket'))


def candidate_page(*, after=None, limit=499, transaction=None, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    users = database.collection('users')
    query = users.order_by('__name__')
    if after:
        query = query.start_after({'__name__': users.document(after)})
    return list(
        query.select(['subscription.plan', 'plan', 'dream_canary', 'deleted', 'deletion_requested_at'])
        .limit(max(1, min(limit, 499)))
        .stream(transaction=transaction, timeout=3)
    )


def discover(database, now, *, pages=20):
    """10,000 owners/hour on bootstrap, without waiting for any session to finish.

    Dirty writes enqueue immediately; this rotating scan supplies never-dirty
    owners and repairs missing queue rows. Future hunts remain in the queue.
    """
    cursor = database.collection('dream_scheduler').document('discovery')
    listed = allowlist_uids() if eligibility() == 'allowlist' else None
    after = None if listed is not None else (cursor.get(timeout=3).to_dict() or {}).get('after')
    for _ in range(1 if listed is not None else pages):
        if listed is not None:
            # Allowlist rollout: read only listed owners instead of scanning every user each sweep.
            users = database.collection('users')
            rows = [
                snapshot
                for snapshot in database.get_all([users.document(uid) for uid in listed[:499]], timeout=3)
                if snapshot.exists
            ]
        else:
            rows = candidate_page(after=after, firestore_client=database)
        if not rows:
            if listed is None:
                cursor.set({'after': None})
            break

        @firestore.transactional
        def initialize(tx):
            queued = {
                snapshot.id
                for snapshot in database.get_all(
                    [database.collection('dream_due').document(row.id) for row in rows], transaction=tx, timeout=3
                )
                if snapshot.exists
            }
            states = {
                snapshot.id: snapshot.to_dict() or {}
                for snapshot in database.get_all(
                    [database.collection('dream_users').document(row.id) for row in rows], transaction=tx, timeout=3
                )
            }
            for row in rows:
                target = database.collection('dream_due').document(row.id)
                if eligible(row.id, row.to_dict() or {}):
                    if row.id not in queued:
                        tx.set(target, {'due_at': due_time(states.get(row.id, {}), now)})
                else:
                    tx.delete(target)
            if listed is None:
                tx.set(cursor, {'after': rows[-1].id})

        initialize(database.transaction())
        after = rows[-1].id


def remove_due(uid, *, firestore_client=None):
    """Drop an ineligible scheduler row, retaining owner state and dirty work.

    Discovery recreates the row if the owner becomes eligible again.
    """
    database = firestore_client if firestore_client is not None else get_firestore_client()
    database.collection('dream_due').document(uid).delete()


def candidates(*, limit=5000, now=None, firestore_client=None):
    if limit <= 0 or not enabled():
        return []
    database = firestore_client if firestore_client is not None else get_firestore_client()
    now = now or datetime.now(timezone.utc)
    discover(database, now)
    rows = (
        database.collection('dream_due')
        .where(filter=firestore.FieldFilter('due_at', '<=', now))
        .order_by('due_at')
        .limit(min(limit, 5000))
        .stream(timeout=3)
    )
    return [row.id for row in rows]
