"""Cross-pod batch vendor health (slice C): breaker, day-keyed audio caps, Soniox budget latch, runway.

Implements ``vendor_route_contracts.VendorHealth``. Slice B asks ``allows(service)`` before choosing
a vendor route; slice D calls ``reserve`` inside the intent mint and ``record_attempt`` when an
attempt settles. Nothing in production calls this module until those slices wire it, so merging
it changes no routing.

State lives in Redis so every pod sees the same breaker and the same daily usage:

* per-minute outcome buckets (``vh:v1:<service>:m:<minute>``) feed the ops section 1.4 signals:
  call-error rate, funds refusals, rate limits, validated-empty rate and the latency tail;
* one breaker record per vendor (closed or open, reason, opened_at, consecutive probe successes),
  updated with optimistic transactions;
* one fleet-wide half-open probe token per vendor (``SET NX PX``);
* day, month, hour and lifetime audio-second counters, reserved atomically in Lua at intent mint.

``allows`` never touches the network: it answers from a snapshot refreshed in the background every
``refresh_seconds``. A missing or stale snapshot falls back to this pod's process-local copy of
the same state (every write goes to both); only if that fails too does a vendor answer
``STATE_UNAVAILABLE``. A cap or budget reached is ``(False, DAILY_CAP_REACHED |
MONTHLY_BUDGET_REACHED)``: unhealthy, never an error. ``gpu`` is always healthy.

Modulate has no balance API, so runway comes from our own usage: an operator enters the balance
read after a top-up (``runway`` in ``BATCH_VENDOR_HEALTH_THRESHOLDS``), and runway is that balance
minus our metered spend since it was entered, over the trailing-24h spend rate. The spend since
entry is measured from this module's first observation of the entry, so it slightly undercounts
when the entry is made before any pod refreshes.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from prometheus_client import Gauge

from config import batch_pipeline_vendor_health as config
from config.stt_provider_policy import STTServingSurface, provider_is_enabled
from utils.batch_pipeline import vendor_route_contracts as contracts
from utils.batch_pipeline import vendor_route_metrics as metrics
from utils.observability.reasons import VendorAttemptOutcome, VendorHealthReason

logger = logging.getLogger(__name__)

CLOSED, DEGRADED, OPEN, HALF_OPEN = 'closed', 'degraded', 'open', 'half_open'
COUNT_FIELDS = ('n', 'ok', 'err', 'funds', 'rate', 'empty', 'timed', 'slow_degraded', 'slow_open')
FAILURE_FIELDS = frozenset({'err', 'funds', 'rate'})
_FIELD_BY_OUTCOME: Mapping[VendorAttemptOutcome, str] = {
    VendorAttemptOutcome.OK: 'ok',
    VendorAttemptOutcome.SILENCE: 'ok',
    VendorAttemptOutcome.ERROR_5XX: 'err',
    VendorAttemptOutcome.TIMEOUT: 'err',
    VendorAttemptOutcome.INVALID_RESPONSE: 'err',
    VendorAttemptOutcome.ABANDONED: 'err',
    VendorAttemptOutcome.CREDIT_REFUSAL: 'funds',
    VendorAttemptOutcome.RATE_LIMITED: 'rate',
    VendorAttemptOutcome.EMPTY_VALIDATED: 'empty',
}
# RUNNING, SUPERSEDED and UNKNOWN say nothing about the vendor's health and are not counted.

RUNWAY_MAX_HOURS = 24.0 * 365
BUCKET_TTL_SECONDS = 2 * 3600
BREAKER_TTL_SECONDS = 86400
DAY_TTL_SECONDS = 3 * 86400
MONTH_TTL_SECONDS = 40 * 86400
HOUR_TTL_SECONDS = 26 * 3600
REDIS_TIMEOUT_SECONDS = 0.5

# Proposed to slice A for vendor_route_metrics (bus 0861bb); same prefix, so already kept by GMP.
SPEND_RATE = Gauge(
    'omi_batch_pipeline_vendor_spend_usd_per_hour',
    'Trailing-24h batch vendor spend rate from our own metered usage',
    ['provider'],
)
RUNWAY_HOURS = Gauge(
    'omi_batch_pipeline_vendor_runway_hours',
    'Operator-entered vendor balance minus our metered spend since, over the spend rate',
    ['provider'],
)


def _provider(value: object) -> str:
    """Closed provider label (reason-label ratchet CLOSED_HELPERS): VENDOR_SERVICES else 'unknown'."""
    return value if isinstance(value, str) and value in contracts.VENDOR_SERVICES else 'unknown'


# --- pure signal evaluation -----------------------------------------------------------------------


@dataclass(frozen=True)
class Counts:
    n: int = 0
    ok: int = 0
    err: int = 0
    funds: int = 0
    rate: int = 0
    empty: int = 0
    timed: int = 0
    slow_degraded: int = 0
    slow_open: int = 0


Buckets = Mapping[int, Mapping[str, int]]


def increments(
    outcome: VendorAttemptOutcome, latency_seconds: float | None, t: config.Thresholds
) -> dict[str, int] | None:
    """Bucket fields one settled attempt adds, or None when the outcome is not a health signal."""
    name = _FIELD_BY_OUTCOME.get(outcome)
    if name is None:
        return None
    fields = {'n': 1, name: 1}
    if latency_seconds is not None and latency_seconds >= 0:
        fields['timed'] = 1
        if latency_seconds > t.latency_degraded_s:
            fields['slow_degraded'] = 1
        if latency_seconds > t.latency_open_s:
            fields['slow_open'] = 1
    return fields


def window(buckets: Buckets, now: float, seconds: float) -> Counts:
    """Sum of the whole-minute buckets inside the trailing window (current minute included)."""
    first, last = int((now - seconds) // 60) + 1, int(now // 60)
    totals = dict.fromkeys(COUNT_FIELDS, 0)
    for minute, fields in buckets.items():
        if first <= minute <= last:
            for name in COUNT_FIELDS:
                totals[name] += int(fields.get(name, 0))
    return Counts(**totals)


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def assess(buckets: Buckets, now: float, t: config.Thresholds) -> tuple[str, VendorHealthReason]:
    """The trip signal the windows show now: OPEN, DEGRADED or CLOSED, with the reason."""
    funds = window(buckets, now, t.funds_window_s)
    if funds.funds >= t.funds_open_count:
        return OPEN, VendorHealthReason.FUNDS_REFUSAL
    errors = window(buckets, now, t.error_open_window_s)
    if errors.n >= t.error_open_min_n and _rate(errors.err, errors.n) >= t.error_open_rate:
        return OPEN, VendorHealthReason.BREAKER_OPEN
    limits = window(buckets, now, t.rate_limit_window_s)
    if limits.n >= t.rate_limit_open_min_n and _rate(limits.rate, limits.n) >= t.rate_limit_open_rate:
        return OPEN, VendorHealthReason.RATE_LIMITED
    latency = window(buckets, now, t.latency_window_s)
    slow_enough = latency.timed >= t.latency_min_n
    if slow_enough and _rate(latency.slow_open, latency.timed) > t.latency_tail_fraction:
        return OPEN, VendorHealthReason.BREAKER_OPEN
    if limits.rate >= t.rate_limit_degraded_count:
        return DEGRADED, VendorHealthReason.RATE_LIMITED
    errors = window(buckets, now, t.error_degraded_window_s)
    if errors.n >= t.error_degraded_min_n and _rate(errors.err, errors.n) >= t.error_degraded_rate:
        return DEGRADED, VendorHealthReason.DEGRADED
    empties = window(buckets, now, t.empty_window_s)
    if empties.n >= t.empty_min_n and _rate(empties.empty, empties.n) > t.empty_degraded_rate:
        return DEGRADED, VendorHealthReason.DEGRADED
    if slow_enough and _rate(latency.slow_degraded, latency.timed) > t.latency_tail_fraction:
        return DEGRADED, VendorHealthReason.DEGRADED
    return CLOSED, VendorHealthReason.HEALTHY


@dataclass(frozen=True)
class BreakerRecord:
    """The latched part of the breaker. Degraded is never latched: it is read from the windows."""

    state: str = CLOSED  # CLOSED or OPEN
    reason: VendorHealthReason = VendorHealthReason.HEALTHY
    opened_at: float = 0.0
    successes: int = 0  # consecutive successes since the last failure while open

    def to_raw(self) -> dict[str, str]:
        return {
            'state': self.state,
            'reason': self.reason.value,
            'opened_at': repr(self.opened_at),
            'successes': str(self.successes),
        }

    @classmethod
    def from_raw(cls, raw: Mapping[Any, Any]) -> 'BreakerRecord':
        decoded = {_text(key): _text(value) for key, value in raw.items()}
        if not decoded:
            return cls()
        state = decoded.get('state')
        reason = VendorHealthReason(decoded.get('reason', ''))
        if state not in (CLOSED, OPEN) or reason is VendorHealthReason.UNKNOWN:
            raise ValueError('malformed breaker record')
        return cls(state, reason, float(decoded.get('opened_at', 0)), int(decoded.get('successes', 0)))


def advance(
    record: BreakerRecord, buckets: Buckets, now: float, t: config.Thresholds, event: str | None = None
) -> BreakerRecord:
    """Next breaker record after ``event`` (a bucket field just recorded) or a plain refresh.

    Closed opens on any OPEN signal. Open re-arms its window on every failure (a failed half-open
    probe waits another full window), counts consecutive successes, and closes once enough probes
    succeeded, no OPEN signal remains and the close window's failure rate is under the bound.
    """
    trip, reason = assess(buckets, now, t)
    if record.state == CLOSED:
        return BreakerRecord(OPEN, reason, now, 0) if trip == OPEN else record
    if event in FAILURE_FIELDS:
        record = replace(record, opened_at=now, successes=0, reason=reason if trip == OPEN else record.reason)
    elif event == 'ok':
        record = replace(record, successes=record.successes + 1)
    elif event == 'empty':
        # Validated-empty is a failover outcome: it breaks the consecutive-success streak.
        record = replace(record, successes=0)
    recent = window(buckets, now, t.close_window_s)
    failure_rate = _rate(recent.err + recent.funds + recent.rate, recent.n)
    if record.successes >= t.close_successes and trip != OPEN and failure_rate < t.close_error_rate:
        return BreakerRecord()
    return record


# --- stores ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Usage:
    day_seconds: float = 0.0
    month_seconds: float = 0.0
    last24h_seconds: float = 0.0
    total_seconds: float = 0.0


RESERVED, DAY_CAP, MONTH_CAP = 1, 0, 2


class HealthStore(Protocol):
    def record(self, service: str, fields: Mapping[str, int], now: float) -> None: ...
    def buckets(self, service: str, now: float, seconds: float) -> dict[int, dict[str, int]]: ...
    def update_breaker(self, service: str, step: Callable[[BreakerRecord], BreakerRecord]) -> BreakerRecord: ...
    def try_probe(self, service: str, now: float, interval: float) -> bool: ...
    def reserve(
        self, service: str, seconds: float, now: float, day_cap: float | None, month_cap: float | None
    ) -> int: ...
    def usage(self, service: str, now: float) -> Usage: ...
    def anchor(self, service: str, as_of: float) -> float: ...


def _day(now: float) -> int:
    return int(now // 86400)


def _month(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime('%Y%m')


def _hours(now: float) -> range:
    current = int(now // 3600)
    return range(current - 23, current + 1)


def _text(value: Any) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _over(used: float, cost: float, cap: float | None) -> bool:
    return cap is not None and used + cost > cap


class MemoryStore:
    """Process-local twin of ``RedisStore``: the fallback state and the test double."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, dict[int, dict[str, int]]] = {}
        self._breakers: dict[str, BreakerRecord] = {}
        self._probes: dict[str, float] = {}
        self._usage: dict[tuple[str, str], float] = {}
        self._anchors: dict[tuple[str, float], float] = {}

    def record(self, service: str, fields: Mapping[str, int], now: float) -> None:
        with self._lock:
            per_service = self._buckets.setdefault(service, {})
            bucket = per_service.setdefault(int(now // 60), {})
            for name, value in fields.items():
                bucket[name] = bucket.get(name, 0) + value
            horizon = int((now - BUCKET_TTL_SECONDS) // 60)
            for minute in [minute for minute in per_service if minute < horizon]:
                del per_service[minute]

    def buckets(self, service: str, now: float, seconds: float) -> dict[int, dict[str, int]]:
        first = int((now - seconds) // 60) + 1
        with self._lock:
            return {
                minute: dict(fields) for minute, fields in self._buckets.get(service, {}).items() if minute >= first
            }

    def update_breaker(self, service: str, step: Callable[[BreakerRecord], BreakerRecord]) -> BreakerRecord:
        with self._lock:
            record = self._breakers[service] = step(self._breakers.get(service, BreakerRecord()))
            return record

    def try_probe(self, service: str, now: float, interval: float) -> bool:
        with self._lock:
            if now < self._probes.get(service, float('-inf')):
                return False
            self._probes[service] = now + interval
            return True

    def reserve(self, service: str, seconds: float, now: float, day_cap: float | None, month_cap: float | None) -> int:
        day, month = (service, f'd{_day(now)}'), (service, f'm{_month(now)}')
        with self._lock:
            if _over(self._usage.get(month, 0.0), seconds, month_cap):
                return MONTH_CAP
            if _over(self._usage.get(day, 0.0), seconds, day_cap):
                return DAY_CAP
            for key in (day, month, (service, f'h{int(now // 3600)}'), (service, 'total')):
                self._usage[key] = self._usage.get(key, 0.0) + seconds
            return RESERVED

    def usage(self, service: str, now: float) -> Usage:
        with self._lock:
            get = lambda key: self._usage.get((service, key), 0.0)  # noqa: E731
            return Usage(
                get(f'd{_day(now)}'),
                get(f'm{_month(now)}'),
                sum(get(f'h{hour}') for hour in _hours(now)),
                get('total'),
            )

    def anchor(self, service: str, as_of: float) -> float:
        with self._lock:
            return self._anchors.setdefault((service, as_of), self._usage.get((service, 'total'), 0.0))


# Atomic across pods: refuse at either cap, else count the reservation on every usage key.
_RESERVE_LUA = """
local cost = tonumber(ARGV[1])
local day_cap, month_cap = tonumber(ARGV[2]), tonumber(ARGV[3])
local day = tonumber(redis.call('GET', KEYS[1]) or '0')
local month = tonumber(redis.call('GET', KEYS[2]) or '0')
if month_cap >= 0 and month + cost > month_cap then return 2 end
if day_cap >= 0 and day + cost > day_cap then return 0 end
redis.call('INCRBYFLOAT', KEYS[1], cost)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]))
redis.call('INCRBYFLOAT', KEYS[2], cost)
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[5]))
redis.call('INCRBYFLOAT', KEYS[3], cost)
redis.call('EXPIRE', KEYS[3], tonumber(ARGV[6]))
redis.call('INCRBYFLOAT', KEYS[4], cost)
return 1
"""


class RedisStore:
    """Shared state. Every method may raise; ``VendorHealthService`` catches and falls back."""

    PREFIX = 'vh:v1'

    def __init__(self, client: Any) -> None:
        self.client = client

    def _key(self, service: str, suffix: str) -> str:
        return f'{self.PREFIX}:{service}:{suffix}'

    def record(self, service: str, fields: Mapping[str, int], now: float) -> None:
        key = self._key(service, f'm:{int(now // 60)}')
        pipe = self.client.pipeline(transaction=False)
        for name, value in fields.items():
            pipe.hincrby(key, name, value)
        pipe.expire(key, BUCKET_TTL_SECONDS)
        pipe.execute()

    def buckets(self, service: str, now: float, seconds: float) -> dict[int, dict[str, int]]:
        minutes = list(range(int((now - seconds) // 60) + 1, int(now // 60) + 1))
        pipe = self.client.pipeline(transaction=False)
        for minute in minutes:
            pipe.hgetall(self._key(service, f'm:{minute}'))
        return {
            minute: {_text(name): int(value) for name, value in raw.items()}
            for minute, raw in zip(minutes, pipe.execute())
            if raw
        }

    def update_breaker(self, service: str, step: Callable[[BreakerRecord], BreakerRecord]) -> BreakerRecord:
        from redis.exceptions import WatchError

        key = self._key(service, 'breaker')
        for _ in range(5):
            with self.client.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    current = BreakerRecord.from_raw(pipe.hgetall(key))
                    nxt = step(current)
                    if nxt == current:
                        pipe.unwatch()
                        return current
                    pipe.multi()
                    pipe.hset(key, mapping=nxt.to_raw())
                    pipe.expire(key, BREAKER_TTL_SECONDS)
                    pipe.execute()
                    return nxt
                except WatchError:
                    continue
        raise RuntimeError('breaker update contended')

    def try_probe(self, service: str, now: float, interval: float) -> bool:
        return bool(self.client.set(self._key(service, 'probe'), '1', nx=True, px=max(1, int(interval * 1000))))

    def reserve(self, service: str, seconds: float, now: float, day_cap: float | None, month_cap: float | None) -> int:
        keys = [
            self._key(service, f'd:{_day(now)}'),
            self._key(service, f'mo:{_month(now)}'),
            self._key(service, f'h:{int(now // 3600)}'),
            self._key(service, 'total'),
        ]
        args = [
            seconds,
            -1 if day_cap is None else day_cap,
            -1 if month_cap is None else month_cap,
            DAY_TTL_SECONDS,
            MONTH_TTL_SECONDS,
            HOUR_TTL_SECONDS,
        ]
        result = int(self.client.eval(_RESERVE_LUA, len(keys), *keys, *args))
        if result not in (RESERVED, DAY_CAP, MONTH_CAP):
            raise ValueError('invalid reserve response')
        return result

    def usage(self, service: str, now: float) -> Usage:
        hours = list(_hours(now))
        keys = [self._key(service, f'd:{_day(now)}'), self._key(service, f'mo:{_month(now)}')]
        keys += [self._key(service, f'h:{hour}') for hour in hours] + [self._key(service, 'total')]
        values = [float(_text(value)) if value is not None else 0.0 for value in self.client.mget(keys)]
        return Usage(values[0], values[1], sum(values[2:-1]), values[-1])

    def anchor(self, service: str, as_of: float) -> float:
        key = self._key(service, f'anchor:{int(as_of)}')
        total = self.client.get(self._key(service, 'total'))
        self.client.set(key, _text(total) if total is not None else '0', nx=True, ex=MONTH_TTL_SECONDS)
        value = self.client.get(key)
        return float(_text(value)) if value is not None else 0.0


# --- service --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class View:
    at: float
    state: str  # CLOSED, DEGRADED or OPEN
    reason: VendorHealthReason
    probe_eligible: bool
    usage: Usage


def _builtin_routes() -> Mapping[str, contracts.RouteConfig]:
    return contracts.BUILTIN_TABLE.routes


def _admitted(service: str) -> bool:
    return service in contracts.VENDOR_SERVICES and provider_is_enabled(service, STTServingSurface.PRERECORDED)


def _legacy_view(service: str) -> tuple[bool, VendorHealthReason]:
    """Kill-switch answer: today's process-local Modulate guard; nothing gates other vendors."""
    if service != contracts.MODULATE:
        return True, VendorHealthReason.HEALTHY
    from utils.stt import vendor_guard

    if vendor_guard.breaker_refuses(vendor_guard.ENDPOINT_STT):
        if vendor_guard.breaker_budget_exhausted(vendor_guard.ENDPOINT_STT):
            return False, VendorHealthReason.FUNDS_REFUSAL
        return False, VendorHealthReason.BREAKER_OPEN
    return True, VendorHealthReason.HEALTHY


class VendorHealthService:
    """``VendorHealth`` for the batch provider route. One per process (``get_vendor_health``).

    ``routes`` returns the active route table's route configs (slice B injects its ladder); caps,
    budgets and prices come from there. ``shared`` is the cross-pod store, or None for local only.
    """

    def __init__(
        self,
        *,
        shared: HealthStore | None,
        local: HealthStore | None = None,
        routes: Callable[[], Mapping[str, contracts.RouteConfig]] = _builtin_routes,
        settings: Callable[[], config.HealthSettings] = config.settings,
        enabled: Callable[[], bool] = config.health_enabled,
        clock: Callable[[], float] = time.time,
        rng: Callable[[], float] = random.random,
        background: bool = True,
    ) -> None:
        self.shared, self.local = shared, local or MemoryStore()
        self.routes, self.settings, self.enabled = routes, settings, enabled
        self.clock, self.rng, self.background = clock, rng, background
        self._lock = threading.Lock()
        self._views: dict[str, View] = {}
        # Fleet probe tokens this pod won, by service: (won_at, interval). Spent once, or lapsed
        # with the token's own interval, so a late consumer cannot add a second probe per interval.
        self._probe_ready: dict[str, tuple[float, float]] = {}
        self._refreshing = False
        self._refreshed_at = float('-inf')

    # -- VendorHealth ---------------------------------------------------------------------------

    def allows(self, service: str) -> tuple[bool, VendorHealthReason]:
        allowed, reason = self._allows(service)
        metrics.health_decision(service, reason)
        return allowed, reason

    def _allows(self, service: str) -> tuple[bool, VendorHealthReason]:
        if service == contracts.GPU:
            return True, VendorHealthReason.HEALTHY
        if not _admitted(service):
            return False, VendorHealthReason.NOT_ADMITTED
        try:
            if not self.enabled():
                return _legacy_view(service)
            t = self.settings().for_vendor(service)
            view, probe = self._current_view(service, t)
            capped = self._cap_reason(service, view.usage)
        except Exception as error:
            logger.warning(
                'event=batch_vendor_health outcome=state_unavailable exception_type=%s', type(error).__name__
            )
            return False, VendorHealthReason.STATE_UNAVAILABLE
        if capped is not None:
            metrics.cap_hit(service, capped)
            return False, capped
        if view.state == OPEN:
            if view.probe_eligible and probe():
                return True, VendorHealthReason.HALF_OPEN_PROBE
            return False, view.reason
        if view.state == DEGRADED:
            if self.rng() < t.degraded_admit_fraction:
                return True, VendorHealthReason.DEGRADED
            return False, view.reason
        return True, VendorHealthReason.HEALTHY

    # -- slice D hooks ---------------------------------------------------------------------------

    def reserve(self, service: str, audio_seconds: float) -> tuple[bool, VendorHealthReason]:
        """Count ``audio_seconds`` against today's cap and the month budget, atomically across pods.

        Called inside the intent mint. No refund: an unbilled refusal still spent the reservation,
        which can only make the cap conservative. Never raises.
        """
        if service == contracts.GPU:
            return True, VendorHealthReason.HEALTHY
        if not _admitted(service):
            return False, VendorHealthReason.NOT_ADMITTED
        try:
            if not self.enabled():
                return True, VendorHealthReason.HEALTHY
            seconds = max(0.0, float(audio_seconds))
            now = self.clock()
            day_cap, month_cap = self._caps(service)
        except Exception:
            return False, VendorHealthReason.STATE_UNAVAILABLE
        result = None
        if self.shared is not None:
            try:
                result = self.shared.reserve(service, seconds, now, day_cap, month_cap)
            except Exception as error:
                logger.warning(
                    'event=batch_vendor_reserve outcome=shared_failed exception_type=%s', type(error).__name__
                )
        if result is None:
            if day_cap is not None or month_cap is not None:
                # One pod cannot enforce a fleet cap: hold the unit (or take GPU) rather than overspend.
                return False, VendorHealthReason.STATE_UNAVAILABLE
            result = RESERVED
        if result == RESERVED:
            try:
                # This pod's copy feeds the process-local fallback view and its gauges.
                self.local.reserve(service, seconds, now, None, None)
            except Exception:
                pass
        if result == MONTH_CAP:
            metrics.cap_hit(service, VendorHealthReason.MONTHLY_BUDGET_REACHED)
            return False, VendorHealthReason.MONTHLY_BUDGET_REACHED
        if result == DAY_CAP:
            metrics.cap_hit(service, VendorHealthReason.DAILY_CAP_REACHED)
            return False, VendorHealthReason.DAILY_CAP_REACHED
        return True, VendorHealthReason.HEALTHY

    def record_attempt(
        self,
        service: str,
        outcome: VendorAttemptOutcome,
        *,
        latency_seconds: float | None = None,
    ) -> None:
        """Feed one settled attempt's outcome into the breaker windows. Never raises."""
        try:
            if service not in contracts.VENDOR_SERVICES or not self.enabled():
                return
            t = self.settings().for_vendor(service)
            fields = increments(VendorAttemptOutcome(outcome), latency_seconds, t)
            if fields is None:
                return
            event = next(name for name in fields if name not in ('n', 'timed', 'slow_degraded', 'slow_open'))
            now = self.clock()
        except Exception:
            return
        for store in (self.local, self.shared):
            if store is None:
                continue
            try:
                store.record(service, fields, now)
                buckets = store.buckets(service, now, t.max_window_s())
                store.update_breaker(service, lambda record: advance(record, buckets, now, t, event))
            except Exception as error:
                logger.warning('event=batch_vendor_record outcome=store_failed exception_type=%s', type(error).__name__)
        if self.shared is not None:
            self._refresh_one(service, t, now)

    # -- snapshots -------------------------------------------------------------------------------

    def refresh(self) -> None:
        """Refresh every vendor's shared snapshot and the health gauges. Never raises."""
        try:
            settings = self.settings()
            now = self.clock()
            for service in sorted(contracts.VENDOR_SERVICES):
                try:
                    self._refresh_one(service, settings.for_vendor(service), now)
                    self._export(service, settings, now)
                except Exception as error:
                    logger.warning(
                        'event=batch_vendor_refresh outcome=export_failed exception_type=%s', type(error).__name__
                    )
        except Exception as error:
            logger.warning('event=batch_vendor_refresh outcome=failed exception_type=%s', type(error).__name__)
        finally:
            with self._lock:
                self._refreshing = False
                self._refreshed_at = self.clock()

    def _refresh_one(self, service: str, t: config.Thresholds, now: float) -> None:
        if self.shared is None:
            return
        try:
            view = self._evaluate(self.shared, service, t, now)
            with self._lock:
                holding = self._probe_live(service, now)
            probe = (
                view.state == OPEN
                and view.probe_eligible
                and not holding
                and self.shared.try_probe(service, now, t.probe_interval_s)
            )
        except Exception as error:
            logger.warning('event=batch_vendor_refresh outcome=shared_failed exception_type=%s', type(error).__name__)
            with self._lock:
                self._views.pop(service, None)
            return
        with self._lock:
            self._views[service] = view
            if probe:
                self._probe_ready[service] = (now, t.probe_interval_s)
            elif view.state != OPEN:
                self._probe_ready.pop(service, None)

    def _evaluate(self, store: HealthStore, service: str, t: config.Thresholds, now: float) -> View:
        buckets = store.buckets(service, now, t.max_window_s())
        record = store.update_breaker(service, lambda current: advance(current, buckets, now, t))
        usage = store.usage(service, now)
        if record.state == OPEN:
            return View(now, OPEN, record.reason, now - record.opened_at >= t.open_seconds, usage)
        trip, reason = assess(buckets, now, t)
        return View(now, DEGRADED if trip == DEGRADED else CLOSED, reason, False, usage)

    def _current_view(self, service: str, t: config.Thresholds) -> tuple[View, Callable[[], bool]]:
        now = self.clock()
        self._maybe_refresh(now, t)
        with self._lock:
            view = self._views.get(service)
        if view is not None and now - view.at <= t.stale_seconds:
            return view, lambda: self._take_probe(service)
        local = self._evaluate(self.local, service, t, now)
        return local, lambda: self.local.try_probe(service, now, t.probe_interval_s)

    def _probe_live(self, service: str, now: float) -> bool:
        """Caller holds ``_lock``. True while a won token is unspent and inside its interval."""
        won = self._probe_ready.get(service)
        if won is None:
            return False
        if now - won[0] >= won[1]:
            del self._probe_ready[service]
            return False
        return True

    def _take_probe(self, service: str) -> bool:
        now = self.clock()
        with self._lock:
            if self._probe_live(service, now):
                del self._probe_ready[service]
                return True
            return False

    def _maybe_refresh(self, now: float, t: config.Thresholds) -> None:
        with self._lock:
            if self._refreshing or now - self._refreshed_at < t.refresh_seconds:
                return
            self._refreshing = True
        if not self.background:
            self.refresh()
            return
        try:
            threading.Thread(target=self.refresh, name='batch-vendor-health', daemon=True).start()
        except Exception:
            with self._lock:
                self._refreshing = False

    # -- caps and gauges -------------------------------------------------------------------------

    def _caps(self, service: str) -> tuple[float | None, float | None]:
        """(day cap seconds, month budget seconds); a budget without a price fails closed at zero."""
        route = self.routes().get(service)
        if route is None:
            return None, None
        day = None if route.daily_audio_hours_cap is None else route.daily_audio_hours_cap * 3600
        month = None
        if route.monthly_budget_usd is not None:
            price = route.price_usd_per_audio_hour
            month = 0.0 if not price else route.monthly_budget_usd / price * 3600
        return day, month

    def _cap_reason(self, service: str, usage: Usage) -> VendorHealthReason | None:
        day_cap, month_cap = self._caps(service)
        if month_cap is not None and usage.month_seconds >= month_cap:
            return VendorHealthReason.MONTHLY_BUDGET_REACHED
        if day_cap is not None and usage.day_seconds >= day_cap:
            return VendorHealthReason.DAILY_CAP_REACHED
        return None

    def _export(self, service: str, settings: config.HealthSettings, now: float) -> None:
        with self._lock:
            view = self._views.get(service)
        store: HealthStore = self.shared if view is not None and self.shared is not None else self.local
        if view is None:
            view = self._evaluate(self.local, service, settings.for_vendor(service), now)
        metrics.breaker_state(service, HALF_OPEN if view.state == OPEN and view.probe_eligible else view.state)
        route = self.routes().get(service)
        cap = None if route is None else route.daily_audio_hours_cap
        metrics.audio_hours(service, view.usage.day_seconds / 3600, cap)
        runway = settings.runway.get(service)
        price = route.price_usd_per_audio_hour if route is not None else None
        if price is None and runway is not None:
            price = runway.price_usd_per_audio_hour
        if price is None:
            return
        spend_rate = view.usage.last24h_seconds / 3600 * price / 24
        SPEND_RATE.labels(provider=_provider(service)).set(spend_rate)
        if runway is None:
            return
        spent = max(0.0, view.usage.total_seconds - store.anchor(service, runway.as_of)) / 3600 * price
        remaining = max(0.0, runway.balance_usd - spent)
        hours = min(RUNWAY_MAX_HOURS, remaining / spend_rate) if spend_rate > 0 else RUNWAY_MAX_HOURS
        RUNWAY_HOURS.labels(provider=_provider(service)).set(hours)


_service: VendorHealthService | None = None
_service_lock = threading.Lock()


def get_vendor_health(routes: Callable[[], Mapping[str, contracts.RouteConfig]] | None = None) -> VendorHealthService:
    """The process's service. Redis client creation failure leaves it process-local only."""
    global _service
    with _service_lock:
        if _service is None:
            shared: HealthStore | None
            try:
                from database.redis_connection import create_bounded_redis_client

                shared = RedisStore(create_bounded_redis_client(REDIS_TIMEOUT_SECONDS))
            except Exception as error:
                logger.warning('event=batch_vendor_health outcome=local_only exception_type=%s', type(error).__name__)
                shared = None
            _service = VendorHealthService(shared=shared)
        if routes is not None:
            _service.routes = routes
        return _service
