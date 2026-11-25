"""Shared leased-recovery contract and process state below caller utilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import math
import re
import threading
import time
from typing import Any, Callable, cast

from database.batch_pipeline_recovery_metrics import (
    CALLER_GAP_SECONDS,
    CUTOFF_AGE_SECONDS,
    PRIMARY_QUERY_SECONDS,
    PRIMARY_SCAN_SUCCESS_TIMESTAMP,
    RECOVERY_COLLECTORS as RECOVERY_COLLECTORS,
    RECOVERY_DISCOVERY_TOTAL,
)

from database.reason_labels import ReasonFamily, reason_label


class RecoveryCaller(StrEnum):
    UNKNOWN = 'unknown'
    PUMP = 'pump_recovery'
    SERVING = 'serving_maintenance'
    RECONCILE = 'serving_reconcile'


def metric_namespace(namespace: str) -> str:
    return namespace if namespace in {'batch_pipeline_dev', 'batch_pipeline_prod'} else 'other'


_LAST_ENTRY: dict[tuple[str, str], float] = {}
_ENTRY_LOCK = threading.Lock()
_FAILURES: dict[str, int] = {}


def primary_failure_generation(namespace: str) -> int:
    with _ENTRY_LOCK:
        return _FAILURES.get(metric_namespace(namespace), 0)


_EVENTS = frozenset(
    {'entry', 'eligible', 'selected', 'pg_attempt', 'primary', 'candidate', 'useful_candidate', 'completed', 'error'}
)


class RecoveryDiscoveryReason(StrEnum):
    ENTRY = 'entry'
    BYPASS = 'bypass'
    UNKNOWN_CALLER = 'unknown_caller'
    POLICY_UNSET = 'policy_unset'
    POLICY_INVALID = 'policy_invalid'
    UNSELECTED = 'unselected'
    DISABLED = 'disabled'
    EXCLUDED = 'excluded'
    COVERAGE_UNKNOWN = 'coverage_unknown'
    SAFETY_SWEEP = 'safety_sweep'
    BACKLOG = 'backlog'
    HINT_INELIGIBLE = 'hint_ineligible'
    INDEX = 'index'
    ERROR = 'error'
    TIMEOUT = 'timeout'
    RETURNED = 'returned'
    TRANSITION = 'transition'
    NO_TRANSITION = 'no_transition'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class RecoveryExposure:
    bps: int

    def __post_init__(self):
        if type(self.bps) is not int or not 0 <= self.bps <= 10000:
            raise ValueError('recovery exposure requires integer BPS in0..10000')

    @classmethod
    def parse(cls, raw: object) -> RecoveryExposure | None:
        if not isinstance(raw, str):
            return None
        match = re.fullmatch(r'role_minute_v1:([0-9]{1,5})', raw)
        if match is None or int(match[1]) > 10000:
            return None
        return cls(int(match[1]))

    def selected(self, namespace: str, caller: RecoveryCaller, wall_time: float) -> bool:
        # One logical namespace/role/UTC-minute unit; independent of replica,
        # process, restart, request and owner. No minute is a metric label.
        if not math.isfinite(wall_time) or wall_time < 0:
            return False
        unit = f'omi:recovery-hints:role-minute:v1:{namespace}:{caller.value}:{int(wall_time // 60)}'
        return int(hashlib.sha256(unit.encode('ascii')).hexdigest(), 16) % 10000 < self.bps


class RecoveryQuery:
    """One actual leased caller entry, including primary-only factory bypasses."""

    def __init__(
        self,
        store: Any,
        now: float,
        limit: int,
        caller: object,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ):
        self.store, self.now, self.limit = store, now, limit
        self.caller = caller if isinstance(caller, RecoveryCaller) else RecoveryCaller.UNKNOWN
        self.namespace = metric_namespace(getattr(store, 'namespace', 'other'))
        self.clock, self.wall_clock = clock, wall_clock
        self.from_pg = False
        self.active = False
        self.entry_wall = math.nan
        self.useful = 0
        self.primary_count = 0
        # A DualStore's canonical due path also owns optional parity. An
        # IndexStore replaces this callback with its forced-primary seam.
        self.fallback: Callable[[], list[str]] = lambda: store.due('leased', now, limit)

    def record_event(self, event: str, reason: str, *, source: str = 'none') -> None:
        RECOVERY_DISCOVERY_TOTAL.labels(
            namespace=self.namespace,
            caller=self.caller.value,
            event=event if event in _EVENTS else 'error',
            source=source if source in {'none', 'primary', 'postgres'} else 'none',
            reason=reason_label(ReasonFamily.FALLBACK, reason, RecoveryDiscoveryReason),
        ).inc()

    def __enter__(self) -> RecoveryQuery:
        self.active = True
        self.record_event('entry', 'entry')
        self.entry_wall = self.wall_clock()
        sampled = self.clock()
        key = self.namespace, self.caller.value
        with _ENTRY_LOCK:
            previous = _LAST_ENTRY.get(key)
            _LAST_ENTRY[key] = sampled
        if previous is not None:
            CALLER_GAP_SECONDS.labels(*key).observe(max(0, sampled - previous))
        return self

    def __exit__(self, kind, value, traceback) -> None:
        self.active = False
        if kind is None and self.from_pg and not self.useful:
            self.record_event('error', 'hint_ineligible', source='postgres')
            raise RuntimeError('leased hints require current-candidate feedback and primary fallback')
        self.record_event(
            'error' if kind else 'completed',
            'error' if kind else 'returned',
            source='postgres' if self.from_pg else ('primary' if self.primary_count else 'none'),
        )

    def primary(self, reason: str, read: Callable[[], list[str]] | None = None) -> list[str]:
        self.from_pg = False
        self.primary_count += 1
        self.record_event('primary', reason, source='primary')
        started = self.clock()
        try:
            rows = (read or self.fallback)()
        except Exception:
            with _ENTRY_LOCK:
                _FAILURES[self.namespace] = _FAILURES.get(self.namespace, 0) + 1
            raise
        finally:
            PRIMARY_QUERY_SECONDS.labels(self.namespace, self.caller.value).observe(max(0, self.clock() - started))
        PRIMARY_SCAN_SUCCESS_TIMESTAMP.labels(self.namespace, 'due_leased').set(self.wall_clock())
        return rows

    def discover(self) -> list[str]:
        age = self.wall_clock() - self.now
        if math.isfinite(age) and age >= 0:
            CUTOFF_AGE_SECONDS.labels(self.namespace, self.caller.value).observe(age)
        gateway = getattr(self.store, 'recovery_due', None)
        if callable(gateway):
            return cast(list[str], gateway(self))
        return self.primary('unknown_caller' if self.caller == RecoveryCaller.UNKNOWN else 'bypass')

    def candidate(self, useful: bool) -> None:
        source = 'postgres' if self.from_pg else 'primary'
        self.record_event('candidate', 'transition' if useful else 'no_transition', source=source)
        if useful:
            self.useful += 1
            self.record_event('useful_candidate', 'transition', source=source)

    def needs_primary(self) -> bool:
        return self.from_pg and self.useful == 0

    def policy_current(self) -> bool:
        wall = self.wall_clock()
        return (
            self.active
            and math.isfinite(self.entry_wall)
            and self.entry_wall >= 0
            and math.isfinite(wall)
            and wall >= 0
            and wall >= self.entry_wall
            and math.isfinite(self.now)
            and wall >= self.now
            and int(wall // 60) == int(self.entry_wall // 60)
        )
