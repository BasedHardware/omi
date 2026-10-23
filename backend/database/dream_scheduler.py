"""Durable due-work queue: bootstrap discovery is independent from admission."""

import logging
import time
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from database import firestore_transaction_retry
from database._client import get_firestore_client
from config.dream_agent import allowlist_uids, eligibility, eligible, enabled, hunt_interval
from utils.observability.fallback import record_fallback

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# A whole 499-row page in one transaction held ~1,000 reads plus up to 500
# writes and broke the 3 s RPC deadlines at 100% eligibility (2026-10-22 sweep
# 500). Chunks bound every transactional get_all, the write count per commit,
# and the non-transactional allowlist reads to the same 100-ref bulk-get size.
DISCOVERY_TRANSACTION_ROWS = 100
# Discovery is queue repair, not the sweep itself: it must never eat the
# 1680 s drain budget that paid passes run under.
DISCOVERY_BUDGET_SECONDS = 120.0

logger = logging.getLogger(__name__)


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


def _fallback_reason(error: BaseException) -> str:
    name = type(error).__name__.lower()
    if 'deadline' in name or 'timeout' in name:
        return 'timeout'
    if 'connection' in name or 'unavailable' in name:
        return 'connection_error'
    return 'other'


def _record_discovery_degrade(to_mode: str, reason: str) -> None:
    record_fallback(
        component='firestore_read',
        from_mode='dream_discovery',
        to_mode=to_mode,
        reason=reason,
        outcome='degraded',
        log=logger,
    )


def discover(database, now, *, pages=20, budget_seconds=DISCOVERY_BUDGET_SECONDS):
    """10,000 owners/hour on bootstrap, without waiting for any session to finish.

    Dirty writes enqueue immediately; this rotating scan supplies never-dirty
    owners and repairs missing queue rows. Future hunts remain in the queue.

    Each page commits in ``DISCOVERY_TRANSACTION_ROWS`` chunks so a fully
    eligible page stays well inside the 3 s RPC deadlines; the cursor advances
    only with a page's final chunk, so a failed or budget-stopped page re-scans
    from its start next sweep. Chunk commits are idempotent under that replay:
    the transactional ``dream_due`` read skips owners a concurrent dirty write
    already enqueued, and dirty writes overwrite ``due_at`` after us anyway.
    The scan also stops once ``budget_seconds`` of wall time is spent, keeping
    discovery from eating the drain's pass budget.
    """
    cursor = database.collection('dream_scheduler').document('discovery')
    listed = allowlist_uids() if eligibility() == 'allowlist' else None
    after = None if listed is not None else (cursor.get(timeout=3).to_dict() or {}).get('after')
    deadline = time.monotonic() + budget_seconds
    for _ in range(1 if listed is not None else pages):
        if time.monotonic() >= deadline:
            logger.warning('dream_discovery_stopped stage=page class=BudgetExhausted')
            _record_discovery_degrade(to_mode='partial_scan', reason='timeout')
            return
        rows = []
        if listed is not None:
            # Allowlist rollout: read only listed owners instead of scanning every user each sweep.
            users = database.collection('users')
            for start in range(0, min(len(listed), 499), DISCOVERY_TRANSACTION_ROWS):
                refs = [users.document(uid) for uid in listed[start : start + DISCOVERY_TRANSACTION_ROWS]]
                rows.extend(snapshot for snapshot in database.get_all(refs, timeout=3) if snapshot.exists)
        else:
            rows = candidate_page(after=after, firestore_client=database)
        if not rows:
            if listed is None:
                cursor.set({'after': None})
            break

        for start in range(0, len(rows), DISCOVERY_TRANSACTION_ROWS):
            if time.monotonic() >= deadline:
                logger.warning('dream_discovery_stopped stage=chunk class=BudgetExhausted')
                _record_discovery_degrade(to_mode='partial_scan', reason='timeout')
                return
            chunk = rows[start : start + DISCOVERY_TRANSACTION_ROWS]
            final_chunk = start + DISCOVERY_TRANSACTION_ROWS >= len(rows)

            @firestore.transactional
            def initialize(tx):
                # Every row's dream_due state is consumed: for eligible rows it
                # is the no-clobber guard against concurrent mark_dirty/finish
                # due_at writes, and for ineligible rows it is what says a
                # stale queue row must be deleted, so this read cannot shrink.
                queued = {
                    snapshot.id
                    for snapshot in database.get_all(
                        [database.collection('dream_due').document(row.id) for row in chunk],
                        transaction=tx,
                        timeout=3,
                    )
                    if snapshot.exists
                }
                eligible_owners = {row.id: eligible(row.id, row.to_dict() or {}) for row in chunk}
                # dream_users state only feeds due_time() for owners this chunk
                # is about to enqueue; skip the bulk read when none qualify.
                state_refs = [
                    database.collection('dream_users').document(uid)
                    for uid, is_eligible in eligible_owners.items()
                    if is_eligible and uid not in queued
                ]
                states = (
                    {
                        snapshot.id: snapshot.to_dict() or {}
                        for snapshot in database.get_all(state_refs, transaction=tx, timeout=3)
                    }
                    if state_refs
                    else {}
                )
                for row in chunk:
                    target = database.collection('dream_due').document(row.id)
                    if eligible_owners[row.id]:
                        if row.id not in queued:
                            tx.set(target, {'due_at': due_time(states.get(row.id, {}), now)})
                    elif row.id in queued:
                        tx.delete(target)
                if listed is None and final_chunk:
                    tx.set(cursor, {'after': rows[-1].id})

            firestore_transaction_retry.run_with_transaction_contention_retry(
                database.transaction, initialize, operation_name='dream_discover'
            )
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
    try:
        discover(database, now)
    except Exception as error:
        # Discovery only repairs queue rows for never-dirty owners; the sweep
        # must still drain whatever is already due. Class name only, never uids.
        logger.warning('dream_discovery_failed stage=discover class=%s', type(error).__name__)
        _record_discovery_degrade(to_mode='queue_only', reason=_fallback_reason(error))
    rows = (
        database.collection('dream_due')
        .where(filter=firestore.FieldFilter('due_at', '<=', now))
        .order_by('due_at')
        .limit(min(limit, 5000))
        .stream(timeout=3)
    )
    return [row.id for row in rows]
