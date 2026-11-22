"""Home processing ownership, enabled by default with per-call kill switches.

Lifecycle: ops_kill; owner home-overlap; permanent env kill switch.
"""

import os

from config.refactor_modes import default_on


def in_cohort(uid: str | None) -> bool:
    members = {part.strip() for part in os.getenv('HOME_PROCESSING_OWNERSHIP_UIDS', '').split(',') if part.strip()}
    return not members or uid in members


def ownership_enabled(uid: str | None = None) -> bool:
    return os.getenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true').strip().lower() == 'true' and in_cohort(uid)


def live_member_notes_enabled(uid: str | None = None) -> bool:
    return os.getenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'true').strip().lower() == 'true' and in_cohort(uid)


def bounded_member_notes_enabled() -> bool:
    return default_on('HOME_LIVE_MEMBER_NOTES_BOUNDED_ENABLED')


def owner_cache_enabled() -> bool:
    return os.getenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'true').strip().lower() == 'true'
