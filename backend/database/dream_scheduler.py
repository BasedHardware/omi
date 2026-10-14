"""Rotating owner pages plus weighted age avoid a permanent score-top-100 window."""

from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from database._client import get_firestore_client
from config.dream_agent import eligible, enabled

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def priority(row, now, *, weight=1):
    last = row.get('last_pass_at')
    if not isinstance(last, datetime) or last.tzinfo is None:
        last = EPOCH
    return max(0, (now - last).total_seconds()) + min(500, row.get('score', 0)) * 60, row.get('score', 0)


def candidate_page(*, after=None, limit=100, transaction=None, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    users = database.collection('users')
    query = users.order_by('__name__')
    if after:
        query = query.start_after({'__name__': users.document(after)})
    return list(
        query.select(['subscription.plan', 'plan', 'dream_canary', 'deleted', 'deletion_requested_at'])
        .limit(max(1, min(limit, 100)))
        .stream(transaction=transaction, timeout=3)
    )


class CandidatePage(list):
    def __init__(self, owners, *, ordered, after, skipped=()):
        super().__init__(owners)
        self.ordered = ordered
        self.after = after
        self.skipped = set(skipped)


def candidates(*, limit=100, now=None, firestore_client=None):
    if limit <= 0 or not enabled():
        return CandidatePage([], ordered=[], after=None)
    database = firestore_client if firestore_client is not None else get_firestore_client()
    cursor = database.collection('dream_scheduler').document('rotation')
    now = now or datetime.now(timezone.utc)
    after = (cursor.get(timeout=3).to_dict() or {}).get('after')
    rows = candidate_page(after=after, limit=limit, firestore_client=database)
    if not rows and after:
        rows = candidate_page(limit=limit, firestore_client=database)
    states = (
        {
            snapshot.id: snapshot.to_dict() or {}
            for snapshot in database.get_all(
                [database.collection('dream_users').document(row.id) for row in rows], timeout=3
            )
        }
        if rows
        else {}
    )
    selected = []
    skipped = []
    for row in rows:
        state = states.get(row.id, {})
        last = state.get('last_attempt_at') or state.get('last_pass_at') or EPOCH
        interval = timedelta(hours=6 if state.get('size_bucket') == 'heavy' else 24)
        due = not isinstance(last, datetime) or now - last >= interval
        lease = state.get('lease') or {}
        started = lease.get('started_at')
        stale = isinstance(started, datetime) and now - started > timedelta(seconds=1740)
        if eligible(row.id, row.to_dict() or {}) and (state.get('score', 0) > 0 or due or stale):
            selected.append(row.id)
        else:
            skipped.append(row.id)
    return CandidatePage(
        sorted(selected, key=lambda uid: priority(states.get(uid, {}), now), reverse=True),
        ordered=[row.id for row in rows],
        after=after,
        skipped=skipped,
    )


def advance(page, tried, *, firestore_client=None):
    # Priority order can differ from document order. Only advance over a contiguous
    # prefix of attempted owners so capacity waits never skip anyone.
    after = page.after
    for uid in page.ordered:
        if uid not in tried and uid not in page.skipped:
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
