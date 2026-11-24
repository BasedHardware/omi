"""Limits on automatic held-audio release (David, 2026-11-02: 25h trial grant, lowered throttles).

A manual tap is not gated here. Every number is read at the dispatch boundary, so
the fleet limits can move through runtime config without a build.
"""

import math
import os

from config.refactor_modes import default_on

# The newest audio an owner hears soon after a trial starts. Later audio waits for idle GPUs.
PRIORITY_HOURS = 2.5
OWNER_HOURS_PER_DAY = 5.0
# Idle means the HPA's own signal stays below its 4-replica floor (32 units per replica):
# fresh + recent + deep never exceeds 96 of the 128 that would add a GPU. Measured 2026-11-02.
IDLE_MAX_FRESH_RECENT_READY = 64
IDLE_MAX_DEEP_READY = 32
IDLE_SAMPLE_SECONDS = 30.0
IDLE_SAMPLE_MAX_AGE_SECONDS = 120.0


def enabled() -> bool:
    """Kill switch. Off stops new admissions at once; audio stays held, nothing is deleted."""
    return default_on('BACKLOG_RELEASE_ENABLED')


def _positive(name: str, default: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError('invalid backlog release limit')
    return value


def fleet_hours_per_day() -> float:
    return _positive('BACKLOG_RELEASE_FLEET_HOURS_PER_DAY', 400.0)


def fleet_hours_per_hour() -> float:
    return _positive('BACKLOG_RELEASE_FLEET_HOURS_PER_HOUR', 20.0)
