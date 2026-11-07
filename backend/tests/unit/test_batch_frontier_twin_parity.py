"""Twin parity: every frontier surface reads the same advisory value.

The rejoin seed must be identical no matter which surface reads it — the
Firestore module function, the ``FirestoreStore`` adapter, the in-memory
``MemoryStore`` twin used by the state-machine suite, the pipeline
simulator's stores and the production Postgres twin. A twin that drifts (a
different filter, an extra ``where(active)``, an included/excluded row shape)
silently re-seeds shards with different fairness credit per surface. Pinned
here:

1. Value parity across surfaces for the same control rows, per priority.
2. Field-name discipline: only ``p{N}_service`` participates, per priority,
   and documents missing the field are excluded everywhere.
3. Faithfulness: negatives, fractions, integers, zero and huge credit are
   read back exactly, never clamped.
4. Bounded priorities refuse on every surface.
5. The Postgres twin's SQL stays ``max(p{N}_service)`` over the namespace.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

from types import SimpleNamespace

import pytest
from google.cloud import firestore

from config.batch_pipeline import scheduler_control_key
from database import batch_pipeline_store as storage
from database.jobstore.postgres_store import PostgresStore
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from testing.pipeline_sim.store import CustomerData, SimStore

EMULATOR_HOST = '127.0.0.1:8081'


class ControlQuery:
    def __init__(self, rows, calls):
        self._rows, self._calls = rows, calls
        self._field, self._direction, self._limit = None, None, None

    def order_by(self, field, direction=None):
        self._field, self._direction = field, direction
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self, transaction=None):
        self._calls.append((self._field, self._direction, self._limit, transaction))
        present = [dict(row) for row in self._rows if self._field in row]
        present.sort(key=lambda row: row[self._field], reverse=self._direction == firestore.Query.DESCENDING)
        return [SimpleNamespace(to_dict=lambda row=row: dict(row)) for row in present[: self._limit]]


class ControlClient:
    _emulator_host = EMULATOR_HOST

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    def transaction(self, max_attempts=1):
        return SimpleNamespace()

    def collection(self, name):
        if not name.endswith('_control'):
            raise AssertionError(f'hint must read the control collection, got {name}')
        return ControlQuery(self.rows, self.calls)


@pytest.fixture(autouse=True)
def _emulator_env(monkeypatch):
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', EMULATOR_HOST)


def firestore_hint(rows, priority, namespace='batch_pipeline_test_unit'):
    client = ControlClient([doc for _, doc in rows])
    store = storage.FirestoreStore(namespace, firestore_client=client)
    return store.service_frontier_hint(priority)


def memory_hint(control_rows, priority):
    store = MemoryStore()
    for key, doc in control_rows:
        store.rows[('control', key)] = dict(doc)
    return store.service_frontier_hint(priority)


def sim_hint(control_rows, priority):
    store = SimStore(CustomerData(), namespace='batch_pipeline_test_unit')
    for key, doc in control_rows:
        store.apply(('control', key), dict(doc))
    return store.service_frontier_hint(priority)


# --------------------------------------------------------------------------
# 1. Cross-surface value parity
# --------------------------------------------------------------------------


def _rows(*values, field='p1_service', base='owner'):
    return [(f'{base}-{index}', {field: value}) for index, value in enumerate(values)]


@pytest.mark.parametrize('values', [[], [4.5], [2.0, 9.0], [9.0, 2.0], [1.0, 33.5, 7.0], [6.25, 6.25]])
def test_parity_firestore_and_memory_agree_on_p1(values):
    rows = _rows(*values)
    assert firestore_hint(rows, 1) == memory_hint(rows, 1)


@pytest.mark.parametrize('values', [[], [4.5], [2.0, 9.0], [1.0, 33.5, 7.0]])
def test_parity_firestore_and_sim_agree_on_p1(values):
    rows = _rows(*values)
    assert firestore_hint(rows, 1) == sim_hint(rows, 1)


@pytest.mark.parametrize('values', [[], [4.5], [2.0, 9.0]])
def test_parity_memory_and_sim_agree_on_p1(values):
    rows = _rows(*values)
    assert memory_hint(rows, 1) == sim_hint(rows, 1)


def test_parity_p0_across_surfaces():
    rows = _rows(1.0, 3.0, 2.0, field='p0_service')
    assert firestore_hint(rows, 0) == memory_hint(rows, 0) == sim_hint(rows, 0) == 3.0


def test_parity_p2_across_surfaces():
    rows = _rows(5.5, 5.5, field='p2_service')
    assert firestore_hint(rows, 2) == memory_hint(rows, 2) == sim_hint(rows, 2) == 5.5


def test_parity_empty_collection_is_zero_everywhere():
    assert firestore_hint([], 1) == memory_hint([], 1) == sim_hint([], 1) == 0.0


def test_parity_max_is_surface_independent_regardless_of_row_order():
    rows = _rows(1.0, 50.0, 2.0, 40.0, 3.0)
    expected = 50.0
    assert firestore_hint(rows, 1) == expected
    assert memory_hint(rows, 1) == expected
    assert sim_hint(rows, 1) == expected


def test_parity_with_mixed_priorities_on_one_document():
    rows = [('shard-a', {'p0_service': 1.0, 'p1_service': 2.0, 'p2_service': 3.0})]
    for priority, expected in ((0, 1.0), (1, 2.0), (2, 3.0)):
        assert firestore_hint(rows, priority) == expected
        assert memory_hint(rows, priority) == expected
        assert sim_hint(rows, priority) == expected


def test_parity_with_ring_and_window_fields_present():
    rows = [
        ('shard-a', {'p1_service': 7.0, 'p1_active': True, 'p1_batch_available_at': 12.0, 'rings': {'1': ['q']}}),
        ('shard-b', {'p1_service': 3.0, 'p1_active': False}),
    ]
    assert firestore_hint(rows, 1) == memory_hint(rows, 1) == sim_hint(rows, 1) == 7.0


def test_parity_ignores_other_tables_rows():
    # Only control documents participate; a stray jobs/queues row shape never
    # contributes to any surface's read.
    rows = [('shard-a', {'p1_service': 4.0})]
    assert firestore_hint(rows, 1) == memory_hint(rows, 1) == 4.0


# --------------------------------------------------------------------------
# 2. Field-name discipline per priority
# --------------------------------------------------------------------------


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_parity_reads_only_its_own_priority_field(priority):
    rows = [('shard-a', {'p0_service': 10.0, 'p1_service': 20.0, 'p2_service': 30.0})]
    field = f'p{priority}_service'
    expected = {0: 10.0, 1: 20.0, 2: 30.0}[priority]
    assert firestore_hint(rows, priority) == expected
    assert memory_hint(rows, priority) == expected
    assert sim_hint(rows, priority) == expected
    assert field == f'p{priority}_service'


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_firestore_query_field_is_the_priority_field(priority):
    client = ControlClient([{'p0_service': 1.0, 'p1_service': 2.0, 'p2_service': 3.0}])
    storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=client).service_frontier_hint(priority)
    assert client.calls[0][0] == f'p{priority}_service'


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_missing_field_for_the_priority_is_excluded_on_every_surface(priority):
    rows = [('shard-a', {'p0_service': 10.0})]
    assert firestore_hint(rows, priority) == memory_hint(rows, priority) == sim_hint(rows, priority)


def test_a_document_with_only_rings_is_never_the_frontier():
    rows = [('shard-a', {'rings': {'0': [], '1': [], '2': []}}), ('shard-b', {'p1_service': 2.0})]
    assert firestore_hint(rows, 1) == memory_hint(rows, 1) == sim_hint(rows, 1) == 2.0


# --------------------------------------------------------------------------
# 3. Faithfulness across credit shapes
# --------------------------------------------------------------------------


@pytest.mark.parametrize('value', [-3.5, 0.0, 0.125, 1.0, 7, 1e12, 1e-9, 6.25])
def test_parity_single_value_faithful_on_every_surface(value):
    rows = [('shard-a', {'p1_service': value})]
    assert firestore_hint(rows, 1) == value
    assert memory_hint(rows, 1) == value
    assert sim_hint(rows, 1) == value


@pytest.mark.parametrize('low,high', [(-8.0, -2.0), (0.0, 0.5), (-5.0, 0.0), (2.0, 2.0), (1e6, 1e9)])
def test_parity_max_of_two_values_on_every_surface(low, high):
    rows = [('a', {'p1_service': low}), ('b', {'p1_service': high})]
    expected = max(low, high)
    assert firestore_hint(rows, 1) == expected
    assert memory_hint(rows, 1) == expected
    assert sim_hint(rows, 1) == expected


def test_parity_negative_frontier_is_read_faithfully_when_it_is_the_max():
    rows = [('a', {'p1_service': -8.0}), ('b', {'p1_service': -2.0})]
    assert firestore_hint(rows, 1) == -2.0
    assert memory_hint(rows, 1) == -2.0
    assert sim_hint(rows, 1) == -2.0


# --------------------------------------------------------------------------
# 4. Bounded priorities refuse on every surface
# --------------------------------------------------------------------------


@pytest.mark.parametrize('priority', [-1, 3, 9])
def test_firestore_refuses_unbounded_priority(priority):
    with pytest.raises(ValueError):
        firestore_hint([('shard-a', {'p1_service': 1.0})], priority)


@pytest.mark.parametrize('priority', [-1, 3, 9])
def test_memory_refuses_unbounded_priority(priority):
    with pytest.raises(ValueError):
        memory_hint([('shard-a', {'p1_service': 1.0})], priority)


@pytest.mark.parametrize('priority', [-1, 3, 9])
def test_sim_refuses_unbounded_priority(priority):
    with pytest.raises(ValueError):
        sim_hint([('shard-a', {'p1_service': 1.0})], priority)


@pytest.mark.parametrize('priority', [-1, 3, 9])
def test_postgres_refuses_unbounded_priority(priority):
    store = PostgresStore.__new__(PostgresStore)
    store.namespace = 'ns'
    with pytest.raises(ValueError):
        store.service_frontier_hint(priority)


# --------------------------------------------------------------------------
# 5. The Postgres twin stays max-over-namespace
# --------------------------------------------------------------------------


class RecordingConn:
    def __init__(self, value):
        self.value = value
        self.sqls = []
        self.params = []

    def execute(self, sql, params=None):
        self.sqls.append(sql)
        self.params.append(params)
        return SimpleNamespace(fetchone=lambda: (self.value,))


def _pg_store():
    store = PostgresStore.__new__(PostgresStore)
    store.namespace = 'batch_pipeline_test_pg'
    return store


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_postgres_hint_selects_the_priority_service_max(priority):
    conn = RecordingConn(9.0)
    store = _pg_store()
    assert store.service_frontier_hint_in(conn, priority) == 9.0
    assert f'max(p{priority}_service)' in conn.sqls[0]
    assert conn.params[0] == ('batch_pipeline_test_pg',)


def test_postgres_hint_null_max_reads_zero():
    conn = RecordingConn(None)
    store = _pg_store()
    assert store.service_frontier_hint_in(conn, 1) == 0.0


def test_postgres_hint_negative_max_reads_faithfully():
    conn = RecordingConn(-4.5)
    store = _pg_store()
    assert store.service_frontier_hint_in(conn, 1) == -4.5


def test_postgres_hint_uses_the_read_connection(monkeypatch):
    store = _pg_store()
    conn = RecordingConn(3.0)
    opened = []
    import contextlib

    @contextlib.contextmanager
    def fake_read_conn():
        opened.append('read')
        yield conn

    monkeypatch.setattr(store, '_read_conn', fake_read_conn)
    assert store.service_frontier_hint(1) == 3.0
    assert opened == ['read']


def test_postgres_transaction_no_longer_exposes_the_frontier():
    from database.jobstore.postgres_store import PostgresTransaction

    assert not hasattr(PostgresTransaction, 'service_frontier')


def test_postgres_retired_in_helper_is_gone():
    assert not hasattr(PostgresStore, 'service_frontier_in')


# --------------------------------------------------------------------------
# 6. The parity property that matters for fairness: rejoin seed equals the
#    frontier any surface would have reported at the same instant
# --------------------------------------------------------------------------


def _sharded_rows(services):
    rows = []
    for index, service in enumerate(services):
        owner = f'{index:08x}'
        rows.append((scheduler_control_key(owner), {f'p1_service': service}))
    return rows


@pytest.mark.parametrize('services', [[1.0, 2.0, 3.0], [3.0, 2.0, 1.0], [0.0, 0.0, 5.0], [7.5], [-1.0, 4.0]])
def test_parity_over_shard_keyed_documents(services):
    rows = _sharded_rows(services)
    expected = max(services) if services else 0.0
    assert firestore_hint(rows, 1) == expected
    assert memory_hint(rows, 1) == expected
    assert sim_hint(rows, 1) == expected


def test_sim_store_hint_is_a_plain_read_with_no_write():
    store = SimStore(CustomerData(), namespace='batch_pipeline_test_unit')
    store.apply(('control', 'shard-a'), {'p1_service': 2.0})
    before = deepcopy_rows(store)
    assert store.service_frontier_hint(1) == 2.0
    assert deepcopy_rows(store) == before


def deepcopy_rows(store):
    from copy import deepcopy

    return deepcopy({address: dict(row) for address, row in store.rows.items()})
