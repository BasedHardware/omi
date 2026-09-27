"""Dispatch and reconcile accepted backfill jobs without occupying idle workers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from database import sync_backfill_sequencer as registry
from database.sync_jobs import TERMINAL_STATUSES, get_raw_sync_job, sync_job_run_lock_present
from utils.cloud_tasks import enqueue_sync_job

logger = logging.getLogger(__name__)


def enabled() -> bool:
    """Pure rollout read, safe on async admission/worker request paths."""
    return registry.enabled()


def _dispatch(claim: dict[str, Any]) -> None:
    payload = {**claim['payload'], 'sequencer_epoch': claim['epoch']}
    enqueue_sync_job(payload)
    latency = max(0.0, (datetime.now(timezone.utc) - claim['accepted_at']).total_seconds())
    logger.info('event=sync_uid_sequencer action=dispatch outcome=enqueued latency_seconds=%.1f', latency)


def kick(uid: str) -> bool:
    """Select one pending job and enqueue it; a persisted reservation survives uncertainty."""
    claim = registry.claim_next(uid)
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


def reconcile_uid(uid: str, owner: dict[str, Any], *, now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    waiting = int(owner.get('pending_count') or 0)
    oldest_age = registry.oldest_waiting_age_seconds(uid, now=current) if waiting else 0.0
    logger.info(
        'event=sync_uid_sequencer action=sample outcome=ok queued_depth=%d oldest_waiting_seconds=%.0f active_leases=%d',
        waiting,
        oldest_age,
        int(bool(owner.get('active_job_id'))),
    )
    if oldest_age >= registry.WAIT_ALERT_SECONDS:
        logger.error(
            'event=sync_uid_sequencer action=wait_alert outcome=over_12h queued_depth=%d oldest_waiting_seconds=%.0f',
            waiting,
            oldest_age,
        )
    job_id = owner.get('active_job_id')
    if not isinstance(job_id, str) or not job_id:
        if waiting:
            return 'dispatched' if kick(uid) else 'raced'
        return 'empty'

    epoch = owner.get('active_epoch')
    if not isinstance(epoch, int):
        logger.error('event=sync_uid_sequencer action=sweep outcome=invalid_epoch')
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        return 'invalid'
    state = owner.get('active_state')
    deadline = owner.get('dispatch_retry_at') if state == 'dispatching' else owner.get('lease_expires_at')
    if not isinstance(deadline, datetime) or deadline > current:
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        return 'healthy'

    # A live run lock is stronger evidence than a stale Firestore timestamp.
    # In particular a Cloud Run cancellation can leave an executor leaf alive.
    if sync_job_run_lock_present(job_id):
        logger.warning('event=sync_uid_sequencer action=sweep outcome=run_lock_held')
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        return 'lock_held'
    job = get_raw_sync_job(job_id)
    if job and job.get('status') in TERMINAL_STATUSES:
        outcome = 'terminal_cleanup'
    elif job is None:
        outcome = 'expired_job_cleanup'
    else:
        outcome = 'lease_expired'
    replacement = registry.redrive_job(uid, job_id, epoch, now=current)
    if replacement is None:
        return 'raced'
    logger.warning('event=sync_uid_sequencer action=sweep outcome=%s', outcome)
    try:
        _dispatch(replacement)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=redrive outcome=uncertain exception_type=%s', type(error).__name__
        )
    return outcome


def sweep(*, limit: int = 100) -> dict[str, int]:
    """One bounded Scheduler tick; each UID is independent and transaction-fenced."""
    now = datetime.now(timezone.utc)
    outcomes: dict[str, int] = {}
    owners = registry.due_owners(limit=limit, now=now)
    for owner in owners:
        try:
            outcome = reconcile_uid(owner['uid'], owner, now=now)
        except Exception as error:
            outcome = 'error'
            logger.error('event=sync_uid_sequencer action=sweep outcome=error exception_type=%s', type(error).__name__)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    logger.info(
        'event=sync_uid_sequencer action=sweep_summary outcome=done '
        'scanned=%d queued_depth=%d active_leases=%d dispatched=%d lease_expired=%d '
        'terminal_cleanup=%d expired_job_cleanup=%d lock_held=%d errors=%d',
        len(owners),
        sum(int(owner.get('pending_count') or 0) for owner in owners),
        sum(bool(owner.get('active_job_id')) for owner in owners),
        outcomes.get('dispatched', 0),
        outcomes.get('lease_expired', 0),
        outcomes.get('terminal_cleanup', 0),
        outcomes.get('expired_job_cleanup', 0),
        outcomes.get('lock_held', 0),
        outcomes.get('error', 0),
    )
    return outcomes
