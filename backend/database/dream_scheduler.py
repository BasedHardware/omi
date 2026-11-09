"""Durable due-work queue: bootstrap discovery is independent from admission."""

import logging
import time
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from database import firestore_transaction_retry
from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_blocks_user_work
from config.dream_agent import allowlist_uids, backed_off_hunt_interval, eligibility, eligible, enabled, hunt_interval
from config import dream_levers
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


def owner_hunt_interval(uid, state):
    """Today's hunt interval, backed off by the owner's dry-hunt streak when the lever serves them."""
    if uid is not None and dream_levers.arm(dream_levers.HUNT_BACKOFF_MODE_ENV, uid) == 'serve':
        return backed_off_hunt_interval(state.get('size_bucket'), state.get('dry_hunts'))
    return hunt_interval(state.get('size_bucket'))


def due_time(state, now, uid=None):
    last = state.get('last_attempt_at') or state.get('last_pass_at') or EPOCH
    if not isinstance(last, datetime) or last.tzinfo is None or last <= EPOCH:
        # A never-attempted owner is due immediately. Backdating the epoch by
        # score minutes created 1969 queue rows with permanent aging priority.
        return now
    if state.get('score', 0) > 0:
        due = last - timedelta(minutes=min(500, state['score']))
        return due if due >= EPOCH else now
    return last + owner_hunt_interval(uid, state)


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
                # The account-deletion marker is pinned to the customer data
                # plane, which may differ from this queue's compute database.
                # Read it through the shared authority outside this transaction;
                # the worker repeats the check immediately before execution.
                deletion_blocked = {row.id: account_deletion_blocks_user_work(row.id) for row in chunk}
                eligible_owners = {
                    row.id: eligible(row.id, row.to_dict() or {}) and not deletion_blocked[row.id] for row in chunk
                }
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
                        if row.id not in queued and not _parked(row.id, states.get(row.id, {})):
                            tx.set(target, {'due_at': due_time(states.get(row.id, {}), now, row.id)})
                    elif row.id in queued:
                        tx.delete(target)
                if listed is None and final_chunk:
                    tx.set(cursor, {'after': rows[-1].id})

            firestore_transaction_retry.run_with_transaction_contention_retry(
                database.transaction, initialize, operation_name='dream_discover'
            )
        after = rows[-1].id


def _parked(uid, state):
    """Idle-skip serve owners with no pending score wait for mark_dirty, not a timed hunt.

    Fails open: any doubt (lever error, a score, an unreadable state) enqueues as before.
    """
    try:
        return (
            dream_levers.arm(dream_levers.IDLE_SKIP_MODE_ENV, uid) == 'serve'
            and not state.get('score', 0)
            and not _backlog_owed(uid)
        )
    except Exception:
        return False


def _backlog_owed(uid):
    from config import required_memory_intake

    return required_memory_intake.backlog_enabled(uid)


# Payoff ordering (lever B2). Owners overdue this long run first in due order, so
# reordering can delay an owner by at most this much beyond today's queue.
# Payoff first (David 2026-10-30). Only a month-overdue owner jumps the payoff order:
# at 10-30 the oldest 200 due rows were all past a 7-day bound, so ranking was FIFO.
PAYOFF_AGING = timedelta(days=30)
# By 11-01 the saturated oldest head was mostly never-yielded heavy owners.
# Recent yield predicts payoff; heavy size now predicts cost, not yield.
PAYOFF_HEAVY_BONUS = 0
PAYOFF_AGING_FLOOR = 300
PAYOFF_RANKED = 1000


def payoff_order(rows, now, *, firestore_client=None):
    """Rank due (uid, due_at) rows: aged owners first, then recent yield and material.

    Reads one dream_users doc per ranked owner (at most PAYOFF_RANKED, in
    DISCOVERY_TRANSACTION_ROWS bulk gets). Keep the oldest PAYOFF_AGING_FLOOR
    rows, then sample evenly through the rest, including the newest due row.
    Unsampled owners keep due order after the ranked window, except that
    the aging guard always precedes payoff-ranked owners across the whole queue.
    """
    database = firestore_client if firestore_client is not None else get_firestore_client()
    if len(rows) <= PAYOFF_RANKED:
        head, tail = rows, []
    else:
        slots = PAYOFF_RANKED - PAYOFF_AGING_FLOOR
        remaining = len(rows) - PAYOFF_AGING_FLOOR
        ranked_indices = set(range(PAYOFF_AGING_FLOOR))
        ranked_indices.update(PAYOFF_AGING_FLOOR + index * (remaining - 1) // (slots - 1) for index in range(slots))
        head = [row for index, row in enumerate(rows) if index in ranked_indices]
        tail = [row for index, row in enumerate(rows) if index not in ranked_indices]
    states = {}
    for start in range(0, len(head), DISCOVERY_TRANSACTION_ROWS):
        refs = [
            database.collection('dream_users').document(uid)
            for uid, _ in head[start : start + DISCOVERY_TRANSACTION_ROWS]
        ]
        for snapshot in database.get_all(refs, timeout=3):
            states[snapshot.id] = snapshot.to_dict() or {}

    def key(row):
        uid, due_at = row
        # Existing pre-epoch sentinels must not win the aging class or due ties.
        due = due_at if isinstance(due_at, datetime) and due_at.tzinfo is not None and due_at >= EPOCH else now
        if now - due >= PAYOFF_AGING:
            return (0, 0.0, due)
        state = states.get(uid, {})
        payoff = (
            min(10, max(0, int(state.get('score', 0) or 0)))
            + 7 * min(10, max(0, int(state.get('last_yield', 0) or 0)))
            + (PAYOFF_HEAVY_BONUS if state.get('size_bucket') == 'heavy' else 0)
        )
        return (1, -float(payoff), due)

    ranked = [uid for uid, _ in sorted(head, key=key)] + [uid for uid, _ in tail]
    # The old contiguous head + FIFO tail kept every aged owner ahead of
    # younger owners. Sampling must retain that guard even for skipped rows;
    # classifying their due timestamp needs no additional state reads.
    aged = [
        uid
        for uid, due_at in rows
        if isinstance(due_at, datetime) and due_at.tzinfo is not None and EPOCH <= due_at <= now - PAYOFF_AGING
    ]
    aged_set = set(aged)
    return aged + [uid for uid in ranked if uid not in aged_set]


def remove_due(uid, *, firestore_client=None):
    """Drop an ineligible scheduler row, retaining owner state and dirty work.

    Discovery recreates the row if the owner becomes eligible again.
    """
    database = firestore_client if firestore_client is not None else get_firestore_client()
    database.collection('dream_due').document(uid).delete()


def candidates(*, limit=5000, now=None, firestore_client=None, with_due=False):
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
    if with_due:
        selected = [(row.id, (row.to_dict() or {}).get('due_at')) for row in rows]
    else:
        selected = [(row.id, None) for row in rows]
    eligible_rows = []
    for uid, due_at in selected:
        if account_deletion_blocks_user_work(uid):
            remove_due(uid, firestore_client=database)
            continue
        eligible_rows.append((uid, due_at))
    if with_due:
        return eligible_rows
    return [uid for uid, _due_at in eligible_rows]


def required_retry_page(*, limit=4990, firestore_client=None):
    """Independent rotating owner inventory for owed intake, never paid-gated.

    Reuse the projected, indexed Dream discovery query. Its own cursor is
    committed only through the completed prefix, so a pass deadline cannot
    skip unvisited owners. No new queue, job or Scheduler is involved.
    """
    database = firestore_client if firestore_client is not None else get_firestore_client()
    cursor = database.collection('dream_scheduler').document('required_intake')
    before = (cursor.get(timeout=3).to_dict() or {}).get('after')
    after = before
    owners = []
    budget = max(0, min(4990, limit))
    while len(owners) < budget:
        rows = candidate_page(after=after, limit=min(499, budget - len(owners)), firestore_client=database)
        if not rows:
            break
        owners.extend(row.id for row in rows if not account_deletion_blocks_user_work(row.id))
        after = rows[-1].id
    return owners, before


def finish_required_retry_page(before, after, *, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    ref = database.collection('dream_scheduler').document('required_intake')

    @firestore.transactional
    def finish(tx):
        current = (ref.get(transaction=tx).to_dict() or {}).get('after')
        if current == before:
            tx.set(ref, {'after': after})

    firestore_transaction_retry.run_with_transaction_contention_retry(
        database.transaction, finish, operation_name='dream_required_retry_cursor'
    )
