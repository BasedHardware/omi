"""Batch vendor health settings (slice C of all-vendor routing): kill switch and breaker thresholds.

Defaults are the vendorscope-ops 2026-11-01 section 1.4 table, calibrated on the 09-28 Modulate 5xx
outage, the 10-22 Modulate credits outage and the chronic 1-3% baseline. Every value is runtime
config: ``BATCH_VENDOR_HEALTH_THRESHOLDS`` holds a JSON object overriding any subset of fields,
optionally per vendor under ``"vendors"``. Spend caps are route-table values, not settings here.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from dataclasses import dataclass, fields, replace
from typing import Any, Mapping

from config.refactor_modes import default_on

logger = logging.getLogger(__name__)

ENABLED_ENV = 'BATCH_VENDOR_HEALTH_ENABLED'
THRESHOLDS_ENV = 'BATCH_VENDOR_HEALTH_THRESHOLDS'
_VENDORS = frozenset({'modulate', 'soniox'})


def health_enabled() -> bool:
    """Kill switch, on unless false. False answers from the process-local vendor_guard view."""
    return default_on(ENABLED_ENV)


@dataclass(frozen=True)
class Thresholds:
    # Call errors (5xx, connection, timeout, invalid response, abandoned).
    error_degraded_rate: float = 0.20
    error_degraded_window_s: float = 600
    error_degraded_min_n: int = 30
    error_open_rate: float = 0.50
    error_open_window_s: float = 300
    error_open_min_n: int = 20
    # Funds refusals (402, credit-marked 429, organization_balance_exhausted): David-only fix.
    funds_open_count: int = 3
    funds_window_s: float = 300
    # Plain rate limits.
    rate_limit_degraded_count: int = 25  # 5 per minute over 5 minutes
    rate_limit_open_rate: float = 0.50
    rate_limit_open_min_n: int = 20
    rate_limit_window_s: float = 300
    # Validated-empty results: 5x the ~1.1% failed_held baseline.
    empty_degraded_rate: float = 0.055
    empty_window_s: float = 1800
    empty_min_n: int = 50
    # Latency tail: more than ``latency_tail_fraction`` of timed calls slower than the bound is a p95 breach.
    latency_degraded_s: float = 30.0
    latency_open_s: float = 120.0
    latency_window_s: float = 300
    latency_min_n: int = 20
    latency_tail_fraction: float = 0.05
    # Degraded sheds part of new sends (the 10-21 39% class); open sends only probes.
    degraded_admit_fraction: float = 0.5
    # Recovery: one fleet-wide probe per interval after the open window; close after consecutive
    # probe successes once the close window's failure rate is low and no open signal remains.
    open_seconds: float = 30.0
    probe_interval_s: float = 30.0
    close_successes: int = 5
    close_error_rate: float = 0.05
    close_window_s: float = 300
    # Alert line for the daily audio-hour cap; reaching the cap itself makes the route unhealthy.
    cap_alert_fraction: float = 0.9
    # Cross-pod snapshot cadence; an older snapshot falls back to process-local state.
    refresh_seconds: float = 5.0
    stale_seconds: float = 60.0

    def max_window_s(self) -> float:
        return max(
            self.error_degraded_window_s,
            self.error_open_window_s,
            self.funds_window_s,
            self.rate_limit_window_s,
            self.empty_window_s,
            self.latency_window_s,
            self.close_window_s,
        )


_FIELDS = {field.name: field.type for field in fields(Thresholds)}
_FRACTIONS = frozenset(
    {
        'error_degraded_rate',
        'error_open_rate',
        'rate_limit_open_rate',
        'empty_degraded_rate',
        'latency_tail_fraction',
        'degraded_admit_fraction',
        'close_error_rate',
        'cap_alert_fraction',
    }
)
# Bounded so a typo cannot ask the store for days of buckets or make a breaker never trip.
_MAX_WINDOW_S = 3600.0


@dataclass(frozen=True)
class Runway:
    """Operator-entered vendor balance (Modulate has no balance API); runway is computed from our usage."""

    balance_usd: float
    as_of: float  # unix seconds when the balance was read
    price_usd_per_audio_hour: float | None = None  # used only when the route table has no price


@dataclass(frozen=True)
class HealthSettings:
    default: Thresholds
    vendors: Mapping[str, Thresholds]
    runway: Mapping[str, Runway]

    def for_vendor(self, service: str) -> Thresholds:
        return self.vendors.get(service, self.default)


DEFAULT_SETTINGS = HealthSettings(Thresholds(), {}, {})


class ThresholdsInvalid(ValueError):
    """Fixed messages only; config content never reaches logs."""


def _number(name: str, value: Any) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ThresholdsInvalid('nonnegative finite number required')
    if _FIELDS[name] == 'int':
        if not float(value).is_integer() or value < 1:
            raise ThresholdsInvalid('positive integer required')
        return int(value)
    if name in _FRACTIONS and value > 1:
        raise ThresholdsInvalid('fraction above 1')
    if name.endswith('_window_s') and not 60 <= value <= _MAX_WINDOW_S:
        raise ThresholdsInvalid('window outside 60s..1h')
    return float(value)


def _overrides(base: Thresholds, raw: Any) -> Thresholds:
    if not isinstance(raw, Mapping) or not set(raw) <= set(_FIELDS):
        raise ThresholdsInvalid('unknown threshold field')
    merged = replace(base, **{name: _number(name, value) for name, value in raw.items()})
    if merged.error_open_rate < merged.error_degraded_rate or merged.latency_open_s < merged.latency_degraded_s:
        raise ThresholdsInvalid('open bound below degraded bound')
    if merged.stale_seconds < merged.refresh_seconds:
        raise ThresholdsInvalid('stale bound below refresh cadence')
    return merged


def _runway(raw: Any) -> Runway:
    if not isinstance(raw, Mapping) or not {'balance_usd', 'as_of'} <= set(raw) <= {
        'balance_usd',
        'as_of',
        'price_usd_per_audio_hour',
    }:
        raise ThresholdsInvalid('runway requires balance_usd and as_of')
    price = raw.get('price_usd_per_audio_hour')
    values = [raw['balance_usd'], raw['as_of']] + ([] if price is None else [price])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in values):
        raise ThresholdsInvalid('runway numbers must be nonnegative')
    return Runway(float(raw['balance_usd']), float(raw['as_of']), None if price is None else float(price))


def parse_settings(raw: Any) -> HealthSettings:
    if not isinstance(raw, Mapping):
        raise ThresholdsInvalid('thresholds must be an object')
    top = {key: value for key, value in raw.items() if key not in ('vendors', 'runway')}
    default = _overrides(Thresholds(), top)
    vendors_raw = raw.get('vendors', {})
    runway_raw = raw.get('runway', {})
    if not isinstance(vendors_raw, Mapping) or not set(vendors_raw) <= _VENDORS:
        raise ThresholdsInvalid('vendors must map vendor services')
    if not isinstance(runway_raw, Mapping) or not set(runway_raw) <= _VENDORS:
        raise ThresholdsInvalid('runway must map vendor services')
    vendors = {service: _overrides(default, override) for service, override in vendors_raw.items()}
    runway = {service: _runway(entry) for service, entry in runway_raw.items()}
    return HealthSettings(default, vendors, runway)


class _Ladder:
    """Configured -> last valid -> defaults, like the route-table ladder."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_text: str | None = None
        self._last_valid: HealthSettings | None = None
        self._warned = False

    def resolve(self, text: str | None) -> HealthSettings:
        if not text or not text.strip():
            return DEFAULT_SETTINGS
        with self._lock:
            if text == self._last_text and self._last_valid is not None:
                return self._last_valid
            try:
                settings = parse_settings(json.loads(text))
            except (ValueError, TypeError):
                if not self._warned:
                    self._warned = True
                    logger.warning('event=batch_vendor_health_thresholds outcome=invalid fallback=last_valid')
                return self._last_valid or DEFAULT_SETTINGS
            self._last_text, self._last_valid, self._warned = text, settings, False
            return settings


_ladder = _Ladder()


def settings(environ: Mapping[str, str] | None = None) -> HealthSettings:
    return _ladder.resolve((os.environ if environ is None else environ).get(THRESHOLDS_ENV))
