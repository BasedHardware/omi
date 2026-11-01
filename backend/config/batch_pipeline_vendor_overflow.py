"""GPU-capacity overflow for all-vendor batch routing (slice B follow-up, vendor_route_contracts.FLAGS).

When the oldest admissible fresh unit in the GPU ring has waited past an SLO, selection sends new
fresh units that would start on GPU to the table's next healthy primary vendor instead (Modulate in
practice; Soniox is failover-only and never a primary). Read per call, never snapshotted at import.
Malformed or out-of-range numbers keep the default. Dormant unless an owner is in the
vendor-routing cohort and a configured route table lists a vendor after GPU.
"""

import math
import os

from config.refactor_switches import default_on as rollout_default_on

ENTER_SECONDS_DEFAULT = 1200.0
EXIT_SECONDS_DEFAULT = 600.0
SECONDS_MIN = 60.0
SECONDS_MAX = 21600.0


def overflow_enabled() -> bool:
    """Kill switch (unset is on). False keeps every capable unit on GPU however long the ring waits."""
    return rollout_default_on(
        'BATCH_VENDOR_OVERFLOW_ENABLED',
        os.getenv('BATCH_VENDOR_OVERFLOW_ENABLED', 'true').strip().lower() != 'false',
    )


def _seconds(raw: str | None, default: float) -> float:
    raw = (raw or '').strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) and SECONDS_MIN <= value <= SECONDS_MAX else default


def thresholds() -> tuple[float, float]:
    """``(enter, exit)`` fresh backlog ages in seconds. Overflow starts at ``enter`` and stops once the
    age falls below ``exit``; an exit at or above enter falls back to half of enter (hysteresis)."""
    enter = _seconds(os.getenv('BATCH_VENDOR_OVERFLOW_ENTER_SECONDS'), ENTER_SECONDS_DEFAULT)
    exit_ = _seconds(os.getenv('BATCH_VENDOR_OVERFLOW_EXIT_SECONDS'), EXIT_SECONDS_DEFAULT)
    return enter, exit_ if exit_ < enter else enter / 2
