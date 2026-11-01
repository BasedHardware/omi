"""A1 doc mode: the batch ``Store`` / ``Transaction`` protocol over Postgres.

Same contract as ``database.batch_pipeline_store.FirestoreStore``: reads inside a transaction see its
own buffered writes, writes are applied when the body returns, the body must be pure (it is retried
on a serialization failure, exactly as Firestore retries on contention), a transaction is bounded to
450 writes, and every written ``jobs`` / ``results`` row re-runs the privacy fence for its owner and
conversation before anything is applied.

Isolation matches Firestore's server-side transactions: per-document pessimistic locks held to commit,
on READ COMMITTED. ``get`` locks the row it reads (``FOR UPDATE``, which also returns the newest committed
version), and a document read as missing is locked by key with a transaction advisory lock, the same key
the A2 mirror locks; a write to a key not read first takes that lock before it is applied. Strict
two-phase locking on documents makes ported check-then-act code serializable without SERIALIZABLE's
page-granular predicate locks, whose false conflicts between unrelated owners exhausted retries and
stranded shard pull claims under concurrent pullers (A3 contention bench, 2026-11-01). A transactional
query locks the rows it returns and restarts the transaction if one changed in between; per-owner
queries are phantom-safe because admission and merge serialize on the owner document (scheduler.py).
Deadlocks and lock timeouts retry the body; exhausted retries raise the scheduler's typed contention
error so it backs off exactly as it does on Firestore.

The privacy authority is still the customer-data Firestore (A5 mirrors it into Postgres later), so
``customer_client`` is required. ``conversations`` / ``content`` documents belong to Firestore; they
reach Postgres only under ``harness_customer_tables=True`` (hermetic goldens), never in production:
moving them is the A4 outbox + receipt-fence seam, not this PR.
"""

from __future__ import annotations

import re
import hashlib
import random
import time
from contextlib import contextmanager
from copy import deepcopy
from typing import Any, Callable, Iterator, TypeVar

from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from database.firestore_transaction_retry import FirestoreContentionExhausted

import database.jobstore.codec as codec
from database.jobstore.connection import Pool

# Same set as database.batch_pipeline_recovery.PROVIDER_STATES (not imported: that module pulls in Firestore).
PROVIDER_STATES = frozenset({'provider_pending', 'provider_running'})

T = TypeVar('T')

WRITE_BUDGET = 450
MAX_SERIALIZATION_RETRIES = 8
# Above Postgres' default deadlock_timeout (1s), so a deadlock is detected before a wait times out.
LOCK_TIMEOUT = '2s'
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
_LOCK_NOT_AVAILABLE = '55P03'


class DocumentChanged(Exception):
    """A row a transactional query returned changed before it was locked; the body restarts."""


class JobStoreContentionExhausted(FirestoreContentionExhausted):
    """Every bounded attempt met a conflict. The scheduler's contention backoff catches the base type."""


def jsonb(value: dict):
    # psycopg joins the lockfile separately; until then pyright cannot resolve it.
    from psycopg.types.json import Jsonb  # pyright: ignore[reportMissingImports]

    return Jsonb(value, dumps=codec.dumps)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, DocumentChanged):
        return True
    return getattr(exc, 'sqlstate', None) in {_SERIALIZATION_FAILURE, _DEADLOCK, _LOCK_NOT_AVAILABLE}


def lock_key(namespace: str, table: str, key: str) -> str:
    """The advisory-lock name of one document; DualStore's mirror locks the same name."""
    return f'{namespace}/{table}/{key}'


class PostgresTransaction:
    def __init__(self, store: 'PostgresStore', conn: Any):
        self.store = store
        self.conn = conn
        self.cache: dict[tuple[str, str], dict] = {}
        self.writes: dict[tuple[str, str], dict] = {}
        self.patches: dict[tuple[str, str], dict] = {}
        # Documents this transaction holds a lock on (row lock or, when missing, the key's advisory lock).
        self.locked: set[tuple[str, str]] = set()

    # -- locking --------------------------------------------------------------------------
    def _lock_read(self, table: str, key: str) -> dict:
        """The newest committed document, locked until this transaction ends ({} if missing, key locked)."""
        found = self.store.read_doc(self.conn, table, key, lock=True)
        if not found:
            self.store.lock_name(self.conn, table, key)
            # Re-read under the key lock: an insert that committed before we took it is visible now.
            found = self.store.read_doc(self.conn, table, key, lock=True)
        self.locked.add((table, key))
        return found

    def _locked_query_row(self, key: str, doc: dict) -> dict:
        """Lock a job row a transactional query returned; restart if it changed before the lock."""
        address = ('jobs', key)
        if address in self.locked:
            return doc  # held since an earlier read: the query saw the locked version
        current = self._lock_read(*address)
        self.cache.setdefault(address, current)
        if current != doc:
            raise DocumentChanged('a queried job changed before it was locked')
        return doc

    # -- Transaction protocol -------------------------------------------------------------
    def get(self, table: str, key: str) -> dict:
        address = (table, key)
        self.store.require_table(table)
        if address not in self.cache:
            self.cache[address] = self._lock_read(table, key)
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
        row = self.store.first_pending_in(self.conn, owner_key)
        return self._locked_query_row(*row) if row else None

    def first_ready_pending(self, owner_key: str) -> dict | None:
        """The owner's earliest-captured pending row that already has a result (bounded head wait)."""
        row = self.store.first_pending_in(self.conn, owner_key, result_ready=True)
        return self._locked_query_row(*row) if row else None

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        # Two matches fail closed, exactly like the Firestore query.
        rows = self.conn.execute(
            "SELECT key, doc FROM jobs WHERE namespace = %s AND owner_key = %s AND priority = %s AND state = 'ready' "
            'AND next_id = %s ORDER BY key COLLATE "C" LIMIT 2',
            (self.store.namespace, owner_key, priority, segment_id),
        ).fetchall()
        return self._locked_query_row(*rows[0]) if len(rows) == 1 else None

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
        # Blind writes take the document lock first, in one order, so they fence readers of a missing key.
        for address in sorted(set(self.writes) | set(self.patches)):
            if address not in self.locked:
                self.cache.setdefault(address, self._lock_read(*address))
        for (table, key), value in self.writes.items():
            self.store.write_doc(self.conn, table, key, value)
        for (table, key), fields in self.patches.items():
            current = self.cache[(table, key)]
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
        for attempt in range(MAX_SERIALIZATION_RETRIES):
            if attempt:
                # Jittered, bounded: two bodies that deadlocked must not collide again in lockstep.
                time.sleep(random.uniform(0, min(0.2, 0.005 * 2**attempt)))
            with self.pool.connection() as conn:
                try:
                    with conn.transaction():
                        conn.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                        conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
                        view = PostgresTransaction(self, conn)
                        result = body(view)
                        view.flush()
                        return result
                except Exception as exc:
                    if not _is_retryable(exc):
                        raise
                    last = exc
        raise JobStoreContentionExhausted('job store transaction kept conflicting') from last

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        if state not in _DUE_FIELDS:
            raise ValueError('only recoverable states may be scanned')
        field = _DUE_FIELDS[state]  # a fixed column name, never caller text
        with self._read_conn() as conn:
            rows = conn.execute(
                f'SELECT key FROM jobs WHERE namespace = %s AND state = %s AND {field} <= %s '
                f'ORDER BY {field}, key COLLATE "C" LIMIT %s',
                (self.namespace, state, now, max(1, min(limit, 100))),
            ).fetchall()
        return [row[0] for row in rows]

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        if ready_only:
            with self._read_conn() as conn:
                row = conn.execute(
                    "SELECT min(enqueued_at) FROM jobs WHERE namespace = %s AND priority = %s AND state = 'ready'",
                    (self.namespace, priority),
                ).fetchone()
            return row[0]
        # The uncommitted-age proxy walks a bounded FIFO prefix past allowance holds, as on Firestore.
        from database.batch_pipeline_store import OLDEST_POLICY_HOLD_SCAN_LIMIT, is_allowance_policy_hold

        with self._read_conn() as conn:
            rows = conn.execute(
                'SELECT enqueued_at, doc FROM jobs WHERE namespace = %s AND priority = %s AND merge_pending '
                'ORDER BY enqueued_at, key COLLATE "C" LIMIT %s',
                (self.namespace, priority, OLDEST_POLICY_HOLD_SCAN_LIMIT + 1),
            ).fetchall()
        oldest_hold = None
        for enqueued_at, doc in rows[:OLDEST_POLICY_HOLD_SCAN_LIMIT]:
            if not is_allowance_policy_hold(doc):
                return enqueued_at
            oldest_hold = enqueued_at if oldest_hold is None else oldest_hold
        # Truncated by the sentinel row: fail toward the oldest hold's age, never a false fresh zero.
        return oldest_hold if len(rows) > OLDEST_POLICY_HOLD_SCAN_LIMIT else None

    def ready_for_capacity(self, priority: int, now: float) -> int:
        """Due ready work awaiting a first or re-authorized attempt; held and decisionless rows never count."""
        with self._read_conn() as conn:
            row = conn.execute(
                "SELECT count(*) FROM jobs WHERE namespace = %s AND priority = %s AND state = 'ready' "
                "AND merge_pending AND available_at <= %s "
                "AND doc->'compute_decision'->>'outcome' IN ('unattempted', 'allowed')",
                (self.namespace, priority, now),
            ).fetchone()
        return int(row[0])

    def longest_ready_pending(self, owner_key: str) -> dict | None:
        # A hint read outside any transaction; rows without ready_at never match (Firestore order_by semantics).
        with self._read_conn() as conn:
            row = conn.execute(
                "SELECT doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending "
                "AND state = 'result_ready' AND doc ? 'ready_at' ORDER BY doc->'ready_at', key COLLATE \"C\" LIMIT 1",
                (self.namespace, owner_key),
            ).fetchone()
        return row[0] if row else None

    def fresh_pending(self, owner_key: str, limit: int) -> list[dict]:
        # A hint read outside any transaction; the fresh-first transaction re-verifies it.
        with self._read_conn() as conn:
            rows = conn.execute(
                "SELECT doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending "
                "AND doc->'fresh_capture' = 'true'::jsonb ORDER BY capture_at, key COLLATE \"C\" LIMIT %s",
                (self.namespace, owner_key, max(1, min(limit, 32))),
            ).fetchall()
        return [row[0] for row in rows]

    def held_merge_owners(self, limit: int, *, after: str | None = None) -> list[tuple[str, str | None]]:
        """Owners whose catch-up commits are held: (owner key, owner id from the earliest pending job, or None)."""
        with self._read_conn() as conn:
            marks = conn.execute(
                # COLLATE "C": Firestore orders document names bytewise, whatever the database's collation.
                "SELECT key FROM docs WHERE namespace = %s AND tbl = 'merge_holds' AND doc->'held' = 'true'::jsonb "
                'AND (%s::text IS NULL OR key COLLATE "C" > %s) ORDER BY key COLLATE "C" LIMIT %s',
                (self.namespace, after, after, max(1, min(limit, 100))),
            ).fetchall()
            owners = []
            for (key,) in marks:
                job = self.first_pending_in(conn, key)
                owners.append((key, job[1].get('owner_id') if job else None))
        return owners

    def projection_successor(self, owner_key: str, previous: str | None) -> str | None:
        """The owner's result committed directly after ``previous``; two matches fail closed (a hint)."""
        # Firestore equality on None matches an explicit null only, never a missing field.
        previous_match = (
            "doc->'previous_segment_id' = 'null'::jsonb"
            if previous is None
            else ("doc->>'previous_segment_id' = %(previous)s AND jsonb_typeof(doc->'previous_segment_id') = 'string'")
        )
        with self._read_conn() as conn:
            rows = conn.execute(
                f"SELECT key FROM results WHERE namespace = %(ns)s AND doc->>'owner_key' = %(owner)s "
                f'AND {previous_match} ORDER BY key COLLATE "C" LIMIT 2',
                {'ns': self.namespace, 'owner': owner_key, 'previous': previous},
            ).fetchall()
        return rows[0][0] if len(rows) == 1 else None

    def oldest_retry(self, priority: int) -> float | None:
        with self._read_conn() as conn:
            row = conn.execute(
                'SELECT min(retry_started_at) FROM jobs WHERE namespace = %s AND priority = %s '
                'AND retry_started_at >= 0',
                (self.namespace, priority),
            ).fetchone()
        return row[0]

    def acquire_pull_claim(self, shard: str, token: str, now: float, ttl: float) -> bool:
        def acquire(tx):
            if tx.get('pull_claims', shard).get('expires_at', 0) > now:
                return False
            tx.put('pull_claims', shard, {'token': token, 'expires_at': now + ttl})
            return True

        return self.run(acquire)

    def control_candidate(self, priority: int, pool: str, now: float, *, worker_id: str = '', exclude=()) -> str | None:
        if priority not in (0, 1, 2) or pool not in {'batch', 'live'}:
            raise ValueError('bounded priority and pool required')
        p, at = f'p{priority}', f'p{priority}_{pool}_at'
        with self._read_conn() as conn:
            rows = conn.execute(
                f'SELECT key, {p}_service FROM control WHERE namespace = %s AND {p}_active AND {p}_service >= 0 '
                f'AND {at} <= %s ORDER BY {p}_service, {at}, key COLLATE "C" LIMIT %s',
                (self.namespace, now, 64 if worker_id else 1),
            ).fetchall()
        if worker_id:
            rows = [row for row in rows if row[0] not in exclude]
            rows.sort(key=lambda row: (row[1], hashlib.sha256(f'{worker_id}:{row[0]}'.encode()).digest()))
        return rows[0][0] if rows else None

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

    def projection_page(
        self, limit: int = 100, *, after=None, states: tuple[str, ...] | None = None
    ) -> tuple[list[str], Any]:
        from database.batch_pipeline_store import PROJECTION_DISCOVERY_STATES, PROJECTION_OBLIGATION_STATES

        states = PROJECTION_DISCOVERY_STATES if states is None else states
        if not states or not set(states) <= set(PROJECTION_OBLIGATION_STATES):
            raise ValueError('projection discovery states must be drain states')
        size = max(1, min(limit, 100))
        clause, params = '', [self.namespace, list(states)]
        if after is not None:
            clause = 'AND (committed_at, key COLLATE "C") > (%s, %s)'
            params += [after[0], after[1]]
        with self._read_conn() as conn:
            rows = conn.execute(
                "SELECT key, committed_at FROM results WHERE namespace = %s "
                f"AND projection_state = ANY(%s) {clause} "
                'ORDER BY committed_at, key COLLATE "C" LIMIT %s',
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

    def read_doc(self, conn: Any, table: str, key: str, *, lock: bool = False) -> dict:
        suffix = ' FOR UPDATE' if lock else ''
        if table in _TYPED:
            row = conn.execute(
                f'SELECT doc FROM {table} WHERE namespace = %s AND key = %s{suffix}', (self.namespace, key)
            )
        else:
            row = conn.execute(
                f'SELECT doc FROM docs WHERE namespace = %s AND tbl = %s AND key = %s{suffix}',
                (self.namespace, table, key),
            )
        found = row.fetchone()
        return found[0] if found else {}

    def lock_name(self, conn: Any, table: str, key: str) -> None:
        """Hold one document's advisory lock until the transaction ends (the key may not exist yet)."""
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))', (lock_key(self.namespace, table, key),))

    def first_pending_in(self, conn: Any, owner_key: str, *, result_ready: bool = False) -> tuple[str, dict] | None:
        state = "AND state = 'result_ready' " if result_ready else ''
        return conn.execute(
            f'SELECT key, doc FROM jobs WHERE namespace = %s AND owner_key = %s AND merge_pending {state}'
            'ORDER BY capture_at, key COLLATE "C" LIMIT 1',
            (self.namespace, owner_key),
        ).fetchone()

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
