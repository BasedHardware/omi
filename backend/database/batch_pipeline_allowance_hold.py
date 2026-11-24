"""Transactional allowance parking for intake, scheduling and migration. No IO at import."""

from dataclasses import dataclass
from datetime import datetime, timezone

from config.policy.kill_switches import kill_switch

STATE = 'allowance_held'
OWNERS = 'allowance_holds'
SWITCH = 'BATCH_ALLOWANCE_PARK_ENABLED'
EXHAUSTED = 'allowance_exhausted'


def enabled() -> bool:
    return kill_switch(SWITCH, log=False)


def intake_enabled() -> bool:
    return enabled() and kill_switch('BATCH_ALLOWANCE_INTAKE_PARK_ENABLED', log=False)


def provider_enabled() -> bool:
    return enabled() and kill_switch('BATCH_ALLOWANCE_PROVIDER_PARK_ENABLED', log=False)


def is_provider(job: dict) -> bool:
    return (job.get('stt_route') or {}).get('stt_route') == 'provider'


def release_fence(owner: dict) -> tuple[str | None, float | None] | None:
    if owner.get('token') or (owner.get('draining') and owner.get('active') is not False):
        return None
    return owner.get('generation'), owner.get('cutoff')


@dataclass(frozen=True)
class IntakeRefusal:
    observed_at: float
    owner_fence: tuple[str | None, float | None]

    def current(self, owner: dict, now: float) -> bool:
        # If a release check crossed the probe, its acknowledged generation
        # could otherwise hide this hold until the next entitlement change.
        return release_fence(owner) == self.owner_fence and datetime.fromtimestamp(
            self.observed_at, timezone.utc
        ).strftime('%Y-%m') == datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m')


def eligible(job: dict) -> bool:
    # A previous sticky hold is NOT authority to park a decisionless refusal.
    decision = job.get('compute_decision') or {}
    return (
        decision.get('outcome') == 'held'
        and decision.get('reason') == EXHAUSTED
        and not job.get('result')
        and not is_provider(job)
    )


def park(tx, job: dict, now: float, *, at_intake: bool = False) -> bool:
    """Accept a detached retry, or an initial row the scheduler has never enqueued."""
    if job.get('state') != ('ready' if at_intake else 'retry'):
        return False
    if at_intake:
        job = {
            **job,
            'next': '',
            'compute_decision': {'outcome': 'held', 'reason': EXHAUSTED, 'at': now},
            'last_policy_hold': {'reason': EXHAUSTED, 'at': now},
        }
    if not eligible(job) or job.get('token') or job.get('lease_until', 0) > now:
        return False
    record_park(tx, job, now)
    return True


def record_park(tx, job: dict, now: float) -> None:
    """Record a caller-validated allowance hold and its owner index entry."""
    key = job['owner_key']
    owner = tx.get(OWNERS, key)
    if not owner:
        owner = {'owner_key': key, 'owner_id': job['owner_id'], 'check_at': now, 'revision': 0}
    if owner.get('draining') and owner.get('active') is False and not owner.get('token'):
        # Older controllers could leave a finished, exactly-full page marked draining.
        owner.update(draining=False, after=None)
    owner.update(active=True, revision=owner['revision'] + 1, check_at=min(now, owner['check_at']))
    owner['held_count'] = owner.get('held_count', 0) + 1
    # Keep an in-progress generation pass/cursor. New holds cannot restart it.
    job.update(state=STATE, merge_pending=False, allowance_held_at=now)
    if 'retry_started_at' in job:
        job['allowance_retry_started_at'] = job.pop('retry_started_at')
    tx.put(OWNERS, key, owner)
    tx.put('jobs', job['segment_id'], job)


def decrement(owner: dict) -> None:
    owner['held_count'] = max(0, owner.get('held_count', 0) - 1)
    owner['active'] = owner['held_count'] > 0


def restore_retry(job: dict, now: float) -> None:
    job.update(state='retry', merge_pending=True, available_at=now, token='', lease_until=0.0)
    if 'allowance_retry_started_at' in job:
        job['retry_started_at'] = job.pop('allowance_retry_started_at')
