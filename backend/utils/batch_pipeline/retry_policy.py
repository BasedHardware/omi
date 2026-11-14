"""Shared quarantine transition and bounded lease-expiry recovery."""

import logging

from config.policy import SchedulerPolicy
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.errors import report_terminal_quarantine
from utils.capture.retry_cap import observe, retry_cap

logger = logging.getLogger(__name__)


def quarantine_job(tx, job: dict, now: float, reason: str) -> None:
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
        # The cap's terminal record must carry what this ladder actually
        # collected -- the same preserved evidence the verdict terminal
        # reports -- read before the quarantine transition rewrites the
        # job's custody fields. The evidence rode on the job through every
        # ladder attempt, so a unit whose worker diagnosed a designed
        # handoff and whose leases then expired reaches this terminal with
        # the diagnosis intact.
        terminal = (job['attempt'], job.get('worker_failure_evidence'))
        quarantine_job(tx, job, now, 'worker_failed')
        event = 'quarantined'
    else:
        # refactor: superseded by retry_policy when CAPTURE_COVERAGE_MODE=serve
        terminal = None
        defer(job, now, 'lease_expired')
        event = 'lease_expired'
    return event, job['duration_seconds'], decision, terminal


def observe_recovery(outcome, metrics) -> None:
    event, seconds, decision, terminal = outcome
    observe('scheduler_lease_expiry', decision)
    if event == 'quarantined':
        record_correctness('failed', seconds=seconds)
        # The cap terminal books the same family-aware report as the
        # verdict terminal: a preserved designed-handoff diagnosis demotes
        # to its INFO transition event, a real fault keeps the attributed
        # ERROR carrying the stage/reason the evidence preserved, and the
        # awaiting-recovery warning follows every booking. The bare
        # ``reason=lease_expired`` line this terminal used to book
        # contradicted the ``quarantine_reason='worker_failed'`` the same
        # transition had just written and named no diagnosis at all, so the
        # sensor saw one fault class as two, one of them unattributable.
        attempt, diagnosis = terminal
        report_terminal_quarantine(logger, attempt=attempt, diagnosis=diagnosis)
    if metrics:
        try:
            metrics.record(event)
            if event == 'quarantined':
                metrics.record('recovery_held')
        except Exception:
            pass
