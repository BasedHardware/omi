"""Shared quarantine transition and bounded lease-expiry recovery."""

import logging

from config.policy import SchedulerPolicy
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.capture.retry_cap import observe, retry_cap

logger = logging.getLogger(__name__)


def quarantine_job(tx, job: dict, now: float, reason: str) -> None:
    # Serialize pending removal against merge/admission; never invent a result.
    owner = tx.get('owners', job['owner_key'])
    owner['revision'] = owner.get('revision', 0) + 1
    job.update(
        state='quarantined',
        merge_pending=False,
        token='',
        lease_until=0.0,
        failure=reason,
        quarantine_reason=reason,
        quarantined_at=now,
        recovery_state='held',
    )
    job.pop('retry_started_at', None)
    tx.put('owners', job['owner_key'], owner)


def expire_lease(tx, job, now, *, stage_policy, candidates, observations, defer):
    # Off preserves even the legacy policy-read behavior.
    decision = retry_cap(job['owner_id'], 0, 1)
    if decision is not None:
        if decision.serving:
            policy = stage_policy(tx, job, 'scheduler', candidates=candidates, observations=observations)
        else:
            # A legacy unpinned lease must remain unpinned in shadow.
            raw = (job.get('policy_parts') or {}).get('scheduler')
            policy = SchedulerPolicy.from_dict(raw or {})
        decision = retry_cap(job['owner_id'], job['attempt'], policy.max_attempts)
    if decision is not None and decision.reached and decision.serving:
        quarantine_job(tx, job, now, 'worker_failed')
        event = 'quarantined'
    else:
        # refactor: superseded by retry_policy when CAPTURE_COVERAGE_MODE=serve
        defer(job, now, 'lease_expired')
        event = 'lease_expired'
    return event, job['duration_seconds'], decision


def observe_recovery(outcome, metrics) -> None:
    event, seconds, decision = outcome
    observe('scheduler_lease_expiry', decision)
    if event == 'quarantined':
        record_correctness('failed', seconds=seconds)
        logger.error('event=batch_quarantined reason=lease_expired recovery=held')
        logger.warning('event=batch_recovery outcome=held reason=awaiting_fenced_recovery')
    if metrics:
        try:
            metrics.record(event)
            if event == 'quarantined':
                metrics.record('recovery_held')
        except Exception:
            pass
