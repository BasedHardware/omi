"""Pure retained-hold classification shared by merge and partial projection."""

from config.policy import RecoveryPolicy

# A reviewed operator intent that is not settled can still change its unit.
OPERATOR_INTENTS = ('speech_redrive', 'terminal_disposition', 'silence_disposition')

# Refusal reason shared by the hold writer and the automatic-redrive guards.
RETAINED_DIGEST_CHANGED = 'retained_digest_changed'


def retained_digest_changed_held(job: dict) -> bool:
    """The unit's input settled after a repeatable pinned-source digest disagreement.

    Its source cannot be re-read into the original manifest, so automatic
    maintenance must not requeue it; a reviewed operator redrive still can.
    """
    if job.get('recovery_state') != 'failed_held':
        return False
    recovery = job.get('recovery')
    if not isinstance(recovery, dict):
        return False
    refusal = recovery.get('refusal')
    return isinstance(refusal, dict) and refusal.get('reason') == RETAINED_DIGEST_CHANGED


def held_without_recovery(job: dict) -> bool:
    """A quarantined unit that nothing automatic will change.

    Its recovery settled without words or hit the hard independent duration
    limit before spending (``failed_held``), or its
    recorded recovery policy is off and no paid call was ever authorized. Either
    way its encrypted audio stays server-side for a reviewed operator redrive.
    """
    retained_dead = job.get('state') == 'dead' and job.get('dead_letter_reason') in {'held_expired', 'input_expiring'}
    if (job.get('state') != 'quarantined' and not retained_dead) or job.get('result'):
        return False
    if any(
        isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
        for key in OPERATOR_INTENTS
    ):
        return False
    if retained_dead or job.get('recovery_state') == 'failed_held':
        return True
    raw = (job.get('policy_parts') or {}).get('recovery')
    return (
        job.get('recovery_state') == 'held'
        and not job.get('recovery')
        and isinstance(raw, dict)
        and not RecoveryPolicy.from_dict(raw).recovery_enabled
    )
