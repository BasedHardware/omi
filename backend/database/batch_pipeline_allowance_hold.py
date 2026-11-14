"""Transactional allowance parking shared by scheduling and migration. No IO at import."""

from config.policy.kill_switches import kill_switch

STATE = 'allowance_held'
OWNERS = 'allowance_holds'
SWITCH = 'BATCH_ALLOWANCE_PARK_ENABLED'


def enabled() -> bool:
    return kill_switch(SWITCH, log=False)


def eligible(job: dict) -> bool:
    # A previous sticky hold is NOT authority to park a decisionless refusal.
    decision = job.get('compute_decision') or {}
    return (
        decision.get('outcome') == 'held'
        and decision.get('reason') == 'allowance_exhausted'
        and not job.get('result')
        and (job.get('stt_route') or {}).get('stt_route') != 'provider'
    )


def park(tx, job: dict, now: float) -> bool:
    """Caller has revoked/refunded a lease or CAS-read a detached retry row."""
    if job.get('state') != 'retry' or not eligible(job) or job.get('token') or job.get('lease_until', 0) > now:
        return False
    key = job['owner_key']
    owner = tx.get(OWNERS, key)
    if not owner:
        owner = {'owner_key': key, 'owner_id': job['owner_id'], 'check_at': now, 'revision': 0}
    owner.update(active=True, revision=owner['revision'] + 1, check_at=min(now, owner['check_at']))
    owner['held_count'] = owner.get('held_count', 0) + 1
    # Keep an in-progress generation pass/cursor. New holds cannot restart it.
    job.update(state=STATE, merge_pending=False, allowance_held_at=now)
    if 'retry_started_at' in job:
        job['allowance_retry_started_at'] = job.pop('retry_started_at')
    tx.put(OWNERS, key, owner)
    tx.put('jobs', job['segment_id'], job)
    return True


def restore_retry(job: dict, now: float) -> None:
    job.update(state='retry', merge_pending=True, available_at=now, token='', lease_until=0.0)
    if 'allowance_retry_started_at' in job:
        job['retry_started_at'] = job.pop('allowance_retry_started_at')
