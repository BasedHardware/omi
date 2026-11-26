"""The single approved aggregate sample window; remove the env var to stop it."""

import os

SLOT_SECONDS = 180
WINDOW_SECONDS = 86_400
ATTEMPT_SECONDS = 2


def _is_backend_sync() -> bool:
    return os.getenv('K_SERVICE') == 'backend-sync'


def metric_revision() -> str:
    """Use only Cloud Run's exact backend-sync identity for cap telemetry."""
    return os.getenv('K_REVISION', '') if _is_backend_sync() else ''


def slot_at(now: float) -> int | None:
    if not _is_backend_sync():
        return None
    try:
        start = int(os.getenv('RECORD_WAL_SAMPLE_START_EPOCH', '0'))
    except ValueError:
        return None
    if start <= 0 or start % SLOT_SECONDS or not start <= now < start + WINDOW_SECONDS - ATTEMPT_SECONDS:
        return None
    # Absolute UTC slots deduplicate overlapping releases and stale revisions.
    return int(now) // SLOT_SECONDS
