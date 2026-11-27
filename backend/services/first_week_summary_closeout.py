"""First-week summary close-out and its aggregate counter (SCA-4790, mechanism 4).

One row per conversation a new paid subscription created inside its first-week
window. At the stored window end the row is stamped with one terminal outcome
and counted once:

- ``summarized``: a usable summary was durable by the window end;
- ``attempt_failed``: an attempt landed but produced no usable summary
  (empty-output budget, BYOK block);
- ``no_attempt``: no attempt was recorded at the window end.

The pass owns its lease and scan budget, separate from ``summary_debt_repair``:
a missing index or a slow page fails this phase only and never the existing
repair phases. The outcome stamp and its aggregate count document are written in
one transaction, so a replayed tick cannot count a conversation twice and the
durable aggregate remains authoritative if the process exits before updating its
Prometheus counter. A summary that lands after the close is not counted
retroactively.
"""

from __future__ import annotations

import logging
import hashlib
import math
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from google.cloud import firestore
from prometheus_client import Counter, REGISTRY

from config.summary_guarantee import first_week_enabled
from database._client import get_firestore_client

logger = logging.getLogger(__name__)

CURSOR = 'maintenance/first_week_summary_closeout_v1'
COUNTS_COLLECTION = 'maintenance/first_week_summary_outcomes/counts'
LEASE_SECONDS = 120
SCAN_LIMIT = 25
SCAN_TIME_BUDGET_SECONDS = 15
OUTCOME_FIELD = 'first_week_outcome'
OUTCOME_AT_FIELD = 'first_week_outcome_at'
WINDOW_END_PATH = 'first_week_summary.window_end_at'
OUTCOMES = frozenset({'summarized', 'attempt_failed', 'no_attempt'})


def _bounded_outcome(value: object) -> str:
    """Keep metric outcomes inside the durable classifier vocabulary."""
    return value if isinstance(value, str) and value in OUTCOMES else 'unknown'


def _counter() -> Counter:
    name = 'omi_first_week_summary_outcome_total'
    try:
        return Counter(
            name,
            'First-week conversations of a new paid subscription by outcome at window close',
            ['outcome', 'interval'],
        )
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]


CLOSED = _counter()


def _epoch(value: Any) -> float | None:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def classify(row: Mapping[str, Any]) -> tuple[str, str]:
    """The terminal outcome and the stored interval for one closed window."""
    stamp = row.get('first_week_summary')
    stamp = stamp if isinstance(stamp, Mapping) else {}
    raw_interval = stamp.get('interval')
    interval = (
        raw_interval
        if isinstance(raw_interval, str) and raw_interval in {'monthly', 'yearly', 'unknown'}
        else 'unknown'
    )
    end = _epoch(stamp.get('window_end_at'))
    completed = _epoch(row.get('summary_completed_at'))
    if row.get('summary_output_present') and (completed is None or end is None or completed <= end):
        return 'summarized', interval
    attempts = row.get('first_week_attempts')
    if type(attempts) is int and attempts > 0 and row.get('first_week_last_class') == 'attempt_failed':
        return 'attempt_failed', interval
    return 'no_attempt', interval


def outcome_patch(row: Mapping[str, Any], *, now: float) -> dict[str, Any] | None:
    """The one-write patch that closes a window, or None when it is already counted."""
    if row.get(OUTCOME_FIELD) is not None:
        return None
    outcome, _ = classify(row)
    return {OUTCOME_FIELD: outcome, OUTCOME_AT_FIELD: now}


def close_one(ref: Any, *, now: float, client: Any) -> tuple[str, str] | None:
    """Stamp one row's outcome inside a transaction that re-reads the summary state.

    A summary that lands between the scan and this transaction wins: the CAS
    stamps ``summarized`` (or leaves the outcome for a write that already set it),
    never ``no_attempt``. Returns the counted (outcome, interval), or None when a
    concurrent writer owns the row.
    """
    result: list[tuple[str, str]] = []

    @firestore.transactional
    def commit(transaction: Any) -> None:
        result.clear()
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return
        row = snapshot.to_dict() or {}
        uid = row.get('uid')
        conversation_id = getattr(ref, 'id', None) or str(getattr(ref, 'path', '')).rsplit('/', 1)[-1]
        if isinstance(uid, str) and uid and conversation_id:
            outbox_id = hashlib.sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest()
            outbox_ref = client.collection('sync_reprocess_outbox').document(outbox_id)
            outbox_snapshot = outbox_ref.get(transaction=transaction)
            outbox_row = outbox_snapshot.to_dict() or {} if outbox_snapshot.exists else {}
            for field_name in ('first_week_attempts', 'first_week_last_class'):
                if field_name in outbox_row:
                    row[field_name] = outbox_row[field_name]
        patch = outcome_patch(row, now=now)
        if patch is None:
            return
        counted = classify(row)
        outcome, interval = counted
        count_ref = client.collection(COUNTS_COLLECTION).document(f'{interval}_{outcome}')
        count_snapshot = count_ref.get(transaction=transaction)
        count_row = count_snapshot.to_dict() or {}
        previous = count_row.get('count')
        count = previous if type(previous) is int and previous >= 0 else 0
        transaction.update(ref, patch)
        transaction.set(
            count_ref,
            {'outcome': outcome, 'interval': interval, 'count': count + 1, 'updated_at': now},
            merge=True,
        )
        result.append(counted)

    commit(client.transaction())
    return result[0] if result else None


def _lease(client: Any, owner: str, now: float) -> Any | None:
    ref = client.document(CURSOR)
    claimed: list[bool] = []

    @firestore.transactional
    def claim(transaction: Any) -> None:
        claimed.clear()
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() or {}
        if float(row.get('lease_until') or 0) > now and row.get('owner') != owner:
            return
        claimed.append(True)
        transaction.set(
            ref,
            {'owner': owner, 'lease_until': now + LEASE_SECONDS, 'updated_at': now},
            merge=True,
        )

    claim(client.transaction())
    return ref if claimed else None


def _release(ref: Any, owner: str, client: Any) -> None:
    try:

        @firestore.transactional
        def release(transaction: Any) -> None:
            snapshot = ref.get(transaction=transaction)
            row = snapshot.to_dict() or {}
            if row.get('owner') != owner:
                return
            transaction.update(ref, {'owner': None, 'lease_until': 0, 'updated_at': time.time()})

        release(client.transaction())
    except Exception:
        logger.warning('event=first_week_closeout outcome=release_failed')


def durable_outcome_counts(*, client: Any | None = None) -> dict[tuple[str, str], int]:
    """Read the bounded durable aggregate used for the gap-free production readback."""
    bound = client or get_firestore_client()
    counts: dict[tuple[str, str], int] = {}
    for snapshot in bound.collection(COUNTS_COLLECTION).stream():
        row = snapshot.to_dict() or {}
        outcome, interval, count = row.get('outcome'), row.get('interval'), row.get('count')
        if (
            outcome in {'summarized', 'attempt_failed', 'no_attempt'}
            and interval in {'monthly', 'yearly', 'unknown'}
            and type(count) is int
            and count >= 0
        ):
            counts[(outcome, interval)] = count
    return counts


def tick(*, now: float | None = None, limit: int = SCAN_LIMIT, client: Any | None = None) -> dict[str, int]:
    current = time.time() if now is None else now
    counts = {'scanned': 0, 'closed': 0, 'errors': 0, 'lease_busy': 0}
    if not first_week_enabled():
        return counts
    from database.first_week_queries import due_first_week_conversations

    bound = client or get_firestore_client()
    owner = f'{time.time_ns()}'
    lease = _lease(bound, owner, current)
    if lease is None:
        counts['lease_busy'] = 1
        return counts
    started = time.monotonic()
    try:
        try:
            page = due_first_week_conversations(now=current, limit=limit, firestore_client=bound)
        except Exception as error:
            # A missing index or an unavailable page fails this phase only; the
            # existing repair phases keep their own query and budget.
            counts['errors'] += 1
            logger.warning('event=first_week_closeout outcome=query_error exception_type=%s', type(error).__name__)
            return counts
        counts['scanned'] = len(page)
        for snapshot in page:
            if time.monotonic() - started >= SCAN_TIME_BUDGET_SECONDS:
                break
            try:
                closed = close_one(snapshot.reference, now=current, client=bound)
            except Exception as error:
                counts['errors'] += 1
                logger.warning('event=first_week_closeout outcome=close_error exception_type=%s', type(error).__name__)
                continue
            if closed is None:
                continue
            outcome, interval = closed
            CLOSED.labels(outcome=_bounded_outcome(outcome), interval=interval).inc()
            counts['closed'] += 1
    finally:
        _release(lease, owner, bound)
    return counts
