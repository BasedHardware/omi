"""GPU-capacity overflow for batch admission (vendor_route_contracts.FLAGS).

The GPU ring is saturated when its oldest admissible fresh unit has waited past an SLO **and** enough
admissible fresh units are waiting that the age is a real backlog, not a few stuck heads (11-01: 4
parked owners held 111 fresh units 42 h old while the ring was idle). While saturated:

* inside the vendor-routing cohort, a fresh unit that would start on GPU starts on the table's
  next healthy primary vendor (Modulate in practice; Soniox is failover-only and never primary);
* an owner whose legacy sync is still on keeps a new fresh upload on legacy sync instead of
  queueing it behind the ring (the same intake fallback heavy-owner exclusion uses).

Read per call, never snapshotted at import. Malformed or out-of-range numbers keep the default.
"""

import math
import os

from config.refactor_switches import default_on as rollout_default_on

ENTER_SECONDS_DEFAULT = 1200.0
EXIT_SECONDS_DEFAULT = 600.0
SECONDS_MIN = 60.0
SECONDS_MAX = 21600.0
MIN_READY_UNITS_DEFAULT = 300
MIN_READY_UNITS_MAX = 100000


def overflow_enabled() -> bool:
    """Vendor overflow kill switch (unset is on). False keeps every capable unit on GPU."""
    return rollout_default_on(
        'BATCH_VENDOR_OVERFLOW_ENABLED',
        os.getenv('BATCH_VENDOR_OVERFLOW_ENABLED', 'true').strip().lower() != 'false',
    )


def legacy_capacity_fallback_enabled() -> bool:
    """Legacy capacity fallback kill switch (unset is on). False queues every upload behind the ring."""
    return rollout_default_on(
        'BATCH_LEGACY_CAPACITY_FALLBACK_ENABLED',
        os.getenv('BATCH_LEGACY_CAPACITY_FALLBACK_ENABLED', 'true').strip().lower() != 'false',
    )


def _number(raw: str | None, default: float, low: float, high: float) -> float:
    raw = (raw or '').strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) and low <= value <= high else default


def thresholds() -> tuple[float, float]:
    """``(enter, exit)`` fresh backlog ages in seconds. Saturation starts at ``enter`` and stops once the
    age falls below ``exit``; an exit at or above enter falls back to half of enter (hysteresis)."""
    enter = _number(os.getenv('BATCH_VENDOR_OVERFLOW_ENTER_SECONDS'), ENTER_SECONDS_DEFAULT, SECONDS_MIN, SECONDS_MAX)
    exit_ = _number(os.getenv('BATCH_VENDOR_OVERFLOW_EXIT_SECONDS'), EXIT_SECONDS_DEFAULT, SECONDS_MIN, SECONDS_MAX)
    return enter, exit_ if exit_ < enter else enter / 2


def min_ready_units() -> int:
    """Admissible fresh units that must be waiting before an old head counts as saturation; it stops
    below half of this."""
    return int(
        _number(os.getenv('BATCH_VENDOR_OVERFLOW_MIN_READY_UNITS'), MIN_READY_UNITS_DEFAULT, 1, MIN_READY_UNITS_MAX)
    )
