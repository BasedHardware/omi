"""Firestore-authoritative discovery with a small, explicit Postgres hint allowlist.

Only ``due`` for leased/retry/result_ready is admitted. Scheduler recovery
rechecks each job in a Firestore transaction; the ready drain discovers an
owner and runs the existing transactional merge. Missing hints can delay that
work, so each query starts on Firestore and returns to it periodically. There
is no cursor, completion marker, queue gauge or scheduling-priority decision
on this path. In particular, control_candidates must stay on Firestore: an
empty higher-priority answer can permit a lower-priority pull.

The mirror remains responsible for every transaction and mutation. This
wrapper does not create connections, perform backfills or change erasure.
Index reads require an already warm connection; no IAM refresh or dial can
enter the caller. Both the server statement and the synchronous psycopg
network wait have deadlines. A failed connection is discarded by its pool.
Generic production discovery stays on Firestore. The only exception is the
qualified leased-recovery gateway, with explicit bounded-hint exposure and
current-candidate feedback. It makes no complete-copy or backlog claim.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Generator, Iterator
from contextlib import contextmanager
from enum import StrEnum
import logging
import math
import threading
import time
from typing import Any

from prometheus_client import Counter, Gauge

from database import rpc_deadline
from database.jobstore.cohort import production_policy_applies
from database.jobstore.dual_store import DualStore
from database.jobstore.postgres_store import PostgresStore
from database.jobstore.connection import sql
from utils.observability.fallback import record_fallback
from utils.observability.reasons import FallbackReason, ReasonFamily, reason_label
from database.batch_pipeline_recovery_discovery import (
    PRIMARY_SCAN_SUCCESS_TIMESTAMP,
    RecoveryCaller,
    RecoveryExposure,
    RecoveryQuery,
    metric_namespace,
    primary_failure_generation,
)
from utils.staging_fence import jobstore_production_mirror_configured

INDEX_QUERIES = frozenset({'due_leased', 'due_retry', 'due_result_ready'})
_DUE_QUERIES = {'leased': 'due_leased', 'retry': 'due_retry', 'result_ready': 'due_result_ready'}
# Psycopg sends an empty readiness event to its generator on each interval.
# Checking that event bounds a stalled socket without a worker or cancel RPC.
_WAIT_INTERVAL_S = 0.01
logger = logging.getLogger(__name__)


class IndexReadReason(StrEnum):
    UNKNOWN = 'unknown'
    INDEX = 'index'
    SAFETY_SWEEP = 'safety_sweep'
    DISABLED = 'disabled'
    UNSELECTED = 'unselected'
    EXCLUDED = 'excluded'
    ERROR = 'error'
    TIMEOUT = 'timeout'
    COVERAGE_UNKNOWN = 'coverage_unknown'
    BACKLOG = 'backlog'
    HINT_INELIGIBLE = 'hint_ineligible'
    POLICY_UNSET = 'policy_unset'
    POLICY_INVALID = 'policy_invalid'


class IndexReadOutcome(StrEnum):
    UNKNOWN = 'unknown'
    RETURNED = 'returned'
    ERROR = 'error'


class IndexReadSource(StrEnum):
    FIRESTORE = 'firestore'
    POSTGRES = 'postgres'


INDEX_READS_TOTAL = Counter(
    'omi_jobstore_index_reads_total',
    'Discovery answers by source; Postgres returns non-authoritative IDs only.',
    ['query', 'source', 'reason', 'outcome'],
)
INDEX_PRIMARY_SCAN_SUCCESS_TIMESTAMP: Gauge = PRIMARY_SCAN_SUCCESS_TIMESTAMP


def _metric_namespace(namespace: str) -> str:
    return metric_namespace(namespace)


def _count(query: str, source: IndexReadSource, reason: IndexReadReason, outcome: IndexReadOutcome) -> None:
    INDEX_READS_TOTAL.labels(
        query=query if query in INDEX_QUERIES else 'other',
        source=source.value,
        reason=reason_label(ReasonFamily.FALLBACK, reason, IndexReadReason),
        outcome=reason_label(ReasonFamily.FALLBACK, outcome, IndexReadOutcome),
    ).inc()


def _remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError('job store index read deadline exceeded')
    return left


def _deadline_steps(generator: Generator[Any, Any, Any], deadline: float) -> Generator[Any, Any, Any]:
    """Pass through psycopg's readiness protocol, checking every socket wait.

    Connection.wait's polling interval also sends readiness=0 when the socket
    never responds. The driver therefore cannot wait beyond the deadline plus
    one 10ms polling interval. No connection/cancel worker survives the call.
    """
    try:
        _remaining(deadline)
        request = next(generator)
        while True:
            ready = yield request
            _remaining(deadline)
            request = generator.send(ready)
    except StopIteration as result:
        return result.value
    finally:
        generator.close()


@contextmanager
def connection_deadline(conn: Any, deadline: float) -> Iterator[None]:
    # The pool grants exclusive use of this connection. Restore the driver
    # method before returning it; a timeout/error escapes to Pool, which closes
    # it instead. BEGIN, SET, SELECT, COMMIT and any ROLLBACK use this same wait.
    original_wait = conn.wait

    def wait(generator: Generator[Any, Any, Any], interval: float | None = None) -> Any:
        left = _remaining(deadline)
        return original_wait(_deadline_steps(generator, deadline), interval=min(_WAIT_INTERVAL_S, left))

    conn.wait = wait
    try:
        yield
    finally:
        conn.wait = original_wait


class BoundedPostgresReader(PostgresStore):
    """Reuse the serving SQL while bounding every step on a read-only session."""

    def __init__(self, source: PostgresStore, budget_s: float):
        super().__init__(source.namespace, pool=source.pool, customer_client=None)
        self.budget_s = budget_s

    @contextmanager
    def _read_conn(self) -> Iterator[Any]:
        deadline = time.monotonic() + self.budget_s
        outer = rpc_deadline.current()
        if outer is not None:
            deadline = min(deadline, outer)
        with self.pool.connection(timeout=_remaining(deadline), existing_only=True) as conn:
            with connection_deadline(conn, deadline):
                with conn.transaction():
                    conn.execute('SET TRANSACTION READ ONLY')
                    conn.execute(
                        sql()
                        .SQL('SET LOCAL statement_timeout = {}')
                        .format(sql().Literal(max(1, int(_remaining(deadline) * 1000))))
                    )
                    yield conn
                    _remaining(deadline)


class IndexStore:
    """Wrap an existing DualStore; only selected discovery calls may use its copy.

    ``enabled`` is read for each call and again before returning a PG answer,
    so callers can supply a live kill switch. ``clock`` controls sweep cadence
    only; the transport deadline always uses real monotonic time. Sweep state
    is bounded by the three admitted queries and advances only after a
    successful Firestore answer. A failed sweep never silently becomes PG.
    """

    def __init__(
        self,
        mirror: DualStore,
        *,
        enabled_queries: Collection[str],
        enabled: Callable[[], bool] = lambda: True,
        sweep_interval_s: float = 60.0,
        read_budget_s: float = 0.2,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        observe: Callable[[str, tuple[Any, ...], dict[str, Any]], None] | None = None,
        recovery_policy: Callable[[], str] = lambda: '',
    ):
        queries = frozenset(enabled_queries)
        if not queries <= INDEX_QUERIES:
            raise ValueError('only audited index discovery queries may be enabled')
        if not callable(enabled):
            raise ValueError('index enabled must be a live predicate')
        if not math.isfinite(sweep_interval_s) or not 0 < sweep_interval_s <= 60:
            raise ValueError('positive finite index safety sweep interval at most 60 seconds required')
        if not math.isfinite(read_budget_s) or not 0 < read_budget_s <= 5:
            raise ValueError('index read budget must be positive and at most five seconds')
        namespace = getattr(mirror.primary, 'namespace', None)
        if not namespace or namespace != getattr(mirror.shadow, 'namespace', None):
            raise ValueError('primary and discovery index must share one namespace')
        self.mirror = mirror
        self.primary = mirror.primary
        self.shadow = mirror.shadow
        self.namespace = namespace
        self.enabled_queries = queries
        self.enabled = enabled
        self.sweep_interval_s = sweep_interval_s
        self.read_budget_s = read_budget_s
        self._clock = clock
        self._wall_clock = wall_clock
        self._observe = observe
        self._recovery_policy = recovery_policy
        self._last_sweep: dict[str, float] = {}
        self._primary_attempt: dict[str, int] = {}
        self._last_failure_generation: dict[str, int] = {}
        # A full primary leased page is evidence of possible backlog, not
        # completion. Continue canonical per-call recovery until a short page.
        self._leased_backlog = False
        self._sweep_lock = threading.Lock()
        # No connection, credential refresh or other IO during construction.
        self._index = BoundedPostgresReader(mirror.shadow, read_budget_s)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.mirror, name)

    def _primary_due(
        self,
        state: str,
        now: float,
        limit: int,
        query: str,
        reason: IndexReadReason,
        *,
        fallback_reason: FallbackReason | None = None,
    ) -> list[str]:
        started = self._clock()
        failure_generation = primary_failure_generation(self.namespace)
        with self._sweep_lock:
            attempt = self._primary_attempt.get(query, 0) + 1
            self._primary_attempt[query] = attempt
            self._last_sweep.pop(query, None)
        try:
            result = self.primary.due(state, now, limit)
        except Exception:
            with self._sweep_lock:
                if self._primary_attempt.get(query) == attempt:
                    self._last_sweep.pop(query, None)
            _count(query, IndexReadSource.FIRESTORE, reason, IndexReadOutcome.ERROR)
            if fallback_reason is not None:
                self._fallback(fallback_reason, 'exhausted')
            raise
        _count(query, IndexReadSource.FIRESTORE, reason, IndexReadOutcome.RETURNED)
        if query in self.enabled_queries:
            with self._sweep_lock:
                if self._primary_attempt.get(query) == attempt:
                    self._last_sweep[query] = started
                    self._last_failure_generation[query] = failure_generation
                    if query == 'due_leased':
                        self._leased_backlog = len(result) >= max(1, min(limit, 100))
        if query in INDEX_QUERIES:
            INDEX_PRIMARY_SCAN_SUCCESS_TIMESTAMP.labels(namespace=_metric_namespace(self.namespace), query=query).set(
                self._wall_clock()
            )
        if fallback_reason is not None:
            self._fallback(fallback_reason, 'recovered')
        self._observe_due(state, now, limit)
        return result

    def _observe_due(self, state: str, now: float, limit: int) -> None:
        # The mirror owns the bounded async parity queue and its opt-in. This
        # hook must enqueue only; it must never synchronously reread Firestore.
        if self._observe is not None:
            try:
                self._observe('due', (state, now, limit), {})
            except Exception:
                logger.warning('event=jobstore_index_parity outcome=enqueue_error')

    @staticmethod
    def _fallback(reason: FallbackReason, outcome: str) -> None:
        record_fallback(
            component='firestore_read',
            from_mode='postgres_index',
            to_mode='firestore',
            reason=reason.value,
            outcome=outcome,
        )

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        return self._due(state, now, limit)

    def recovery_due(self, recovery: RecoveryQuery) -> list[str]:
        recovery.fallback = lambda: self._primary_due(
            'leased',
            recovery.now,
            recovery.limit,
            'due_leased',
            IndexReadReason.HINT_INELIGIBLE,
        )
        if not recovery.active or recovery.store is not self or recovery.caller == RecoveryCaller.UNKNOWN:
            return recovery.primary('unknown_caller', recovery.fallback)
        if self.namespace not in {'batch_pipeline_dev', 'batch_pipeline_prod'}:
            return recovery.primary('excluded', recovery.fallback)
        return self._due('leased', recovery.now, recovery.limit, recovery=recovery)

    def _due(self, state: str, now: float, limit: int, *, recovery: RecoveryQuery | None = None) -> list[str]:
        query = _DUE_QUERIES.get(state, 'other')

        def primary(reason: IndexReadReason, *, fallback_reason: FallbackReason | None = None) -> list[str]:
            read = lambda: self._primary_due(state, now, limit, query, reason, fallback_reason=fallback_reason)
            return recovery.primary(reason.value, read) if recovery is not None else read()

        if query not in INDEX_QUERIES:
            return primary(IndexReadReason.EXCLUDED)
        if query not in self.enabled_queries:
            return primary(IndexReadReason.UNSELECTED)
        if not self.enabled():
            return primary(IndexReadReason.DISABLED)
        # Owner copies never certify a complete global prefix. Only the
        # audited recovery gateway may accept incomplete bounded hints;
        # generic discovery and every other production query stay primary.
        production = production_policy_applies(self.namespace)
        if production and (recovery is None or not jobstore_production_mirror_configured()):
            return primary(IndexReadReason.COVERAGE_UNKNOWN)
        raw_policy = self._recovery_policy() if recovery is not None else ''
        exposure = RecoveryExposure.parse(raw_policy) if recovery is not None else None
        selected = True
        if recovery is not None:
            if exposure is None or not recovery.policy_current():
                return primary(IndexReadReason.POLICY_INVALID if raw_policy else IndexReadReason.POLICY_UNSET)
            selected = exposure.selected(self.namespace, recovery.caller, recovery.entry_wall)
            if selected:
                recovery.record_event('selected', 'index')
        with self._sweep_lock:
            last = self._last_sweep.get(query)
            backlog = query == 'due_leased' and self._leased_backlog
            if recovery is not None and self._last_failure_generation.get(query) != primary_failure_generation(
                self.namespace
            ):
                last = None
        if backlog:
            return primary(IndexReadReason.BACKLOG)
        if last is None or self._clock() - last >= self.sweep_interval_s:
            return primary(IndexReadReason.SAFETY_SWEEP)
        if recovery is not None:
            recovery.record_event('eligible', 'index')
            if not selected:
                return primary(IndexReadReason.UNSELECTED)
            recovery.record_event('pg_attempt', 'index', source='postgres')
        try:
            # Validate the driver's runtime answer before trusting its shape.
            result: Any = self._index.due(state, now, limit)
        except Exception as exc:
            timeout = isinstance(exc, TimeoutError) or getattr(exc, 'sqlstate', None) == '57014'
            return primary(
                IndexReadReason.TIMEOUT if timeout else IndexReadReason.ERROR,
                fallback_reason=FallbackReason.TIMEOUT if timeout else FallbackReason.UNAVAILABLE,
            )
        if not self.enabled():
            return primary(IndexReadReason.DISABLED)
        if production_policy_applies(self.namespace) and (
            recovery is None or not jobstore_production_mirror_configured()
        ):
            return primary(IndexReadReason.COVERAGE_UNKNOWN)
        if recovery is not None and (self._recovery_policy() != raw_policy or not recovery.policy_current()):
            return primary(IndexReadReason.POLICY_INVALID)
        # SQL may have crossed the safety deadline, or a concurrent primary
        # attempt may have failed. Neither may buy another hint interval.
        with self._sweep_lock:
            last = self._last_sweep.get(query)
            backlog = query == 'due_leased' and self._leased_backlog
            if recovery is not None and self._last_failure_generation.get(query) != primary_failure_generation(
                self.namespace
            ):
                last = None
        if last is None or self._clock() - last >= self.sweep_interval_s or backlog:
            return primary(IndexReadReason.SAFETY_SWEEP)
        if query == 'due_leased' and (
            not isinstance(result, list)
            or not 0 < len(result) < max(1, min(limit, 100))
            or any(not isinstance(key, str) or not key for key in result)
            or len(set(result)) != len(result)
        ):
            return primary(IndexReadReason.HINT_INELIGIBLE)
        if recovery is not None:
            recovery.from_pg = True
        _count(query, IndexReadSource.POSTGRES, IndexReadReason.INDEX, IndexReadOutcome.RETURNED)
        self._observe_due(state, now, limit)
        return result
