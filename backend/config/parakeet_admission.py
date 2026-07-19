"""Admission control for the Parakeet live-STT provider.

Parakeet has a hard concurrent-stream ceiling (~25–30 safe streams) that
must be enforced *before* a connection attempt, not after the service
rejects it.  This module exposes a single ``try_admit`` gate that the
STT selection path calls at connect time.

Allocation percentage is read from ``PARAKEET_ALLOCATION_PCT`` at
*request* time (env reads at import are cached too early).  A value
of ``0`` forces all traffic to Modulate.  ``100`` admits everything
(up to the hard cap).  Values between 1–99 implement a probabilistic
canary allocation.

Operators can set ``PARAKEET_ALLOCATION_PCT=0`` for immediate mitigation
without a code deploy, and increase it after confirming capacity headroom.

See ``docs/runbooks/parakeet-admission-runbook.md`` for operational
mitigation procedures.
"""

from __future__ import annotations

import logging
import os
import random
import threading
from typing import Final

logger = logging.getLogger(__name__)

# --- Hard cap ----------------------------------------------------------------

DEFAULT_PARAKEET_MAX_CONCURRENT: Final[int] = 30

_current_concurrent: int = 0
_concurrent_lock = threading.Lock()


def parakeet_active_count() -> int:
    """Return the current number of admitted Parakeet streams (best-effort)."""
    with _concurrent_lock:
        return _current_concurrent


def parakeet_max_concurrent() -> int:
    """Read the hard concurrent-stream ceiling from env at call time."""
    try:
        return max(1, int(os.getenv("PARAKEET_MAX_CONCURRENT", str(DEFAULT_PARAKEET_MAX_CONCURRENT))))
    except (ValueError, TypeError):
        return DEFAULT_PARAKEET_MAX_CONCURRENT


# --- Allocation ---------------------------------------------------------------


def parakeet_allocation_pct() -> float:
    """Read the allocation percentage from env at call time.

    Returns a value in [0.0, 1.0].
    """
    try:
        pct = float(os.getenv("PARAKEET_ALLOCATION_PCT", "100"))
    except (ValueError, TypeError):
        pct = 100.0
    return max(0.0, min(1.0, pct / 100.0))


# --- Admission gate -----------------------------------------------------------

# Reasons returned by try_admit for observability.
ADMIT_REASON_CAPACITY_FULL = "capacity_full"
ADMIT_REASON_ALLOCATION_ZERO = "allocation_zero"
ADMIT_REASON_ALLOCATION_REJECTED = "allocation_rejected"
ADMIT_REASON_ADMITTED = "admitted"


def try_admit() -> tuple[bool, str]:
    """Decide whether to admit a request to Parakeet.

    Returns ``(admitted, reason)``.  The reason is one of the
    ``ADMIT_REASON_*`` constants above and should be passed through
    to ``record_fallback`` when admission is denied.

    The gate checks allocation percentage first (cheap, no lock), then
    hard capacity under the lock.  This ordering means setting
    ``PARAKEET_ALLOCATION_PCT=0`` blocks admission without touching the
    capacity counter.
    """
    global _current_concurrent
    allocation = parakeet_allocation_pct()
    if allocation <= 0.0:
        return False, ADMIT_REASON_ALLOCATION_ZERO

    # Probabilistic allocation: reject before touching the counter.
    if allocation < 1.0:
        if random.random() > allocation:
            return False, ADMIT_REASON_ALLOCATION_REJECTED

    max_concurrent = parakeet_max_concurrent()
    with _concurrent_lock:
        if _current_concurrent >= max_concurrent:
            return False, ADMIT_REASON_CAPACITY_FULL
        _current_concurrent += 1

    logger.debug(
        "Parakeet admission: active=%d cap=%d allocation=%.0f%%", _current_concurrent, max_concurrent, allocation * 100
    )
    return True, ADMIT_REASON_ADMITTED


def release() -> None:
    """Decrement the active-stream counter after the Parakeet session ends."""
    global _current_concurrent
    with _concurrent_lock:
        _current_concurrent = max(0, _current_concurrent - 1)


def reset_state_for_testing() -> None:
    """Clear all admission state (unit-test-only)."""
    global _current_concurrent
    with _concurrent_lock:
        _current_concurrent = 0
