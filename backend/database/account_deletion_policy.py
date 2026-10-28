"""Pure policy for the durable account-deletion authority.

This module intentionally depends on no higher application layer so database,
service, and transport boundaries make the same fail-closed decision.
"""

from __future__ import annotations

from datetime import timedelta

ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES = frozenset({'cancelled', 'billing_failed'})
ACCOUNT_DELETION_INVALID_STATUS = '__invalid_account_deletion_status__'

# Grace window admission state: the deletion intent is durable and every
# access fence treats it like an active deletion, but the irreversible wipe is
# deferred until ``wipe_due_at`` so the owner can restore the account.
ACCOUNT_DELETION_GRACE_STATUS = 'pending_deletion'

# A grace marker is restorable until the window-end wipe is claimed; once a
# task claim or worker owns the wipe the data is being destroyed.
ACCOUNT_DELETION_RESTORABLE_STATUSES = frozenset({'pending_deletion', 'pending'})
DELETION_WIPE_RETRY_BASE_DELAY = timedelta(minutes=5)
DELETION_WIPE_RETRY_MAX_DELAY = timedelta(hours=1)


def deletion_wipe_retry_delay(attempts: int) -> timedelta:
    """Back off failed wipe retries without making accepted deletion terminal."""
    if attempts <= 1:
        return timedelta(0)
    doublings = min(attempts - 2, 20)
    return min(DELETION_WIPE_RETRY_BASE_DELAY * (2**doublings), DELETION_WIPE_RETRY_MAX_DELAY)


def deletion_billing_error_is_already_gone(error: object) -> bool:
    """Recognize historical billing failures that no longer block erasure.

    This is only a reconciliation filter. The worker still checks Stripe's
    current state before deleting Auth; arbitrary outages are not eligible.
    """
    if not isinstance(error, str):
        return False
    message = error.lower().strip()
    return message == 'stripe cancel returned no subscription' or any(
        text in message
        for text in (
            'resource_missing',
            'no such subscription',
            'a canceled subscription can only update its cancellation_details and metadata',
            'already canceled',
            'already cancelled',
            'incomplete_expired',
        )
    )


def normalize_account_deletion_status(*, marker_exists: bool, raw_status: object) -> str | None:
    """Normalize marker state without treating malformed markers as misses."""
    if not marker_exists:
        return None
    if isinstance(raw_status, str) and raw_status.strip():
        return raw_status.strip()
    return ACCOUNT_DELETION_INVALID_STATUS


def account_deletion_blocks_access(status: str | None) -> bool:
    """Deny every existing marker unless its state explicitly restores access."""
    return status is not None and status not in ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES


def account_deletion_marker_blocks_access(*, marker_exists: bool, raw_status: object) -> bool:
    """Apply the shared access decision to an already-read marker snapshot."""
    return account_deletion_blocks_access(
        normalize_account_deletion_status(marker_exists=marker_exists, raw_status=raw_status)
    )


def account_deletion_restorable(status: str | None) -> bool:
    """Whether the owner can still cancel the deletion and keep their data."""
    return status in ACCOUNT_DELETION_RESTORABLE_STATUSES


__all__ = [
    'ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES',
    'ACCOUNT_DELETION_GRACE_STATUS',
    'ACCOUNT_DELETION_INVALID_STATUS',
    'ACCOUNT_DELETION_RESTORABLE_STATUSES',
    'DELETION_WIPE_RETRY_BASE_DELAY',
    'DELETION_WIPE_RETRY_MAX_DELAY',
    'account_deletion_blocks_access',
    'account_deletion_marker_blocks_access',
    'account_deletion_restorable',
    'deletion_wipe_retry_delay',
    'normalize_account_deletion_status',
]
