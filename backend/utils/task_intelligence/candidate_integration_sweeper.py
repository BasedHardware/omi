"""Bounded retry and stale-abandon pass for candidate_integration_outbox.

One invocation inspects at most ``MAX_ROWS`` collection-group rows and stops
at ``BUDGET_SECONDS``. Rows older than seven days, missing ``created_at``, or
on a previous account generation are dead-lettered with no provider call.
Younger due rows use the blocking dispatch so the lease is completed before
the pass moves on.

A ``processing`` row is reclaimed only when ``claimed_at`` is older than
``SWEEP_RECLAIM_AFTER`` (one hour). The claim protocol's 300s lease stays as
it is: an inline accept job can sit on the shared postprocess pool past those
300s and still own the row. That job re-stamps ``claimed_at`` when it starts,
and this pass's blocking dispatch does the same just before the provider call.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import database.candidate_integration_outbox as integration_outbox_db
from utils.executors import db_executor, postprocess_executor, run_blocking
from utils.metrics import CANDIDATE_INTEGRATION_SWEEP_DISPOSITIONS, OMI_CANDIDATE_INTEGRATION_SWEEP_TOTAL
from utils.task_intelligence import candidate_service

logger = logging.getLogger(__name__)

MAX_ROWS = 200
BUDGET_SECONDS = 50.0
STALE_AFTER = timedelta(days=7)
PENDING_GRACE = timedelta(minutes=10)
# Not the 300s claim lease. Reclaiming a processing row at 300s races an inline
# export that is still queued; one hour is long enough for that job to start
# and re-stamp, or to lose the token and skip the provider.
SWEEP_RECLAIM_AFTER = timedelta(hours=1)
SCAN_STATUSES = ('failed', 'processing', 'pending')


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bump(counts: dict[str, int], disposition: str) -> None:
    if disposition not in CANDIDATE_INTEGRATION_SWEEP_DISPOSITIONS:
        raise ValueError('unknown sweep disposition')
    counts[disposition] += 1
    OMI_CANDIDATE_INTEGRATION_SWEEP_TOTAL.labels(disposition=disposition).inc()


def _lease_is_live(row: dict[str, Any], now: datetime) -> bool:
    """True while this pass must not reclaim or dead-letter the processing row."""
    if row.get('status') != 'processing':
        return False
    claimed_at = row.get('claimed_at')
    if not isinstance(claimed_at, datetime):
        return False
    return _aware(claimed_at) + SWEEP_RECLAIM_AFTER > now


async def _generation(uid: str, cache: dict[str, int]) -> int:
    if uid not in cache:
        cache[uid] = await run_blocking(db_executor, integration_outbox_db.current_task_account_generation, uid)
    return cache[uid]


async def _abandon(uid: str, candidate_id: str, reason: str, now: datetime) -> bool:
    return await run_blocking(
        db_executor,
        integration_outbox_db.abandon_candidate_integration_dispatch,
        uid,
        candidate_id,
        reason=reason,
        now=now,
    )


async def _dispose(
    row: dict[str, Any],
    *,
    now: datetime,
    counts: dict[str, int],
    generations: dict[str, int],
) -> None:
    uid = row.get('uid')
    candidate_id = row.get('candidate_id')
    if not isinstance(uid, str) or not uid or not isinstance(candidate_id, str) or not candidate_id:
        _bump(counts, 'error')
        return
    if _lease_is_live(row, now):
        _bump(counts, 'skipped_live_lease')
        return
    created_at = row.get('created_at')
    if not isinstance(created_at, datetime):
        wrote = await _abandon(uid, candidate_id, 'missing_created_at', now)
        _bump(counts, 'dead_letter_missing_created_at' if wrote else 'skipped_not_claimed')
        return
    if _aware(created_at) < now - STALE_AFTER:
        wrote = await _abandon(uid, candidate_id, 'stale_abandoned', now)
        _bump(counts, 'dead_letter_stale_abandoned' if wrote else 'skipped_not_claimed')
        return
    if row.get('status') == 'pending' and now - _aware(created_at) < PENDING_GRACE:
        _bump(counts, 'skipped_pending_young')
        return
    try:
        generation = await _generation(uid, generations)
    except Exception as error:
        logger.error(
            'candidate integration sweep generation read failed exception_type=%s',
            type(error).__name__,
        )
        _bump(counts, 'error')
        return
    row_generation = row.get('account_generation')
    if row_generation != generation:
        wrote = await _abandon(uid, candidate_id, 'generation_mismatch', now)
        _bump(counts, 'dead_letter_generation_mismatch' if wrote else 'skipped_not_claimed')
        return
    task_id = row.get('task_id')
    if not isinstance(task_id, str) or not task_id:
        try:
            wrote = await run_blocking(
                db_executor,
                integration_outbox_db.dead_letter_malformed_candidate_integration,
                uid,
                candidate_id,
                account_generation=generation,
                error_text='malformed integration outbox item',
                now=now,
            )
        except Exception as error:
            logger.error(
                'candidate integration sweep malformed dead-letter failed exception_type=%s',
                type(error).__name__,
            )
            _bump(counts, 'error')
            return
        _bump(counts, 'dead_letter_malformed' if wrote else 'skipped_not_claimed')
        return
    available_at = row.get('available_at')
    if isinstance(available_at, datetime) and _aware(available_at) > now:
        _bump(counts, 'skipped_not_due')
        return
    try:
        attempt_count = int(row.get('attempt_count') or 0)
    except (TypeError, ValueError):
        attempt_count = 0
    if attempt_count >= integration_outbox_db.CANDIDATE_INTEGRATION_POLICY.max_attempts:
        _bump(counts, 'skipped_attempt_budget')
        return
    try:
        recorded = await run_blocking(
            postprocess_executor,
            candidate_service.dispatch_task_integration_blocking,
            uid,
            candidate_id,
            task_id,
            account_generation=generation,
        )
    except Exception as error:
        logger.error('candidate integration sweep dispatch failed exception_type=%s', type(error).__name__)
        _bump(counts, 'error')
        return
    _bump(counts, 'retried' if recorded else 'skipped_not_claimed')


async def sweep_candidate_integrations(
    *,
    now: Optional[datetime] = None,
    max_rows: int = MAX_ROWS,
    budget_seconds: float = BUDGET_SECONDS,
    firestore_client: Any = None,
    monotonic: Optional[Callable[[], float]] = None,
) -> dict[str, int]:
    """One bounded pass. Counts are dispositions plus ``inspected``; no uid."""
    clock = monotonic or time.monotonic
    started = clock()
    deadline = started + budget_seconds
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        observed = observed.replace(tzinfo=timezone.utc)
    counts = {name: 0 for name in CANDIDATE_INTEGRATION_SWEEP_DISPOSITIONS}
    inspected = 0
    remaining = max_rows
    generations: dict[str, int] = {}
    for status in SCAN_STATUSES:
        if remaining <= 0 or clock() >= deadline:
            break
        rows = await run_blocking(
            db_executor,
            integration_outbox_db.list_candidate_integration_sweep_rows,
            status,
            limit=remaining,
            firestore_client=firestore_client,
        )
        for row in rows:
            if remaining <= 0 or clock() >= deadline:
                break
            inspected += 1
            remaining -= 1
            await _dispose(row, now=observed, counts=counts, generations=generations)
    return {'inspected': inspected, **counts}
