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
