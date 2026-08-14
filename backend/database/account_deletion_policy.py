"""Pure policy for the durable account-deletion authority.

This module intentionally depends on no higher application layer so database,
service, and transport boundaries make the same fail-closed decision.
"""

from __future__ import annotations

ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES = frozenset({'cancelled', 'billing_failed'})
ACCOUNT_DELETION_INVALID_STATUS = '__invalid_account_deletion_status__'


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
