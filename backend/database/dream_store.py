"""Transactional Dream admission and conservative stale-lease settlement.

Abandoned workers retain their reservation and pending dirty versions. New
admission and reclamation share one transaction, fenced by the current run_id.
"""

import os
import math
from hashlib import sha256

from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any

from google.cloud import firestore

from config.dream_agent import (
    Caps,
    canary_eligible,
    canary_uid,
    backed_off_hunt_interval,
    eligible,
    may_be_eligible,
    mode,
    DRAIN_TIMEOUT_SECONDS,
    LEASE_RECLAIM_MARGIN_SECONDS,
)
from config.plan_catalog import PAID_PLAN_IDS
from database import firestore_transaction_retry
from database.dream_history import review_id
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


def spend_ref(database, uid, day):
    """Per-user UTC-day accounting, shared only by that user's passes and hosts."""
    return state_ref(database, uid).collection('spend').document(day)


def global_spend_ref(database, uid, day, *, shards=64, shard=None):
    slot = int(sha256(uid.encode()).hexdigest(), 16) % shards if shard is None else shard
    return database.collection('dream_global_spend').document(day + '-' + str(slot))


def lease_global_ref(database, uid, lease):
    if 'global_shard' not in lease:
        return database.collection('dream_global_spend').document(lease['day'])
    return global_spend_ref(database, uid, lease['day'], shard=lease['global_shard'])


def lease_spend_ref(database, uid, lease):
    return (
        spend_ref(database, uid, lease['day'])
        if lease.get('spend_scope') == 'user'
        else database.collection('dream_spend').document(lease['day'])
    )


# Bound retries of a consumed product version after billable reasoning failures.
# Refreshed versions reset their streak; ambiguous worker timeouts retain leases.
POISON_FAILURE_LIMIT = 3
DIRTY_INSPECTION_LIMIT = 32  # Bound dirty metadata and authoritative product reads per pass.
UNAVAILABLE_FAILURE_LIMIT = 3
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
    priority_state = state.get().to_dict() or {}
    from database.dream_scheduler import due_time

    now = datetime.now(timezone.utc)
    priority_due = min(now, due_time({**priority_state, 'score': priority_state.get('score', 0) + weight}, now))
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
            batch.set(database.collection('dream_due').document(uid), {'due_at': priority_due})
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


class AdmissionDenied(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _abandoned_usage(abandoned):
    """Receipt for a lease that died after one or more settled turns.

    Numeric ``cost_usd`` is present only when every receipt is priced. Otherwise
    the run keeps the conservative ``budget_charge_usd`` and omits a dollar cost.
    """
    receipts = abandoned.get('turn_receipts') or []
    tokens = 0
    micros = 0
    priced = bool(receipts)
    for row in receipts:
        if not isinstance(row, dict):
            priced = False
            continue
        accounted = row.get('accounted_tokens', row.get('tokens', 0))
        if type(accounted) is int and accounted >= 0:
            tokens += accounted
        else:
            priced = False
        micro = row.get('cost_micro_usd')
        if row.get('cost_status') == 'priced' and type(micro) is int and micro >= 0:
            micros += micro
        else:
            priced = False
    charge = abandoned.get('budget_charge_usd', abandoned.get('reservation_usd', 0))
    usage = {
        'tokens': tokens,
        'usage_unknown': not priced,
        'cost_status': 'priced' if priced else 'unpriced',
        'budget_charge_usd': float(charge),
    }
    if priced:
        usage['cost_usd'] = micros / 1000000
    return usage


def acquire(
    uid,
    caps: Caps,
    *,
    rng=None,
    trigger='schedule',
    canary=False,
    now=None,
    firestore_client=None,
    reclaim_sink: dict[str, Any] | None = None,
    denial_sink: dict[str, Any] | None = None,
    skip_idle=False,
):
    """Return admission and publish count-only reclaim details after commit, even on denial.

    ``denial_sink['reason']`` names why a scheduled owner was not admitted.
    ``skip_idle`` (the idle-skip lever) denies a scheduled hunt with no dirty
    work and parks the owner: the due row is deleted, and the next product
    write re-enqueues it through ``mark_dirty``.
    """
    database = client(firestore_client)
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    day = now.date().isoformat()
    state = state_ref(database, uid)
    spend = spend_ref(database, uid, day)
    owner = database.collection('users').document(uid)
    run_id = str(uuid4())
    denial_reason = None

    def admit(tx, data, budget, user):
        nonlocal denial_reason
        denial_reason = None
        passes = int(data.get('passes', 0)) if data.get('day') == day else 0
        manual_runs = int(data.get('manual_runs', 0)) if data.get('day') == day else 0
        if trigger == 'manual' and data.get('lease'):
            raise AdmissionDenied('dream_run_in_progress')
        if trigger == 'manual' and manual_runs >= caps.manual_runs:
            raise AdmissionDenied('dream_manual_limit')
        last_pass = data.get('last_attempt_at') or data.get('last_pass_at') or EPOCH
        from database.dream_scheduler import owner_hunt_interval

        interval = owner_hunt_interval(uid, data)
        hunt_due = not canary and (not isinstance(last_pass, datetime) or now - last_pass >= interval)
        # Hunt-backoff shadow: this hunt would have waited for the backed-off interval.
        backed_off = backed_off_hunt_interval(data.get('size_bucket'), data.get('dry_hunts'))
        backoff_would_defer = bool(
            hunt_due and isinstance(last_pass, datetime) and now - last_pass < backed_off and interval < backed_off
        )
        has_dirty = dirty_count(uid, transaction=tx, firestore_client=database) > 0
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        if trigger != 'manual' and passes >= caps.passes:
            denial_reason = 'daily_pass_cap'
            return None, {'next_due_at': tomorrow}
        if data.get('lease'):
            denial_reason = 'run_in_progress'
            started = data['lease'].get('started_at') or now
            return None, {'next_due_at': started + timedelta(seconds=1741)}
        if skip_idle and not canary and trigger != 'manual' and not has_dirty:
            denial_reason = 'idle_no_material'
            return None, {'park': True}
        if (
            mode() == 'off'
            or (not canary and os.getenv('REVIEW_SURFACE_MODE', 'off') != 'on')
            or not (canary_eligible(uid, user) if canary else eligible(uid, user))
            or data.get('lease')
            or (not has_dirty and not hunt_due and trigger != 'manual')
            or (trigger != 'manual' and passes >= caps.passes)
            or (trigger == 'manual' and manual_runs >= caps.manual_runs)
            or caps.tokens < 1024
            or caps.edits < 1
            or float(budget.get('reserved_usd', 0)) >= caps.daily_usd
        ):
            if trigger == 'manual':
                raise AdmissionDenied('dream_budget_unavailable')
            denial_reason = (
                'disabled'
                if mode() == 'off'
                else (
                    'review_surface_off'
                    if not canary and os.getenv('REVIEW_SURFACE_MODE', 'off') != 'on'
                    else (
                        'ineligible'
                        if not (canary_eligible(uid, user) if canary else eligible(uid, user))
                        else 'not_due' if not has_dirty and not hunt_due else 'budget'
                    )
                )
            )
            from database.dream_scheduler import due_time

            return None, {'next_due_at': max(now + timedelta(minutes=5), due_time(data, now, uid))}
        lease = {
            'run_id': run_id,
            'day': day,
            'watermark': data.get('watermark') if isinstance(data.get('watermark'), datetime) else EPOCH,
            'dirty_dropped': int(data.get('dirty_dropped', 0)),
            'dirty_dropped_reported': int(data.get('dirty_dropped_reported', 0)),
            'reservation_usd': 0.0,
            'budget_charge_usd': 0.0,
            'admission_refunded': False,
            'spend_scope': 'user',
            'score': data.get('score', 0),
            'daily_cap': caps.daily_usd,
            'passes_per_day': caps.passes,
            'hunt': not has_dirty,
            'dry_hunts': _dry_hunts(data),
            'backoff_would_defer': backoff_would_defer and not has_dirty,
            # Weekly whole-corpus state pass cadence; derived from the state doc already read.
            'state_pass_due': _state_pass_due(data, now),
            'canary': canary,
            'mode': 'shadow' if canary else mode(),
            'size_bucket': data.get('size_bucket', 'light'),
            'trigger': trigger,
            'started_at': now,
        }
        return lease, {
            'lease': lease,
            'last_attempt_at': now,
            'day': day,
            'passes': passes + int(trigger != 'manual'),
            'manual_runs': manual_runs + int(trigger == 'manual'),
        }

    @firestore.transactional
    def claim(tx):
        data = state.get(transaction=tx).to_dict() or {}
        budget = spend.get(transaction=tx).to_dict() or {}
        user = owner.get(transaction=tx).to_dict() or {}
        abandoned = data.get('lease') or {}
        started = abandoned.get('started_at')
        if isinstance(started, datetime) and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        duration = DRAIN_TIMEOUT_SECONDS + LEASE_RECLAIM_MARGIN_SECONDS
        bucket = abandoned.get('size_bucket', 'light')
        bucket = bucket if bucket in {'empty', 'light', 'medium', 'heavy'} else 'light'
        age_s = (now - started).total_seconds() if isinstance(started, datetime) else 0
        reclaimed = None
        old_spend = None
        old_budget = {}
        old_global_spend = None
        old_global_budget = {}
        if abandoned and age_s > duration:
            old_spend = lease_spend_ref(database, uid, abandoned)
            old_budget = old_spend.get(transaction=tx).to_dict() or {}
            reservation = float(abandoned['reservation_usd'])
            previous_charge = float(abandoned.get('budget_charge_usd', reservation))
            old_budget['reserved_usd'] = float(old_budget.get('reserved_usd', 0)) + reservation - previous_charge
            if abandoned.get('global_spend_scope'):
                old_global_spend = lease_global_ref(database, uid, abandoned)
                old_global_budget = old_global_spend.get(transaction=tx).to_dict() or {}
                old_global_budget['reserved_usd'] = (
                    float(old_global_budget.get('reserved_usd', 0)) + reservation - previous_charge
                )
            if old_spend.path == spend.path:
                budget = old_budget
            data = {
                **data,
                'lease': None,
                'last_attempt_at': data.get('last_pass_at') or EPOCH,
                'abandoned_passes': int(data.get('abandoned_passes', 0)) + 1,
            }
            reclaimed = (int(age_s), bucket)
        queued_count = dirty_count(uid, transaction=tx, firestore_client=database) if reclaimed else None
        denial = None
        try:
            lease, patch = admit(tx, data, budget, user)
        except AdmissionDenied as exc:
            # A denial must not roll back reclamation (including manual caps).
            lease, patch, denial = None, {}, exc.reason
        park = bool(patch.pop('park', False))
        # All reads, including admission's dirty count, precede settlement writes.
        if old_spend is not None and isinstance(started, datetime):
            usage = _abandoned_usage(abandoned)
            source = {
                'status': 'failed',
                'reason': 'abandoned',
                'usage_unknown': usage['usage_unknown'],
                'size_bucket': bucket,
                'abandoned': 1,
                'tokens': usage['tokens'],
                'records_queued_after': queued_count,
                'budget_charge_usd': usage['budget_charge_usd'],
                'cost_status': usage['cost_status'],
            }
            if 'cost_usd' in usage:
                source['cost_usd'] = usage['cost_usd']
            run = owner.collection('dream_runs').document(abandoned['run_id'])
            tx.set(
                run,
                {
                    **_review_store().encode_doc(uid, {'source': source}),
                    'created_at': started,
                    'expires_at': started + timedelta(days=30),
                    'mode': abandoned['mode'],
                    'trigger': abandoned.get('trigger', 'schedule'),
                    'success': False,
                    'records_read': 0,
                    'records_queued_after': queued_count,
                    'tokens': usage['tokens'],
                    'cost_status': usage['cost_status'],
                    **({'cost_usd': usage['cost_usd']} if 'cost_usd' in usage else {}),
                },
            )
            if old_spend.path != spend.path or lease is None:
                tx.set(old_spend, old_budget)
            if old_global_spend:
                tx.set(old_global_spend, old_global_budget)
        if lease:
            tx.set(state, {**data, **patch})
            tx.set(spend, {**budget, 'reserved_usd': float(budget.get('reserved_usd', 0))})
        elif reclaimed or patch:
            tx.set(state, {**data, **patch})
        if park:
            tx.delete(database.collection('dream_due').document(uid))
        elif patch.get('next_due_at'):
            tx.set(database.collection('dream_due').document(uid), {'due_at': patch['next_due_at']})
        return lease, reclaimed, denial

    lease, reclaimed, denial = firestore_transaction_retry.run_with_transaction_contention_retry(
        database.transaction, claim, operation_name='dream_acquire'
    )
    if reclaimed and reclaim_sink is not None:
        reclaim_sink.update(age_s=reclaimed[0], size_bucket=reclaimed[1])
    if denial_sink is not None and lease is None:
        denial_sink['reason'] = denial or denial_reason or 'unknown'
    if denial:
        raise AdmissionDenied(denial)
    return lease


def park_if_idle(uid, *, firestore_client=None):
    """Idle-skip lever: drop the due row when no dirty work is queued; True when parked.

    The state read is the conflict fence: every mark_dirty batch writes the
    state doc (score increment), so a concurrent write aborts and retries this
    transaction; an aggregation count alone carries no document identity.
    A positive score also keeps the owner queued, matching discovery's rule.
    """
    database = client(firestore_client)

    @firestore.transactional
    def park(tx):
        state = state_ref(database, uid).get(transaction=tx).to_dict() or {}
        if state.get('score', 0) or dirty_count(uid, transaction=tx, firestore_client=database) > 0:
            return False
        tx.delete(database.collection('dream_due').document(uid))
        return True

    return firestore_transaction_retry.run_with_transaction_contention_retry(
        database.transaction, park, operation_name='dream_park_idle'
    )


def assert_lease(uid, run_id, *, firestore_client=None):
    data = state_ref(client(firestore_client), uid).get().to_dict() or {}
    if (data.get('lease') or {}).get('run_id') != run_id:
        raise RuntimeError('dream_lease_lost')


def _state_pass_due(data, now):
    # Kept here (not utils.dream_state_pass) so acquire stays import-light.
    try:
        days = max(1, int(os.getenv('DREAM_STATE_PASS_WEEK_DAYS', '7') or 7))
    except ValueError:
        days = 7
    last = data.get('last_state_pass_at')
    return not isinstance(last, datetime) or now - last >= timedelta(days=days)


def _dry_hunts(data):
    try:
        return max(0, int(data.get('dry_hunts', 0) or 0))
    except (TypeError, ValueError):
        return 0


def finish(
    uid,
    lease,
    report,
    *,
    success,
    consumed=(),
    deferred=(),
    unavailable=(),
    release=True,
    refund=False,
    count_failure=False,
    reviewed=(),
    seeded=(),
    cleanup_cursor=None,
    now=None,
    firestore_client=None,
    park_when_idle=False,
):
    database = client(firestore_client)
    state = state_ref(database, uid)
    run = database.collection('users').document(uid).collection('dream_runs').document(lease['run_id'])
    # Leases admitted before this change still belong to the old shared ledger.
    # Never debit a new user ledger for a reservation it did not acquire.
    spend = lease_spend_ref(database, uid, lease)
    global_spend = lease_global_ref(database, uid, lease) if lease.get('global_spend_scope') else None
    report['dirty_dropped'] = max(0, lease['dirty_dropped'] - lease['dirty_dropped_reported'])
    failure_eligible = count_failure and not success and release and not refund
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    deferred_until = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    deferred = set(deferred)
    # Seed-only refs have review metadata, never an inspected dirty version.
    deferred_ids = {dirty_id(*ref.split('/', 1)) for ref in deferred - set(seeded)}

    @firestore.transactional
    def complete(tx):
        data = state.get(transaction=tx).to_dict() or {}
        current_lease = data.get('lease') or {}
        if current_lease.get('run_id') != lease['run_id']:
            raise RuntimeError('dream_lease_lost')
        budget = spend.get(transaction=tx).to_dict() or {}
        global_budget = global_spend.get(transaction=tx).to_dict() or {} if global_spend else {}
        reservation = float(current_lease.get('reservation_usd', 0))
        previous_charge = float(current_lease.get('budget_charge_usd', reservation))
        tokens = report.get('accounted_tokens', report.get('tokens'))
        rate = current_lease.get('max_usd_per_token')
        micro = report.get('cost_micro_usd')
        known = report.get('usage_unknown') is not True and (
            report.get('usage_unknown') is False or report.get('usage_complete') is True
        )
        zero_refund = refund and report.get('usage_unknown') is not True and report.get('tokens', 0) == 0
        # Unknown or unpriced usage keeps the dollars already held. A known
        # priced pass replaces that hold. In-flight leases that still carry
        # max_usd_per_token settle with that frozen rate.
        charge = reservation
        actual_cost = None
        if zero_refund:
            charge = 0.0
        elif known and report.get('cost_status') == 'priced' and type(micro) is int and micro >= 0:
            actual_cost = micro / 1000000
            if math.isfinite(actual_cost):
                charge = actual_cost
            else:
                actual_cost = None
        elif known and type(tokens) is int and tokens >= 0 and isinstance(rate, (int, float)) and rate > 0:
            actual_cost = tokens * rate
            if math.isfinite(actual_cost):
                charge = actual_cost
            else:
                actual_cost = None
        # Read before writing, including the bounded queue query. This makes
        # acknowledging versions and deciding whether the queue drained atomic.
        queued_count = dirty_count(uid, transaction=tx, firestore_client=database)
        # Re-read only inspected refs, fencing every observed version. Never
        # scan all 500 queued documents again just to settle a bounded pass.
        items = {dirty_id(item['collection'], item['id']): item for item in [*consumed, *unavailable]}
        keys = set(items) | deferred_ids
        if len(keys) > DIRTY_INSPECTION_LIMIT:
            raise ValueError('dream_settlement_limit')
        observed = []
        waiting = []
        for key in keys:
            snapshot = state.collection('dirty').document(key).get(transaction=tx)
            row = snapshot.to_dict() or {}
            if row and key in deferred_ids and release:
                waiting.append(snapshot)
            item = items.get(key)
            if item and row.get('version') == item['version']:
                observed.append((snapshot, item))
        versions = {item['version'] for item in consumed}
        touched = [
            snapshot
            for snapshot, item in observed
            if item['version'] in versions and dirty_id(item['collection'], item['id']) not in deferred_ids
        ]
        poisoned = [
            snapshot
            for snapshot in touched
            if failure_eligible and int(snapshot.to_dict().get('failed_passes', 0)) + 1 >= POISON_FAILURE_LIMIT
        ]
        unavailable_versions = {item['version'] for item in unavailable}
        misses = [
            (snapshot, item) for snapshot, item in observed if release and item['version'] in unavailable_versions
        ]
        permanent = [snapshot for snapshot, item in misses if not item['transient']]
        transient = [snapshot for snapshot, item in misses if item['transient']]
        expired = [
            snapshot
            for snapshot in transient
            if int(snapshot.to_dict().get('failed_passes', 0)) + 1 >= UNAVAILABLE_FAILURE_LIMIT
        ]
        acknowledged = list(
            {
                snapshot.reference.path: snapshot
                for snapshot in [*(touched if success else poisoned), *permanent, *expired]
            }.values()
        )
        acknowledged_paths = {snapshot.reference.path for snapshot in acknowledged}
        queued_after = queued_count - len(acknowledged)
        counts = {
            **report.get('dirty_counts', {}),
            'permanent_acknowledged': len(permanent),
            'transient_expired': len(expired),
        }
        settled: dict[str, Any] = {
            **report,
            'records_queued_after': queued_after,
            'poisoned': len(poisoned),
            'dirty_counts': counts,
        }
        settled['budget_charge_usd'] = charge
        if actual_cost is not None:
            settled['cost_usd'] = actual_cost
            settled['cost_status'] = 'priced'
        elif report.get('cost_status') == 'unpriced':
            settled['cost_status'] = 'unpriced'
        watermark = lease['watermark']
        if acknowledged:
            frontier = max(snapshot.to_dict()['last_changed_at'] for snapshot in acknowledged)
            if queued_after:
                # At most k acknowledged rows can precede the oldest remaining
                # row, so k+1 is enough to preserve the diagnostic frontier.
                oldest = dirty_refs(
                    uid, limit=len(acknowledged) + 1, newest=False, transaction=tx, firestore_client=database
                )
                remaining_times = [
                    snapshot.to_dict()['last_changed_at']
                    for snapshot in oldest
                    if snapshot.reference.path not in acknowledged_paths
                ]
                if remaining_times:
                    frontier = min(frontier, min(remaining_times) - timedelta(microseconds=1))
            watermark = max(watermark, frontier)
        encoded = _review_store().encode_doc(uid, {'source': settled})
        for snapshot in acknowledged:
            tx.delete(snapshot.reference)
        for snapshot in waiting:
            if snapshot.reference.path not in acknowledged_paths:
                # Attention belongs to the UTC day, so a refreshed version also
                # waits. Only this bounded set of affected refs is read/updated.
                tx.update(snapshot.reference, {'deferred_until': deferred_until})
        retrying = {
            snapshot.reference.path: snapshot
            for snapshot in [*(touched if failure_eligible else []), *transient]
            if snapshot.reference.path not in acknowledged_paths
        }
        for snapshot in retrying.values():
            tx.update(snapshot.reference, {'failed_passes': int(snapshot.to_dict().get('failed_passes', 0)) + 1})
        if report.get('reason') != 'idle':
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
                    **({'cost_usd': float(settled['cost_usd'])} if settled.get('cost_status') == 'priced' else {}),
                    'cost_status': settled.get('cost_status', 'unpriced'),
                    'poisoned': len(poisoned),
                },
            )
        patch = {
            'lease': (
                None
                if release
                else {
                    **current_lease,
                    'budget_charge_usd': charge,
                    'admission_refunded': bool(zero_refund or current_lease.get('admission_refunded')),
                }
            ),
            # The dirty set is authoritative; never filter reads by this diagnostic
            # frontier, which must remain behind older unread references.
            'watermark': watermark,
            'dirty_dropped_reported': lease['dirty_dropped'],
            'score': (
                max(0, data.get('score', 0) - lease['score'])
                if acknowledged and queued_after == 0
                else data.get('score', 0)
            ),
        }
        if zero_refund and not current_lease.get('admission_refunded'):
            # A midnight completion must not decrement the new day's allowance.
            if data.get('day') == lease['day']:
                counter = 'manual_runs' if lease.get('trigger') == 'manual' else 'passes'
                patch[counter] = max(0, int(data.get(counter, 0)) - 1)
        # Read-modify-write with lease completion prevents duplicate settlement
        # and preserves other charges already present in this user's UTC day.
        tx.set(
            spend, {**budget, 'reserved_usd': max(0, float(budget.get('reserved_usd', 0)) - previous_charge) + charge}
        )
        if global_spend:
            tx.set(
                global_spend,
                {
                    **global_budget,
                    'reserved_usd': max(0, float(global_budget.get('reserved_usd', 0)) - previous_charge) + charge,
                },
            )
        patch['size_bucket'] = report.get('size_bucket', data.get('size_bucket', 'light'))
        if success:
            # Payoff ordering reads the last pass's applied count; no extra write.
            patch['last_yield'] = sum(
                1 for row in report.get('outcomes') or [] if isinstance(row, dict) and row.get('status') == 'applied'
            )
            # Hunt backoff: consecutive hunts that applied nothing; any yield resets the streak.
            if patch['last_yield']:
                patch['dry_hunts'] = 0
            elif lease.get('hunt') and not lease.get('canary') and lease.get('trigger') == 'schedule':
                patch['dry_hunts'] = min(16, _dry_hunts(data) + 1)
        if poisoned:
            patch['poisoned'] = int(data.get('poisoned', 0)) + len(poisoned)
        for ref in sorted(deferred if release else ())[:8]:
            # Seeded targets have no dirty entry. Share their daily deferral with
            # both sampling paths without adding a second metadata read.
            tx.set(state.collection('reviews').document(review_id(ref)), {'deferred_until': deferred_until}, merge=True)
        if success:
            if cleanup_cursor is not None:
                patch['cleanup_cursor'] = cleanup_cursor
            if not zero_refund:
                patch['last_pass_at'] = lease['started_at']
                if report.get('state_pass_done'):
                    patch['last_state_pass_at'] = lease['started_at']
                for ref in sorted(set(reviewed) - deferred)[:8]:
                    tx.set(
                        state.collection('reviews').document(review_id(ref)),
                        {'last_reviewed_at': lease['started_at']},
                        merge=True,
                    )
        tx.update(state, patch)
        from database.dream_scheduler import due_time

        next_due = due_time({**data, **patch}, now, uid)
        if data.get('day') == now.date().isoformat() and data.get('passes', 0) >= current_lease.get(
            'passes_per_day', 2
        ):
            next_due = deferred_until
        if not release:
            next_due = now + timedelta(seconds=1740)
        if park_when_idle and release and queued_after == 0 and patch['score'] == 0:
            # Idle-skip lever: nothing left to do, so wait for mark_dirty instead of a timed hunt.
            tx.delete(database.collection('dream_due').document(uid))
        else:
            tx.set(database.collection('dream_due').document(uid), {'due_at': next_due})
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


def demoted_types(uid, caps, *, firestore_client=None):
    from utils import dream_telemetry

    since = datetime.now(timezone.utc) - timedelta(days=30)
    query = client(firestore_client).collection('users').document(uid).collection('review_changes')
    rows = (
        query.where(filter=firestore.FieldFilter('created_at', '>=', since))
        .order_by('created_at', direction='DESCENDING')
        .limit(500)
        .stream()
    )
    recent_since = datetime.now(timezone.utc) - timedelta(days=caps.undo_recent_days)
    counts = {}
    recent = {}
    for snapshot in rows:
        data = _review_store().decode_doc(uid, snapshot.to_dict()) or {}
        if not data.get('edit_key', '').startswith(('dream:', 'agent:')) or data.get('phase', 'applied') != 'applied':
            continue
        # The policy kind auto-apply checks; key segments differ (memory-target
        # spelling keys 'memory', accepted proposals 'user').
        kind = dream_telemetry.change_kind(data) or data['edit_key'].split(':')[1]
        undone_now = int(bool(data['change']['undone']))
        total, undone = counts.get(kind, (0, 0))
        counts[kind] = (total + 1, undone + undone_now)
        created = data.get('created_at')
        if undone_now and isinstance(created, datetime) and created >= recent_since:
            recent[kind] = recent.get(kind, 0) + 1
    return {
        kind
        for kind, (total, undone) in counts.items()
        if (total >= caps.undo_min_samples and undone / total > caps.undo_rate)
        or recent.get(kind, 0) >= caps.undo_recent_count
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
        count = max(0, min(requested, 3 - proposed - answers.get('dream_suggestions', 0), 3 - answers.get('used', 0)))
        tx.update(state, {'question_day': day, 'questions': proposed + count})
        return count

    return reserve(database.transaction())
