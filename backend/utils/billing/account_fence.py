"""Account-fence classification for Stripe subscription-event unlocks.

When a user deletes their account, the deletion worker acquires the
account-wide destructive-operation gate, cancels the Stripe subscription and
erases the account. Stripe then delivers the cancellation webhook for exactly
that cancellation. The subscription-event unlock trio
(``unlock_all_conversations`` / ``unlock_all_memories`` /
``unlock_all_action_items``) reads the same authority through
``external_write_fence`` and raises ``DestructiveOperationInProgress`` — for an
account whose rows the deletion is concurrently (or has already) removed. The
lifecycle event's remaining effects are moot for that account: there is no
living entitlement to project content unlocks onto, and the erased rows are
where the unlocks wanted the account to be.
"""

from __future__ import annotations

import logging

from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_blocks_access

logger = logging.getLogger(__name__)


def account_deletion_fence_is_terminal(uid: str) -> bool:
    """True when the blocking fence is an account deletion, past billing's reach.

    Reads ``account_deletions/{uid}`` directly (the same authority the fence
    read) and returns True when a blocking marker is present and its wipe is
    not parked on billing itself: any live/terminal wipe state
    (``pending``/``retrying``/``running``/``failed``/``completed``/legacy
    ``deleting_auth``) outlives this event — the deletion owns the account for
    its whole run, and the rows the unlocks target are gone or going — while
    ``billing_failed`` and ``cancelled`` can restore access, so they keep the
    retryable-fence classification. False also for a missing marker (the fence
    came from a temporary destructive gate) and for any authority read error:
    every False keeps the caller's retry handling, so this classification can
    only downgrade a doomed retry, never skip a delivery that could still
    succeed.
    """
    try:
        snapshot = account_deletion_document(uid).get()
    except Exception:
        logger.warning('billing account-fence probe failed uid=%s', uid)
        return False
    exists = getattr(snapshot, 'exists', None)
    if exists is not True:
        return False
    try:
        payload = snapshot.to_dict() or {}
    except Exception:
        return False
    status = payload.get('wipe_status')
    if not account_deletion_blocks_access(status):
        # A marker that does not block access (billing_failed, cancelled,
        # malformed absence) did not raise this fence.
        return False
    return True


def subscription_event_unlock_refused_by_account_deletion(uid: str, error: BaseException) -> bool:
    """Classify a failed lifecycle-event unlock as an account-deletion refusal.

    True only when the unlock failed on the account fence (a destructive
    operation owns the account or deletion blocks access) *and* that fence is
    a past-billing account deletion. A temporary gate (an explicit memory
    deletion, a legal-hold flow) or an authority read failure returns False so
    the delivery stays retryable — the gate can lift while Stripe still holds
    delivery attempts.
    """
    from database.legal_holds import DestructiveOperationInProgress

    return isinstance(error, DestructiveOperationInProgress) and account_deletion_fence_is_terminal(uid)


__all__ = ['subscription_event_unlock_refused_by_account_deletion']
