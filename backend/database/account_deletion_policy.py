"""Pure policy for the durable account-deletion authority.

This module intentionally depends on no higher application layer so database,
service, and transport boundaries make the same fail-closed decision.
"""

from __future__ import annotations

ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES = frozenset({'cancelled', 'billing_failed'})
ACCOUNT_DELETION_INVALID_STATUS = '__invalid_account_deletion_status__'


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


__all__ = [
    'ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES',
    'ACCOUNT_DELETION_INVALID_STATUS',
    'account_deletion_blocks_access',
    'normalize_account_deletion_status',
]
