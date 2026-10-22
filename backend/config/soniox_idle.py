"""Soniox paid idle transport lifetime.

Soniox bills real-time streams for every connected second, keepalive silence
included, so the idle close is on by default. ``SONIOX_IDLE_CLOSE_SECONDS=0``
(or ``off``/``false``) is the kill switch and restores the always-connected
adapter. Every knob reads the current environment at call time.

The VAD-silence policy keeps the values prod ran since 2026-10-06 (45 s close,
60 s re-arm, 12 closes per session-hour). Each reopen starts a new provider
speaker scope, so lowering these waits for speaker scope to survive a reopen.

A uid-hash treatment cohort (``SONIOX_IDLE_COHORT_PERCENT``, default 0 = off)
runs tighter values on a static percent of users without touching the global
knobs: in-cohort sessions read the ``SONIOX_IDLE_COHORT_*`` overrides when set
(each falls back to the global knob when unset) and every other session keeps
today's values. ``SONIOX_IDLE_COHORT_PERCENT=0`` is the cohort kill switch;
``SONIOX_IDLE_CLOSE_SECONDS=0`` remains the fleet-wide kill switch either way.
"""

import logging
import math
import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_IDLE_CLOSE_SECONDS = 45.0
MIN_IDLE_CLOSE_SECONDS = 20.0
DEFAULT_NO_FRAMES_CLOSE_SECONDS = 60.0
MIN_NO_FRAMES_CLOSE_SECONDS = 10.0
# Mirrors utils.stt.vad_gate.VAD_GATE_HANGOVER_MS (pinned by a unit test). A
# no-frames close never finalizes inside this tail after the last speech frame.
VAD_HANGOVER_SECONDS = 4.0
DEFAULT_REARM_SECONDS = 60.0
MIN_REARM_SECONDS = 5.0
DEFAULT_MAX_CLOSES_PER_HOUR = 12
_OFF_VALUES = frozenset({'off', 'false', 'no', 'disabled'})
COHORT_SALT = 'soniox-idle-close'
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
    """Rolling-hour cap on planned closes (VAD silence and no frames) per logical session."""
    try:
        value = int(os.getenv('SONIOX_IDLE_MAX_CLOSES_PER_HOUR', str(DEFAULT_MAX_CLOSES_PER_HOUR)))
    except ValueError:
        return DEFAULT_MAX_CLOSES_PER_HOUR
    return value if value > 0 else DEFAULT_MAX_CLOSES_PER_HOUR


def cohort_percent() -> float:
    """``SONIOX_IDLE_COHORT_PERCENT`` in [0, 100]; anything else is 0 (cohort off)."""
    raw = os.getenv('SONIOX_IDLE_COHORT_PERCENT', '0')
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value <= 0:
        return 0.0
    return min(value, 100.0)


def _cohort_override(name: str, floor: float | None) -> float | None:
    """Unset/blank/invalid/off -> None (no override); a positive number -> floored value."""
    raw = os.getenv(name, '').strip()
    if not raw or raw.lower() in _OFF_VALUES:
        return None
    try:
        value = float(raw)
    except ValueError:
        _warn_invalid(name)
        return None
    if math.isnan(value) or math.isinf(value) or value <= 0:
        return None
    return max(floor, value) if floor is not None else value


def _cohort_cap_override() -> int | None:
    """``SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR``: unset/invalid/<=0 -> None."""
    raw = os.getenv('SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR', '').strip()
    if not raw:
        return None
    try:
        cap = int(raw)
    except ValueError:
        _warn_invalid('SONIOX_IDLE_COHORT_MAX_CLOSES_PER_HOUR')
        return None
    return cap if cap > 0 else None


def cohort_armed() -> bool:
    """True when the cohort knobs could assign a treatment arm to a known uid.

    ``SONIOX_IDLE_COHORT_PERCENT`` at its default 0 (the cohort kill switch)
    leaves this false: callers holding lazy identity must not consult it, and a
    uid-less resolution is plain control.
    """
    if cohort_percent() <= 0:
        return False
    return (
        _cohort_override('SONIOX_IDLE_COHORT_CLOSE_SECONDS', MIN_IDLE_CLOSE_SECONDS) is not None
        or _cohort_override('SONIOX_IDLE_COHORT_REARM_SECONDS', MIN_REARM_SECONDS) is not None
        or _cohort_cap_override() is not None
    )


@dataclass(frozen=True)
class IdleCohortSettings:
    """Per-session resolution of the idle policy against the treatment cohort."""

    arm: str  # 'control' | 'treatment'
    close_seconds: float
    rearm_seconds: float
    max_closes_per_hour: int


def idle_settings_for(uid: str | None) -> IdleCohortSettings:
    """Resolve the idle knobs for one logical session.

    The arm is ``treatment`` only when the uid hashes into the cohort percent
    and at least one ``SONIOX_IDLE_COHORT_*`` override is set; a treatment arm
    with no overrides behaves identically to control and is labelled control so
    the cohort metrics stay a clean A/B. Overrides never widen a global kill:
    when the global close knob is 0 the idle wrapper is disabled for everyone.
    """
    global_close = idle_close_seconds()
    close_override = _cohort_override('SONIOX_IDLE_COHORT_CLOSE_SECONDS', MIN_IDLE_CLOSE_SECONDS)
    rearm_override = _cohort_override('SONIOX_IDLE_COHORT_REARM_SECONDS', MIN_REARM_SECONDS)
    cap_override = _cohort_cap_override()
    percent = cohort_percent()
    in_cohort = False
    if percent > 0 and uid and (close_override is not None or cap_override is not None or rearm_override is not None):
        from config.policy.batch import cohort_bucket

        in_cohort = cohort_bucket(uid, COHORT_SALT, bits=64) < percent
    treatment = in_cohort and global_close > 0
    return IdleCohortSettings(
        arm='treatment' if treatment else 'control',
        close_seconds=close_override if treatment and close_override is not None else global_close,
        rearm_seconds=rearm_override if treatment and rearm_override is not None else idle_rearm_seconds(),
        max_closes_per_hour=cap_override if treatment and cap_override is not None else idle_max_closes_per_hour(),
    )
