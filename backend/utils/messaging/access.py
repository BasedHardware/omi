"""Fail-closed channel admission using the existing subscription authority."""

import os
import time
import threading

from config.messaging import cohort_enabled, channel_policy

from database.users import get_user_valid_subscription
from database.account_deletion_marker import get_user_deletion_wipe_status
from database.account_deletion_policy import account_deletion_blocks_access
from utils.subscription import is_paid_plan


class AccessDenied(PermissionError):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


class SeatFull(AccessDenied):
    def __init__(self):
        super().__init__('seat_cap', 'iMessage is full — join the waitlist')


_kill_cache = {}
_kill_lock = threading.Lock()


def remote_enabled(channel):
    """Optional content-free operator switch; failures deny, cache lifetime <=60s."""
    path = os.getenv('OMI_MESSAGING_KILL_SWITCH_DOC')
    if not path:
        return True
    with _kill_lock:
        cache = _kill_cache.get(path)
        if cache is None or time.monotonic() - cache[0] >= 60:
            from database._client import get_firestore_client

            try:
                row = get_firestore_client().document(path).get().to_dict() or {}
            except Exception:
                row = {}
            cache = (time.monotonic(), row)
            _kill_cache[path] = cache
        return cache[1].get(channel) is True


def require_access(uid, channel='telegram'):
    if not cohort_enabled(uid, channel) or not remote_enabled(channel):
        raise AccessDenied('channel_disabled', 'Messaging channels disabled')
    if account_deletion_blocks_access(get_user_deletion_wipe_status(uid)):
        raise AccessDenied('account_deletion', 'Account deletion in progress')
    subscription = get_user_valid_subscription(uid, provision=False)
    if subscription is None or not is_paid_plan(subscription.plan):
        raise AccessDenied('paid_plan', 'Paid plan required')

    plans = channel_policy(channel).get('plans')
    plan = getattr(subscription.plan, 'value', subscription.plan)
    if plans is not None:
        if not isinstance(plans, list):
            raise AccessDenied('channel_disabled', 'Invalid channel plan policy')
        allowed_plans: list[str] = [value for value in plans if isinstance(value, str)]
        if plan not in allowed_plans:
            raise AccessDenied('channel_plan', 'Operator or Architect plan required for iMessage')


def require_app_access(uid):
    """App awareness is enabled when at least one channel admits this user."""
    try:
        require_access(uid, 'telegram')
    except PermissionError:
        require_access(uid, 'imessage')
