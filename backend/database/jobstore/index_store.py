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

from prometheus_client import Counter

from database import rpc_deadline
from database.jobstore.dual_store import DualStore
from database.jobstore.postgres_store import PostgresStore
from utils.observability.fallback import record_fallback
from utils.observability.reasons import FallbackReason, ReasonFamily, reason_label

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
                    conn.execute(f'SET LOCAL statement_timeout = {max(1, int(_remaining(deadline) * 1000))}')
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
        observe: Callable[[str, tuple[Any, ...], dict[str, Any]], None] | None = None,
    ):
        queries = frozenset(enabled_queries)
        if not queries <= INDEX_QUERIES:
            raise ValueError('only audited index discovery queries may be enabled')
        if not callable(enabled):
            raise ValueError('index enabled must be a live predicate')
        if not math.isfinite(sweep_interval_s) or sweep_interval_s <= 0:
            raise ValueError('positive finite index safety sweep interval required')
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
        self._observe = observe
        self._last_sweep: dict[str, float] = {}
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
        try:
            result = self.primary.due(state, now, limit)
        except Exception:
            _count(query, IndexReadSource.FIRESTORE, reason, IndexReadOutcome.ERROR)
            if fallback_reason is not None:
                self._fallback(fallback_reason, 'exhausted')
            raise
        _count(query, IndexReadSource.FIRESTORE, reason, IndexReadOutcome.RETURNED)
        if query in self.enabled_queries:
            with self._sweep_lock:
                self._last_sweep[query] = self._clock()
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
        query = _DUE_QUERIES.get(state, 'other')
        if query not in INDEX_QUERIES:
            return self._primary_due(state, now, limit, query, IndexReadReason.EXCLUDED)
        if query not in self.enabled_queries:
            return self._primary_due(state, now, limit, query, IndexReadReason.UNSELECTED)
        if not self.enabled():
            return self._primary_due(state, now, limit, query, IndexReadReason.DISABLED)
        with self._sweep_lock:
            last = self._last_sweep.get(query)
        if last is None or self._clock() - last >= self.sweep_interval_s:
            return self._primary_due(state, now, limit, query, IndexReadReason.SAFETY_SWEEP)
        try:
            result = self._index.due(state, now, limit)
        except Exception as exc:
            timeout = isinstance(exc, TimeoutError) or getattr(exc, 'sqlstate', None) == '57014'
            return self._primary_due(
                state,
                now,
                limit,
                query,
                IndexReadReason.TIMEOUT if timeout else IndexReadReason.ERROR,
                fallback_reason=FallbackReason.TIMEOUT if timeout else FallbackReason.UNAVAILABLE,
            )
        if not self.enabled():
            return self._primary_due(state, now, limit, query, IndexReadReason.DISABLED)
        _count(query, IndexReadSource.POSTGRES, IndexReadReason.INDEX, IndexReadOutcome.RETURNED)
        self._observe_due(state, now, limit)
        return result
