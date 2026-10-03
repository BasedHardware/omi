"""Paid-only conversation mentor admission using the canonical plan resolver."""

import logging

import database.users as users_db
from database._client import get_customer_firestore_client
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def mentor_plan_allows_evaluation(uid: str) -> bool:
    """Paid-only mentor, preserving paid access when plan identification fails.

    Reuse managed-compute plan/alias resolution without BYOK granting this
    company-funded feature. Never provision a subscription or alter frequency.
    The uid-less, fixed-reason log is an aggregate skip/fail-open counter.
    """
    from utils.managed_compute import authorize_managed_compute

    try:
        subscription = users_db.get_user_valid_subscription(
            uid, firestore_client=get_customer_firestore_client(), provision=False
        )
        decision = authorize_managed_compute(uid, 'proactive_notification', 'omi', subscription=subscription)
        if decision.plan_resolved:
            if not decision.allowed:
                logger.info('mentor_plan_admission outcome=skipped reason=basic_not_entitled')
            return decision.allowed
    except Exception:
        pass
    logger.warning('mentor_plan_admission outcome=fail_open reason=plan_lookup_unavailable')
    record_fallback(
        component='firestore_read',
        from_mode='none',
        to_mode='none',
        reason='authorization_unavailable',
        outcome='degraded',
    )
    return True
