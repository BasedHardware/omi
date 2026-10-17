"""Dispatch and reconcile accepted backfill jobs without occupying idle workers."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from prometheus_client import Counter

from database import sync_backfill_sequencer as registry
from database import sync_redrive
from database.sync_jobs import (
    TERMINAL_STATUSES,
    SyncLedgerFenceMode,
    get_sync_job,
    get_sync_ledger_fence_mode,
    mark_job_failed,
    sync_job_run_lock_present,
    sync_job_key_exists,
    try_acquire_job_run_lock,
    release_job_run_lock,
)
from utils.cloud_tasks import enqueue_sync_job, get_sync_tasks_max_attempts
from utils.sync import backfill_cutover, stage as sync_stage
from utils.sync.backfill_order import newest_first

logger = logging.getLogger(__name__)
MAX_EXPIRED_RETIREMENTS = 50
EXPIRED_RETIRED = Counter(
    'sync_backfill_expired_retired', 'Expired backfill entries retired without dispatch', ['source']
)


class _RetirementOutcome(Enum):
    RETIRED = 'retired'
    KEY_PRESENT = 'key_present'
    REFUSED = 'refused'
    LOCK_HELD = 'lock_held'


@dataclass
class _ClaimProgress:
    retired: int = 0
    needs_wake: bool = False


def retire_expired_enabled() -> bool:
    return production_stage() and os.getenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'false').strip().lower() == 'true'


def _retire_expired(
    uid: str, job_id: str, *, epoch: int | None = None, allow_active_owner: bool = False
) -> _RetirementOutcome:
    # Malformed job JSON must never count as absence. Redis errors propagate.
    sync_job_key_exists(job_id)
    token = try_acquire_job_run_lock(job_id)
    if token is None:
        return _RetirementOutcome.LOCK_HELD
    try:
        if sync_job_key_exists(job_id):
            return _RetirementOutcome.KEY_PRESENT
        options: dict[str, Any] = {'allow_active_owner': True} if allow_active_owner else {}
        retired = registry.retire_expired(uid, job_id, epoch=epoch, **options)
    finally:
        release_job_run_lock(job_id, token)
    if retired:
        source = 'dispatching' if epoch is not None else 'pending'
        EXPIRED_RETIRED.labels(source=source).inc()
        logger.info(
            'event=sync_backfill_expired_retired source=%s outcome=retired job_id=%s uid=%s',
            source,
            job_id,
            uid,
            extra={
                'json_fields': {
                    'event': 'sync_backfill_expired_retired',
                    'source': source,
                    'outcome': 'retired',
                    'job_id': job_id,
                    'uid': uid,
                }
            },
        )
    return _RetirementOutcome.RETIRED if retired else _RetirementOutcome.REFUSED


def _claim_next(
    uid: str, *, retire_limit: int = MAX_EXPIRED_RETIREMENTS, progress: _ClaimProgress | None = None
) -> dict[str, Any] | None:
    progress = progress if progress is not None else _ClaimProgress()
    if retire_expired_enabled() or sync_redrive.enabled():
        for _ in range(min(MAX_EXPIRED_RETIREMENTS, max(0, retire_limit))):
            head = registry.pending_head(uid)
            if head is None:
                return None
            outcome = _retire_expired(uid, head['job_id'])
            if outcome is _RetirementOutcome.RETIRED:
                progress.retired += 1
                continue
            if outcome is _RetirementOutcome.KEY_PRESENT:
                claim = registry.claim_next(uid, expected_job_id=head['job_id'])
                progress.needs_wake = claim is None
                return claim
            # A refused transaction or another lock holder must not be
            # bypassed by reserving the protected head or scheduling a wake.
            return None
        progress.needs_wake = True
        return None
    return registry.claim_next(uid)


def production_stage() -> bool:
    """Pure runtime identity check for async route guards."""
    return sync_stage.production_stage()


def production_fence_mode() -> SyncLedgerFenceMode | None:
    """Read the sync fence only for the production delivery path."""
    return get_sync_ledger_fence_mode() if production_stage() else None


def foreign_delivery(payload: Any) -> bool:
    """ACK non-prod sequenced and legacy backfill tasks before shared state access."""
    return (
        sync_stage.nonproduction_stage()
        and isinstance(payload, dict)
        and (payload.get('sequencer_epoch') is not None or payload.get('lane') == 'backfill')
    )


def enabled() -> bool:
    """Pure rollout read, safe on async admission/worker request paths."""
    return registry.enabled()


def _dispatch(claim: dict[str, Any]) -> None:
    payload = {**claim['payload'], 'sequencer_epoch': claim['epoch']}
    enqueue_sync_job(payload, dispatch_attempt=claim.get('dispatch_attempt', 0))
    latency = max(0.0, (datetime.now(timezone.utc) - claim['accepted_at']).total_seconds())
    logger.info('event=sync_uid_sequencer action=dispatch outcome=enqueued latency_seconds=%.1f', latency)


def _enqueue_wake(uid: str, uid_hash: str, deadline: int) -> None:
    # Import at dispatch time: isolated legacy sync tests stub only the task
    # functions they exercise, but never execute this cutover path.
    from utils.cloud_tasks import enqueue_sync_uid_wake

    enqueue_sync_uid_wake(uid, uid_hash, deadline)


def kick(uid: str, *, retire_limit: int = MAX_EXPIRED_RETIREMENTS, progress: _ClaimProgress | None = None) -> bool:
    """Select one pending job and enqueue it; a persisted reservation survives uncertainty."""
    if not registry.production_stage():
        return False
    remaining, direct_job_id = (
        backfill_cutover.quiet_remaining(uid) if enabled() else backfill_cutover.direct_remaining_for_uid(uid)
    )
    if remaining:
        if not registry.has_pending(uid):
            return False
        deadline = int(time.time()) + remaining + 1
        if backfill_cutover.claim_wake(uid, deadline):
            try:
                _enqueue_wake(uid, backfill_cutover.uid_hash(uid), deadline)
            except Exception:
                backfill_cutover.release_wake(uid, deadline)
                raise
        if backfill_cutover.should_log_wait(uid):
            sample = registry.waiting_sample(uid)
            logger.warning(
                'event=sync_uid_sequencer action=cutover_wait outcome=deferred '
                'job_id=%s uid_hash=%s direct_job_id=%s wait_seconds=%d',
                sample['job_id'],
                backfill_cutover.uid_hash(uid),
                direct_job_id or 'unknown',
                remaining,
            )
        return False
    progress = progress if progress is not None else _ClaimProgress()
    claim = _claim_next(uid, retire_limit=retire_limit, progress=progress)
    if claim is None:
        if progress.needs_wake and registry.pending_head(uid) is not None:
            # Stable future bucket deduplicates concurrent kicks. A wake that
            # itself exhausts the budget schedules the following bucket.
            deadline = (int(time.time()) // 5 + 1) * 5
            if backfill_cutover.claim_wake(uid, deadline):
                try:
                    _enqueue_wake(uid, backfill_cutover.uid_hash(uid), deadline)
                except Exception:
                    backfill_cutover.release_wake(uid, deadline)
                    raise
        return False
    try:
        _dispatch(claim)
    except Exception as error:
        # A named task may exist despite a lost acknowledgement. The periodic
        # reconciler retries dispatch with the same epoch so queued work stays valid.
        logger.error(
            'event=sync_uid_sequencer action=dispatch outcome=uncertain exception_type=%s', type(error).__name__
        )
    return True


def _finalize_abandoned_budget_chain_job(job_id: str) -> bool:
    """Terminalize a capped budget-deferral chain's Redis job, conservatively.

    The sweep is about to release the sequencer owner because the chain spent
    its whole attempt contract; ``is_sync_job_stale`` deliberately excludes
    sequenced dispatch, so no status poll can ever finalize it — the client
    would see a nonterminal job until the 24h Redis TTL and the durable
    content claim could not recover through the normal terminal path. Marking
    it failed here is the terminal handoff. Fenced by the run lock's absence:
    a still-held lock means an attempt may be running under the old lease, and
    its own terminal write must win. ``queued`` is accepted alongside
    ``processing`` because the final whole-budget attempt can expire during
    staged-file download or another pre-pipeline step, before the attempt ever
    marked the job processing — that job is exactly as abandoned as the
    processing one, and nothing else will finalize it either.

    Returns whether the terminal state is assured: ``True`` once the job is
    failed, was already terminal, vanished (its own expiry owns recovery), or
    a live run lock names another writer that owns the terminal write;
    ``False`` only for transient Redis read/write failures, which the caller
    must retry before releasing the owner — after the release no sweep
    retains an identity for this job, so a skipped handoff would strand the
    accepted job and its durable claim until the TTL.
    """
    try:
        job = get_sync_job(job_id)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=budget_chain_finalize outcome=read_failed ' 'job_id=%s exception_type=%s',
            job_id,
            type(error).__name__,
        )
        return False
    if not isinstance(job, dict) or job.get('status') in TERMINAL_STATUSES:
        return True
    if job.get('status') not in ('processing', 'queued'):
        return True
    if sync_job_run_lock_present(job_id):
        # An attempt still holds the run lock under the released lease: its
        # own terminal write (or its deferral) must win, never the sweep's.
        logger.warning('event=sync_uid_sequencer action=budget_chain_finalize outcome=lock_held job_id=%s', job_id)
        return True
    try:
        finalized = mark_job_failed(
            job_id,
            'sync budget deferral chain exhausted the attempt contract',
            reason_code='sync_budget_chain_exhausted',
        )
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=budget_chain_finalize outcome=write_failed ' 'job_id=%s exception_type=%s',
            job_id,
            type(error).__name__,
        )
        return False
    if finalized is not None:
        logger.error('event=sync_uid_sequencer action=budget_chain_finalize outcome=failed job_id=%s', job_id)
    else:
        logger.warning('event=sync_uid_sequencer action=budget_chain_finalize outcome=cas_lost job_id=%s', job_id)
    return True


def reconcile_uid(
    uid: str,
    owner: dict[str, Any],
    *,
    now: datetime | None = None,
    retire_limit: int = MAX_EXPIRED_RETIREMENTS,
    progress: _ClaimProgress | None = None,
) -> str:
    if not registry.production_stage():
        return 'disabled'
    current = now or datetime.now(timezone.utc)
    sample = registry.waiting_sample(uid, now=current)
    waiting, oldest_age = sample['depth'], sample['age_seconds']
    logger.info(
        'event=sync_uid_sequencer action=sample outcome=ok queued_depth=%d oldest_waiting_seconds=%.0f active_leases=%d',
        waiting,
        oldest_age,
        int(bool(owner.get('active_job_id'))),
    )
    if oldest_age >= registry.WAIT_ALERT_SECONDS:
        logger.error(
            'event=sync_uid_sequencer action=wait_alert outcome=over_12h '
            'job_id=%s uid_hash=%s queued_depth=%d oldest_waiting_seconds=%.0f',
            sample['job_id'],
            backfill_cutover.uid_hash(uid),
            waiting,
            oldest_age,
        )
    job_id = owner.get('active_job_id')
    if not isinstance(job_id, str) or not job_id:
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        if waiting:
            return 'dispatched' if kick(uid, retire_limit=retire_limit, progress=progress) else 'raced'
        return 'empty'

    epoch = owner.get('active_epoch')
    if not isinstance(epoch, int):
        logger.error(
            'event=sync_uid_sequencer action=sweep outcome=invalid_epoch job_id=%s uid_hash=%s',
            job_id,
            backfill_cutover.uid_hash(uid),
        )
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        return 'invalid'
    state = owner.get('active_state')
    if (retire_expired_enabled() or sync_redrive.enabled()) and state == 'dispatching':
        retirement = _retire_expired(uid, job_id, epoch=epoch)
        if retirement is _RetirementOutcome.RETIRED:
            kick(uid, retire_limit=retire_limit, progress=progress)
            return 'expired_retired'
        if retirement in (_RetirementOutcome.REFUSED, _RetirementOutcome.LOCK_HELD):
            registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
            return retirement.value
    deadline = owner.get('dispatch_retry_at') if state == 'dispatching' else owner.get('lease_expires_at')
    if not isinstance(deadline, datetime) or deadline > current:
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        return 'healthy'

    # A live run lock is stronger evidence than a stale Firestore timestamp.
    # In particular a Cloud Run cancellation can leave an executor leaf alive.
    if sync_job_run_lock_present(job_id):
        logger.warning(
            'event=sync_uid_sequencer action=sweep outcome=run_lock_held job_id=%s uid_hash=%s',
            job_id,
            backfill_cutover.uid_hash(uid),
        )
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        return 'lock_held'
    job = get_sync_job(job_id)
    if job and job.get('status') in TERMINAL_STATUSES:
        outcome = 'terminal_cleanup'
    elif job is None:
        outcome = 'expired_job_cleanup'
    else:
        outcome = 'lease_expired'
    deferrals = owner.get('active_budget_deferrals')
    if (
        outcome == 'lease_expired'
        and isinstance(deferrals, int)
        and not isinstance(deferrals, bool)
        and deferrals + 1 >= get_sync_tasks_max_attempts()
    ):
        # The handler's own bound already refused the next replacement at this
        # count (its final whole-budget run ends through the 409/queue), so a
        # redrive would copy the maxed count into a fresh epoch payload and run
        # another full budget, then redrive again — forever. Backfill allows
        # one in-flight job per UID, so that loop would also block every later
        # capture for this user. Release the owner and dispatch the next
        # waiting capture instead; the deferred job's own marker/lock expiry
        # leaves it to the same recovery as any other abandoned attempt.
        logger.error(
            'event=sync_uid_sequencer action=sweep outcome=budget_chain_exhausted job_id=%s uid_hash=%s deferrals=%d',
            job_id,
            backfill_cutover.uid_hash(uid),
            deferrals,
        )
        # The terminal handoff must be assured BEFORE the owner is released:
        # after release no sweep retains an identity for this job, and status
        # polling cannot stale-finalize sequenced jobs. A transient Redis
        # failure here keeps the owner on the books (deferred one heartbeat)
        # so the next sweep retries the finalize-and-release sequence; only a
        # settled job releases the owner and lets the lane advance to the
        # next waiting capture.
        if not _finalize_abandoned_budget_chain_job(job_id):
            registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
            return 'finalize_deferred'
        if registry.finish_expired_job(uid, job_id, epoch, 'budget_chain_exhausted', now=current):
            # The Redis job is deliberately left nonterminal here only if it
            # is already gone (key absent = retired/expired) — those degrade
            # to the same recovery as any other abandoned attempt.
            kick(uid, retire_limit=retire_limit, progress=progress)
            return 'budget_chain_exhausted'
        return 'raced'
    replacement = registry.redrive_job(uid, job_id, epoch, now=current)
    if replacement is None:
        return 'raced'
    logger.warning(
        'event=sync_uid_sequencer action=sweep outcome=%s job_id=%s uid_hash=%s',
        outcome,
        job_id,
        backfill_cutover.uid_hash(uid),
    )
    try:
        _dispatch(replacement)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=redrive outcome=uncertain exception_type=%s', type(error).__name__
        )
    return outcome


def sweep(*, limit: int = 100) -> dict[str, int]:
    """One bounded Scheduler tick; each UID is independent and transaction-fenced."""
    if not registry.production_stage():
        return {'disabled': 1}
    if sync_redrive.enabled():
        sync_redrive.refresh_metrics()
    now = datetime.now(timezone.utc)
    outcomes: dict[str, int] = {}
    pending_retired = 0
    try:
        owners = registry.due_owners(limit=limit, now=now)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=sweep outcome=due_owners_error exception_type=%s', type(error).__name__
        )
        owners = []
        outcomes['due_owners_error'] = outcomes.get('due_owners_error', 0) + 1
    for owner in owners:
        progress = _ClaimProgress()
        try:
            outcome = reconcile_uid(owner['uid'], owner, now=now, retire_limit=1, progress=progress)
        except Exception as error:
            outcome = 'error'
            logger.error(
                'event=sync_uid_sequencer action=sweep outcome=error job_id=%s uid_hash=%s exception_type=%s',
                owner.get('active_job_id') or 'unknown',
                backfill_cutover.uid_hash(owner['uid']),
                type(error).__name__,
            )
            try:
                registry.defer_owner(owner['uid'], registry.HEARTBEAT_SECONDS, now=now)
            except Exception:
                pass
        pending_retired += progress.retired
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    try:
        pending = registry.due_pending(limit=limit, now=now)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=sweep outcome=due_pending_error exception_type=%s', type(error).__name__
        )
        pending = []
        outcomes['due_pending_error'] = outcomes.get('due_pending_error', 0) + 1
    # Each UID gets one reconcile attempt per tick even when it appears in
    # both scans; pending rows are still deferred to rotate the bounded page.
    seen_uids: set[str] = {owner['uid'] for owner in owners}
    for job in pending:
        progress = _ClaimProgress()
        try:
            registry.defer_pending(job['id'], now=now)
            # Reuse the existing bounded page, independent of newest selection
            # and of this UID's live reservation. Age is only a cheap filter;
            # exact Redis absence, run-lock and ledger proofs still decide.
            accepted_at = job.get('accepted_at')
            if (
                newest_first(job['uid'])
                and (retire_expired_enabled() or sync_redrive.enabled())
                and isinstance(accepted_at, datetime)
                and accepted_at <= now - timedelta(days=1)
            ):
                retirement = _retire_expired(job['uid'], job['job_id'], allow_active_owner=True)
                if retirement is _RetirementOutcome.RETIRED:
                    progress.retired += 1
                    continue
            if job['uid'] in seen_uids:
                continue
            seen_uids.add(job['uid'])
            if registry.repair_owner(job['uid'], now=now):
                outcomes['owner_repaired'] = outcomes.get('owner_repaired', 0) + 1
                continue  # The staggered owner deadline owns this UID's next attempt.
            sample = registry.waiting_sample(job['uid'], now=now)
            if sample['age_seconds'] >= registry.WAIT_ALERT_SECONDS:
                logger.error(
                    'event=sync_uid_sequencer action=wait_alert outcome=over_12h '
                    'job_id=%s uid_hash=%s queued_depth=%d oldest_waiting_seconds=%.0f',
                    sample['job_id'],
                    backfill_cutover.uid_hash(job['uid']),
                    sample['depth'],
                    sample['age_seconds'],
                )
            if kick(job['uid'], retire_limit=1, progress=progress):
                outcomes['pending_dispatched'] = outcomes.get('pending_dispatched', 0) + 1
        except Exception as error:
            outcomes['error'] = outcomes.get('error', 0) + 1
            logger.error(
                'event=sync_uid_sequencer action=sweep outcome=error job_id=%s uid_hash=%s exception_type=%s',
                job['id'],
                backfill_cutover.uid_hash(job['uid']),
                type(error).__name__,
            )

        finally:
            pending_retired += progress.retired
    if pending_retired:
        outcomes['expired_retired'] = outcomes.get('expired_retired', 0) + pending_retired
    logger.info(
        'event=sync_uid_sequencer action=sweep_summary outcome=done '
        'scanned=%d pending_scanned=%d queued_depth=%d active_leases=%d dispatched=%d lease_expired=%d '
        'terminal_cleanup=%d expired_job_cleanup=%d expired_retired=%d lock_held=%d errors=%d',
        len(owners),
        len(pending),
        len(pending),
        sum(bool(owner.get('active_job_id')) for owner in owners),
        outcomes.get('dispatched', 0),
        outcomes.get('lease_expired', 0),
        outcomes.get('terminal_cleanup', 0),
        outcomes.get('expired_job_cleanup', 0),
        outcomes.get('expired_retired', 0),
        outcomes.get('lock_held', 0),
        outcomes.get('error', 0),
    )
    return outcomes
