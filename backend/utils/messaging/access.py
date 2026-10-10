"""Fail-closed channel admission using the existing subscription authority."""

from config.messaging import cohort_enabled

from database.users import get_user_valid_subscription
from database.account_deletion_marker import get_user_deletion_wipe_status
from models.users import PlanType
from utils.subscription import is_paid_plan


def require_access(uid):
    if not cohort_enabled(uid):
        raise PermissionError('Messaging channels disabled')
    if get_user_deletion_wipe_status(uid) is not None:
        raise PermissionError('Account deletion in progress')
    subscription = get_user_valid_subscription(uid, provision=False)
    if subscription is None or not is_paid_plan(subscription.plan) or subscription.plan != PlanType.architect:
        raise PermissionError('Pro entitlement required')
