"""A1 doc mode: the batch ``Store`` / ``Transaction`` protocol over Postgres.

Same contract as ``database.batch_pipeline_store.FirestoreStore``: reads inside a transaction see its
own buffered writes, writes are applied when the body returns, the body must be pure (it is retried
on a serialization failure, exactly as Firestore retries on contention), a transaction is bounded to
450 writes, and every written ``jobs`` / ``results`` row re-runs the privacy fence for its owner and
conversation before anything is applied.

Isolation is SERIALIZABLE with bounded retry, the closest match to Firestore's optimistic
transactions for ported check-then-act code (A3 replaces the hot paths with SKIP LOCKED queries).

The privacy authority is still the customer-data Firestore (A5 mirrors it into Postgres later), so
``customer_client`` is required. ``conversations`` / ``content`` documents belong to Firestore; they
reach Postgres only under ``harness_customer_tables=True`` (hermetic goldens), never in production:
moving them is the A4 outbox + receipt-fence seam, not this PR.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, TypeVar

from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed

import database.jobstore.codec as codec
from database.jobstore.connection import Pool

# Same set as database.batch_pipeline_recovery.PROVIDER_STATES (not imported: that module pulls in Firestore).
PROVIDER_STATES = frozenset({'provider_pending', 'provider_running'})

T = TypeVar('T')

WRITE_BUDGET = 450
MAX_SERIALIZATION_RETRIES = 8
_TYPED = {'jobs', 'results', 'control'}
_CUSTOMER_TABLES = {'conversations', 'content'}
_DUE_FIELDS = {
    'leased': 'lease_until',
    'retry': 'available_at',
    'result_ready': 'enqueued_at',
    'record_pending': 'available_at',
}
_NAMESPACE = re.compile(r'batch_pipeline_(prod|dev|test_[a-z0-9_]{1,40})')
_SERIALIZATION_FAILURE = '40001'
_DEADLOCK = '40P01'


def jsonb(value: dict):
    # psycopg joins the lockfile separately; until then pyright cannot resolve it.
    from psycopg.types.json import Jsonb  # pyright: ignore[reportMissingImports]

    return Jsonb(value, dumps=codec.dumps)


def _is_retryable(exc: BaseException) -> bool:
    return getattr(exc, 'sqlstate', None) in {_SERIALIZATION_FAILURE, _DEADLOCK}


class PostgresTransaction:
    def __init__(self, store: 'PostgresStore', conn: Any):
        self.store = store
        self.conn = conn
        self.cache: dict[tuple[str, str], dict] = {}
        self.writes: dict[tuple[str, str], dict] = {}
        self.patches: dict[tuple[str, str], dict] = {}

    # -- Transaction protocol -------------------------------------------------------------
    def get(self, table: str, key: str) -> dict:
        address = (table, key)
        self.store.require_table(table)
        if address not in self.cache:
            self.cache[address] = self.store.read_doc(self.conn, table, key)
        return deepcopy({**self.writes.get(address, self.cache[address]), **self.patches.get(address, {})})

    def put(self, table: str, key: str, value: dict) -> None:
        if table == 'conversations':
            raise ValueError('conversation admission requires a field patch, never a document set')
        self.store.require_table(table)
        self.writes[(table, key)] = deepcopy(value)

    def patch(self, table: str, key: str, fields: dict) -> None:
        if table != 'conversations' or set(fields) != {'record_lane_owner'}:
            raise ValueError('only the conversation route owner may be patched by admission')
        self.store.require_table(table)
        self.patches.setdefault((table, key), {}).update(deepcopy(fields))

    def first_pending(self, owner_key: str) -> dict | None:
        row = self.conn.execute(
            'SELECT doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending '
            'ORDER BY capture_at, key LIMIT 1',
            (self.store.namespace, owner_key),
        ).fetchone()
        return row[0] if row else None

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        # Two matches fail closed, exactly like the Firestore query.
        rows = self.conn.execute(
            "SELECT doc FROM jobs WHERE namespace = %s AND owner_key = %s AND priority = %s AND state = 'ready' "
            'AND next_id = %s ORDER BY key LIMIT 2',
            (self.store.namespace, owner_key, priority, segment_id),
        ).fetchall()
        return rows[0][0] if len(rows) == 1 else None

    def service_frontier(self, priority: int) -> float:
        return self.store.service_frontier_in(self.conn, priority)

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        return self.store.check_privacy_for(uid, conversation_ids, expected_generation)

    # -- commit -----------------------------------------------------------------------------
    def flush(self) -> None:
        if len(self.writes) + len(self.patches) > WRITE_BUDGET:
            raise RuntimeError('batch transaction write budget exceeded')
        guarded = set()
        for (table, key), value in self.writes.items():
            if table not in {'jobs', 'results'}:
                continue
            job = value if table == 'jobs' else self.get('jobs', key)
            identity = (job['owner_id'], job.get('conversation_id'), job.get('privacy_generation'))
            if identity in guarded:
                continue
            guarded.add(identity)
            generation = self.check_privacy(
                job['owner_id'],
                (job['conversation_id'],) if job.get('conversation_id') else (),
                job.get('privacy_generation'),
            )
            if table == 'jobs' and value.get('privacy_generation') is None:
                value['privacy_generation'] = generation
        for (table, key), value in self.writes.items():
            self.store.write_doc(self.conn, table, key, value)
        for (table, key), fields in self.patches.items():
            current = self.store.read_doc(self.conn, table, key)
            if not current and (table, key) not in self.writes:
                # Firestore `update` on a missing document fails; keep that contract.
                raise LookupError(f'cannot patch missing document {table}/{key}')
            self.store.write_doc(self.conn, table, key, {**self.writes.get((table, key), current), **fields})


class PostgresStore:
    def __init__(
        self,
        namespace: str,
        *,
        pool: Pool,
        customer_client: Any,
        harness_customer_tables: bool = False,
    ):
        if not _NAMESPACE.fullmatch(namespace):
            raise ValueError('explicit batch_pipeline_{prod,dev,test_<id>} namespace required')
        self.namespace = namespace
        self.pool = pool
        self.customer_client = customer_client
        self.harness_customer_tables = harness_customer_tables

    # -- Store protocol -----------------------------------------------------------------------
    def run(self, body: Callable[[PostgresTransaction], T]) -> T:
        last: BaseException | None = None
        for _ in range(MAX_SERIALIZATION_RETRIES):
            with self.pool.connection() as conn:
                try:
                    with conn.transaction():
                        conn.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                        view = PostgresTransaction(self, conn)
                        result = body(view)
                        view.flush()
                        return result
                except Exception as exc:
                    if not _is_retryable(exc):
                        raise
                    last = exc
        raise RuntimeError('job store transaction kept conflicting') from last

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        if state not in _DUE_FIELDS:
            raise ValueError('only recoverable states may be scanned')
        field = _DUE_FIELDS[state]  # a fixed column name, never caller text
        with self._read_conn() as conn:
            rows = conn.execute(
                f'SELECT key FROM jobs WHERE namespace = %s AND state = %s AND {field} <= %s '
                f'ORDER BY {field}, key LIMIT %s',
                (self.namespace, state, now, max(1, min(limit, 100))),
            ).fetchall()
        return [row[0] for row in rows]

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        predicate = "state = 'ready'" if ready_only else 'merge_pending'
        with self._read_conn() as conn:
            row = conn.execute(
                f'SELECT min(enqueued_at) FROM jobs WHERE namespace = %s AND priority = %s AND {predicate}',
                (self.namespace, priority),
            ).fetchone()
        return row[0]

    def oldest_retry(self, priority: int) -> float | None:
        with self._read_conn() as conn:
            row = conn.execute(
                'SELECT min(retry_started_at) FROM jobs WHERE namespace = %s AND priority = %s '
                'AND retry_started_at >= 0',
                (self.namespace, priority),
            ).fetchone()
        return row[0]

    def control_candidate(self, priority: int, pool: str, now: float) -> str | None:
        if priority not in (0, 1, 2) or pool not in {'batch', 'live'}:
            raise ValueError('bounded priority and pool required')
        p, at = f'p{priority}', f'p{priority}_{pool}_at'
        with self._read_conn() as conn:
            row = conn.execute(
                f'SELECT key FROM control WHERE namespace = %s AND {p}_active AND {p}_service >= 0 '
                f'AND {at} <= %s ORDER BY {p}_service, {at}, key LIMIT 1',
                (self.namespace, now),
            ).fetchone()
        return row[0] if row else None

    def quarantine_fenced(self, segment_id: str, now: float) -> bool:
        """Revoke a fenced detached lease/retry; same fence recheck and revoke-only write as Firestore."""

        def revoke(tx: PostgresTransaction) -> bool:
            job = tx.get('jobs', segment_id)
            if job.get('state') not in {'leased', 'retry'} | PROVIDER_STATES:
                return False
            try:
                tx.check_privacy(
                    job['owner_id'],
                    (job['conversation_id'],) if job.get('conversation_id') else (),
                    job.get('privacy_generation'),
                )
            except BatchPrivacyBlocked:
                # A shallow field update, not a put: flush must not re-run the (failing) fence.
                revoked = {
                    **job,
                    'state': 'privacy_blocked',
                    'token': '',
                    'lease_until': 0.0,
                    'privacy_blocked_at': now,
                }
                if job['state'] in PROVIDER_STATES:
                    revoked['merge_pending'] = False
                tx.store.write_doc(tx.conn, 'jobs', segment_id, revoked)
                return True
            return False

        return self.run(revoke)

    def projection_pending(self, limit: int = 100) -> list[str]:
        return self.projection_page(limit)[0]

    def projection_page(self, limit: int = 100, *, after=None) -> tuple[list[str], Any]:
        size = max(1, min(limit, 100))
        clause, params = '', [self.namespace]
        if after is not None:
            clause = 'AND (committed_at, key) > (%s, %s)'
            params += [after[0], after[1]]
        with self._read_conn() as conn:
            rows = conn.execute(
                "SELECT key, committed_at FROM results WHERE namespace = %s "
                f"AND projection_state IN ('pending', 'persisted', 'ready') {clause} "
                'ORDER BY committed_at, key LIMIT %s',
                (*params, size),
            ).fetchall()
        cursor = (rows[-1][1], rows[-1][0]) if len(rows) == size else None
        return [row[0] for row in rows], cursor

    # -- internals ---------------------------------------------------------------------------
    @contextmanager
    def _read_conn(self) -> Iterator[Any]:
        with self.pool.connection() as conn:
            yield conn

    def require_table(self, table: str) -> None:
        if table in _CUSTOMER_TABLES and not self.harness_customer_tables:
            raise RuntimeError(f'{table} documents live in Firestore; Postgres holds them only in harness mode (A4)')

    def read_doc(self, conn: Any, table: str, key: str) -> dict:
        if table in _TYPED:
            row = conn.execute(f'SELECT doc FROM {table} WHERE namespace = %s AND key = %s', (self.namespace, key))
        else:
            row = conn.execute(
                'SELECT doc FROM docs WHERE namespace = %s AND tbl = %s AND key = %s', (self.namespace, table, key)
            )
        found = row.fetchone()
        return found[0] if found else {}

    def write_doc(self, conn: Any, table: str, key: str, value: dict) -> None:
        if table in _TYPED:
            conn.execute(
                f'INSERT INTO {table} (namespace, key, doc) VALUES (%s, %s, %s) '
                'ON CONFLICT (namespace, key) DO UPDATE SET doc = EXCLUDED.doc',
                (self.namespace, key, jsonb(value)),
            )
        else:
            conn.execute(
                'INSERT INTO docs (namespace, tbl, key, doc) VALUES (%s, %s, %s, %s) '
                'ON CONFLICT (namespace, tbl, key) DO UPDATE SET doc = EXCLUDED.doc',
                (self.namespace, table, key, jsonb(value)),
            )

    def delete_doc(self, conn: Any, table: str, key: str) -> None:
        if table in _TYPED:
            conn.execute(f'DELETE FROM {table} WHERE namespace = %s AND key = %s', (self.namespace, key))
        else:
            conn.execute(
                'DELETE FROM docs WHERE namespace = %s AND tbl = %s AND key = %s', (self.namespace, table, key)
            )

    def service_frontier_in(self, conn: Any, priority: int) -> float:
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        row = conn.execute(
            f'SELECT max(p{priority}_service) FROM control WHERE namespace = %s', (self.namespace,)
        ).fetchone()
        return row[0] if row[0] is not None else 0.0

    def check_privacy_for(self, uid: str, conversation_ids, expected_generation: int | None) -> int:
        # Each check is its own read-only customer-data transaction (the privacy authority is
        # still Firestore until A5), as in the pipeline simulator.
        return assert_batch_write_allowed(
            self.customer_client,
            self.customer_client.transaction(),
            uid,
            conversation_ids=tuple(conversation_ids),
            expected_generation=expected_generation,
        )

    def purge_namespace(self) -> None:
        """Test-only cleanup of this namespace (conformance fixtures own throwaway namespaces)."""
        if not self.namespace.startswith('batch_pipeline_test_'):
            raise RuntimeError('only test namespaces may be purged')
        with self._read_conn() as conn:
            for table in ('jobs', 'results', 'control', 'docs', 'outbox'):
                conn.execute(f'DELETE FROM {table} WHERE namespace = %s', (self.namespace,))
