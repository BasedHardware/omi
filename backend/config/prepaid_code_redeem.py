"""Switch for redeeming a fully prepaid Omi Pro code without a card. Pure module: stdlib only.

``PREPAID_CODE_REDEEM=on`` admits everyone; any other value (default off) admits only members of
the ``prepaid-code-redeem`` rollout cohort document. Env is read at call time.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from config import rollout_cohorts

ENV = 'PREPAID_CODE_REDEEM'
ROLLOUT_COHORT = 'prepaid-code-redeem'
# Stripe subscription metadata on a no-card prepaid subscription.
SUBSCRIPTION_MARKER = 'prepaid_code_redemption'


def enabled_for(uid: Optional[str], environ: Optional[Mapping[str, str]] = None) -> bool:
    if not isinstance(uid, str) or not rollout_cohorts.valid_uid(uid):
        return False
    env = os.environ if environ is None else environ
    if (env.get(ENV) or '').strip().lower() == 'on':
        return True
    try:
        return rollout_cohorts.in_rollout_cohort(uid, ROLLOUT_COHORT)
    except Exception:
        # Unknown membership keeps today's behaviour.
        return False


def is_prepaid_subscription(stripe_sub: object) -> bool:
    """A no-card prepaid subscription. Plan changes and reactivation must never touch it: without a
    card, any change that outlives the code would end in a failed charge."""
    metadata = (stripe_sub.get('metadata') if isinstance(stripe_sub, Mapping) else None) or {}
    return isinstance(metadata, Mapping) and metadata.get(SUBSCRIPTION_MARKER) == '1'


def prepaid_end(stripe_sub: object) -> Optional[int]:
    """When a prepaid no-card subscription ends (its ``cancel_at``); None for every other subscription.
    Clients show this as the end date instead of a monthly renewal that will never be charged."""
    if not is_prepaid_subscription(stripe_sub):
        return None
    cancel_at = stripe_sub.get('cancel_at')  # type: ignore[union-attr]  # Mapping checked above
    return cancel_at if isinstance(cancel_at, int) and not isinstance(cancel_at, bool) else None
