"""Shared quarantine transition and bounded lease-expiry recovery."""

import logging

from config.batch_pipeline import batch_held_dead_letter_enabled, HELD_DEAD_LETTER_SECONDS

from config.policy import SchedulerPolicy
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.errors import validate_worker_failure
from utils.capture.retry_cap import observe, retry_cap

logger = logging.getLogger(__name__)


def quarantine_job(
    tx, job: dict, now: float, reason: str, *, lease_expired: bool = False, worker_failure: dict | None = None
) -> None:
    if worker_failure is not None:
        validate_worker_failure(worker_failure)
    # Preserve the durable audio and any existing artifact references for
    # operator recovery; quarantine never deletes encrypted source material.
    # Lease expiry/decode failures may never have reached VAD. Keep unknown
    # explicit so observers cannot mistake absent evidence for measured silence.
    job.setdefault('measured_held_vad_speech_seconds', None)
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
    # Keep the legacy evidence for operator consumers. The diagnostic below
    # describes the current quarantine independently of earlier attempts.
    if worker_failure is not None:
        job['worker_failure'] = dict(worker_failure)
    diagnostic = {
        'exception_class': 'unknown',
        'stage': 'unknown',
        'worker_reason': 'unknown',
        'provider_error': 'unknown',
        'artifact_kind': 'unknown',
    }
    if lease_expired:
        diagnostic.update(exception_class='lease_expired', stage='scheduler')
    elif worker_failure is not None:
        diagnostic.update(
            exception_class='worker_validation', stage=worker_failure['stage'], worker_reason=worker_failure['reason']
        )
    job['quarantine_diagnostic'] = diagnostic
    job.pop('retry_started_at', None)
    if batch_held_dead_letter_enabled():
        job['held_deadline_at'] = now + HELD_DEAD_LETTER_SECONDS
    tx.put('owners', job['owner_key'], owner)


def expire_lease(tx, job, now, *, stage_policy, candidates, observations, defer):
    # Off preserves even the legacy policy-read behavior.
    decision = retry_cap(job['owner_id'], 0, 1, enforce=True)
    if decision is not None:
        if decision.serving:
            policy = stage_policy(tx, job, 'scheduler', candidates=candidates, observations=observations)
        else:
            # A legacy unpinned lease must remain unpinned in shadow.
            raw = (job.get('policy_parts') or {}).get('scheduler')
            policy = SchedulerPolicy.from_dict(raw or {})
        decision = retry_cap(job['owner_id'], job['attempt'], policy.max_attempts, enforce=True)
    if decision is not None and decision.reached and decision.serving:
        quarantine_job(tx, job, now, 'worker_failed', lease_expired=True)
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
