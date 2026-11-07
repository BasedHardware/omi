"""Home processing ownership rollout, default off.

Lifecycle: rollout; owner home-overlap; review 2026-11-21.
"""

import os


def in_cohort(uid: str | None) -> bool:
    members = {part.strip() for part in os.getenv('HOME_PROCESSING_OWNERSHIP_UIDS', '').split(',') if part.strip()}
    return not members or uid in members


def ownership_enabled(uid: str | None = None) -> bool:
    return os.getenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'false').strip().lower() == 'true' and in_cohort(uid)


def live_member_notes_enabled(uid: str | None = None) -> bool:
    return os.getenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'false').strip().lower() == 'true' and in_cohort(uid)
