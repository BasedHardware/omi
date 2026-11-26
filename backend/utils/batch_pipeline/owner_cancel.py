"""Owner-requested cancellation of an uploaded batch recording that has not been transcribed.

``DELETE /v2/sync-local-files/{job_id}`` calls :func:`cancel_owner_upload`. Two phases:

1. **Fence**: one store transaction over the intake, the content ledger and every
   sibling unit. Nothing is written unless every unit is detached from compute
   (queued, retry, allowance/vendor held, quarantined without a running recovery,
   dead). The units become the existing terminal ``privacy_blocked`` state with
   ``merge_pending=False``, queued units are unlinked from the owner's FIFO,
   allowance-hold counts are released, and the intake and ledger are stamped.
   A worker transaction that leased, merged or projected a unit first makes the
   fence answer ``in_progress`` instead; a committed transcript is never erased.
2. **Erase**: idempotent and retryable. Each fenced unit's objects and rows,
   then the upload's private-cloud raw originals. A failure leaves the fence,
   so nothing transcribes, and the owner's next call finishes the erasure.

Completed and partially projected uploads answer ``already_processed`` with
their conversation ids; the owner deletes those conversations normally.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
import time
from typing import Any, Protocol

from config import sync_owner_cancel
from database.batch_pipeline_privacy import BatchPrivacyReason
from database.record_wal_handoff import JOB_PREFIX as WAL_HANDOFF_PREFIX
from database.sync_ledger import (
    BATCH_PARTIAL_STATUS,
    LEDGER_RETENTION_DAYS,
    is_valid_completed_sync_content_result,
    is_valid_partial_sync_content_result,
)

logger = logging.getLogger(__name__)

JOB_PREFIX = 'bp_'
REASON_CODE = 'owner_cancelled'
LEDGER_STATUS = 'owner_cancelled'
FENCED_STATE = 'privacy_blocked'
ALLOWANCE_HELD = 'allowance_held'
ALLOWANCE_OWNERS = 'allowance_holds'

# Detached from compute: no lease, no merge or projection in flight.
CANCELLABLE_STATES = frozenset({'ready', 'retry', ALLOWANCE_HELD, 'vendor_held', 'quarantined', 'dead', FENCED_STATE})
# A paid or operator recovery has been prepared or is running for the unit.
_RUNNING_RECOVERY = frozenset({'prepared', 'running'})
_OPERATOR_INTENTS = ('speech_redrive', 'terminal_disposition', 'silence_disposition')


class Outcome(str, Enum):
    CANCELLED = 'cancelled'
    ALREADY_PROCESSED = 'already_processed'
    NOT_FOUND = 'not_found'
    IN_PROGRESS = 'in_progress'
    NOT_CANCELLABLE = 'not_cancellable'


@dataclass(frozen=True)
class CancelResult:
    outcome: Outcome
    conversation_ids: tuple[str, ...] = ()
    erasure: str | None = None  # 'complete' | 'pending' for CANCELLED
    archive_paths: tuple[str, ...] = ()


class CancelDisabled(RuntimeError):
    """The kill switch is off; the phone keeps its tombstone and retries later."""


class Eraser(Protocol):
    def erase_unit(self, uid: str, segment_id: str) -> None:
        """Erase one fenced unit's objects and rows; a no-op for an absent row. Raises on failure."""

    def erase_archives(self, uid: str, job_id: str, paths: tuple[str, ...]) -> None:
        """Erase the upload's unlinked private-cloud originals. Raises on failure."""

    def erase_hold(self, uid: str, hold_id: str) -> None:
        """Erase one fenced legacy cap hold's objects and row; a no-op when absent. Raises on failure."""


def is_owner_cancelled(job: dict) -> bool:
    """The fence wrote this unit; the eraser re-proves it before deleting anything."""
    return job.get('state') == FENCED_STATE and job.get('owner_cancelled_at') is not None


def _handle_shape_ok(job_id: str) -> bool:
    return job_id.startswith(JOB_PREFIX) and len(job_id) <= 128 and '/' not in job_id


def conversation_ids(result: Any) -> tuple[str, ...]:
    result = result if isinstance(result, dict) else {}
    ids: list[str] = []
    for value in (*(result.get('new_memories') or []), *(result.get('updated_memories') or [])):
        if isinstance(value, str) and value not in ids:
            ids.append(value)
    return tuple(ids)


def _processed(ledger: dict) -> bool:
    result = ledger.get('result')
    status = ledger.get('status')
    return (status == 'completed' and is_valid_completed_sync_content_result(result)) or (
        status == BATCH_PARTIAL_STATUS and is_valid_partial_sync_content_result(result)
    )


def _detached(job: dict) -> bool:
    if job.get('state') not in CANCELLABLE_STATES or job.get('token'):
        return False
    if job.get('state') == 'quarantined' and job.get('recovery_state') in _RUNNING_RECOVERY:
        return False
    return not any(
        isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
        for key in _OPERATOR_INTENTS
    )


def _unlink(tx, job: dict, removed: dict[str, str | None]) -> None:
    """Remove ``job`` from its owner's FIFO so no pull can lease it.

    Only the queue head and a ready predecessor reach a unit; stale ``next``
    links on leased or completed rows are never followed. ``removed`` maps each
    unit already unlinked in this transaction to its own predecessor, because
    the predecessor query reads committed state, not this transaction's writes.
    """
    segment_id = job['segment_id']
    key, priority = job['owner_key'], int(job['priority'])
    queue_key = f'{priority}_{key}'
    queue = tx.get('queues', queue_key)
    if not queue:
        removed[segment_id] = None
        return
    predecessor_id = None
    if queue.get('head') != segment_id:
        found = tx.ready_predecessor(key, priority, segment_id)
        predecessor_id = found['segment_id'] if found else None
        while predecessor_id in removed:
            predecessor_id = removed[predecessor_id]
        if predecessor_id is not None:
            predecessor = tx.get('jobs', predecessor_id)
            if predecessor.get('next') != segment_id:
                predecessor_id = None
    removed[segment_id] = predecessor_id
    following = tx.get('jobs', segment_id).get('next', '')
    if queue.get('head') == segment_id:
        queue['head'] = following
    elif predecessor_id is not None:
        predecessor = tx.get('jobs', predecessor_id)
        predecessor['next'] = following
        tx.put('jobs', predecessor_id, predecessor)
    else:
        return  # Not reachable from the FIFO: nothing can lease it.
    if queue.get('tail') == segment_id:
        queue['tail'] = predecessor_id or ''
    if not queue.get('head'):
        queue.update(head='', tail='', deficit=0.0, continuing=False)
    tx.put('queues', queue_key, queue)


def _fence(tx, uid: str, job_id: str, now: float) -> tuple[CancelResult, tuple[str, ...]]:
    intake = tx.get('intakes', job_id)
    if not intake or intake.get('owner_id') != uid:
        return CancelResult(Outcome.NOT_FOUND), ()
    segments = tuple(intake.get('segment_ids') or ())
    if intake.get('owner_cancelled_at') is not None:
        erased = intake.get('owner_cancel_erased_at') is not None
        paths = tuple(intake.get('raw_capture_paths') or ()) if not erased else ()
        return (
            CancelResult(Outcome.CANCELLED, erasure='complete' if erased else 'pending', archive_paths=paths),
            segments,
        )
    content_id = intake.get('content_id')
    if intake.get('coalesce_group') or not isinstance(content_id, str) or not content_id:
        return CancelResult(Outcome.NOT_CANCELLABLE), ()
    ledger_key = f'{uid}/{content_id}'
    ledger = tx.get('content', ledger_key)
    if _processed(ledger):
        return CancelResult(Outcome.ALREADY_PROCESSED, conversation_ids(ledger.get('result'))), ()
    if ledger and ledger.get('job_id') not in (None, job_id):
        return CancelResult(Outcome.NOT_CANCELLABLE), ()  # another upload owns this content
    jobs = [tx.get('jobs', segment_id) for segment_id in segments]
    present = [job for job in jobs if job]
    for job in present:
        if job.get('owner_id') != uid or job.get('source_alias') or job.get('source_alias_fallback'):
            return CancelResult(Outcome.NOT_CANCELLABLE), ()
        if not _detached(job):
            return CancelResult(Outcome.IN_PROGRESS), ()
    removed: dict[str, str | None] = {}
    holds: dict[str, int] = {}
    for job in present:
        if job['state'] == ALLOWANCE_HELD:
            holds[job['owner_key']] = holds.get(job['owner_key'], 0) + 1
        _unlink(tx, job, removed)
        fenced = tx.get('jobs', job['segment_id'])  # may carry a sibling's relink
        fenced.update(
            state=FENCED_STATE,
            token='',
            lease_until=0.0,
            merge_pending=False,
            next='',
            privacy_blocked_at=now,
            privacy_blocked_reason=BatchPrivacyReason.OWNER_CANCELLED.value,
            owner_cancelled_at=now,
            owner_cancelled_from=job['state'],
        )
        tx.put('jobs', job['segment_id'], fenced)
    for key, count in holds.items():
        hold = tx.get(ALLOWANCE_OWNERS, key)
        if hold:
            hold['held_count'] = max(0, hold.get('held_count', 0) - count)
            hold['active'] = hold['held_count'] > 0
            tx.put(ALLOWANCE_OWNERS, key, hold)
    intake.pop('expires_at', None)
    tx.put('intakes', job_id, {**intake, 'owner_cancelled_at': now})
    if ledger:
        ledger.pop('expires_at', None)
        updated = datetime.fromtimestamp(now, timezone.utc)
        tx.put('content', ledger_key, {**ledger, 'status': LEDGER_STATUS, 'updated_at': updated})
    paths = tuple(intake.get('raw_capture_paths') or ())
    return CancelResult(Outcome.CANCELLED, erasure='pending', archive_paths=paths), segments


def _mark_erased(tx, uid: str, job_id: str, now: float) -> None:
    intake = tx.get('intakes', job_id)
    if not intake or intake.get('owner_id') != uid or intake.get('owner_cancelled_at') is None:
        raise RuntimeError('owner cancellation fence missing')
    if intake.get('owner_cancel_erased_at') is not None:
        return
    expires = datetime.fromtimestamp(now, timezone.utc) + timedelta(days=LEDGER_RETENTION_DAYS)
    ledger_key = f"{uid}/{intake['content_id']}"
    ledger = tx.get('content', ledger_key)
    intake.pop('raw_capture_paths', None)
    tx.put('intakes', job_id, {**intake, 'owner_cancel_erased_at': now, 'expires_at': expires})
    if ledger.get('job_id') == job_id and ledger.get('status') == LEDGER_STATUS:
        tx.put('content', ledger_key, {**ledger, 'expires_at': expires})


def cancel_owner_upload(
    uid: str, job_id: str, *, store, eraser: Eraser, legacy=None, now: float | None = None
) -> CancelResult:
    """Fence then erase one owner upload. Idempotent; see the module docstring.

    A legacy (non-``bp_``) handle goes to ``utils.sync.owner_cancel_legacy`` with the
    ``legacy`` store: its audio sits in cap holds, not batch units.
    """
    if not sync_owner_cancel.enabled():
        raise CancelDisabled('owner cancellation is switched off')
    if job_id.startswith(WAL_HANDOFF_PREFIX):
        return CancelResult(Outcome.NOT_CANCELLABLE)  # live-record handoff: its conversation already exists
    now = time.time() if now is None else now
    if not _handle_shape_ok(job_id):
        from utils.sync import owner_cancel_legacy

        if legacy is None or not owner_cancel_legacy.is_legacy_handle(job_id):
            return CancelResult(Outcome.NOT_FOUND)
        return owner_cancel_legacy.cancel_legacy_upload(uid, job_id, store=legacy, eraser=eraser, now=now)
    result, segments = store.run(lambda tx: _fence(tx, uid, job_id, now))
    if result.outcome is not Outcome.CANCELLED or result.erasure == 'complete':
        logger.info('event=sync_owner_cancel outcome=%s erasure=%s', result.outcome.value, result.erasure)
        return result
    try:
        for segment_id in segments:
            eraser.erase_unit(uid, segment_id)
        eraser.erase_archives(uid, job_id, result.archive_paths)
        store.run(lambda tx: _mark_erased(tx, uid, job_id, now))
    except Exception as error:  # The fence holds; the owner's next call resumes erasure.
        logger.warning(
            'event=sync_owner_cancel outcome=cancelled erasure=pending exception_type=%s', type(error).__name__
        )
        return CancelResult(Outcome.CANCELLED, erasure='pending')
    logger.info('event=sync_owner_cancel outcome=cancelled erasure=complete units=%d', len(segments))
    return CancelResult(Outcome.CANCELLED, erasure='complete')


def cancelled_status(intake: dict, job_id: str) -> dict:
    """Poll/upload answer for a cancelled upload.

    ``failed`` returns custody to any sibling recording that shared the upload
    and was not deleted: it re-uploads on its own, never marked synced. The
    cancelled recording itself has no local copy left to re-upload.
    """
    total = len(intake.get('segment_ids') or ())
    return {
        'job_id': job_id,
        'status': 'failed',
        'lane': intake.get('lane', 'fresh'),
        'total_files': intake.get('total_files', 0),
        'total_segments': total,
        'processed_segments': 0,
        'successful_segments': 0,
        'failed_segments': total,
        'errors': [],
        'result': None,
        'reason_code': REASON_CODE,
        'poll_after_ms': 0,
    }
