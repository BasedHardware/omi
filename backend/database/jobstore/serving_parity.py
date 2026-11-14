"""Counts-only comparisons of actual serving methods; never executes a claim or wake.

Frozen callers require ``match``. Live observations re-read both sides once; a
changing pair is ``unknown``, not evidence of parity. No payloads enter metrics.
Transaction queries run without flush(), so this cannot become a second writer.
"""

from __future__ import annotations

from contextlib import contextmanager
import time
from typing import Any

from prometheus_client import Counter

import database.jobstore.codec as codec
from database.jobstore.postgres_store import PostgresStore, PostgresTransaction
from database import rpc_deadline

STORE_QUERIES = frozenset(
    {
        'due',
        'oldest',
        'oldest_retry',
        'oldest_admissible_ready',
        'ready_for_capacity',
        'control_candidate',
        'control_candidates',
        'fresh_pending',
        'longest_ready_pending',
        'held_merge_owners',
        'projection_pending',
        'projection_page',
        'projection_successor',
    }
)
TRANSACTION_QUERIES = frozenset(
    {'get', 'first_pending', 'first_ready_pending', 'ready_predecessor', 'service_frontier'}
)
SERVING_PARITY_TOTAL = Counter(
    'omi_jobstore_serving_parity_total',
    'Actual serving-query comparisons; unknown is not a pass.',
    ['query', 'outcome'],
)


class _ParityPostgresStore(PostgresStore):
    """The serving implementation with bounded read connections and no writer dispatch."""

    def __init__(self, source: PostgresStore, budget_s: float):
        super().__init__(source.namespace, pool=source.pool, customer_client=None)
        self.budget_s = budget_s

    @contextmanager
    def _read_conn(self):
        remaining = rpc_deadline.remaining()
        budget = min(self.budget_s, remaining) if remaining is not None else self.budget_s
        if budget <= 0:
            raise TimeoutError('serving observation deadline exceeded')
        with self.pool.connection(timeout=budget, existing_only=True) as conn:
            with conn.transaction():
                remaining = rpc_deadline.remaining()
                budget = min(budget, remaining) if remaining is not None else budget
                if budget <= 0:
                    raise TimeoutError('serving observation deadline exceeded')
                conn.execute(f'SET LOCAL statement_timeout = {max(1, int(budget * 1000))}')
                yield conn

    read_connection = _read_conn


def query_value(store, query: str, args: tuple, kwargs: dict, *, transaction: bool, budget_s: float):
    allowed = TRANSACTION_QUERIES if transaction else STORE_QUERIES
    if query not in allowed:
        raise ValueError('only enumerated serving reads may be compared')
    if query == 'get':
        from database.jobstore.dual_store import MIRRORED_TABLES

        if (args[0] if args else kwargs.get('table')) not in MIRRORED_TABLES:
            raise ValueError('only mirrored batch documents may be compared')
    if isinstance(store, PostgresStore):
        bounded = _ParityPostgresStore(store, budget_s)
        if transaction:
            with bounded.read_connection() as conn:
                # Locks match the real transaction read; never flush buffered writes.
                return getattr(PostgresTransaction(bounded, conn), query)(*args, **kwargs)
        return getattr(bounded, query)(*args, **kwargs)
    from database.batch_pipeline_store import FirestoreStore, due

    if isinstance(store, FirestoreStore):
        rpc_deadline.bind_firestore_client(store.client)
        if query == 'due':
            # The serving wrapper promotes record recoveries. Observe its shared
            # query implementation without replaying that mutation.
            return due(store.client, store.namespace, *args, promote_recoveries=False, **kwargs)
    if transaction:
        return store.run(lambda tx: getattr(tx, query)(*args, **kwargs))
    return getattr(store, query)(*args, **kwargs)


def compare_serving_query(
    primary, shadow, query: str, *args: Any, transaction: bool = False, budget_s: float = 0.2, **kwargs: Any
) -> str:
    """Compare full ordered results and cursors on a stable pair. Errors fail closed.

    Two immediate observations bound the stability recheck. This is source proof
    machinery; it does not certify a ten-second live convergence/lag gate.
    """
    if query not in (TRANSACTION_QUERIES if transaction else STORE_QUERIES):
        raise ValueError('only enumerated serving reads may be compared')
    if primary.namespace != shadow.namespace:
        raise ValueError('serving parity requires one namespace')
    try:

        def read(store):
            return codec.canonical(query_value(store, query, args, kwargs, transaction=transaction, budget_s=budget_s))

        deadline = time.monotonic() + budget_s
        with rpc_deadline.rpc_deadline(deadline):
            before = read(primary), read(shadow)
            after = read(primary), read(shadow)
        if time.monotonic() > deadline:
            raise TimeoutError('serving observation exceeded its deadline')
        if before != after:
            outcome = 'unknown'
        elif before[0] == before[1]:
            outcome = 'match'
        else:
            outcome = 'mismatch'
    except Exception:
        outcome = 'error'
    SERVING_PARITY_TOTAL.labels(query=query, outcome=outcome).inc()
    return outcome
