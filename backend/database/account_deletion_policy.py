"""Pure policy for the durable account-deletion authority.

This module intentionally depends on no higher application layer so database,
service, and transport boundaries make the same fail-closed decision.

Design: invalid types fail fast with TypeError; malformed marker states resolve
safely to ACCOUNT_DELETION_INVALID_STATUS to block access.
"""

from __future__ import annotations

ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES = frozenset({'cancelled', 'billing_failed'})
ACCOUNT_DELETION_INVALID_STATUS = '__invalid_account_deletion_status__'
MAX_ACCOUNT_DELETION_STATUS_CHARS = 256


def normalize_account_deletion_status(*, marker_exists: bool, raw_status: object) -> str | None:
    """Normalize marker state without treating malformed markers as misses."""
    if isinstance(marker_exists, (str, list, dict)):
        raise TypeError("marker_exists must be a boolean")
    if not bool(marker_exists):
        return None
    if isinstance(raw_status, str):
        cleaned = raw_status.strip()
        if cleaned and len(cleaned) <= MAX_ACCOUNT_DELETION_STATUS_CHARS:
            return cleaned
    return ACCOUNT_DELETION_INVALID_STATUS


def account_deletion_blocks_access(status: str | None) -> bool:
    """Deny every existing marker unless its state explicitly restores access."""
    if status is None:
        return False
    if not isinstance(status, str):
        raise TypeError("status must be a str or None")
    return status.strip() not in ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES


__all__ = [
    'ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES',
    'ACCOUNT_DELETION_INVALID_STATUS',
    'MAX_ACCOUNT_DELETION_STATUS_CHARS',
    'account_deletion_blocks_access',
    'normalize_account_deletion_status',
]

