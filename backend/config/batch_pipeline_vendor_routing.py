"""All-vendor batch routing inputs (slice B). Defaults serve today's routing to everyone.

``BATCH_VENDOR_ROUTING_ENABLED`` is the kill switch: only ``false`` disables it, and
disabled serves ``vendor_route_contracts.BUILTIN_TABLE`` (today's routing) to every
owner. The cohort percent is the runtime ``batch-vendor-routing`` ramp (env fallback
``BATCH_VENDOR_ROUTING_PERCENT``, default 0), clamped to the batch percent: its bucket
is the batch bucket, so every vendor-routed owner is a batch owner.
"""

import json
import math
import os
from typing import Any

from config.policy.batch import parse_percent
from config.refactor_switches import default_on
from config.rollout_cohorts import runtime_percent, valid_uid
from utils.batch_pipeline.vendor_route_contracts import VENDOR_ROUTING_COHORT

# A payload that is set but is not JSON: the ladder rejects it (last valid, else builtin).
INVALID_PAYLOAD = object()


def vendor_routing_enabled() -> bool:
    """Kill switch (unset is on; only ``false`` disables it)."""
    return default_on(
        'BATCH_VENDOR_ROUTING_ENABLED',
        os.getenv('BATCH_VENDOR_ROUTING_ENABLED', 'true').strip().lower() != 'false',
    )


def vendor_routing_percent(batch_percent: float) -> float:
    """Runtime ramp percent, else the env value; never above the batch percent."""
    percent = parse_percent(os.getenv('BATCH_VENDOR_ROUTING_PERCENT', '0'))
    ramped = runtime_percent(VENDOR_ROUTING_COHORT, env_default=math.nan)
    if math.isfinite(ramped):
        percent = parse_percent(str(ramped))
    return min(percent, parse_percent(str(batch_percent)))


def vendor_routing_shadow_percent() -> float:
    """Owners whose decision is computed and logged while their routing stays builtin."""
    return parse_percent(os.getenv('BATCH_VENDOR_ROUTING_SHADOW_PERCENT', '0'))


def vendor_routing_allowlisted(uid: str) -> bool:
    """Explicit env owners (a ramp step, never an end state); no cohort-document membership."""
    members = {value.strip() for value in os.getenv('BATCH_VENDOR_ROUTING_UID_ALLOWLIST', '').split(',')}
    return valid_uid(uid) and uid in members


def route_table_raw() -> str | None:
    """The configured table text; unset or blank is ``None`` (serve the builtin table)."""
    raw = os.getenv('BATCH_VENDOR_ROUTE_TABLE', '')
    return raw if raw.strip() else None


def parse_route_table(raw: str | None) -> Any:
    """``None`` (unset) stays ``None``; text that is not a JSON table becomes ``INVALID_PAYLOAD``.

    A literal JSON ``null`` is a set-but-invalid payload, not an unset table: it must serve the
    last valid table, never silently switch to the builtin one.
    """
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return INVALID_PAYLOAD
    return INVALID_PAYLOAD if parsed is None else parsed
