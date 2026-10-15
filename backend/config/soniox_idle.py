"""Soniox paid idle transport lifetime; zero preserves the existing wire path."""

import logging
import math
import os
from functools import lru_cache

MIN_IDLE_CLOSE_SECONDS = 20.0
MIN_REARM_SECONDS = 60.0
DEFAULT_MAX_CLOSES_PER_HOUR = 12
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _warn_threshold_floor() -> None:
    logger.warning('SONIOX_IDLE_CLOSE_SECONDS below safety floor; clamping to %s seconds', MIN_IDLE_CLOSE_SECONDS)


def idle_close_seconds() -> float:
    try:
        value = float(os.getenv('SONIOX_IDLE_CLOSE_SECONDS', '0'))
    except ValueError:
        return 0.0
    if not math.isfinite(value) or value <= 0:
        return 0.0
    if value < MIN_IDLE_CLOSE_SECONDS:
        _warn_threshold_floor()
    return max(MIN_IDLE_CLOSE_SECONDS, value)


def idle_rearm_seconds() -> float:
    try:
        value = float(os.getenv('SONIOX_IDLE_REARM_SECONDS', str(MIN_REARM_SECONDS)))
    except ValueError:
        return MIN_REARM_SECONDS
    return max(MIN_REARM_SECONDS, value) if math.isfinite(value) else MIN_REARM_SECONDS


def idle_max_closes_per_hour() -> int:
    try:
        value = int(os.getenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', str(DEFAULT_MAX_CLOSES_PER_HOUR)))
    except ValueError:
        return DEFAULT_MAX_CLOSES_PER_HOUR
    return value if value > 0 else DEFAULT_MAX_CLOSES_PER_HOUR
