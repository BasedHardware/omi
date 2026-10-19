"""A2 shadow: Firestore stays the primary and the only authority; Postgres is a best-effort mirror.

After a primary transaction commits, the batch documents it wrote are copied into Postgres (doc mode, the
same rows ``PostgresStore`` reads) by one background thread per store. The caller never waits for the
mirror and nothing on the mirror path raises into it: the queue is bounded (a full queue drops the copy),
the pool wait and every statement are bounded by ``budget_s`` (200 ms), and any failure is counted.

Parity is measured on reads, not timings (plan A risk 7). In the same Postgres transaction, before the
writes are applied, the mirror reads its own copy of every batch document the primary transaction read
and compares it with what Firestore returned. A complete mirror holds the same pre-image.

``omi_jobstore_shadow_parity_total{table,op,outcome}``:
- ``op=read``: ``match``; ``mismatch``; ``missing`` (Firestore has the document, Postgres has no copy:
  written before the shadow started, until the A6 backfill, or a lost mirror write); ``extra`` (Postgres
  has a document Firestore lacks); ``uncomparable`` (a value the job store cannot encode).
- ``op=write``: ``mirrored``; ``error``; ``timeout``; ``dropped`` (queue full); ``skipped`` (kill switch).

Customer documents (``conversations``, ``content``) are never mirrored. The selector is
``BATCH_JOBSTORE_MODE=shadow`` (default ``firestore``: no shadow, no Postgres connection), and the live
stop lever is the ops kill switch ``JOBSTORE_SHADOW_WRITES`` (on unless set off; cross-plan L3/X3).
The ``batch_pipeline_prod`` namespace is refused until account deletion purges the Postgres copy too.
"""

from __future__ import annotations

import contextvars
import logging
import os
import queue
import threading
from copy import deepcopy
from enum import StrEnum
from typing import Any, Callable, TypeVar

from prometheus_client import Counter

from database.jobstore import codec
from utils.observability.reasons import ReasonFamily, reason_label

logger = logging.getLogger(__name__)

T = TypeVar('T')

BUDGET_S = 0.2
QUEUE_LIMIT = 1000
MIRRORED_TABLES = frozenset({'jobs', 'queues', 'owners', 'control', 'results', 'gpus', 'intakes', 'artifacts'})
_OFF = {'0', 'false', 'off', 'no'}
_QUERY_CANCELED = '57014'


class ShadowParityOutcome(StrEnum):
    UNKNOWN = 'unknown'
    MATCH = 'match'
    MISMATCH = 'mismatch'
    MISSING = 'missing'
    EXTRA = 'extra'
    UNCOMPARABLE = 'uncomparable'
    MIRRORED = 'mirrored'
    ERROR = 'error'
    TIMEOUT = 'timeout'
    DROPPED = 'dropped'
    SKIPPED = 'skipped'


SHADOW_PARITY_TOTAL = Counter(
    'omi_jobstore_shadow_parity_total',
    'A2 job-store shadow: Postgres mirror writes and read-parity comparisons against Firestore.',
    ['table', 'op', 'outcome'],
)


def _count(table: str, op: str, outcome: ShadowParityOutcome, n: int = 1) -> None:
    SHADOW_PARITY_TOTAL.labels(
        table=table if table in MIRRORED_TABLES else 'other',
        op=op,
        outcome=reason_label(ReasonFamily.PARITY, outcome, ShadowParityOutcome),
    ).inc(n)


def shadow_writes_enabled() -> bool:
    return os.getenv('JOBSTORE_SHADOW_WRITES', '').strip().lower() not in _OFF


def compare(primary_doc: dict, shadow_doc: dict) -> ShadowParityOutcome:
    if not primary_doc and not shadow_doc:
        return ShadowParityOutcome.MATCH
    if not shadow_doc:
        return ShadowParityOutcome.MISSING
    if not primary_doc:
        return ShadowParityOutcome.EXTRA
    try:
        same = codec.canonical(primary_doc) == codec.canonical(shadow_doc)
    except (TypeError, ValueError):
        return ShadowParityOutcome.UNCOMPARABLE
    return ShadowParityOutcome.MATCH if same else ShadowParityOutcome.MISMATCH


def _is_timeout(exc: BaseException) -> bool:
    return isinstance(exc, TimeoutError) or getattr(exc, 'sqlstate', None) == _QUERY_CANCELED


class _Recorder:
    """The primary's transaction view, recording the pre-image of each batch document the body reads."""

    def __init__(self, inner: Any):
        self._inner = inner
        self.reads: dict[tuple[str, str], dict] = {}

    def get(self, table: str, key: str) -> dict:
        value = self._inner.get(table, key)
        address = (table, key)
        if table in MIRRORED_TABLES and address not in self.reads and address not in self._inner.writes:
            self.reads[address] = deepcopy(value)
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class DualStore:
    """``Store`` protocol: every call is the primary's; committed batch writes are mirrored to ``shadow``."""

    def __init__(self, primary: Any, shadow: Any, *, budget_s: float = BUDGET_S, queue_limit: int = QUEUE_LIMIT):
        if getattr(primary, 'namespace', None) != getattr(shadow, 'namespace', None):
            raise ValueError('primary and shadow must share one namespace')
        self.primary = primary
        self.shadow = shadow
        self.budget_s = budget_s
        self._queue: queue.Queue = queue.Queue(maxsize=queue_limit)
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def __getattr__(self, name: str) -> Any:
        # due / oldest / oldest_retry / control_candidate / quarantine_fenced / projection_* / client / namespace
        return getattr(self.primary, name)

    def run(self, body: Callable[[Any], T]) -> T:
        attempt: dict[str, _Recorder] = {}

        def recorded(view: Any) -> T:
            # The primary may retry the body; only the attempt that committed is kept.
            attempt['view'] = _Recorder(view)
            return body(attempt['view'])

        result = self.primary.run(recorded)
        try:
            self._after_commit(attempt['view'])
        except Exception:  # never let the shadow reach the caller
            logger.warning('event=jobstore_shadow outcome=capture_error', exc_info=True)
        return result

    # -- mirror -----------------------------------------------------------------------------------
    def _after_commit(self, view: _Recorder) -> None:
        writes = {address: deepcopy(value) for address, value in view.writes.items() if address[0] in MIRRORED_TABLES}
        if not writes and not view.reads:
            return
        if not shadow_writes_enabled():
            for table, _ in writes:
                _count(table, 'write', ShadowParityOutcome.SKIPPED)
            return
        try:
            self._queue.put_nowait((view.reads, writes))
        except queue.Full:
            for table, _ in writes:
                _count(table, 'write', ShadowParityOutcome.DROPPED)
            return
        self._ensure_worker()

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                # A fresh, empty context: the mirror thread never sees request state.
                self._worker = threading.Thread(
                    target=contextvars.Context().run, args=(self._drain_forever,), name='jobstore-shadow', daemon=True
                )
                self._worker.start()

    def _drain_forever(self) -> None:
        while True:
            reads, writes = self._queue.get()
            try:
                self.mirror(reads, writes)
            finally:
                self._queue.task_done()

    def mirror(self, reads: dict[tuple[str, str], dict], writes: dict[tuple[str, str], dict]) -> None:
        """One Postgres transaction: compare the read pre-images, then apply the writes. Never raises."""
        try:
            with self.shadow.pool.connection(timeout=self.budget_s) as conn:
                with conn.transaction():
                    conn.execute(f'SET LOCAL statement_timeout = {int(self.budget_s * 1000)}')
                    for (table, key), primary_doc in reads.items():
                        _count(table, 'read', compare(primary_doc, self.shadow.read_doc(conn, table, key)))
                    for (table, key), value in writes.items():
                        self.shadow.write_doc(conn, table, key, value)
        except Exception as exc:
            outcome = ShadowParityOutcome.TIMEOUT if _is_timeout(exc) else ShadowParityOutcome.ERROR
            for table, _ in writes:
                _count(table, 'write', outcome)
            logger.warning('event=jobstore_shadow outcome=%s error=%s', outcome.value, type(exc).__name__)
            return
        for table, _ in writes:
            _count(table, 'write', ShadowParityOutcome.MIRRORED)

    def drain(self, timeout: float = 10.0) -> bool:
        """Wait until every queued mirror has been applied (tests and shutdown). True when drained."""
        done = threading.Event()

        def wait() -> None:
            self._queue.join()
            done.set()

        threading.Thread(target=wait, daemon=True).start()
        return done.wait(timeout)


def shadow_from_env(primary: Any) -> Any:
    """``primary`` unchanged unless ``BATCH_JOBSTORE_MODE=shadow`` and the staging Postgres is configured.

    Fails closed to Firestore-only: any other mode, the prod namespace, or a missing setting returns
    ``primary`` and logs why. No Postgres connection is opened here (the pool dials lazily).
    """
    mode = os.getenv('BATCH_JOBSTORE_MODE', 'firestore').strip().lower()
    if mode != 'shadow':
        return primary
    namespace = getattr(primary, 'namespace', '')
    if namespace == 'batch_pipeline_prod':
        logger.warning('event=jobstore_shadow outcome=refused reason=prod_namespace')
        return primary
    target = [os.getenv(name, '').strip() for name in ('JOBSTORE_PG_HOST', 'JOBSTORE_PG_DATABASE', 'JOBSTORE_PG_USER')]
    if not all(target):
        logger.warning('event=jobstore_shadow outcome=refused reason=unconfigured')
        return primary
    from database.jobstore.connection import Pool, iam_connector
    from database.jobstore.postgres_store import PostgresStore

    pool = Pool('', size=2, connect=iam_connector(*target))
    shadow = PostgresStore(namespace, pool=pool, customer_client=None)
    logger.info('event=jobstore_shadow outcome=enabled')
    return DualStore(primary, shadow)
