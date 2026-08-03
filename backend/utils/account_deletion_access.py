"""Single-source account-deletion access policy.

The durable ``account_deletions/{uid}`` marker outlives the user document and
Firebase Auth account.  A pre-deletion Firebase ID token can remain
cryptographically valid until expiry, so ``completed`` must remain fenced.

Only states that explicitly mean no destructive deletion is active restore
ordinary access.  Unknown future states fail closed so adding a lifecycle
state cannot silently reopen one of the independent auth boundaries.
"""

from __future__ import annotations

ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES = frozenset({'cancelled', 'billing_failed'})
ACCOUNT_DELETION_ACCESS_BLOCKING_STATUSES = frozenset(
    {
        'deleting_auth',
        'pending',
        'retrying',
        'running',
        'failed',
        'completed',
    }
)
ACCOUNT_DELETION_INVALID_STATUS = '__invalid_account_deletion_status__'


def normalize_account_deletion_status(*, marker_exists: bool, raw_status: object) -> str | None:
    """Normalize a marker status without treating malformed markers as misses."""
    if not marker_exists:
        return None
    if isinstance(raw_status, str) and raw_status.strip():
        return raw_status.strip()
    return ACCOUNT_DELETION_INVALID_STATUS


def account_deletion_blocks_access(status: str | None) -> bool:
    """Return whether an authenticated UID must be denied product access."""
    if status is None:
        return False
    return status not in ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES


__all__ = [
    'ACCOUNT_DELETION_ACCESS_ALLOWED_STATUSES',
    'ACCOUNT_DELETION_ACCESS_BLOCKING_STATUSES',
    'ACCOUNT_DELETION_INVALID_STATUS',
    'account_deletion_blocks_access',
    'normalize_account_deletion_status',
]
