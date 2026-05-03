"""Decisions extraction allowlist (v0 dogfood gate).

The Decisions lens is gated to a small set of uids during the v0 dogfood
phase. Allowlist is supplied via the `DECISIONS_DOGFOOD_UIDS` env var as
a comma-separated list of uids.
"""

import os


def _parse_uids(env_value: str) -> set[str]:
    """Parse a comma-separated env value into a set of trimmed, non-empty uids."""
    if not env_value:
        return set()
    return {u.strip() for u in env_value.split(",") if u.strip()}


DOGFOOD_UIDS: set[str] = _parse_uids(os.environ.get("DECISIONS_DOGFOOD_UIDS", ""))


def is_dogfood_uid(uid: str) -> bool:
    """Check if a uid is in the Decisions extraction allowlist (v0 dogfood gate)."""
    return uid in DOGFOOD_UIDS
