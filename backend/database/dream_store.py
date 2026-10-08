"""Transactional dream admission. Leases cannot be stolen, even after expiry.

A dead worker's lease requires operator recovery after proving it has exited.
This intentionally trades liveness for no overlapping per-user passes. Daily
spend is reserved before inference; ambiguous failures retain their reservation.
"""

import os

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud import firestore

from config.dream_agent import Caps, eligible, mode
from config.plan_catalog import PAID_PLAN_IDS
from database._client import get_firestore_client
from database import review_store


def client(firestore_client=None):
    return firestore_client if firestore_client is not None else get_firestore_client()


def state_ref(database, uid):
    return database.collection('dream_users').document(uid)


def mark_dirty(uid, refs, *, firestore_client=None):
    database = client(firestore_client)
    user = database.collection('users').document(uid).get().to_dict() or {}
    if not eligible(uid, user):
        return
    state = state_ref(database, uid)
    # Plan ids come from the shared catalog, never a duplicate plan list.
    plan = (user.get('subscription') or {}).get('plan', user.get('plan', ''))
    weight = 2 if plan in PAID_PLAN_IDS else 1

    @firestore.transactional
    def write(tx):
        data = state.get(transaction=tx).to_dict() or {}
        seq = int(data.get('sequence', 0))
        for start in range(0, len(refs), 5):
            seq += 1
            event = state.collection('events').document(str(seq))
            tx.set(
                event,
                {
                    'sequence': seq,
                    'refs': [list(ref) for ref in refs[start : start + 5]],
                    'at': datetime.now(timezone.utc),
                },
            )
        tx.set(state, {**data, 'sequence': seq, 'score': int(data.get('score', 0)) + weight})

    write(database.transaction())


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


def acquire(uid, caps: Caps, *, now=None, firestore_client=None):
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
        if (
            mode() == 'off'
            or (mode() == 'on' and os.getenv('REVIEW_SURFACE_MODE', 'off') != 'on')
            or not eligible(uid, user)
            or data.get('lease')
            or data.get('score', 0) <= 0
            or passes >= caps.passes
            or caps.tokens < 1024
            or caps.edits < 1
            or caps.max_usd_per_token <= 0
            or float(budget.get('reserved_usd', 0)) + caps.reservation_usd > caps.daily_usd
        ):
            return None
        lease = {
            'run_id': run_id,
            'day': day,
            'watermark': int(data.get('watermark', 0)),
            'sequence': data['sequence'],
            'score': data['score'],
            'mode': mode(),
            'started_at': now,
        }
        tx.set(state, {**data, 'lease': lease, 'day': day, 'passes': passes + 1})
        tx.set(spend, {'reserved_usd': float(budget.get('reserved_usd', 0)) + caps.reservation_usd})
        return lease

    return claim(database.transaction())


def assert_lease(uid, run_id, *, firestore_client=None):
    data = state_ref(client(firestore_client), uid).get().to_dict() or {}
    if (data.get('lease') or {}).get('run_id') != run_id:
        raise RuntimeError('dream_lease_lost')


def events(uid, lease, *, firestore_client=None):
    query = state_ref(client(firestore_client), uid).collection('events')
    query = query.where(filter=firestore.FieldFilter('sequence', '>', lease['watermark']))
    query = query.where(filter=firestore.FieldFilter('sequence', '<=', lease['sequence']))
    return [s.to_dict() for s in query.order_by('sequence').limit(4).stream()]


def finish(uid, lease, report, *, success, watermark=None, release=True, firestore_client=None):
    database = client(firestore_client)
    state = state_ref(database, uid)
    run = database.collection('users').document(uid).collection('dream_runs').document(lease['run_id'])
    # Reuse encrypted content encoding; no private plaintext in run docs.
    encoded = review_store.encode_doc(uid, {'source': report})

    @firestore.transactional
    def complete(tx):
        data = state.get(transaction=tx).to_dict() or {}
        if (data.get('lease') or {}).get('run_id') != lease['run_id']:
            raise RuntimeError('dream_lease_lost')
        end = watermark if success else lease['watermark']
        drained = end == lease['sequence']
        tx.set(
            run,
            {
                **encoded,
                'created_at': lease['started_at'],
                'expires_at': lease['started_at'] + timedelta(days=30),
                'mode': lease['mode'],
                'success': success,
            },
        )
        tx.set(
            state,
            {
                **data,
                'lease': None if release else lease,
                'watermark': end,
                'score': max(0, data['score'] - lease['score']) if drained else data['score'],
            },
        )

    complete(database.transaction())


def vocabulary(uid, *, firestore_client=None):
    ref = client(firestore_client).collection('users').document(uid).collection('dream_vocabulary').document('current')
    return (review_store.decode_doc(uid, ref.get().to_dict()) or {}).get('source', [])


def save_vocabulary(uid, terms, *, firestore_client=None):
    ref = client(firestore_client).collection('users').document(uid).collection('dream_vocabulary').document('current')
    merged = {row['spelling'].casefold(): row for row in vocabulary(uid, firestore_client=firestore_client)}
    merged.update({t.spelling.casefold(): t.model_dump() for t in terms})
    ref.set(review_store.encode_doc(uid, {'source': list(merged.values())[-500:]}))


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
        data = review_store.decode_doc(uid, snapshot.to_dict()) or {}
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
