"""A2 shadow: Firestore stays the primary and the only authority; Postgres is a best-effort mirror.

After a primary transaction commits, the batch documents it wrote are copied into Postgres (doc mode, the
same rows ``PostgresStore`` reads) by one background thread per store. The copy is the primary's current
state, re-read under a per-key Postgres advisory lock, never the commit's snapshot, so mirrors that arrive out
of commit order cannot regress a row (one extra primary read per mirrored document; shadow never runs in
prod). The caller never waits for the
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
- ``op=refresh``: the same outcomes, for documents re-copied after a writer outside ``Store.run``.

Writers that commit outside ``Store.run`` (the projection apply transaction, purge) call
``mirror_refresh(namespace, keys)`` after their commit: the mirror thread re-reads those documents from the
primary and copies them to Postgres, or deletes the copy when the primary no longer has the document. It
returns at once, without constructing anything, unless this process runs ``BATCH_JOBSTORE_MODE=shadow``.

Customer documents (``conversations``, ``content``) are never mirrored. The selector is
``BATCH_JOBSTORE_MODE=shadow`` (default ``firestore``: no shadow, no Postgres connection), and the live
stop lever is the ops kill switch ``JOBSTORE_SHADOW_WRITES`` (on unless set off; cross-plan L3/X3).
The ``batch_pipeline_prod`` namespace is refused until account deletion purges the Postgres copy too,
except in staging on the staging Firestore database, which keeps that worker namespace
(``utils.staging_fence.jobstore_shadow_admits``, ruling L02-2).
"""

from __future__ import annotations

import contextvars
import heapq
import hashlib
import importlib.util
import logging
import os
import queue
import re
import threading
import time
from copy import deepcopy
from enum import StrEnum
from typing import Any, Callable, TypeVar

from prometheus_client import Counter, Histogram

import database.jobstore.codec as codec
from utils.observability.reasons import ReasonFamily, reason_label
from utils.staging_fence import jobstore_shadow_admits

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


class ShadowConvergenceOutcome(StrEnum):
    """``omi_jobstore_shadow_convergence_total{outcome}``: what became of a non-matching read (lead ruling a2d720)."""

    UNKNOWN = 'unknown'
    CONVERGED = 'converged'  # Postgres equalled Firestore's current state within the window: mirror lag
    DIVERGED = 'diverged'  # still different after the window: a real divergence
    DROPPED = 'dropped'  # tracker queue full: unknown, gated as diverged (fail closed)
    ERROR = 'error'  # a check failed: unknown, gated as diverged (fail closed)


# Non-matching reads are re-checked (Postgres copy vs the primary's current state, lock-free) at these offsets
# from the comparison; the first match records its lag. No match by the last offset is a divergence.
CONVERGENCE_DELAYS_S = (0.0, 0.5, 1.0, 2.0, 5.0, 10.0)
CONVERGENCE_QUEUE_LIMIT = 1000

SHADOW_CONVERGENCE_TOTAL = Counter(
    'omi_jobstore_shadow_convergence_total',
    'A2 job-store shadow: non-matching reads re-checked until Postgres equals the primary (lag) or the window ends.',
    ['table', 'outcome'],
)
SHADOW_CONVERGENCE_SECONDS = Histogram(
    'omi_jobstore_shadow_convergence_seconds',
    'A2 job-store shadow: seconds from a non-matching read comparison until Postgres equalled the primary.',
    ['table'],
    buckets=(0.05, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 10.5),  # the last legal observation ends <= 10 s + budget_s
)


def _table_label(table: str) -> str:
    return table if table in MIRRORED_TABLES else 'other'


def _converge_count(table: str, outcome: ShadowConvergenceOutcome) -> None:
    SHADOW_CONVERGENCE_TOTAL.labels(
        table=_table_label(table), outcome=reason_label(ReasonFamily.PARITY, outcome, ShadowConvergenceOutcome)
    ).inc()


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


# -- parity diagnostics ---------------------------------------------------------------------------
# A non-matching read is logged (rate-limited) with the namespace, table, a hashed key and the NAMES of the
# top-level fields that differ: never a raw key, id or value. ``current`` says whether the Postgres copy
# equals the primary's state now: ``shadow_current`` means the mirror already holds a newer state than the
# pre-image the transaction read (lag between the read and its comparison), ``shadow_differs`` means
# Postgres disagrees with the primary's current state as well.
DIAG_LINES_PER_MINUTE = 120
DIAG_MAX_FIELDS = 8
_FIELD_NAME = re.compile(r'[a-z][a-z0-9_]{0,47}')
_diag_window = [0.0, 0]
_diag_lock = threading.Lock()


def key_hash(namespace: str, table: str, key: str) -> str:
    return hashlib.sha256(f'{namespace}/{table}/{key}'.encode()).hexdigest()[:12]


def differing_fields(primary_doc: dict, shadow_doc: dict) -> str:
    """Comma-separated schema names of the top-level fields that differ; dynamic names collapse to ``other``."""
    names: set[str] = set()
    for name in set(primary_doc or {}) | set(shadow_doc or {}):
        try:
            same = codec.canonical((primary_doc or {}).get(name)) == codec.canonical((shadow_doc or {}).get(name))
        except (TypeError, ValueError):
            same = False
        if not same:
            names.add(name if isinstance(name, str) and _FIELD_NAME.fullmatch(name) else 'other')
    ordered = sorted(names)
    extra = len(ordered) - DIAG_MAX_FIELDS
    return ','.join(ordered[:DIAG_MAX_FIELDS]) + (f',+{extra}' if extra > 0 else '') if ordered else '-'


def _diag_allowed() -> bool:
    now = time.monotonic()
    with _diag_lock:
        if now - _diag_window[0] >= 60:
            _diag_window[0], _diag_window[1] = now, 0
        if _diag_window[1] >= DIAG_LINES_PER_MINUTE:
            return False
        _diag_window[1] += 1
        return True


def _error_class(exc: BaseException) -> str:
    text = str(exc).lower()
    if 'contention' in text:
        return 'contention'
    if 'expired' in text:
        return 'expired'
    if 'deadline' in text or _is_timeout(exc):
        return 'deadline'
    return 'other'


def read_current(primary: Any, keys: list[tuple[str, str]]) -> dict[tuple[str, str], dict]:
    """The primary's current state of ``keys`` (``{}`` when absent).

    On Firestore this is one strongly consistent ``get_all`` outside any transaction, so it takes no locks
    and cannot abort a writer's transaction. Other primaries (the simulator) read through ``run``.
    """
    from database.batch_pipeline_store import FirestoreStore

    if not isinstance(primary, FirestoreStore):
        return primary.run(lambda tx: {address: tx.get(*address) for address in keys})
    client = primary.client
    refs = [client.collection(f'{primary.namespace}_{table}').document(key) for table, key in keys]
    found = {snap.reference.path: (snap.to_dict() or {}) for snap in client.get_all(refs) if snap.exists}
    return {address: found.get(ref.path, {}) for address, ref in zip(keys, refs)}


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

    def __init__(
        self,
        primary: Any,
        shadow: Any,
        *,
        budget_s: float = BUDGET_S,
        queue_limit: int = QUEUE_LIMIT,
        inline: bool = False,
    ):
        if getattr(primary, 'namespace', None) != getattr(shadow, 'namespace', None):
            raise ValueError('primary and shadow must share one namespace')
        self.primary = primary
        self.shadow = shadow
        self.budget_s = budget_s
        self.inline = inline  # single-threaded harnesses mirror in the caller, deterministically
        self._queue: queue.Queue = queue.Queue(maxsize=queue_limit)
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        # Convergence tracker (lead ruling a2d720): its own thread and heap, so re-checks never delay the mirror.
        self.convergence_delays: tuple[float, ...] = CONVERGENCE_DELAYS_S
        self._pending: list[tuple[float, int, str, str, float, int]] = []
        self._pending_cv = threading.Condition()
        self._pending_seq = 0
        self._in_flight = 0
        self._tracker: threading.Thread | None = None

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
        # Only the written addresses travel: the mirror copies the primary's current state, never this
        # commit's snapshot (see ``copy_current``).
        writes = sorted({address for address in view.writes if address[0] in MIRRORED_TABLES})
        if not writes and not view.reads:
            return
        if not shadow_writes_enabled():
            for table, _ in writes:
                _count(table, 'write', ShadowParityOutcome.SKIPPED)
            return
        if self.inline:
            self.mirror(view.reads, writes)
            return
        try:
            self._queue.put_nowait(('txn', view.reads, writes))
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
            kind, first, second = self._queue.get()
            try:
                if kind == 'refresh':
                    self.refresh_now(first)
                else:
                    self.mirror(first, second)
            finally:
                self._queue.task_done()

    def refresh(self, keys) -> None:
        """Queue a re-copy of ``keys`` from the primary (after a commit outside ``Store.run``). Never raises."""
        keys = sorted({(table, key) for table, key in keys if table in MIRRORED_TABLES})
        if not keys:
            return
        if not shadow_writes_enabled():
            for table, _ in keys:
                _count(table, 'refresh', ShadowParityOutcome.SKIPPED)
            return
        if self.inline:
            self.refresh_now(keys)
            return
        try:
            self._queue.put_nowait(('refresh', keys, None))
        except queue.Full:
            for table, _ in keys:
                _count(table, 'refresh', ShadowParityOutcome.DROPPED)
            return
        self._ensure_worker()

    def copy_current(
        self,
        conn: Any,
        keys: list[tuple[str, str]],
        phase: list[str] | None = None,
        reader: Callable[[Any, list[tuple[str, str]]], dict] | None = None,
    ) -> None:
        """Copy the primary's CURRENT state of ``keys`` into Postgres (upsert, or delete when gone).

        Commits reach the mirror out of order: two threads can queue in the reverse of Firestore's commit
        order, and every instance runs its own mirror thread. Applying a commit's captured snapshot could
        therefore land an older write after a newer one (or undo a purge). Instead each key is locked with a
        transaction advisory lock, then re-read from the primary and copied. Firestore reads are strongly
        consistent, so whichever mirror takes a key's lock later also reads a state at least as new, and the
        last copy applied is the current one. ``keys`` is sorted, so the lock order cannot deadlock.

        The re-read is ``read_current``: one lock-free ``get_all``, never a read-write transaction. A
        transactional read takes Firestore locks that contend with the pipeline's own writers while the
        Postgres locks are held, and the SDK does not retry an ``Aborted`` raised on a transaction's read
        path (staging 10-20: every ``op=refresh outcome=error`` was ``Aborted``).
        """
        for table, key in keys:
            conn.execute(
                'SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (f'{self.shadow.namespace}/{table}/{key}',)
            )
        phase = phase if phase is not None else ['']
        phase[0] = 'primary_read'
        docs = (reader or read_current)(self.primary, keys)
        phase[0] = 'postgres_write'
        for (table, key), doc in docs.items():
            if doc:
                self.shadow.write_doc(conn, table, key, doc)
            else:
                self.shadow.delete_doc(conn, table, key)

    def refresh_now(self, keys: list[tuple[str, str]]) -> None:
        """Re-copy ``keys`` from the primary into Postgres (upsert, or delete when gone). Never raises."""
        phase = ['postgres_connect']
        try:
            with self.shadow.pool.connection(timeout=self.budget_s) as conn:
                with conn.transaction():
                    conn.execute(f'SET LOCAL statement_timeout = {int(self.budget_s * 1000)}')
                    self.copy_current(conn, keys, phase)
        except Exception as exc:
            outcome = ShadowParityOutcome.TIMEOUT if _is_timeout(exc) else ShadowParityOutcome.ERROR
            for table, _ in keys:
                _count(table, 'refresh', outcome)
            self._log_failure('refresh', outcome, exc, phase[0], keys)
            return
        for table, _ in keys:
            _count(table, 'refresh', ShadowParityOutcome.MIRRORED)

    def mirror(self, reads: dict[tuple[str, str], dict], writes: list[tuple[str, str]]) -> None:
        """One Postgres transaction: compare the read pre-images, then copy the written keys. Never raises."""
        phase = ['postgres_connect']
        differing: list[tuple[str, str, ShadowParityOutcome, dict, dict]] = []
        try:
            with self.shadow.pool.connection(timeout=self.budget_s) as conn:
                with conn.transaction():
                    conn.execute(f'SET LOCAL statement_timeout = {int(self.budget_s * 1000)}')
                    phase[0] = 'postgres_read'
                    for (table, key), primary_doc in reads.items():
                        shadow_doc = self.shadow.read_doc(conn, table, key)
                        outcome = compare(primary_doc, shadow_doc)
                        _count(table, 'read', outcome)
                        if outcome is not ShadowParityOutcome.MATCH:
                            differing.append((table, key, outcome, primary_doc, shadow_doc))
                    if writes:
                        self.copy_current(conn, writes, phase)
        except Exception as exc:
            outcome = ShadowParityOutcome.TIMEOUT if _is_timeout(exc) else ShadowParityOutcome.ERROR
            for table, _ in writes:
                _count(table, 'write', outcome)
            self._log_failure('write', outcome, exc, phase[0], writes)
            return
        finally:
            self._track_convergence(differing)
            self._log_differing(differing)
        for table, _ in writes:
            _count(table, 'write', ShadowParityOutcome.MIRRORED)

    # -- convergence (lead ruling a2d720) ----------------------------------------------------------
    def _track_convergence(self, differing: list[tuple[str, str, ShadowParityOutcome, dict, dict]]) -> None:
        """Re-check every mismatch / missing / extra read until Postgres equals the primary or the window ends.

        A read that converges is mirror lag (``converged``, with its lag in seconds); one that does not is a
        divergence. The parity counter itself is unchanged: this is a second, separately gated signal.
        Never raises.
        """
        tracked = {ShadowParityOutcome.MISMATCH, ShadowParityOutcome.MISSING, ShadowParityOutcome.EXTRA}
        try:
            entries = [(table, key) for table, key, outcome, *_ in differing if outcome in tracked]
            if not entries:
                return
            if self.inline:  # deterministic harnesses: one check, no waiting
                for table, key in entries:
                    self._check_convergence((0.0, 0, table, key, time.monotonic(), len(self.convergence_delays)))
                return
            with self._pending_cv:
                for table, key in entries:
                    if len(self._pending) >= CONVERGENCE_QUEUE_LIMIT:
                        _converge_count(table, ShadowConvergenceOutcome.DROPPED)
                        continue
                    started = time.monotonic()
                    self._pending_seq += 1
                    heapq.heappush(self._pending, (started, self._pending_seq, table, key, started, 0))
                self._pending_cv.notify()
                if self._tracker is None or not self._tracker.is_alive():
                    self._tracker = threading.Thread(
                        target=contextvars.Context().run,
                        args=(self._converge_forever,),
                        name='jobstore-shadow-converge',
                        daemon=True,
                    )
                    self._tracker.start()
        except Exception:
            logger.warning('event=jobstore_shadow op=converge outcome=track_error', exc_info=True)

    def _converge_forever(self) -> None:
        while True:
            with self._pending_cv:
                while not self._pending or self._pending[0][0] > time.monotonic():
                    wait = (self._pending[0][0] - time.monotonic()) if self._pending else None
                    self._pending_cv.wait(wait)
                item = heapq.heappop(self._pending)
                self._in_flight += 1
            try:
                self._check_convergence(item)
            finally:
                with self._pending_cv:
                    self._in_flight -= 1
                    self._pending_cv.notify_all()

    def _read_shadow(self, table: str, key: str) -> dict:
        with self.shadow.pool.connection(timeout=self.budget_s) as conn:
            with conn.transaction():
                conn.execute(f'SET LOCAL statement_timeout = {int(self.budget_s * 1000)}')
                return self.shadow.read_doc(conn, table, key)

    def _check_convergence(self, item: tuple[float, int, str, str, float, int]) -> None:
        """One observation. ``converged`` needs a STABLE pair inside the window (Grok #22965 B1).

        Postgres is read, then the primary (lock-free), then Postgres again: a mirror committing between the
        reads (a torn pair) cannot count. And the observation must finish within the last re-check offset
        plus one ``budget_s`` of slop, so a late check after a backlog cannot turn a stuck row into lag.
        Anything else re-schedules, and the last step counts ``diverged``. Never raises; any failure counts
        ``error`` (fail closed).
        """
        _, seq, table, key, started, step = item
        try:
            shadow_before = self._read_shadow(table, key)
            primary_doc = read_current(self.primary, [(table, key)]).get((table, key), {})
            shadow_after = self._read_shadow(table, key)
            elapsed = time.monotonic() - started
            in_window = elapsed <= self.convergence_delays[-1] + self.budget_s
            stable = compare(shadow_before, shadow_after) is ShadowParityOutcome.MATCH
            if in_window and stable and compare(primary_doc, shadow_after) is ShadowParityOutcome.MATCH:
                _converge_count(table, ShadowConvergenceOutcome.CONVERGED)
                SHADOW_CONVERGENCE_SECONDS.labels(table=_table_label(table)).observe(elapsed)
                return
            step += 1
            if step >= len(self.convergence_delays) or not in_window:
                _converge_count(table, ShadowConvergenceOutcome.DIVERGED)
                namespace = getattr(self.shadow, 'namespace', '?')
                logger.warning(
                    'event=jobstore_shadow op=converge outcome=diverged namespace=%s table=%s key=%s fields=%s late=%s',
                    namespace,
                    table,
                    key_hash(namespace, table, key),
                    differing_fields(primary_doc, shadow_after),
                    not in_window,
                )
                return
            with self._pending_cv:
                heapq.heappush(self._pending, (started + self.convergence_delays[step], seq, table, key, started, step))
                self._pending_cv.notify()
        except Exception as exc:
            _converge_count(table, ShadowConvergenceOutcome.ERROR)
            logger.warning(
                'event=jobstore_shadow op=converge outcome=error error=%s error_class=%s table=%s',
                type(exc).__name__,
                _error_class(exc),
                table,
            )

    def drain_convergence(self, timeout: float = 15.0) -> bool:
        """Wait until every tracked read has converged or diverged (tests). True when drained."""
        deadline = time.monotonic() + timeout
        with self._pending_cv:
            while self._pending or self._in_flight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._pending_cv.wait(remaining)
        return True

    def _log_failure(
        self, op: str, outcome: ShadowParityOutcome, exc: BaseException, phase: str, keys: list[tuple[str, str]]
    ) -> None:
        logger.warning(
            'event=jobstore_shadow op=%s outcome=%s error=%s error_class=%s phase=%s namespace=%s tables=%s',
            op,
            outcome.value,
            type(exc).__name__,
            _error_class(exc),
            phase,
            getattr(self.shadow, 'namespace', '?'),
            ','.join(sorted({table for table, _ in keys})) or '-',
        )

    def _log_differing(self, differing: list[tuple[str, str, ShadowParityOutcome, dict, dict]]) -> None:
        """Rate-limited diagnostics for non-matching reads. Never raises; never logs a raw key or value."""
        try:
            allowed = [entry for entry in differing if _diag_allowed()]
            if not allowed:
                return
            try:
                now = read_current(self.primary, sorted({(table, key) for table, key, *_ in allowed}))
            except Exception:
                now = None
            namespace = getattr(self.shadow, 'namespace', '?')
            for table, key, outcome, primary_doc, shadow_doc in allowed:
                if now is None:
                    current = 'unread'
                elif compare(now.get((table, key), {}), shadow_doc) is ShadowParityOutcome.MATCH:
                    current = 'shadow_current'
                else:
                    current = 'shadow_differs'
                logger.warning(
                    'event=jobstore_shadow_parity outcome=%s namespace=%s table=%s key=%s fields=%s current=%s',
                    outcome.value,
                    namespace,
                    table,
                    key_hash(namespace, table, key),
                    differing_fields(primary_doc, shadow_doc),
                    current,
                )
        except Exception:
            logger.warning('event=jobstore_shadow_parity outcome=diag_error', exc_info=True)

    def drain(self, timeout: float = 10.0) -> bool:
        """Wait until every queued mirror has been applied (tests and shutdown). True when drained."""
        done = threading.Event()

        def wait() -> None:
            self._queue.join()
            done.set()

        threading.Thread(target=wait, daemon=True).start()
        return done.wait(timeout)


_SHADOWED: dict[str, DualStore] = {}
_SHADOWED_LOCK = threading.Lock()


def shadow_from_env(primary: Any) -> Any:
    """``primary`` unchanged unless ``BATCH_JOBSTORE_MODE=shadow`` and the staging Postgres is configured.

    Fails closed to Firestore-only: any other mode, the prod namespace outside the staging DB, a missing
    setting, or an image
    without the Postgres driver returns
    ``primary`` and logs why. One ``DualStore`` (one mirror thread, one pool) serves each namespace per
    process, so call sites that build a store per call share it. No Postgres connection is opened here
    (the pool dials lazily).
    """
    mode = os.getenv('BATCH_JOBSTORE_MODE', 'firestore').strip().lower()
    if mode != 'shadow':
        return primary
    namespace = getattr(primary, 'namespace', '')
    if not jobstore_shadow_admits(namespace):
        logger.warning('event=jobstore_shadow outcome=refused reason=prod_namespace')
        return primary
    target = [os.getenv(name, '').strip() for name in ('JOBSTORE_PG_HOST', 'JOBSTORE_PG_DATABASE', 'JOBSTORE_PG_USER')]
    if not all(target):
        logger.warning('event=jobstore_shadow outcome=refused reason=unconfigured')
        return primary
    if importlib.util.find_spec('psycopg') is None:  # an image without the driver would only count errors
        logger.warning('event=jobstore_shadow outcome=refused reason=driver_missing')
        return primary
    with _SHADOWED_LOCK:
        if namespace in _SHADOWED:
            return _SHADOWED[namespace]
        from database.jobstore.connection import Pool, iam_connector
        from database.jobstore.postgres_store import PostgresStore

        pool = Pool('', size=2, connect=iam_connector(*target))
        shadow = PostgresStore(namespace, pool=pool, customer_client=None)
        _SHADOWED[namespace] = DualStore(primary, shadow)
        logger.info('event=jobstore_shadow outcome=enabled')
        return _SHADOWED[namespace]


def mirror_refresh(namespace: str, keys) -> None:
    """Post-commit hook for batch writers outside ``Store.run``: re-copy ``keys`` [(table, key)] to the shadow.

    A strict no-op (nothing constructed, nothing read) unless this process runs ``BATCH_JOBSTORE_MODE=shadow``;
    otherwise queued for the mirror thread. Never raises into the caller.
    """
    if os.getenv('BATCH_JOBSTORE_MODE', 'firestore').strip().lower() != 'shadow' or not jobstore_shadow_admits(
        namespace
    ):
        return
    try:
        store = _SHADOWED.get(namespace)
        if store is None:
            from database.batch_pipeline_store import FirestoreStore

            store = shadow_from_env(FirestoreStore(namespace))
        if isinstance(store, DualStore):
            store.refresh(keys)
    except Exception:
        logger.warning('event=jobstore_shadow op=refresh outcome=hook_error', exc_info=True)
