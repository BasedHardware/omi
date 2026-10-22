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
    FencedSyncJobMutationOutcome,
    SyncLedgerFenceMode,
    get_sync_job,
    get_sync_ledger_fence_mode,
    fenced_mark_job_failed,
    sync_job_run_lock_present,
    sync_job_key_exists,
    sync_job_uses_ledger_fence,
    try_acquire_job_run_lock,
    try_acquire_sync_job_run_lock,
    release_job_run_lock,
    delete_sync_job_run_lock_epoch,
)
from database.sync_ledger import release_sync_content_claim_after_job_retired
from utils.cloud_tasks import enqueue_sync_job, get_sync_tasks_max_attempts
from utils.sync import backfill_cutover, legacy_dark, stage as sync_stage
from utils.sync.backfill import release_backfill_slot
from utils.sync.backfill_order import newest_first
from utils.sync.ledger_completion import bind_or_converge_sync_ledger_completion

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
    if not legacy_dark.sequencer_dispatch_allowed():
        # Legacy-dark: ``dark`` claims and dispatches nothing (contract (h)).
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


def _converge_capped_ledger_completion(*, job_id: str, uid: Any, content_id: Any, run_lock_token: str) -> Any:
    """Resolve a capped fenced job's durable content ledger before failure.

    Budget cancellation can land after a detached pipeline leaf has durably
    completed the content ledger but before the matching Redis terminal
    write; failing such a job unconditionally would dead-letter transcription
    whose side effects already committed. ``bind_or_converge_sync_ledger_completion``
    converges exactly that ordering (it is the same helper the final-attempt
    exception path uses). Kept as a named wrapper over the module-scope
    import from ``utils.sync.ledger_completion`` — the lightweight top-level
    seam that keeps this module importable without the pipeline's heavy
    dependency graph; tests monkeypatch this wrapper directly.
    """
    return bind_or_converge_sync_ledger_completion(
        job_id=job_id, uid=uid, content_id=content_id, run_lock_token=run_lock_token
    )


def _finalize_abandoned_budget_chain_job(
    uid: str,
    job_id: str,
    epoch: int,
    *,
    now: datetime | None = None,
    failure_message: str = 'sync budget deferral chain exhausted the attempt contract',
    reason_code: str = 'sync_budget_chain_exhausted',
) -> bool:
    """Terminalize a capped dispatch or budget chain conservatively.

    Sequenced jobs are excluded from stale polling, so the sweep must assure
    terminal state and cleanup before releasing their owner. Both queued and
    processing jobs can be abandoned before the handler publishes a result.

    The handoff is fenced by *acquiring* the run lock atomically rather than
    checking it and writing later: a final replacement that acquires between
    the check and the terminal write would be racing an unfenced
    ``mark_job_failed``, and treating a live nonterminal writer as a
    successful handoff releases the owner while the old attempt still runs —
    if that attempt then times out it returns 409 without terminalizing and
    no owner remains to recover the job. An unacquirable lock therefore
    retains the owner (the next sweep re-checks); the lock's own holder keeps
    the right to its terminal write or deferral.

    Returns whether the terminal state is assured: ``True`` once the job is
    failed, converged to a durably completed result, was already terminal, or
    vanished (its own expiry owns recovery); ``False`` when the owner must be
    retained — a still-live deferred marker (the final scheduled replacement
    has not run yet), a lock another writer holds, an owner whose lease a
    final replacement renewed after the sweeper's expired read, or a
    transient Redis read/write failure — which the caller must retry before
    releasing the owner, because after the release no sweep retains an
    identity for this job and a skipped handoff would strand the accepted
    job and its durable claim until the TTL.
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
    if not isinstance(job, dict):
        return True
    if job.get('status') in TERMINAL_STATUSES:
        # Already terminal — the final replacement's own handler path (which
        # performs this exact cleanup), or a prior sweep's converged handoff
        # whose cleanup failed and retained the owner. Run the cleanup again:
        # every step compares against this exact job, so a completed cleanup
        # is inert while a failed one gets its retry here.
        return _cleanup_capped_chain_job_side_effects(
            job, release_claim=job.get('status') in ('failed', 'partial_failure')
        )
    if job.get('status') not in ('processing', 'queued'):
        return True
    # A still-future deferred_until marker means the chain's final scheduled
    # replacement has not run yet: the persisted count denotes a successfully
    # enqueued next attempt, not a completed one, and the replacement is
    # deliberately delayed past this lease (RUN_LOCK_TTL + 60s) — so the sweep
    # normally lands here first. Terminalizing now would make that already
    # paid-for final delivery a stale epoch the moment the lane advances.
    # Sequenced jobs are exempt from stale polling, so nothing else would ever
    # finalize the job: keep the owner and re-check after the marker horizon.
    # This check precedes the run-lock acquire on purpose — the marker's live
    # replacement must be able to take the lock when it arrives, and a capped
    # attempt can no longer defer to re-arm the chain.
    raw_marker = job.get('deferred_until')
    marker_until = (
        float(raw_marker) if isinstance(raw_marker, (int, float)) and not isinstance(raw_marker, bool) else None
    )
    if marker_until is not None and time.time() < marker_until:
        logger.info(
            'event=sync_uid_sequencer action=budget_chain_finalize outcome=replacement_pending job_id=%s', job_id
        )
        return False
    job_uses_fence = sync_job_uses_ledger_fence(job)
    acquire_final_lock = try_acquire_sync_job_run_lock if job_uses_fence else try_acquire_job_run_lock
    try:
        lock_token = acquire_final_lock(job_id)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=budget_chain_finalize outcome=acquire_failed '
            'job_id=%s exception_type=%s',
            job_id,
            type(error).__name__,
        )
        return False
    if lock_token is None:
        # An attempt still holds the run lock under the released lease: its
        # own terminal write (or its deferral) must win, never the sweep's —
        # and if that attempt times out it ends through the queue while this
        # owner keeps an identity on the job, so the chain cannot strand.
        # Retain the owner; the next sweep re-checks after the lock's TTL.
        logger.warning('event=sync_uid_sequencer action=budget_chain_finalize outcome=lock_held job_id=%s', job_id)
        return False
    # The final replacement can begin after its marker horizon while still
    # queued behind the lane's concurrency cap: it renews the Firestore lease
    # in begin_job after the sweep's expired-owner read but before its Redis
    # acquire, so this finalization lock can be acquired in that gap. Its
    # later finish_expired_job correctly refuses to release the renewed
    # owner, but it cannot undo a failure already published against the
    # live attempt. Re-check the release fence the sweeper acted on — the
    # owner must still name this job/epoch with its lease (or dispatch
    # retry) deadline past — before writing any terminal state; a renewal
    # retains the owner so the replacement's own terminal write decides.
    # The recheck runs inside the lock-release try/finally: both of its
    # early returns (recheck failure, owner renewed) must drop the lock they
    # hold, or its TTL outlives the renewed replacement's whole attempt
    # contract and the one-in-flight UID lane stays blocked past every
    # queue retry.
    try:
        try:
            release_due = registry.owner_release_due(uid, job_id, epoch, now=now)
        except Exception as error:
            logger.error(
                'event=sync_uid_sequencer action=budget_chain_finalize outcome=fence_recheck_failed '
                'job_id=%s exception_type=%s',
                job_id,
                type(error).__name__,
            )
            return False
        if not release_due:
            logger.info('event=sync_uid_sequencer action=budget_chain_finalize outcome=owner_renewed job_id=%s', job_id)
            return False
        # A fence job may have durably completed its content ledger after
        # budget cancellation cancelled the await but before the terminal
        # write: converge that proven completion into the Redis result before
        # publishing a failure, exactly like the handler's final-attempt
        # exception path. Only a fence job carries a content ledger.
        if job_uses_fence:
            try:
                converged = _converge_capped_ledger_completion(
                    job_id=job_id,
                    uid=job.get('uid'),
                    content_id=job.get('content_id'),
                    run_lock_token=lock_token,
                )
            except Exception as error:
                logger.error(
                    'event=sync_uid_sequencer action=budget_chain_finalize outcome=ledger_converge_failed '
                    'job_id=%s exception_type=%s',
                    job_id,
                    type(error).__name__,
                )
                return False
            if converged is not None:
                logger.info(
                    'event=sync_uid_sequencer action=budget_chain_finalize outcome=ledger_converged job_id=%s', job_id
                )
                # The converged completion is the terminal state the redelivery
                # branches would own: finish their exact-job cleanup before the
                # caller can release the owner. A completed content's claim
                # persists as the re-upload dedupe, mirroring those branches.
                converged_status = converged.get('status') if isinstance(converged, dict) else None
                if not _cleanup_capped_chain_job_side_effects(
                    job, release_claim=converged_status in ('failed', 'partial_failure')
                ):
                    return False
                return True
        try:
            mutation = fenced_mark_job_failed(
                job_id,
                lock_token,
                failure_message,
                reason_code=reason_code,
            )
        except Exception as error:
            logger.error(
                'event=sync_uid_sequencer action=budget_chain_finalize outcome=write_failed '
                'job_id=%s exception_type=%s',
                job_id,
                type(error).__name__,
            )
            return False
        if mutation.applied:
            logger.error('event=sync_uid_sequencer action=budget_chain_finalize outcome=failed job_id=%s', job_id)
            # The sweep is now this failure's only cleanup owner: run the
            # terminal branch's exact-job cleanup (slot, claim, run-lock epoch)
            # before the caller releases the sequencer owner, so the lane and
            # the content's re-upload path do not stay blocked past this sweep.
            if not _cleanup_capped_chain_job_side_effects(job, release_claim=True):
                return False
            return True
        if mutation.outcome in (
            FencedSyncJobMutationOutcome.MISSING_JOB,
            FencedSyncJobMutationOutcome.INVALID_JOB,
        ):
            # Vanished or corrupt: its own expiry owns recovery from here.
            return True
        # CAS lost: the terminal write did not apply while the job read
        # nonterminal. Accept only a re-read that proves terminality or absence —
        # releasing the owner on a lost CAS would strand the accepted job (no
        # sweep identity remains, polls never stale-finalize sequenced jobs)
        # until the Redis TTL despite the claimed handoff.
        try:
            settled = get_sync_job(job_id)
        except Exception as error:
            logger.error(
                'event=sync_uid_sequencer action=budget_chain_finalize outcome=cas_verify_failed '
                'job_id=%s exception_type=%s',
                job_id,
                type(error).__name__,
            )
            return False
        if isinstance(settled, dict) and settled.get('status') not in TERMINAL_STATUSES:
            logger.warning(
                'event=sync_uid_sequencer action=budget_chain_finalize outcome=cas_lost_nonterminal job_id=%s', job_id
            )
            return False
        logger.warning('event=sync_uid_sequencer action=budget_chain_finalize outcome=cas_lost job_id=%s', job_id)
        # Another writer terminalized the job between the lost CAS and this
        # re-read: its own path performs the exact-job cleanup, but it has no
        # obligation to run before this sweep releases the owner — run the
        # cleanup here too; idempotence makes the overlap inert.
        if not _cleanup_capped_chain_job_side_effects(
            settled if isinstance(settled, dict) else job,
            release_claim=(
                settled.get('status') in ('failed', 'partial_failure') if isinstance(settled, dict) else True
            ),
        ):
            return False
        return True
    finally:
        # The finalization lock protects nothing past this helper: the job is
        # terminal (or the sweep retains the owner for a retry, and any racing
        # capped replacement only 409-caps against the lock). Best-effort
        # release; a lost release keeps the lock until its TTL.
        try:
            release_job_run_lock(job_id, lock_token)
        except Exception:
            pass


def _cleanup_capped_chain_job_side_effects(job: dict, *, release_claim: bool) -> bool:
    """Release a capped chain's per-UID slot and durable content claim.

    The terminal branch of a redelivery performs this exact-job cleanup for
    every terminal transition, but the capped chain's handoff releases the
    sequencer owner with no later terminal poll — sequenced jobs are exempt
    from stale polling and the task's attempt contract is spent — so nothing
    else runs it: the backfill slot would hold the UID's lane for its ~2-day
    TTL and re-uploading the same content would deflect off the ledger claim
    until its 45-day TTL. Every step is idempotent (compare-and-delete
    semantics against the exact job), so a partially completed cleanup
    retries safely on the next sweep; ``False`` keeps the owner on the books
    for exactly that retry. ``release_claim`` carries the settled status
    decision — a completed content's claim deliberately persists as the
    re-upload dedupe, mirroring the redelivery branches. A job dict without
    a uid has no exact identity to clean (corrupt read): nothing to do.
    """
    uid = job.get('uid')
    if not isinstance(uid, str) or not uid:
        logger.info('event=sync_uid_sequencer action=budget_chain_finalize outcome=cleanup_skipped_no_identity')
        return True
    job_id = job.get('job_id')
    if not isinstance(job_id, str) or not job_id:
        logger.info('event=sync_uid_sequencer action=budget_chain_finalize outcome=cleanup_skipped_no_identity')
        return True
    try:
        if job.get('lane') == 'backfill':
            release_backfill_slot(uid, job_id)
        content_id = job.get('content_id')
        if content_id and release_claim:
            release_sync_content_claim_after_job_retired(uid, content_id, job_id)
        if sync_job_uses_ledger_fence(job):
            delete_sync_job_run_lock_epoch(job_id)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=budget_chain_finalize outcome=side_effect_cleanup_failed '
            'job_id=%s exception_type=%s',
            job_id,
            type(error).__name__,
        )
        return False
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
    from utils.sync.retry_hygiene import reconcile_dispatch_cap

    capped = reconcile_dispatch_cap(
        uid,
        owner,
        epoch,
        current,
        registry=registry,
        finalize=_finalize_abandoned_budget_chain_job,
        kick=lambda: kick(uid, retire_limit=retire_limit, progress=progress),
    )
    if capped is not None:
        return capped
    deferrals = owner.get('active_budget_deferrals')
    if (
        outcome == 'lease_expired'
        and isinstance(deferrals, int)
        and not isinstance(deferrals, bool)
        and deferrals + 1 >= get_sync_tasks_max_attempts()
    ):
        # A spent budget chain must terminalize before its owner is released.
        logger.error(
            'event=sync_uid_sequencer action=sweep outcome=budget_chain_exhausted job_id=%s uid_hash=%s deferrals=%d',
            job_id,
            backfill_cutover.uid_hash(uid),
            deferrals,
        )
        if not _finalize_abandoned_budget_chain_job(uid, job_id, epoch, now=current):
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
    if not legacy_dark.sequencer_dispatch_allowed():
        return {'legacy_dark': 1}
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
