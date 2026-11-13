"""UID-first, at-most-once admission. Existing enrollment is the only roster.

An enrollment is consumed even if its response is lost. Never retry delivery:
intention-to-treat includes admitted readers who never rendered the placement.
No payer inference, new identity key, collection, or billing mutation lives here.
"""

import os
from datetime import datetime, timedelta, timezone

from utils import experiments

EXPERIMENT_ID = 'EXP-006-yearly-switch-retention'
ENGAGED_CAPTURES = 8
WINDOW_DAYS = 14


def enabled() -> bool:
    """Default-on kill switch, behind explicit approval and rollout gates."""
    return (
        os.getenv('YEARLY_SWITCH_RETENTION_ENABLED', 'true').strip().lower() != 'false'
        and bool(os.getenv('YEARLY_SWITCH_RETENTION_APPROVAL_REF', '').strip())
        and os.getenv('YEARLY_SWITCH_RETENTION_ROLLOUT_AUTHORIZED', '').strip().lower() == 'true'
    )


def erase_assignment(uid: str, client) -> None:
    # A failed erase propagates into the existing retryable account wipe.
    client.collection('experiments').document(EXPERIMENT_ID).collection('assignments').document(uid).delete()


def admit(uid: str, placement: str, *, count_captures, blocked, client=None, now=None) -> bool:
    if placement not in {'cancel', 'engaged'} or not enabled() or blocked():
        return False
    if client is None:
        from database._client import get_firestore_client

        client = get_firestore_client()
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=WINDOW_DAYS)
    count = None
    if placement == 'engaged':
        count = count_captures(start, now)
        if count < ENGAGED_CAPTURES:
            return False
    enrollment = experiments.enroll(
        experiment_id=EXPERIMENT_ID,
        uid=uid,
        eligibility={
            'placement': placement,
            'predicate_version': 1,
            'completed_saved_captures': count,
            'window_start': start,
            'window_end': now,
        },
        source=placement,
        firestore_client=client,
    )
    # Fence a deletion that began while enrollment was in flight. Its marker
    # survives user-subtree erasure. Do not recreate an erased roster row.
    if blocked():
        erase_assignment(uid, client)
        return False
    return bool(enrollment and enrollment.newly_enrolled and enrollment.is_treatment and enabled())
