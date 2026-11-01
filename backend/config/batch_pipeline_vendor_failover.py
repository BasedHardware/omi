"""Slice D runtime switches for the multi-vendor provider stage (vendor_route_contracts.FLAGS).

All four are read per call, never snapshotted at import. Malformed or out-of-range numbers keep
the default; nothing here can make a vendor call that today's routing would not make.
"""

import math
import os

from config.refactor_switches import default_on as rollout_default_on

HELD_REDRIVE_SECONDS_DEFAULT = 300.0
HELD_REDRIVE_SECONDS_MIN = 30.0
HELD_REDRIVE_SECONDS_MAX = 3600.0
HELD_STALE_GRACE_SECONDS_DEFAULT = 900.0
HELD_STALE_GRACE_SECONDS_MAX = 86400.0


def failover_enabled() -> bool:
    """Kill switch (unset is on). False makes a failed vendor attempt terminal ``failed_held`` as
    before slice D, and disables the self-LID fallback when the vendor language probe is down."""
    return rollout_default_on(
        'BATCH_VENDOR_FAILOVER_ENABLED',
        os.getenv('BATCH_VENDOR_FAILOVER_ENABLED', 'true').strip().lower() != 'false',
    )


def held_redrive_enabled() -> bool:
    """Kill switch (unset is on). False parks ``vendor_held`` units without redriving them; their
    holds then go stale after the grace and surface as wedges instead of hiding."""
    return rollout_default_on(
        'BATCH_VENDOR_HELD_REDRIVE_ENABLED',
        os.getenv('BATCH_VENDOR_HELD_REDRIVE_ENABLED', 'true').strip().lower() != 'false',
    )


def _seconds(raw: str | None, default: float, low: float, high: float) -> float:
    raw = (raw or '').strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) and low <= value <= high else default


def held_redrive_seconds() -> float:
    """How long a ``vendor_held`` unit waits before its next redrive (``redrive_at - now``)."""
    return _seconds(
        os.getenv('BATCH_VENDOR_HELD_REDRIVE_SECONDS'),
        HELD_REDRIVE_SECONDS_DEFAULT,
        HELD_REDRIVE_SECONDS_MIN,
        HELD_REDRIVE_SECONDS_MAX,
    )


def held_stale_grace_seconds() -> float:
    """Grace past ``redrive_at`` before guards stop excluding a hold (``is_vendor_policy_hold``)."""
    return _seconds(
        os.getenv('BATCH_VENDOR_HELD_STALE_GRACE_SECONDS'),
        HELD_STALE_GRACE_SECONDS_DEFAULT,
        0.0,
        HELD_STALE_GRACE_SECONDS_MAX,
    )
