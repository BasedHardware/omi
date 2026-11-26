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
repair phases. The stamp is the counting key, so a replayed tick cannot count a
conversation twice, and a summary that lands after the close is not counted
retroactively.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from google.cloud import firestore
from prometheus_client import Counter, REGISTRY

from config.summary_guarantee import first_week_enabled
from database._client import get_firestore_client
from database.first_week_queries import due_first_week_conversations

logger = logging.getLogger(__name__)

CURSOR = 'maintenance/first_week_summary_closeout_v1'
LEASE_SECONDS = 120
SCAN_LIMIT = 100
SCAN_TIME_BUDGET_SECONDS = 60
OUTCOME_FIELD = 'first_week_outcome'
OUTCOME_AT_FIELD = 'first_week_outcome_at'
WINDOW_END_PATH = 'first_week_summary.window_end_at'
ATTEMPT_FAILED_REASONS = frozenset(
    {'empty_output_exhausted', 'empty_output_lifetime_exhausted', 'blocked_byok', 'empty_output'}
)


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
    interval = stamp.get('interval') if stamp.get('interval') in {'monthly', 'yearly', 'unknown'} else 'unknown'
    end = _epoch(stamp.get('window_end_at'))
    completed = _epoch(row.get('summary_completed_at'))
    if row.get('summary_output_present') and (completed is None or end is None or completed <= end):
        return 'summarized', interval
    if isinstance(row.get('summary_empty_failures'), (int, float)) and not isinstance(
        row.get('summary_empty_failures'), bool
    ):
        if row['summary_empty_failures'] > 0:
            return 'attempt_failed', interval
    if row.get('summary_blocked_reason') in ATTEMPT_FAILED_REASONS:
        return 'attempt_failed', interval
    return 'no_attempt', interval


def outcome_patch(row: Mapping[str, Any], *, now: float) -> dict[str, Any] | None:
    """The one-write patch that closes a window, or None when it is already counted."""
    if not isinstance(row, Mapping) or row.get(OUTCOME_FIELD) is not None:
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
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return
        row = snapshot.to_dict() or {}
        patch = outcome_patch(row, now=now)
        if patch is None:
            return
        transaction.update(ref, patch)
        result.append(classify(row))

    commit(client.transaction())
    return result[0] if result else None


def _lease(client: Any, owner: str, now: float) -> Any | None:
    ref = client.document(CURSOR)
    claimed: list[bool] = []

    @firestore.transactional
    def claim(transaction: Any) -> None:
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


def _release(ref: Any) -> None:
    try:
        ref.set({'owner': None, 'lease_until': 0, 'updated_at': time.time()}, merge=True)
    except Exception:
        logger.warning('event=first_week_closeout outcome=release_failed')


def tick(*, now: float | None = None, limit: int = SCAN_LIMIT, client: Any | None = None) -> dict[str, int]:
    current = time.time() if now is None else now
    counts = {'scanned': 0, 'closed': 0, 'errors': 0}
    if not first_week_enabled():
        return counts
    bound = client or get_firestore_client()
    owner = f'{time.time_ns()}'
    lease = _lease(bound, owner, current)
    if lease is None:
        counts['errors'] = 1
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
            CLOSED.labels(outcome=outcome, interval=interval).inc()
            counts['closed'] += 1
    finally:
        _release(lease)
    return counts
