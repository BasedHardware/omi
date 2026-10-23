"""The pipeline simulator's store, backed by the REAL ``PostgresStore`` (A1 gate).

``SimStore`` is an in-memory model; this subclass keeps its public surface (``rows``, ``jobs()``, ``mutate``,
``purge``, ``observers`` ...) but sends every transaction through ``database.jobstore.PostgresStore.run``,
so the characterization goldens are produced by the production doc-mode code: its SQL, its jsonb round
trip, its serialization-failure retry and its privacy flush. The privacy authority is the same real
fence over ``CustomerData``. Only the harness's out-of-band edits (``apply`` / ``delete`` / ``mutate`` /
``purge``, models of non-simulated writers) bypass transactions, as they do in ``SimStore``.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Callable, Iterator, TypeVar

from database.jobstore.connection import Pool
from database.jobstore.postgres_store import PostgresStore, PostgresTransaction
from testing.pipeline_sim.store import CustomerData, SimStore

T = TypeVar('T')
_TYPED = ('jobs', 'results', 'control')


class PgRows(Mapping):
    """Read-only ``{(table, key): document}`` view over the namespace; mutation goes through the store."""

    def __init__(self, store: 'PgSimStore'):
        self._store = store

    def _all(self) -> dict[tuple[str, str], dict]:
        namespace = self._store.pg.namespace
        sql = ' UNION ALL '.join(f"SELECT '{t}', key, doc FROM {t} WHERE namespace = %s" for t in _TYPED)
        sql += ' UNION ALL SELECT tbl, key, doc FROM docs WHERE namespace = %s'
        with self._store.pg.pool.connection() as conn:
            rows = conn.execute(sql, (namespace,) * (len(_TYPED) + 1)).fetchall()
        return {(table, key): doc for table, key, doc in rows}

    def __getitem__(self, address: tuple[str, str]) -> dict:
        document = self._store.read(*address)
        if not document:
            raise KeyError(address)
        return document

    def get(self, address, default=None):  # type: ignore[override]
        return self._store.read(*address) or default

    def __contains__(self, address: object) -> bool:
        return isinstance(address, tuple) and bool(self._store.read(*address))

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(self._all())

    def __len__(self) -> int:
        return len(self._all())

    def items(self):  # type: ignore[override]
        return self._all().items()


class _Recording:
    """Delegates to the PostgresTransaction; remembers each written row's committed predecessor."""

    def __init__(self, tx: PostgresTransaction):
        self._tx = tx

    def get(self, table: str, key: str) -> dict:
        return self._tx.get(table, key)

    def put(self, table: str, key: str, value: dict) -> None:
        self._tx.get(table, key)  # first touch caches the committed row (the observers' "previous")
        self._tx.put(table, key, value)

    def patch(self, table: str, key: str, fields: dict) -> None:
        self._tx.get(table, key)
        self._tx.patch(table, key, fields)

    def first_pending(self, owner_key: str) -> dict | None:
        return self._tx.first_pending(owner_key)

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        return self._tx.ready_predecessor(owner_key, priority, segment_id)

    def service_frontier(self, priority: int) -> float:
        return self._tx.service_frontier(priority)

    def check_privacy(self, uid: str, conversation_ids=(), expected_generation: int | None = None) -> int:
        return self._tx.check_privacy(uid, conversation_ids, expected_generation)


class PgSimStore(SimStore):
    def __init__(self, customer: CustomerData, *, namespace: str, pool: Pool):
        super().__init__(customer, namespace=namespace)
        self.pg = PostgresStore(namespace, pool=pool, customer_client=customer.client, harness_customer_tables=True)
        self.rows = PgRows(self)  # type: ignore[assignment]

    # -- reads ------------------------------------------------------------------------------------------
    def read(self, table: str, key: str) -> dict:
        with self.pg.pool.connection() as conn:
            return self.pg.read_doc(conn, table, key)

    def get(self, table: str, key: str) -> dict:
        return deepcopy(self.read(table, key))

    def jobs(self) -> list[dict]:
        with self.pg.pool.connection() as conn:
            return [row[0] for row in conn.execute('SELECT doc FROM jobs WHERE namespace = %s', (self.pg.namespace,))]

    def jobs_in_state(self, state: str) -> list[str]:
        with self.pg.pool.connection() as conn:
            rows = conn.execute(
                'SELECT key FROM jobs WHERE namespace = %s AND state = %s ORDER BY key', (self.pg.namespace, state)
            ).fetchall()
        return [row[0] for row in rows]

    def due(self, state: str, now: float, limit: int = 100) -> list[str]:
        return self.pg.due(state, now, limit)

    def oldest(self, priority: int, *, ready_only: bool = False) -> float | None:
        return self.pg.oldest(priority, ready_only=ready_only)

    def oldest_retry(self, priority: int) -> float | None:
        return self.pg.oldest_retry(priority)

    def control_candidate(self, priority: int, pool: str, now: float) -> str | None:
        return self.pg.control_candidate(priority, pool, now)

    def first_pending(self, owner_key: str) -> dict | None:
        return self.pg.run(lambda tx: tx.first_pending(owner_key))

    def service_frontier(self, priority: int) -> float:
        return self.pg.run(lambda tx: tx.service_frontier(priority))

    def ready_predecessor(self, owner_key: str, priority: int, segment_id: str) -> dict | None:
        return self.pg.run(lambda tx: tx.ready_predecessor(owner_key, priority, segment_id))

    # -- transactions -----------------------------------------------------------------------------------
    def run(self, body: Callable[[Any], T]) -> T:  # type: ignore[override]
        self.transactions += 1
        holder: dict[str, PostgresTransaction] = {}

        def wrapped(tx: PostgresTransaction) -> T:
            holder['tx'] = tx  # a serialization retry replaces it: the last attempt is the committed one
            return body(_Recording(tx))

        result = self.pg.run(wrapped)
        tx = holder['tx']
        for address, value in tx.writes.items():
            self._notify(address, tx.cache.get(address, {}), value)
        for address, fields in tx.patches.items():
            base = tx.writes.get(address, tx.cache.get(address, {}))
            self._notify(address, base, {**base, **fields})
        return result

    def _notify(self, address: tuple[str, str], previous: dict, value: dict) -> None:
        for observer in self.observers:
            observer(address, previous or {}, value)

    # -- harness edits (models of writers the simulation does not run) ----------------------------------
    def apply(self, address: tuple[str, str], value: dict) -> None:
        previous = self.read(*address)
        with self.pg.pool.connection() as conn:
            self.pg.write_doc(conn, address[0], address[1], deepcopy(value))
        self._notify(address, previous, value)

    def delete(self, table: str, key: str) -> None:
        with self.pg.pool.connection() as conn:
            if table in _TYPED:
                conn.execute(f'DELETE FROM {table} WHERE namespace = %s AND key = %s', (self.pg.namespace, key))
            else:
                conn.execute(
                    'DELETE FROM docs WHERE namespace = %s AND tbl = %s AND key = %s', (self.pg.namespace, table, key)
                )
