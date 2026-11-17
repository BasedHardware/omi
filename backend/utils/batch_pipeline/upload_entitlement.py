"""CPU intake entitlement lookup, separate from worker-safe metric collectors."""

from database import users
from utils import subscription

import math


def subscription_policy():
    return users, subscription


def classify(uid):
    """Same effective plan/reviewer/probe rules as allowance, without usage reads.

    Current Subscription has no trial status (desktop trials are retired).
    A trial status, if supplied by an entitlement adapter, is always protected.
    Never infer free from a lookup error, an exempt user, or an unknown plan.
    """
    try:
        users, policy = subscription_policy()
        if not uid or policy.is_marketplace_reviewer(uid) or uid == policy.RELEASE_PROBE_UID:
            return 'unknown'
        subscription = users.get_user_valid_subscription(uid, provision=False)
        if subscription is None:
            return 'unknown'
        if getattr(subscription.status, 'value', subscription.status) == 'trialing':
            return 'trial'
        if policy.is_paid_plan(subscription.plan):
            return 'paid'
        if getattr(subscription.plan, 'value', subscription.plan) == 'basic':
            allowance = policy.transcription_allowance_seconds(subscription.plan)
            if type(allowance) in (int, float) and math.isfinite(allowance) and allowance >= 0:
                return 'free'
    except Exception:
        pass
    return 'unknown'
