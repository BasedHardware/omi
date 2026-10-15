"""Bounded retry and stale-abandon pass for candidate_integration_outbox.

One invocation inspects at most ``MAX_ROWS`` collection-group rows and stops
at ``BUDGET_SECONDS``. Rows older than seven days (or older than seven days
since ``redriven_at``, when an operator redrive stamped one), missing
``created_at``, or on a previous account generation are dead-lettered with no
provider call. A failed row is retried only when its recorded provider outcome
is known to be pre-accept. Ambiguous creates are dead-lettered, or completed
from a recorded external id, and never posted again.

A ``processing`` row is reclaimed only when ``claimed_at`` is older than
``SWEEP_RECLAIM_AFTER`` (one hour). The claim protocol's 300s lease stays as
it is: an inline accept job can sit on the shared postprocess pool past those
300s and still own the row. That job re-stamps ``claimed_at`` when it starts,
and this pass's blocking dispatch does the same just before the provider call.

The scan orders each status by document name and continues from the previous
pass's cursor, so rows that stay in the same status do not pin the budget on
the same prefix. One invocation reads each status at most once. An empty page
after a cursor clears that cursor for the next invocation and moves on; it
does not reread the prefix in this pass.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import database.action_items as action_items_db
import database.candidate_integration_outbox as integration_outbox_db
from database._client import get_firestore_client
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


def _row_path(row: dict[str, Any]) -> str:
    return f"users/{row['uid']}/{integration_outbox_db.CANDIDATE_INTEGRATION_OUTBOX_COLLECTION}/{row['candidate_id']}"


def _lease_is_live(row: dict[str, Any], now: datetime) -> bool:
    """True while this pass must not reclaim or dead-letter the processing row."""
    if row.get('status') != 'processing':
        return False
    claimed_at = row.get('claimed_at')
    if not isinstance(claimed_at, datetime):
        return False
    return _aware(claimed_at) + SWEEP_RECLAIM_AFTER > now


def _attempt_count(row: dict[str, Any]) -> int:
    try:
        return int(row.get('attempt_count') or 0)
    except (TypeError, ValueError):
        return 0


def _external_task_id(row: dict[str, Any]) -> Optional[str]:
    external_id = row.get('external_task_id')
    if isinstance(external_id, str) and external_id:
        return external_id
    return None


def _provider_retry_allowed(row: dict[str, Any]) -> bool:
    """True only when this row is known not to have been accepted by the provider."""
    outcome = row.get('provider_attempt_outcome')
    if outcome in integration_outbox_db.PROVIDER_ATTEMPT_RETRY_SAFE:
        return True
    return row.get('status') == 'pending' and _attempt_count(row) == 0 and outcome is None


def _load_sweep_state(firestore_client: Any) -> tuple[Any, dict[str, str]]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        cursors = integration_outbox_db.read_candidate_integration_sweep_cursors(firestore_client=client)
    except Exception as error:
        logger.error('candidate integration sweep cursor read failed exception_type=%s', type(error).__name__)
        cursors = {}
    return client, cursors


async def _generation(uid: str, cache: dict[str, int], firestore_client: Any) -> int:
    if uid not in cache:
        cache[uid] = await run_blocking(
            db_executor,
            integration_outbox_db.current_task_account_generation,
            uid,
            firestore_client=firestore_client,
        )
    return cache[uid]


async def _abandon(uid: str, candidate_id: str, reason: str, now: datetime, firestore_client: Any) -> bool:
    return await run_blocking(
        db_executor,
        integration_outbox_db.abandon_candidate_integration_dispatch,
        uid,
        candidate_id,
        reason=reason,
        now=now,
        firestore_client=firestore_client,
    )


async def _recover_recorded_export(
    row: dict[str, Any],
    *,
    external_id: str,
    now: datetime,
    counts: dict[str, int],
    firestore_client: Any,
) -> None:
    """Mark the local task exported from the recorded id. No provider call."""
    uid = row['uid']
    candidate_id = row['candidate_id']
    task_id = row['task_id']
    export_platform = row.get('export_platform')

    def _mark_exported() -> Any:
        fields = integration_outbox_db.recorded_export_action_fields(
            now=now,
            external_task_id=external_id,
            export_platform=export_platform,
        )
        return action_items_db.update_action_item(uid, task_id, fields)

    try:
        updated = await run_blocking(db_executor, _mark_exported)
    except Exception as error:
        logger.error(
            'candidate integration sweep export recovery failed exception_type=%s',
            type(error).__name__,
        )
        _bump(counts, 'error')
        return
    if not updated:
        wrote = await _abandon(uid, candidate_id, 'in_doubt', now, firestore_client)
        _bump(counts, 'dead_letter_in_doubt' if wrote else 'skipped_not_claimed')
        return
    try:
        wrote = await run_blocking(
            db_executor,
            integration_outbox_db.complete_candidate_integration_recorded_export,
            uid,
            candidate_id,
            external_task_id=external_id,
            now=now,
            firestore_client=firestore_client,
        )
    except Exception as error:
        logger.error(
            'candidate integration sweep recorded-export complete failed exception_type=%s',
            type(error).__name__,
        )
        _bump(counts, 'error')
        return
    _bump(counts, 'recovered_external_id' if wrote else 'skipped_not_claimed')


async def _dispose(
    row: dict[str, Any],
    *,
    now: datetime,
    counts: dict[str, int],
    generations: dict[str, int],
    firestore_client: Any,
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
    redriven_at = row.get('redriven_at')
    if isinstance(redriven_at, datetime):
        age_anchor = redriven_at
    elif isinstance(created_at, datetime):
        age_anchor = created_at
    else:
        wrote = await _abandon(uid, candidate_id, 'missing_created_at', now, firestore_client)
        _bump(counts, 'dead_letter_missing_created_at' if wrote else 'skipped_not_claimed')
        return
    if _aware(age_anchor) < now - STALE_AFTER:
        wrote = await _abandon(uid, candidate_id, 'stale_abandoned', now, firestore_client)
        _bump(counts, 'dead_letter_stale_abandoned' if wrote else 'skipped_not_claimed')
        return
    if isinstance(created_at, datetime) and row.get('status') == 'pending' and now - _aware(created_at) < PENDING_GRACE:
        _bump(counts, 'skipped_pending_young')
        return
    try:
        generation = await _generation(uid, generations, firestore_client)
    except Exception as error:
        logger.error(
            'candidate integration sweep generation read failed exception_type=%s',
            type(error).__name__,
        )
        _bump(counts, 'error')
        return
    row_generation = row.get('account_generation')
    if row_generation != generation:
        try:
            outcome = await run_blocking(
                db_executor,
                integration_outbox_db.dead_letter_candidate_integration_generation_mismatch,
                uid,
                candidate_id,
                now=now,
                firestore_client=firestore_client,
            )
        except Exception as error:
            logger.error(
                'candidate integration sweep generation check failed exception_type=%s',
                type(error).__name__,
            )
            _bump(counts, 'error')
            return
        if outcome == 'dead_letter':
            _bump(counts, 'dead_letter_generation_mismatch')
            return
        if outcome != 'current':
            _bump(counts, 'skipped_not_claimed')
            return
        if isinstance(row_generation, int):
            generations[uid] = row_generation
            generation = row_generation
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
    if _attempt_count(row) >= integration_outbox_db.CANDIDATE_INTEGRATION_POLICY.max_attempts:
        _bump(counts, 'skipped_attempt_budget')
        return
    try:
        deleting = await run_blocking(
            db_executor,
            candidate_service.provider_dispatch_blocked_by_account_deletion,
            uid,
        )
    except Exception as error:
        logger.error(
            'candidate integration sweep deletion fence failed exception_type=%s',
            type(error).__name__,
        )
        deleting = True
    if deleting:
        _bump(counts, 'skipped_account_deleting')
        return
    external_id = _external_task_id(row)
    if external_id is not None:
        await _recover_recorded_export(
            row,
            external_id=external_id,
            now=now,
            counts=counts,
            firestore_client=firestore_client,
        )
        return
    if not _provider_retry_allowed(row):
        wrote = await _abandon(uid, candidate_id, 'in_doubt', now, firestore_client)
        _bump(counts, 'dead_letter_in_doubt' if wrote else 'skipped_not_claimed')
        return
    try:
        recorded = await run_blocking(
            postprocess_executor,
            candidate_service.dispatch_task_integration_blocking,
            uid,
            candidate_id,
            task_id,
            account_generation=generation,
            firestore_client=firestore_client,
        )
    except Exception as error:
        logger.error('candidate integration sweep dispatch failed exception_type=%s', type(error).__name__)
        _bump(counts, 'error')
        return
    _bump(counts, 'retried' if recorded else 'skipped_not_claimed')


async def _page(
    status: str,
    *,
    limit: int,
    start_after_path: Optional[str],
    firestore_client: Any,
) -> tuple[list[dict[str, Any]], bool]:
    return await run_blocking(
        db_executor,
        integration_outbox_db.list_candidate_integration_sweep_rows,
        status,
        limit=limit,
        firestore_client=firestore_client,
        start_after_path=start_after_path,
    )


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
    client, cursors = await run_blocking(db_executor, _load_sweep_state, firestore_client)
    for status in SCAN_STATUSES:
        if remaining <= 0 or clock() >= deadline:
            break
        cursor = cursors.get(status)
        page_limit = remaining
        rows, reached_end = await _page(
            status,
            limit=page_limit,
            start_after_path=cursor,
            firestore_client=client,
        )
        if not rows and cursor:
            # The cursor is past the last row of this status. Clear it for the
            # next invocation and move on. Rereading the prefix here spends the
            # rest of this pass on rows the previous pass already skipped.
            cursors.pop(status, None)
            continue
        inspected_paths: list[str] = []
        for row in rows:
            if remaining <= 0 or clock() >= deadline:
                break
            inspected += 1
            remaining -= 1
            inspected_paths.append(_row_path(row))
            await _dispose(
                row,
                now=observed,
                counts=counts,
                generations=generations,
                firestore_client=client,
            )
        if not inspected_paths:
            if reached_end:
                cursors.pop(status, None)
            continue
        if reached_end and len(inspected_paths) == len(rows):
            cursors.pop(status, None)
        else:
            cursors[status] = inspected_paths[-1]
    try:
        await run_blocking(
            db_executor,
            integration_outbox_db.write_candidate_integration_sweep_cursors,
            cursors,
            firestore_client=client,
        )
    except Exception as error:
        logger.error('candidate integration sweep cursor write failed exception_type=%s', type(error).__name__)
    return {'inspected': inspected, **counts}
