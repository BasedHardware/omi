"""Funded dispatch rollout; runtime cohort resolution is injected by the host."""

from config.refactor_switches import default_off as rollout_default_off
from config.refactor_modes import default_on

import logging
import os
from threading import Lock
from typing import Callable

from config.rollout_cohorts import cohort_admits, parse_cohort

LANES = frozenset({'live', 'sync', 'batch'})
# Legacy full batch rollout fence. Offline allowance refusal does not depend on
# selecting this scope; admission-time BYOK policy remains authoritative.
_BATCH_LANE_READY = False
_logger = logging.getLogger(__name__)
_batch_warning_lock = Lock()
_batch_warning_emitted = False
_recovery_warning_lock = Lock()
_recovery_warning_emitted = False
_cohort_resolver: Callable[[], str] | None = None


def configure_cohort_resolver(resolver: Callable[[], str]) -> None:
    global _cohort_resolver
    _cohort_resolver = resolver


def cohort_tokens() -> str:
    """Pure env fallback before composition; configured resolvers never wait for IO."""
    return _cohort_resolver() if _cohort_resolver is not None else os.getenv('STT_CAP_DISPATCH_COHORT', '')


def _warn_batch_not_ready() -> None:
    global _batch_warning_emitted
    with _batch_warning_lock:
        if not _batch_warning_emitted:
            _batch_warning_emitted = True
            _logger.warning('STT cap batch lane remains disabled pending batch admission readiness')


def enabled() -> bool:
    """Raw legacy switch, for allowance selection; never sufficient admission."""
    return rollout_default_off(
        'STT_CAP_DISPATCH_ENFORCEMENT', os.getenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false').lower() == 'true'
    )


def execution_admission_configured() -> bool:
    """Host/metric setup only. Per-user work must use execution_admission_enabled."""
    return enabled() or rollout_default_off(
        'LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', os.getenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'false') == 'true'
    )


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
        and cohort_admits(uid, cohort_tokens())
    )


def enabled_for(uid: str, lane: str) -> bool:
    return enabled() and selected(uid, lane)


def any_legacy_admission_enabled(uid: str) -> bool:
    """Legacy reporting/config validation only; ladder-only never turns it on."""
    return any(enabled_for(uid, lane) for lane in LANES)


def offline_enforcement_enabled(lane: str | None) -> bool:
    """Ship existing sync/batch allowance enforcement on; never widen live scope."""
    return lane in {'sync', 'batch'} and default_on('STT_CAP_OFFLINE_ENFORCEMENT')


def offline_admission_enabled(uid: str, lane: str) -> bool:
    """Sync/batch spend fails closed independently of the legacy live rollout."""
    return bool(uid) and (offline_enforcement_enabled(lane) or execution_admission_enabled(uid, lane))


def execution_admission_enabled(uid: str, lane: str) -> bool:
    """Legacy and ladder-only execution share the exact same cohort and lanes."""
    return execution_admission_configured() and selected(uid, lane)


def any_execution_admission_enabled(uid: str) -> bool:
    """Owner-facing backlog/consent surfaces; each dispatch still names its lane."""
    return any(execution_admission_enabled(uid, lane) for lane in LANES)


def _recovery_cohort_state(raw: str | None) -> str:
    global _recovery_warning_emitted
    if raw is None:
        return 'unset'
    if parse_cohort(raw) is not None:
        return 'set'
    with _recovery_warning_lock:
        if not _recovery_warning_emitted:
            _recovery_warning_emitted = True
            _logger.warning('Malformed STT cap recovery cohort; denying all recovery')
    return 'malformed'


def recovery_cohort_state() -> str:
    """Low-cardinality effective env state; never expose the private tokens."""
    return _recovery_cohort_state(os.getenv('STT_CAP_RECOVERY_COHORT'))


def recovery_cohort_admits(uid: str) -> bool:
    """Additional filter only; callers must also require dispatch admission."""
    raw = os.getenv('STT_CAP_RECOVERY_COHORT')
    state = _recovery_cohort_state(raw)
    return state == 'unset' or state == 'set' and cohort_admits(uid, raw)


def recovery_admission_enabled(uid: str, lane: str) -> bool:
    """Additional intersection only: listen/capture admission stays unchanged."""
    return recovery_cohort_admits(uid) and execution_admission_enabled(uid, lane)


def any_recovery_admission_enabled(uid: str) -> bool:
    """Gate owner visits, consent and wakes before acquiring recovery work."""
    return recovery_cohort_admits(uid) and any_execution_admission_enabled(uid)


def hold_lane(metadata: object) -> str | None:
    """Original encrypted custody origin. Pre-origin holds were sync-only.

    source is a device/conversation source, sync_lane is freshness, and neither
    is the dispatch lane. A future/unknown explicit origin must stay paused.
    """
    if not isinstance(metadata, dict):
        return None
    origin = metadata.get('origin', 'sync')
    return origin if isinstance(origin, str) and origin in LANES else None
