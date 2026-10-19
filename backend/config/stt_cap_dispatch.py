"""Environment-owned funded dispatch rollout; scope is evaluated at each call."""

import logging
import os
from threading import Lock

from config.rollout_cohorts import cohort_admits

LANES = frozenset({'live', 'sync', 'batch'})
# Lane8 must write provider_reason=byok into binding.policy at batch admission
# before this code-owned fence can open. Environment configuration cannot open it.
_BATCH_LANE_READY = False
_logger = logging.getLogger(__name__)
_batch_warning_lock = Lock()
_batch_warning_emitted = False


def _warn_batch_not_ready() -> None:
    global _batch_warning_emitted
    with _batch_warning_lock:
        if not _batch_warning_emitted:
            _batch_warning_emitted = True
            _logger.warning('STT cap batch lane remains disabled pending batch admission readiness')


def enabled() -> bool:
    """Raw legacy switch, for allowance selection; never sufficient admission."""
    return os.getenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false').lower() == 'true'


def execution_admission_configured() -> bool:
    """Host/metric setup only. Per-user work must use execution_admission_enabled."""
    return enabled() or os.getenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false') == 'true'


def selected(uid: str, lane: str) -> bool:
    raw = os.getenv('STT_CAP_DISPATCH_LANES')
    lanes = (
        frozenset({'live'})
        if raw is None or not raw.strip()
        else frozenset(part.strip().lower() for part in raw.split(','))
    )
    # An unknown/empty list token invalidates the whole selection. Never
    # map unknown call-site provenance to a permitted execution lane.
    if not lanes <= LANES:
        return False
    if 'batch' in lanes and not _BATCH_LANE_READY:
        _warn_batch_not_ready()
    return (
        lane in LANES
        and (lane != 'batch' or _BATCH_LANE_READY)
        and lane in lanes
        and cohort_admits(uid, os.getenv('STT_CAP_DISPATCH_COHORT', ''))
    )


def enabled_for(uid: str, lane: str) -> bool:
    return enabled() and selected(uid, lane)


def any_legacy_admission_enabled(uid: str) -> bool:
    """Legacy reporting/config validation only; ladder-only never turns it on."""
    return any(enabled_for(uid, lane) for lane in LANES)


def execution_admission_enabled(uid: str, lane: str) -> bool:
    """Legacy and ladder-only execution share the exact same cohort and lanes."""
    return execution_admission_configured() and selected(uid, lane)


def any_execution_admission_enabled(uid: str) -> bool:
    """Owner-facing backlog/consent surfaces; each dispatch still names its lane."""
    return any(execution_admission_enabled(uid, lane) for lane in LANES)


def hold_lane(metadata: object) -> str | None:
    """Original encrypted custody origin. Pre-origin holds were sync-only.

    source is a device/conversation source, sync_lane is freshness, and neither
    is the dispatch lane. A future/unknown explicit origin must stay paused.
    """
    if not isinstance(metadata, dict):
        return None
    origin = metadata.get('origin', 'sync')
    return origin if isinstance(origin, str) and origin in LANES else None
