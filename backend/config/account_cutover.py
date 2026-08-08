"""Server-owned defaults for whole-account cohort cutover.

LIFECYCLE: permanent

Minimum supported builds default to zero so accounts remaining ``legacy`` keep
current main behavior. Operators raise these only after the mandatory bridge
release ships. The code-owned empty enrollment set means this foundation never
migrates a user by itself.
"""

from __future__ import annotations

# Empty by design: enrollment is an explicit operator/ceremony action outside
# this foundation PR. ``AccountCutoverCoordinator.begin`` refuses any uid that
# is not a member, so an empty set migrates no user.
ACCOUNT_CUTOVER_COHORT: frozenset[str] = frozenset()

# Per-platform integer build floors. Zero means no force-upgrade for that
# platform until operators configure a bridge-release floor.
MINIMUM_SUPPORTED_BUILDS: dict[str, int] = {
    'ios': 0,
    'android': 0,
    'macos': 0,
    'windows': 0,
    'linux': 0,
    'web': 0,
}

# Product-traffic generations advertised to bridge clients. Legacy accounts
# continue to see generation 0 until cutover begins.
DEFAULT_UI_GENERATION = 0
DEFAULT_API_GENERATION = 0

# Schema for the persisted account cutover control document.
ACCOUNT_CUTOVER_SCHEMA_VERSION = 1


def is_account_cutover_cohort_member(uid: object) -> bool:
    """Return whether ``uid`` is explicitly enrolled for whole-account cutover."""

    return bool(uid) and isinstance(uid, str) and uid in ACCOUNT_CUTOVER_COHORT


__all__ = [
    'ACCOUNT_CUTOVER_COHORT',
    'ACCOUNT_CUTOVER_SCHEMA_VERSION',
    'DEFAULT_API_GENERATION',
    'DEFAULT_UI_GENERATION',
    'MINIMUM_SUPPORTED_BUILDS',
    'is_account_cutover_cohort_member',
]
