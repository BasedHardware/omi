"""Post-seal latency controls; backlog keeps its existing scheduling policy."""

from datetime import datetime
import math

from config.refactor_modes import default_off, default_on

_FRESH_MERGE_ENV = 'RECORD_FRESH_MERGE_ENABLED'
_NOTES_EAGER_ENV = 'RECORD_NOTES_EAGER_ENABLED'
_FOLLOWUP_WAKE_ENV = 'RECORD_FOLLOWUP_WAKE_ENABLED'
_SEAL_WAKE_ENV = 'RECORD_SEAL_WAKE_PRESERVED_ENABLED'

RECENT_RECORD_SECONDS = 1800


def recent_record_end(value, now: float) -> bool:
    if isinstance(value, datetime):
        value = value.timestamp()
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and 0 <= now - value <= RECENT_RECORD_SECONDS
    )


def record_fresh_merge_enabled() -> bool:
    return default_off(_FRESH_MERGE_ENV)


def record_notes_eager_enabled() -> bool:
    return default_off(_NOTES_EAGER_ENV)


def record_followup_wake_enabled() -> bool:
    return default_on(_FOLLOWUP_WAKE_ENV)


def record_seal_wake_preserved_enabled() -> bool:
    return default_on(_SEAL_WAKE_ENV)


def recent_native_record(job: dict, now: float) -> bool:
    return recent_native_record_notes(job, now)


def recent_native_record_notes(job: dict, now: float) -> bool:
    """Notes urgency follows recording end, independently of merge rollout."""
    binding = job.get('projection_binding') or {}
    # Partial pages can still acquire siblings. Keep their settle window.
    return (
        binding.get('native_record') is True
        and binding.get('partial_record') is not True
        and recent_record_end(job.get('record_finished_at'), now)
    )
