"""Owner activation reads the service frontier outside the admission transaction.

A transactional order_by(...).limit(1) query locks the top control document, which workers
advance constantly; admissions then exhausted their retries and sync uploads got
503 sync_batch_unavailable (2026-11-07).
"""

from types import SimpleNamespace

import pytest

from config import firestore_read_levers as levers
from database import batch_pipeline_store as store_module


@pytest.fixture
def view(monkeypatch):
    calls = []

    def frontier(client, namespace, priority, *, transaction=None):
        calls.append(transaction)
        return 42.0

    monkeypatch.setattr(store_module, 'service_frontier', frontier)
    tx = SimpleNamespace(name='admission-transaction')
    return store_module.FirestoreTransaction(object(), 'batch_pipeline_dev', tx), tx, calls


def test_default_reads_the_frontier_outside_the_transaction(monkeypatch, view):
    monkeypatch.delenv(levers.ENV_KEY, raising=False)
    transaction_view, _, calls = view
    assert levers.lever_percent('admission_frontier_hint') == 100
    assert transaction_view.service_frontier(1) == 42.0
    assert calls == [None]


def test_hint_read_is_not_reported_as_a_contended_transactional_read(monkeypatch, view):
    monkeypatch.delenv(levers.ENV_KEY, raising=False)
    transaction_view, _, _ = view
    store_module._note_direct_reads(transaction_view)
    transaction_view.service_frontier(1)
    assert 'control_query' not in transaction_view.direct_reads
    monkeypatch.setenv(levers.ENV_KEY, '{"admission_frontier_hint": 0}')
    transaction_view.service_frontier(1)
    assert 'control_query' in transaction_view.direct_reads


@pytest.mark.parametrize('value', ['0', '"x"', '101'])
def test_lever_off_or_invalid_restores_the_transactional_query(monkeypatch, view, value):
    monkeypatch.setenv(levers.ENV_KEY, '{"admission_frontier_hint": %s}' % value)
    transaction_view, tx, calls = view
    assert transaction_view.service_frontier(0) == 42.0
    assert calls == [tx]


def test_activation_still_takes_the_max_of_own_credit_and_the_frontier(monkeypatch):
    from utils.batch_pipeline import control

    class Tx:
        def service_frontier(self, priority):
            return 10.0

    rejoining = {'p1_active': False, 'p1_service': 25.0, 'p1_batch_available_at': 9e9, 'p1_live_available_at': 9e9}
    control.activate(Tx(), rejoining, 1, now=100.0)
    assert rejoining['p1_service'] == 25.0  # a stale (lower) frontier never lowers earned credit
    behind = {'p1_active': False, 'p1_service': 3.0, 'p1_batch_available_at': 9e9, 'p1_live_available_at': 9e9}
    control.activate(Tx(), behind, 1, now=100.0)
    assert behind['p1_service'] == 10.0 and behind['p1_active'] is True


# -- post-commit re-seed (lead2 c54915 follow-up; design (c), not a pull-time clamp) --------------------


class _Snap:
    def __init__(self, doc):
        self._doc, self.exists = doc, doc is not None

    def to_dict(self):
        return self._doc


class _Client:
    def __init__(self, doc):
        from unittest.mock import Mock

        self.doc, self.tx = doc, SimpleNamespace(update=Mock())

    def collection(self, name):
        assert name == 'batch_pipeline_dev_control'
        return SimpleNamespace(document=lambda key: SimpleNamespace(get=lambda transaction=None, **kw: _Snap(self.doc)))

    def transaction(self, **options):
        self.tx_options = options
        return self.tx


@pytest.fixture
def plain_transactions(monkeypatch):
    from google.cloud import firestore

    monkeypatch.setattr(firestore, 'transactional', lambda fn: fn)


def test_reseed_lifts_a_still_marked_shard_to_the_post_commit_frontier(monkeypatch, plain_transactions):
    from google.cloud import firestore

    reads = []
    monkeypatch.setattr(
        store_module,
        'service_frontier',
        lambda c, ns, p, transaction=None, timeout=None: reads.append((transaction, timeout)) or 900.0,
    )
    client = _Client({'p2_service': 100.0, 'p2_frontier_hint': True})
    assert store_module.reseed_hinted_activation(client, 'batch_pipeline_dev', 'scheduler_07', 2) is True
    # Frontier re-read outside any transaction, with a short deadline (the upload ack waits on it).
    assert reads == [(None, store_module.RESEED_RPC_TIMEOUT_SECONDS)]
    assert client.tx_options == {'max_attempts': 1}
    _, update = client.tx.update.call_args.args
    assert update == {'p2_service': 900.0, 'p2_frontier_hint': firestore.DELETE_FIELD}


@pytest.mark.parametrize(
    'doc',
    [{'p2_service': 100.0}, None, {'p2_service': 100.0, 'p2_frontier_hint': False}],
    ids=['pulled', 'gone', 'off'],
)
def test_reseed_is_a_no_op_once_a_pull_consumed_the_marker(monkeypatch, plain_transactions, doc):
    monkeypatch.setattr(store_module, 'service_frontier', lambda *a, **k: 900.0)
    client = _Client(doc)
    assert store_module.reseed_hinted_activation(client, 'batch_pipeline_dev', 'scheduler_07', 2) is False
    client.tx.update.assert_not_called()


def test_reseed_never_lowers_earned_credit(monkeypatch, plain_transactions):
    monkeypatch.setattr(store_module, 'service_frontier', lambda *a, **k: 50.0)
    client = _Client({'p2_service': 300.0, 'p2_frontier_hint': True})
    store_module.reseed_hinted_activation(client, 'batch_pipeline_dev', 'scheduler_07', 2)
    assert client.tx.update.call_args.args[1]['p2_service'] == 300.0


def test_activation_notes_the_shard_only_with_the_lever_on(monkeypatch):
    from utils.batch_pipeline import control

    noted = []
    tx = SimpleNamespace(service_frontier=lambda p: 5.0, _note_hinted_activation=lambda k, p: noted.append((k, p)))
    fresh = lambda: {'p2_active': False, 'p2_service': 0.0, 'p2_batch_available_at': 9e9, 'p2_live_available_at': 9e9}
    monkeypatch.delenv(levers.ENV_KEY, raising=False)
    doc = fresh()
    control.activate(tx, doc, 2, 1.0, 'scheduler_07')
    assert isinstance(doc['p2_frontier_hint'], float) and noted == [('scheduler_07', 2)]
    control.activate(tx, doc, 2, 1.0, 'scheduler_07')  # already active: no second note
    assert noted == [('scheduler_07', 2)]
    monkeypatch.setenv(levers.ENV_KEY, '{"admission_frontier_hint": 0}')
    doc = fresh()
    control.activate(tx, doc, 2, 1.0, 'scheduler_07')
    assert 'p2_frontier_hint' not in doc and noted == [('scheduler_07', 2)]


def test_a_late_pull_consumes_the_marker_without_lifting():
    from utils.batch_pipeline.control import PULL_LIFT_WINDOW_SECONDS, consume_frontier_hint

    tx = SimpleNamespace(service_frontier=lambda p: 500.0)
    control = {'p1_service': 10.0, 'p1_frontier_hint': 1000.0}
    assert consume_frontier_hint(tx, control, 1, 1000.0 + PULL_LIFT_WINDOW_SECONDS + 1) is False
    assert control == {'p1_service': 10.0}  # waiting is never charged to the joiner


def test_a_pull_that_beats_the_reseed_lifts_the_shard_itself():
    # Luna reseed BLOCKING 1: a pull consuming the marker before the re-seed lands must not
    # preserve the stale activation credit.
    from utils.batch_pipeline.control import consume_frontier_hint

    reads = []
    tx = SimpleNamespace(service_frontier=lambda p: reads.append(p) or 500.0)
    control = {'p1_service': 10.0, 'p1_frontier_hint': 1000.0}
    assert consume_frontier_hint(tx, control, 1, 1005.0) is True
    assert control == {'p1_service': 500.0} and reads == [1]
    earned = {'p1_service': 900.0, 'p1_frontier_hint': 1000.0}
    consume_frontier_hint(tx, earned, 1, 1001.0)
    assert earned == {'p1_service': 900.0}


def test_no_marker_means_no_frontier_read():
    from utils.batch_pipeline.control import consume_frontier_hint

    tx = SimpleNamespace(service_frontier=lambda p: 1 / 0)
    control = {'p1_service': 10.0}
    assert consume_frontier_hint(tx, control, 1, 5.0) is False


def test_store_run_reseeds_each_hinted_activation_after_commit(monkeypatch):
    calls = []
    view = SimpleNamespace(hinted_activations={('scheduler_09', 2), ('scheduler_01', 0)})
    store = store_module.FirestoreStore.__new__(store_module.FirestoreStore)
    store.namespace = 'batch_pipeline_dev'
    store._client = object()
    monkeypatch.setattr(store_module.FirestoreStore, 'client', property(lambda self: self._client))

    def committed(self, client, commit, last_view):
        calls.append('commit')
        last_view[:] = [view]
        return 'result'

    monkeypatch.setattr(store_module.FirestoreStore, '_run_committed', committed)
    monkeypatch.setattr(
        store_module, 'reseed_hinted_activation', lambda client, ns, key, p: calls.append((key, p)) or True
    )
    assert store.run(lambda tx: None) == 'result'
    assert calls == ['commit', ('scheduler_01', 0), ('scheduler_09', 2)]
    # A failed re-seed never fails the committed admission.
    monkeypatch.setattr(store_module, 'reseed_hinted_activation', lambda *a: 1 / 0)
    assert store.run(lambda tx: None) == 'result'
