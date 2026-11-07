"""The non-transactional frontier hint read: ``Store.service_frontier_hint``.

The rejoin fairness seed used to be read with an indexed query inside the
caller's transaction (``Transaction.service_frontier``). The query's limit-1
descending read lands on the argmax ``p{N}_service`` control document — the
shard every fairness scan of the winning priority rewrites — so every
rejoining admission joined the fleet's hottest abort set for a purely advisory
value and burned its five-attempt budget on ``outcome=exhausted`` storms. The
seed is now an advisory probe: same collection, same order, same bound, read
outside any transaction, never authorizing anything.

Pinned here, per priority and namespace:

1. The hint returns the maximum committed ``p{N}_service`` across the control
   collection, ``0.0`` on an empty collection, and faithfully reads negative
   or fractional credit rather than clamping it.
2. Documents missing the ordered field are excluded, exactly as the
   transactional query excluded them.
3. The query shape never drifts: one stream, the ``{namespace}_control``
   collection, ``p{N}_service`` descending, limit 1, and — the abort-set
   property — never bound to a transaction.
4. Bounded priorities only: outside ``(0, 1, 2)`` the hint refuses before any
   read, on the module function and on every store adapter.
5. The ``FirestoreStore`` adapter forwards namespace and priority unchanged to
   the module function and uses the injected client.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

from types import SimpleNamespace

import pytest
from google.cloud import firestore

from database import batch_pipeline_store as storage

EMULATOR_HOST = '127.0.0.1:8081'


class ControlQuery:
    """One control-collection query over fixed rows; records each stream binding."""

    def __init__(self, rows, calls, table):
        self._rows, self._calls, self._table = rows, calls, table
        self._field, self._direction, self._limit = None, None, None

    def order_by(self, field, direction=None):
        self._field, self._direction = field, direction
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self, transaction=None):
        self._calls.append((self._table, self._field, self._direction, self._limit, transaction))
        if self._field is None or self._limit is None:
            raise AssertionError('hint must be an ordered, bounded query')
        present = [dict(row) for row in self._rows if self._field in row]
        present.sort(key=lambda row: row[self._field], reverse=self._direction == firestore.Query.DESCENDING)
        return [SimpleNamespace(to_dict=lambda row=row: dict(row)) for row in present[: self._limit]]


class SimpleTx:
    """Duck-typed Firestore transaction for bodies that only read."""

    _max_attempts = 1
    _read_only = False
    _id = None

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = b'synthetic'

    def _commit(self):
        self._id = None

    def _rollback(self):
        self._id = None


class ControlClient:
    """Minimal client exposing only a control collection; records stream bindings."""

    _emulator_host = EMULATOR_HOST

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    def transaction(self, max_attempts=1):
        return SimpleTx()

    def collection(self, name):
        if not name.endswith('_control'):
            raise AssertionError(f'hint must read the control collection, got {name}')
        return ControlQuery(self.rows, self.calls, name)


@pytest.fixture(autouse=True)
def _emulator_env(monkeypatch):
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', EMULATOR_HOST)


@pytest.fixture
def make_store():
    def build(rows=(), namespace='batch_pipeline_test_unit'):
        return storage.FirestoreStore(namespace, firestore_client=ControlClient(rows))

    return build


# --------------------------------------------------------------------------
# 1. Empty collection reads as the zero seed
# --------------------------------------------------------------------------


def test_hint_empty_collection_priority_0_is_zero(make_store):
    assert make_store().service_frontier_hint(0) == 0.0


def test_hint_empty_collection_priority_1_is_zero(make_store):
    assert make_store().service_frontier_hint(1) == 0.0


def test_hint_empty_collection_priority_2_is_zero(make_store):
    assert make_store().service_frontier_hint(2) == 0.0


def test_hint_empty_module_function_priority_0_is_zero():
    assert storage.service_frontier_hint(ControlClient(), 'batch_pipeline_test_unit', 0) == 0.0


def test_hint_empty_module_function_priority_1_is_zero():
    assert storage.service_frontier_hint(ControlClient(), 'batch_pipeline_test_unit', 1) == 0.0


def test_hint_empty_module_function_priority_2_is_zero():
    assert storage.service_frontier_hint(ControlClient(), 'batch_pipeline_test_unit', 2) == 0.0


# --------------------------------------------------------------------------
# 2. The seed is the maximum committed service
# --------------------------------------------------------------------------


def test_hint_single_document_is_its_value(make_store):
    store = make_store([{'p1_service': 4.5}])
    assert store.service_frontier_hint(1) == 4.5


def test_hint_returns_the_larger_of_two_documents(make_store):
    store = make_store([{'p1_service': 2.0}, {'p1_service': 9.0}])
    assert store.service_frontier_hint(1) == 9.0


def test_hint_returns_the_larger_when_inserted_in_reverse(make_store):
    store = make_store([{'p1_service': 9.0}, {'p1_service': 2.0}])
    assert store.service_frontier_hint(1) == 9.0


def test_hint_over_three_documents_is_the_maximum(make_store):
    store = make_store([{'p0_service': 1.0}, {'p0_service': 33.5}, {'p0_service': 7.0}])
    assert store.service_frontier_hint(0) == 33.5


def test_hint_priorities_are_independent(make_store):
    store = make_store([{'p0_service': 1.0}, {'p1_service': 22.0}, {'p2_service': 3.0}])
    assert store.service_frontier_hint(0) == 1.0
    assert store.service_frontier_hint(1) == 22.0
    assert store.service_frontier_hint(2) == 3.0


def test_hint_equal_values_return_that_value(make_store):
    store = make_store([{'p2_service': 6.25}, {'p2_service': 6.25}])
    assert store.service_frontier_hint(2) == 6.25


def test_hint_reads_negative_credit_faithfully(make_store):
    store = make_store([{'p1_service': -3.5}])
    assert store.service_frontier_hint(1) == -3.5


def test_hint_reads_negative_maximum_faithfully(make_store):
    store = make_store([{'p1_service': -8.0}, {'p1_service': -2.0}])
    assert store.service_frontier_hint(1) == -2.0


def test_hint_reads_fractional_credit_faithfully(make_store):
    store = make_store([{'p0_service': 0.125}])
    assert store.service_frontier_hint(0) == 0.125


def test_hint_reads_integer_credit_as_number(make_store):
    store = make_store([{'p2_service': 7}])
    assert store.service_frontier_hint(2) == 7


def test_hint_reads_a_very_large_frontier(make_store):
    store = make_store([{'p1_service': 1e15}])
    assert store.service_frontier_hint(1) == 1e15


def test_hint_reads_a_tiny_frontier(make_store):
    store = make_store([{'p1_service': 1e-9}])
    assert store.service_frontier_hint(1) == 1e-9


def test_hint_zero_is_a_valid_stored_frontier(make_store):
    store = make_store([{'p0_service': 0.0}])
    assert store.service_frontier_hint(0) == 0.0


def test_hint_zero_beats_negative_sibling(make_store):
    store = make_store([{'p0_service': -5.0}, {'p0_service': 0.0}])
    assert store.service_frontier_hint(0) == 0.0


def test_hint_positive_beats_zero_sibling(make_store):
    store = make_store([{'p0_service': 0.0}, {'p0_service': 0.5}])
    assert store.service_frontier_hint(0) == 0.5


# --------------------------------------------------------------------------
# 3. Documents missing the ordered field are excluded, as the query always did
# --------------------------------------------------------------------------


def test_hint_skips_documents_missing_the_field(make_store):
    store = make_store([{'other_field': 99.0}, {'p1_service': 3.0}])
    assert store.service_frontier_hint(1) == 3.0


def test_hint_all_documents_missing_the_field_is_zero(make_store):
    store = make_store([{'rings': []}, {'other_field': 1.0}])
    assert store.service_frontier_hint(1) == 0.0


def test_hint_missing_field_for_one_priority_does_not_leak_into_another(make_store):
    store = make_store([{'p0_service': 50.0}])
    assert store.service_frontier_hint(1) == 0.0
    assert store.service_frontier_hint(2) == 0.0
    assert store.service_frontier_hint(0) == 50.0


def test_hint_shard_document_with_partial_priorities_reads_each_present_one(make_store):
    store = make_store([{'p0_service': 1.0, 'p2_service': 2.0}])
    assert store.service_frontier_hint(0) == 1.0
    assert store.service_frontier_hint(1) == 0.0
    assert store.service_frontier_hint(2) == 2.0


def test_hint_missing_field_never_hides_a_present_smaller_value(make_store):
    store = make_store([{'p1_service': 4.0}, {'inactive': True}])
    assert store.service_frontier_hint(1) == 4.0


# --------------------------------------------------------------------------
# 4. Query shape never drifts (collection, order, bound, no transaction)
# --------------------------------------------------------------------------


def _hint_and_calls(make_store, rows=(), priority=1):
    client = ControlClient(rows)
    store = storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=client)
    value = store.service_frontier_hint(priority)
    return value, client.calls


def test_hint_streams_exactly_once():
    _, calls = _hint_and_calls(None, [{'p1_service': 1.0}])
    assert len(calls) == 1


def test_hint_reads_the_namespaced_control_collection():
    _, calls = _hint_and_calls(None, [{'p1_service': 1.0}])
    assert calls[0][0] == 'batch_pipeline_test_unit_control'


def test_hint_orders_by_the_priority_service_field():
    _, calls = _hint_and_calls(None, [{'p1_service': 1.0}], priority=1)
    assert calls[0][1] == 'p1_service'


def test_hint_orders_by_p0_service_for_priority_0():
    _, calls = _hint_and_calls(None, [{'p0_service': 1.0}], priority=0)
    assert calls[0][1] == 'p0_service'


def test_hint_orders_by_p2_service_for_priority_2():
    _, calls = _hint_and_calls(None, [{'p2_service': 1.0}], priority=2)
    assert calls[0][1] == 'p2_service'


def test_hint_orders_descending():
    _, calls = _hint_and_calls(None, [{'p1_service': 1.0}])
    assert calls[0][2] == firestore.Query.DESCENDING


def test_hint_limits_to_one_row():
    _, calls = _hint_and_calls(None, [{'p1_service': 1.0}])
    assert calls[0][3] == 1


def test_hint_is_never_bound_to_a_transaction():
    # The abort-set property: the seed read is advisory exactly because it
    # carries no transaction binding, so no concurrent commit to the argmax
    # shard can abort the caller.
    _, calls = _hint_and_calls(None, [{'p1_service': 1.0}])
    assert calls[0][4] is None


def test_module_function_hint_is_never_bound_to_a_transaction():
    client = ControlClient([{'p2_service': 2.0}])
    storage.service_frontier_hint(client, 'batch_pipeline_test_unit', 2)
    assert client.calls[0][4] is None


def test_hint_collection_name_tracks_the_dev_namespace():
    client = ControlClient([{'p0_service': 1.0}])
    storage.service_frontier_hint(client, 'batch_pipeline_dev', 0)
    assert client.calls[0][0] == 'batch_pipeline_dev_control'


def test_hint_collection_name_tracks_a_test_namespace():
    client = ControlClient([{'p0_service': 1.0}])
    storage.service_frontier_hint(client, 'batch_pipeline_test_probe', 0)
    assert client.calls[0][0] == 'batch_pipeline_test_probe_control'


def test_hint_never_touches_a_non_control_collection():
    client = ControlClient([{'p1_service': 1.0}])
    storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=client).service_frontier_hint(1)
    assert all(name.endswith('_control') for name, *_ in client.calls)


def test_hint_takes_no_other_client_calls_besides_the_one_query():
    client = ControlClient([{'p1_service': 1.0}])
    storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=client).service_frontier_hint(1)
    assert len(client.calls) == 1


# --------------------------------------------------------------------------
# 5. Bounded priorities only, on every surface
# --------------------------------------------------------------------------


@pytest.mark.parametrize('priority', [-1, 3, 7, 100, -100])
def test_module_function_refuses_unbounded_priority(priority):
    with pytest.raises(ValueError):
        storage.service_frontier_hint(ControlClient(), 'batch_pipeline_test_unit', priority)


def test_module_function_refuses_a_string_priority():
    with pytest.raises(ValueError):
        storage.service_frontier_hint(ControlClient(), 'batch_pipeline_test_unit', '1')


def test_module_function_refuses_none_priority():
    with pytest.raises(ValueError):
        storage.service_frontier_hint(ControlClient(), 'batch_pipeline_test_unit', None)


def test_module_function_refuses_priority_before_any_client_call():
    client = ControlClient()
    with pytest.raises(ValueError):
        storage.service_frontier_hint(client, 'batch_pipeline_test_unit', 9)
    assert client.calls == []


def test_store_adapter_refuses_unbounded_priority(make_store):
    with pytest.raises(ValueError):
        make_store().service_frontier_hint(3)


def test_store_adapter_refuses_negative_priority(make_store):
    with pytest.raises(ValueError):
        make_store().service_frontier_hint(-2)


def test_store_adapter_refuses_priority_without_reading(make_store):
    store = make_store()
    with pytest.raises(ValueError):
        store.service_frontier_hint(4)
    assert store.client.calls == []


# --------------------------------------------------------------------------
# 6. The FirestoreStore adapter forwards namespace and priority unchanged
# --------------------------------------------------------------------------


def test_store_adapter_reads_priority_0(make_store):
    assert make_store([{'p0_service': 11.0}]).service_frontier_hint(0) == 11.0


def test_store_adapter_reads_priority_1(make_store):
    assert make_store([{'p1_service': 12.0}]).service_frontier_hint(1) == 12.0


def test_store_adapter_reads_priority_2(make_store):
    assert make_store([{'p2_service': 13.0}]).service_frontier_hint(2) == 13.0


def test_store_adapter_uses_the_injected_client(make_store):
    store = make_store([{'p1_service': 5.0}])
    assert store.service_frontier_hint(1) == 5.0
    assert len(store.client.calls) == 1


def test_store_adapter_reads_from_the_dev_stage_namespace(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = ControlClient([{'p1_service': 6.0}])
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=client)
    assert store.service_frontier_hint(1) == 6.0


def test_store_adapter_reads_from_the_prod_stage_namespace(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = ControlClient([{'p1_service': 8.0}])
    store = storage.FirestoreStore('batch_pipeline_prod', firestore_client=client)
    assert store.service_frontier_hint(1) == 8.0


def test_store_adapter_hint_is_repeatedly_readable(make_store):
    store = make_store([{'p1_service': 3.0}])
    assert store.service_frontier_hint(1) == 3.0
    assert store.service_frontier_hint(1) == 3.0
    assert len(store.client.calls) == 2


def test_store_adapter_hint_tracks_fresh_rows(make_store):
    client = ControlClient([{'p1_service': 3.0}])
    store = storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=client)
    assert store.service_frontier_hint(1) == 3.0
    client.rows.append({'p1_service': 40.0})
    assert store.service_frontier_hint(1) == 40.0


def test_module_function_is_exposed_on_the_store_module():
    assert callable(storage.service_frontier_hint)


def test_transactional_frontier_is_gone_from_the_transaction_view():
    assert not hasattr(storage.FirestoreTransaction, 'service_frontier')


def test_transaction_protocol_no_longer_declares_the_frontier_read():
    assert not hasattr(storage.Transaction, 'service_frontier')


def test_store_protocol_declares_the_hint():
    assert callable(getattr(storage.Store, 'service_frontier_hint', None))


def test_firestore_store_implements_the_hint():
    assert callable(storage.FirestoreStore.service_frontier_hint)


def test_firestore_transaction_no_longer_joins_the_frontier_query():
    # The transaction view exposes the hint nowhere: an append body cannot
    # re-acquire the abort-set join even by accident.
    view_methods = {name for name in dir(storage.FirestoreTransaction) if not name.startswith('_')}
    assert 'service_frontier' not in view_methods
    assert 'service_frontier_hint' not in view_methods


# --------------------------------------------------------------------------
# 7. The hint is a pure read: it never mutates anything
# --------------------------------------------------------------------------


def test_hint_leaves_rows_untouched(make_store):
    client = ControlClient([{'p1_service': 3.0}])
    before = [dict(row) for row in client.rows]
    storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=client).service_frontier_hint(1)
    assert client.rows == before


def test_hint_performs_no_writes_on_the_client():
    client = ControlClient([{'p1_service': 3.0}])
    store = storage.FirestoreStore('batch_pipeline_test_unit', firestore_client=client)
    store.service_frontier_hint(1)
    write_like = [call for call in client.calls if call[1] is None and call[2] is None]
    assert write_like == []


def test_hint_does_not_advance_a_write_budget(make_store):
    # The hint is outside the transaction: it cannot consume the body's write
    # budget, unlike any in-transaction read it replaced.
    store = make_store([{'p1_service': 3.0}])
    seen = []

    def body(tx):
        seen.append(getattr(tx, 'service_frontier', None))
        return 'ok'

    assert store.run(body, operation='batch_hint_purity') == 'ok'
    assert seen == [None]


def test_hint_value_survives_deepcopy_round_trip(make_store):
    # Store bodies deepcopy reads; the seed passes through the same copies
    # unchanged as a plain float.
    import copy

    value = make_store([{'p1_service': 2.5}]).service_frontier_hint(1)
    assert copy.deepcopy(value) == 2.5
