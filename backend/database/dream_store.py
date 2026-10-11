"""Transactional dream admission. Leases cannot be stolen, even after expiry.

A dead worker's lease requires operator recovery after proving it has exited.
This intentionally trades liveness for no overlapping per-user passes. Daily
spend is reserved before inference; ambiguous failures retain their reservation.
"""

import os
from hashlib import sha256

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud import firestore

from config.dream_agent import Caps, canary_eligible, canary_uid, eligible, may_be_eligible, mode
from config.plan_catalog import PAID_PLAN_IDS
from database._client import get_firestore_client


def _review_store():
    # Keep Dream's cheap write-signal import independent from Review's Firestore
    # query module. Callers that only need mark_dirty shouldn't load FieldFilter.
    from database import review_store

    return review_store


def client(firestore_client=None):
    return firestore_client if firestore_client is not None else get_firestore_client()


def state_ref(database, uid):
    return database.collection('dream_users').document(uid)


# Bound retries of a consumed product version after billable reasoning failures.
# Refreshed versions reset their streak; ambiguous worker timeouts retain leases.
POISON_FAILURE_LIMIT = 3
DIRTY_LIMIT = 500
WRITE_CHUNK = 400  # Leave room for state/report writes in Firestore's 500-write limit.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def dirty_id(collection, key):
    # Hashing also handles opaque ids containing ':' without collisions or path injection.
    return sha256((collection + '/' + key).encode()).hexdigest()


def mark_dirty(uid, refs, *, canary=False, firestore_client=None):
    # Every product write calls this; outside the cohort it must cost no Firestore read.
    if mode() == 'off' or not refs or not (uid == canary_uid() if canary else may_be_eligible(uid)):
        return False
    database = client(firestore_client)
    user = database.collection('users').document(uid).get().to_dict() or {}
    if not (canary_eligible(uid, user) if canary else eligible(uid, user)):
        return False
    state = state_ref(database, uid)
    plan = (user.get('subscription') or {}).get('plan', user.get('plan', ''))
    weight = 2 if plan in PAID_PLAN_IDS else 1
    refs = list(dict.fromkeys(refs))
    for start in range(0, len(refs), WRITE_CHUNK):
        batch = database.batch()
        for collection, key in refs[start : start + WRITE_CHUNK]:
            batch.set(
                state.collection('dirty').document(dirty_id(collection, key)),
                {
                    'collection': collection,
                    'id': key,
                    'version': str(uuid4()),
                    'last_changed_at': firestore.SERVER_TIMESTAMP,
                    'change_count': firestore.Increment(1),
                    'failed_passes': 0,
                },
                merge=True,
            )
        # Bump once in the final chunk: a concurrent pass must not clear the
        # score before this product write has finished queuing all its refs.
        if start + WRITE_CHUNK >= len(refs):
            batch.set(state, {'score': firestore.Increment(weight)}, merge=True)
        batch.commit()
        trim_dirty(uid, firestore_client=database)
    return True


def dirty_count(uid, *, transaction=None, firestore_client=None):
    # Aggregation reads index entries, not every document's contents. Under the
    # 500-ref cap it costs one billed read and avoids a per-write state transaction.
    query = state_ref(client(firestore_client), uid).collection('dirty')
    return int(query.count().get(transaction=transaction)[0][0].value)


def dirty_refs(uid, *, limit=DIRTY_LIMIT, newest=True, transaction=None, firestore_client=None):
    query = state_ref(client(firestore_client), uid).collection('dirty')
    return list(
        query.order_by('last_changed_at', direction='DESCENDING' if newest else 'ASCENDING')
        .limit(max(1, min(limit, DIRTY_LIMIT)))
        .stream(transaction=transaction)
    )


def trim_dirty(uid, *, firestore_client=None):
    database = client(firestore_client)
    state = state_ref(database, uid)
    while (excess := dirty_count(uid, firestore_client=database) - DIRTY_LIMIT) > 0:
        oldest = dirty_refs(uid, limit=min(excess, WRITE_CHUNK), newest=False, firestore_client=database)

        @firestore.transactional
        def trim(tx):
            # Recheck size in the transaction: a pass may have drained records
            # after the outer count. Only prune current excess, never spare refs.
            excess_now = max(0, dirty_count(uid, transaction=tx, firestore_client=database) - DIRTY_LIMIT)
            # Fence each observed version: concurrent refreshes must survive.
            current = [(s, s.reference.get(transaction=tx).to_dict() or {}) for s in oldest]
            victims = [s for s, row in current if row.get('version') == s.to_dict()['version']][:excess_now]
            for snapshot in victims:
                tx.delete(snapshot.reference)
            if victims:
                tx.set(state, {'dirty_dropped': firestore.Increment(len(victims))}, merge=True)

        trim(database.transaction())


def candidates(*, limit=100, firestore_client=None):
    # Single-field query: no composite index or collection-group scan.
    return [
        s.id
        for s in client(firestore_client)
        .collection('dream_users')
        .order_by('score', direction='DESCENDING')
        .limit(limit)
        .stream()
    ]


class AdmissionDenied(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def acquire(uid, caps: Caps, *, trigger='schedule', canary=False, now=None, firestore_client=None):
    database = client(firestore_client)
    now = now or datetime.now(timezone.utc)
    day = now.date().isoformat()
    state = state_ref(database, uid)
    spend = database.collection('dream_spend').document(day)
    owner = database.collection('users').document(uid)
    run_id = str(uuid4())

    @firestore.transactional
    def claim(tx):
        data = state.get(transaction=tx).to_dict() or {}
        budget = spend.get(transaction=tx).to_dict() or {}
        user = owner.get(transaction=tx).to_dict() or {}
        passes = int(data.get('passes', 0)) if data.get('day') == day else 0
        manual_runs = int(data.get('manual_runs', 0)) if data.get('day') == day else 0
        if trigger == 'manual':
            if data.get('lease'):
                raise AdmissionDenied('dream_run_in_progress')
            if data.get('score', 0) <= 0 or dirty_count(uid, transaction=tx, firestore_client=database) == 0:
                return None
            if manual_runs >= caps.manual_runs:
                raise AdmissionDenied('dream_manual_limit')
        if (
            mode() == 'off'
            or (not canary and mode() == 'on' and os.getenv('REVIEW_SURFACE_MODE', 'off') != 'on')
            or not (canary_eligible(uid, user) if canary else eligible(uid, user))
            or data.get('lease')
            or data.get('score', 0) <= 0
            or (trigger != 'manual' and passes >= caps.passes)
            or caps.tokens < 1024
            or caps.edits < 1
            or caps.max_usd_per_token <= 0
            or float(budget.get('reserved_usd', 0)) + caps.reservation_usd > caps.daily_usd
        ):
            if trigger == 'manual':
                raise AdmissionDenied('dream_budget_unavailable')
            return None
        lease = {
            'run_id': run_id,
            'day': day,
            'watermark': data.get('watermark') if isinstance(data.get('watermark'), datetime) else EPOCH,
            'dirty_dropped': int(data.get('dirty_dropped', 0)),
            'dirty_dropped_reported': int(data.get('dirty_dropped_reported', 0)),
            'reservation_usd': caps.reservation_usd,
            'score': data['score'],
            'mode': 'shadow' if canary else mode(),
            'trigger': trigger,
            'started_at': now,
        }
        tx.set(
            state,
            {
                **data,
                'lease': lease,
                'day': day,
                'passes': passes + int(trigger != 'manual'),
                'manual_runs': manual_runs + int(trigger == 'manual'),
            },
        )
        tx.set(spend, {'reserved_usd': float(budget.get('reserved_usd', 0)) + caps.reservation_usd})
        return lease

    return claim(database.transaction())


def assert_lease(uid, run_id, *, firestore_client=None):
    data = state_ref(client(firestore_client), uid).get().to_dict() or {}
    if (data.get('lease') or {}).get('run_id') != run_id:
        raise RuntimeError('dream_lease_lost')


def finish(
    uid, lease, report, *, success, consumed=(), release=True, refund=False, count_failure=False, firestore_client=None
):
    database = client(firestore_client)
    state = state_ref(database, uid)
    run = database.collection('users').document(uid).collection('dream_runs').document(lease['run_id'])
    spend = database.collection('dream_spend').document(lease['day'])
    report['dirty_dropped'] = max(0, lease['dirty_dropped'] - lease['dirty_dropped_reported'])
    failure_eligible = count_failure and not success and release and not refund

    @firestore.transactional
    def complete(tx):
        data = state.get(transaction=tx).to_dict() or {}
        if (data.get('lease') or {}).get('run_id') != lease['run_id']:
            raise RuntimeError('dream_lease_lost')
        budget = (spend.get(transaction=tx).to_dict() or {}) if refund else {}
        # Read before writing, including the bounded queue query. This makes
        # acknowledging versions and deciding whether the queue drained atomic.
        queued_count = dirty_count(uid, transaction=tx, firestore_client=database)
        queued = (
            dirty_refs(uid, newest=False, transaction=tx, firestore_client=database)
            if success or failure_eligible
            else []
        )
        versions = {item['version'] for item in consumed}
        touched = [s for s in queued if s.to_dict()['version'] in versions]
        poisoned = [
            s
            for s in touched
            if failure_eligible and int(s.to_dict().get('failed_passes', 0)) + 1 >= POISON_FAILURE_LIMIT
        ]
        acknowledged = touched if success else poisoned
        acknowledged_paths = {s.reference.path for s in acknowledged}
        remaining = [s for s in queued if s.reference.path not in acknowledged_paths]
        queued_after = queued_count - len(acknowledged)
        settled = {**report, 'records_queued_after': queued_after, 'poisoned': len(poisoned)}
        encoded = _review_store().encode_doc(uid, {'source': settled})
        watermark = lease['watermark']
        if acknowledged:
            frontier = max(s.to_dict()['last_changed_at'] for s in acknowledged)
            if remaining:
                frontier = min(
                    frontier, min(s.to_dict()['last_changed_at'] for s in remaining) - timedelta(microseconds=1)
                )
            watermark = max(watermark, frontier)
        for snapshot in acknowledged:
            tx.delete(snapshot.reference)
        if failure_eligible:
            for snapshot in remaining:
                if snapshot.to_dict()['version'] in versions:
                    tx.update(
                        snapshot.reference, {'failed_passes': int(snapshot.to_dict().get('failed_passes', 0)) + 1}
                    )
        tx.set(
            run,
            {
                **encoded,
                'created_at': lease['started_at'],
                'expires_at': lease['started_at'] + timedelta(days=30),
                'mode': lease['mode'],
                'success': success,
                'trigger': lease.get('trigger', 'schedule'),
                'records_read': int(report.get('records_read', report.get('dirty_read', 0))),
                'records_queued_after': queued_after,
                'tokens': int(report.get('tokens', 0)),
                'cost_usd': float(report.get('cost_usd', 0)),
                'poisoned': len(poisoned),
            },
        )
        patch = {
            'lease': None if release else lease,
            # The dirty set is authoritative; never filter reads by this diagnostic
            # frontier, which must remain behind older unread references.
            'watermark': watermark,
            'dirty_dropped_reported': lease['dirty_dropped'],
            'score': (
                max(0, data['score'] - lease['score']) if (success or poisoned) and queued_after == 0 else data['score']
            ),
        }
        if refund:
            # A midnight completion must not decrement the new day's allowance.
            if data.get('day') == lease['day']:
                counter = 'manual_runs' if lease.get('trigger') == 'manual' else 'passes'
                patch[counter] = max(0, int(data.get(counter, 0)) - 1)
            tx.set(spend, {'reserved_usd': max(0, float(budget.get('reserved_usd', 0)) - lease['reservation_usd'])})
        if poisoned:
            patch['poisoned'] = int(data.get('poisoned', 0)) + len(poisoned)
        tx.update(state, patch)
        return settled

    report.update(complete(database.transaction()))


def own_runs(uid, *, limit=10, firestore_client=None):
    query = client(firestore_client).collection('users').document(uid).collection('dream_runs')
    return [
        (s.id, s.to_dict())
        for s in query.order_by('created_at', direction='DESCENDING').limit(max(1, min(limit, 20))).stream()
    ]


def own_run(uid, run_id, *, firestore_client=None):
    return (
        client(firestore_client)
        .collection('users')
        .document(uid)
        .collection('dream_runs')
        .document(run_id)
        .get()
        .to_dict()
    )


def own_state(uid, *, firestore_client=None):
    return state_ref(client(firestore_client), uid).get().to_dict() or {}


def vocabulary(uid, *, firestore_client=None):
    ref = client(firestore_client).collection('users').document(uid).collection('dream_vocabulary').document('current')
    return (_review_store().decode_doc(uid, ref.get().to_dict()) or {}).get('source', [])


def save_vocabulary(uid, terms, *, firestore_client=None):
    ref = client(firestore_client).collection('users').document(uid).collection('dream_vocabulary').document('current')
    merged = {row['spelling'].casefold(): row for row in vocabulary(uid, firestore_client=firestore_client)}
    merged.update({t.spelling.casefold(): t.model_dump() for t in terms})
    ref.set(_review_store().encode_doc(uid, {'source': list(merged.values())[-500:]}))


def demoted_types(uid, caps, *, firestore_client=None):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    query = client(firestore_client).collection('users').document(uid).collection('review_changes')
    rows = (
        query.where(filter=firestore.FieldFilter('created_at', '>=', since))
        .order_by('created_at', direction='DESCENDING')
        .limit(500)
        .stream()
    )
    counts = {}
    for snapshot in rows:
        data = _review_store().decode_doc(uid, snapshot.to_dict()) or {}
        if not data.get('edit_key', '').startswith('dream:') or data.get('phase', 'applied') != 'applied':
            continue
        kind = data['edit_key'].split(':')[1]
        total, undone = counts.get(kind, (0, 0))
        counts[kind] = (total + 1, undone + int(data['change']['undone']))
    return {
        kind
        for kind, (total, undone) in counts.items()
        if total >= caps.undo_min_samples and undone / total > caps.undo_rate
    }


def reserve_questions(uid, run_id, requested, *, firestore_client=None):
    """Three proposed questions per UTC day, sharing answer headroom with Review."""
    database = client(firestore_client)
    state = state_ref(database, uid)
    day = datetime.now(timezone.utc).date().isoformat()
    attention = database.collection('users').document(uid).collection('review_attention').document(day)

    @firestore.transactional
    def reserve(tx):
        data = state.get(transaction=tx).to_dict() or {}
        answers = attention.get(transaction=tx).to_dict() or {}
        if (data.get('lease') or {}).get('run_id') != run_id:
            raise RuntimeError('dream_lease_lost')
        proposed = data.get('questions', 0) if data.get('question_day') == day else 0
        count = max(0, min(requested, 3 - proposed, 3 - answers.get('used', 0)))
        tx.update(state, {'question_day': day, 'questions': proposed + count})
        return count

    return reserve(database.transaction())
