"""Soniox paid idle transport lifetime.

Soniox bills real-time streams for every connected second, keepalive silence
included, so the idle close is on by default. ``SONIOX_IDLE_CLOSE_SECONDS=0``
(or ``off``/``false``) is the kill switch and restores the always-connected
adapter. Every knob reads the current environment at call time.
"""

import logging
import math
import os
from functools import lru_cache

DEFAULT_IDLE_CLOSE_SECONDS = 20.0
MIN_IDLE_CLOSE_SECONDS = 20.0
DEFAULT_NO_FRAMES_CLOSE_SECONDS = 20.0
# Must stay above the VAD hangover (4 s) so a client that pauses mid-word is not
# closed before the gate would have released its silence tail.
MIN_NO_FRAMES_CLOSE_SECONDS = 10.0
DEFAULT_REARM_SECONDS = 10.0
MIN_REARM_SECONDS = 5.0
DEFAULT_MAX_CLOSES_PER_HOUR = 120
_OFF_VALUES = frozenset({'off', 'false', 'no', 'disabled'})
logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _warn_threshold_floor() -> None:
    logger.warning('SONIOX_IDLE_CLOSE_SECONDS below safety floor; clamping to %s seconds', MIN_IDLE_CLOSE_SECONDS)


@lru_cache(maxsize=4)
def _warn_invalid(name: str) -> None:
    logger.warning('%s is not a number; using the code default', name)


def _seconds(name: str, default: float, floor: float) -> float:
    """Unset/blank/invalid -> default; zero, negative or an off word -> 0 (off)."""
    raw = os.getenv(name, '').strip()
    if not raw:
        return default
    if raw.lower() in _OFF_VALUES:
        return 0.0
    try:
        value = float(raw)
    except ValueError:
        _warn_invalid(name)
        return default
    if math.isnan(value):
        _warn_invalid(name)
        return default
    if value <= 0 or math.isinf(value):
        return 0.0
    return max(floor, value)


def idle_close_seconds() -> float:
    """Active-VAD silence before a planned close; 0 disables the idle wrapper entirely."""
    raw = os.getenv('SONIOX_IDLE_CLOSE_SECONDS', '').strip()
    try:
        below_floor = 0 < float(raw) < MIN_IDLE_CLOSE_SECONDS
    except ValueError:
        below_floor = False
    if below_floor:
        _warn_threshold_floor()
    return _seconds('SONIOX_IDLE_CLOSE_SECONDS', DEFAULT_IDLE_CLOSE_SECONDS, MIN_IDLE_CLOSE_SECONDS)


def idle_no_frames_seconds() -> float:
    """Wall time with no client frames at all before a planned close; 0 disables only this trigger."""
    return _seconds('SONIOX_IDLE_NO_FRAMES_SECONDS', DEFAULT_NO_FRAMES_CLOSE_SECONDS, MIN_NO_FRAMES_CLOSE_SECONDS)


def idle_rearm_seconds() -> float:
    """Minimum connected time after a successful reopen before another planned close."""
    try:
        value = float(os.getenv('SONIOX_IDLE_REARM_SECONDS', str(DEFAULT_REARM_SECONDS)))
    except ValueError:
        return DEFAULT_REARM_SECONDS
    return max(MIN_REARM_SECONDS, value) if math.isfinite(value) else DEFAULT_REARM_SECONDS


def idle_max_closes_per_hour() -> int:
    """Rolling-hour cap on VAD-silence closes per logical session."""
    try:
        value = int(os.getenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', str(DEFAULT_MAX_CLOSES_PER_HOUR)))
    except ValueError:
        return DEFAULT_MAX_CLOSES_PER_HOUR
    return value if value > 0 else DEFAULT_MAX_CLOSES_PER_HOUR
