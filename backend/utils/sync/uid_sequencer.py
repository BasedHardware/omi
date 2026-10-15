"""Dispatch and reconcile accepted backfill jobs without occupying idle workers."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter

from database import sync_backfill_sequencer as registry
from database.sync_jobs import (
    TERMINAL_STATUSES,
    SyncLedgerFenceMode,
    get_sync_job,
    get_sync_ledger_fence_mode,
    sync_job_run_lock_present,
    sync_job_key_exists,
    try_acquire_job_run_lock,
    release_job_run_lock,
)
from utils.cloud_tasks import enqueue_sync_job
from utils.sync import backfill_cutover, stage as sync_stage

logger = logging.getLogger(__name__)
MAX_EXPIRED_RETIREMENTS = 50
EXPIRED_RETIRED = Counter(
    'sync_backfill_expired_retired', 'Expired backfill entries retired without dispatch', ['source']
)


def retire_expired_enabled() -> bool:
    return production_stage() and os.getenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'false').strip().lower() == 'true'


def _retire_expired(uid: str, job_id: str, *, epoch: int | None = None) -> bool:
    # Malformed job JSON must never count as absence. Redis errors propagate.
    if sync_job_key_exists(job_id):
        return False
    token = try_acquire_job_run_lock(job_id)
    if token is None:
        return False
    try:
        if sync_job_key_exists(job_id):
            return False
        retired = registry.retire_expired(uid, job_id, epoch=epoch)
    finally:
        release_job_run_lock(job_id, token)
    if retired:
        source = 'dispatching' if epoch is not None else 'pending'
        EXPIRED_RETIRED.labels(source=source).inc()
        logger.info(
            'event=sync_backfill_expired_retired source=%s outcome=retired',
            source,
            extra={'json_fields': {'event': 'sync_backfill_expired_retired', 'source': source, 'outcome': 'retired'}},
        )
    return retired


def _claim_next(uid: str, *, retire_limit: int = MAX_EXPIRED_RETIREMENTS) -> dict[str, Any] | None:
    if retire_expired_enabled():
        for _ in range(min(MAX_EXPIRED_RETIREMENTS, max(0, retire_limit))):
            head = registry.pending_head(uid)
            if head is None:
                return None
            if not _retire_expired(uid, head['job_id']):
                break
        else:
            # Leave the next head durable for the bounded periodic sweep.
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
    enqueue_sync_job(payload)
    latency = max(0.0, (datetime.now(timezone.utc) - claim['accepted_at']).total_seconds())
    logger.info('event=sync_uid_sequencer action=dispatch outcome=enqueued latency_seconds=%.1f', latency)


def _enqueue_wake(uid: str, uid_hash: str, deadline: int) -> None:
    # Import at dispatch time: isolated legacy sync tests stub only the task
    # functions they exercise, but never execute this cutover path.
    from utils.cloud_tasks import enqueue_sync_uid_wake

    enqueue_sync_uid_wake(uid, uid_hash, deadline)


def kick(uid: str, *, retire_limit: int = MAX_EXPIRED_RETIREMENTS) -> bool:
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
    claim = _claim_next(uid, retire_limit=retire_limit)
    if claim is None:
        return False
    try:
        _dispatch(claim)
    except Exception as error:
        # A named task may exist despite a lost acknowledgement. The periodic
        # reconciler replaces the dispatch epoch; old deliveries then ACK stale.
        logger.error(
            'event=sync_uid_sequencer action=dispatch outcome=uncertain exception_type=%s', type(error).__name__
        )
    return True


def reconcile_uid(
    uid: str, owner: dict[str, Any], *, now: datetime | None = None, retire_limit: int = MAX_EXPIRED_RETIREMENTS
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
        if waiting:
            return 'dispatched' if kick(uid, retire_limit=retire_limit) else 'raced'
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
    if retire_expired_enabled() and state == 'dispatching' and _retire_expired(uid, job_id, epoch=epoch):
        kick(uid, retire_limit=retire_limit)
        return 'expired_retired'
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
    now = datetime.now(timezone.utc)
    outcomes: dict[str, int] = {}
    owners = registry.due_owners(limit=limit, now=now)
    for owner in owners:
        try:
            outcome = reconcile_uid(owner['uid'], owner, now=now, retire_limit=1)
        except Exception as error:
            outcome = 'error'
            logger.error(
                'event=sync_uid_sequencer action=sweep outcome=error job_id=%s uid_hash=%s exception_type=%s',
                owner.get('active_job_id') or 'unknown',
                backfill_cutover.uid_hash(owner['uid']),
                type(error).__name__,
            )
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    pending = registry.due_pending(limit=limit, now=now)
    seen_uids: set[str] = set()
    for job in pending:
        try:
            registry.defer_pending(job['id'], now=now)
            if job['uid'] in seen_uids:
                continue
            seen_uids.add(job['uid'])
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
            if kick(job['uid'], retire_limit=1):
                outcomes['pending_dispatched'] = outcomes.get('pending_dispatched', 0) + 1
        except Exception as error:
            outcomes['error'] = outcomes.get('error', 0) + 1
            logger.error(
                'event=sync_uid_sequencer action=sweep outcome=error job_id=%s uid_hash=%s exception_type=%s',
                job['id'],
                backfill_cutover.uid_hash(job['uid']),
                type(error).__name__,
            )
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
