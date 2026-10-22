"""Env-gated Free-plan mechanics. Every switch defaults to off; a malformed value is off.

Read at the call boundary, never snapshotted at import, so a deploy can flip
one without a restart of every service that imports ``utils.subscription``.
"""

import os


def _positive_int(name: str) -> int:
    """``0`` (off) unless the variable holds a strictly positive integer."""
    raw = os.getenv(name, '').strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


def free_retention_lock_days() -> int:
    """Days after which a Free-plan conversation is retention locked; ``0`` disables the lock."""
    return _positive_int('FREE_RETENTION_LOCK_DAYS')


def free_transcription_hard_pause() -> bool:
    """When true, an exhausted Free-plan allowance blocks transcription instead of falling back on-device."""
    return os.getenv('FREE_TRANSCRIPTION_HARD_PAUSE', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}


def free_chat_questions_per_day() -> int:
    """Per-UTC-day Free-plan chat cap that replaces the catalog's monthly cap; ``0`` keeps the monthly cap."""
    return _positive_int('FREE_CHAT_QUESTIONS_PER_DAY')
