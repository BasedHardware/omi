from __future__ import annotations

from dataclasses import replace
import threading
from typing import Any

import pytest

from llm_gateway.gateway import jit_budget


class _Snapshot:
    def __init__(self, value: dict[str, Any] | None):
        self._value = value
        self.exists = value is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._value or {})


class _SharedStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.documents: dict[str, dict[str, Any]] = {}


class _Reference:
    def __init__(self, store: _SharedStore, key: str):
        self.store = store
        self.key = key

    def get(self, *, transaction: _Transaction) -> _Snapshot:
        return _Snapshot(transaction.store.documents.get(self.key))


class _Transaction:
    def __init__(self, store: _SharedStore):
        self.store = store

    def run(self, function, *args, **kwargs):
        with self.store.lock:
            return function(self, *args, **kwargs)

    def set(self, reference: _Reference, value: dict[str, Any], *, merge: bool = False) -> None:
        current = dict(self.store.documents.get(reference.key, {})) if merge else {}
        current.update(value)
        self.store.documents[reference.key] = current

    def update(self, reference: _Reference, value: dict[str, Any]) -> None:
        current = dict(self.store.documents[reference.key])
        current.update(value)
        self.store.documents[reference.key] = current


class _Collection:
    def __init__(self, store: _SharedStore, name: str):
        self.store = store
        self.name = name

    def document(self, key: str) -> _Reference:
        return _Reference(self.store, f'{self.name}/{key}')


class _Client:
    def __init__(self, store: _SharedStore):
        self.store = store

    def collection(self, name: str) -> _Collection:
        return _Collection(self.store, name)

    def transaction(self) -> _Transaction:
        return _Transaction(self.store)


def _transactional(function):
    def wrapper(transaction, *args, **kwargs):
        return transaction.run(function, *args, **kwargs)

    return wrapper


@pytest.fixture
def fake_clients(monkeypatch):
    monkeypatch.setattr(jit_budget.firestore, 'transactional', _transactional)
    store = _SharedStore()
    clients = (_Client(store), _Client(store))
    current = threading.local()

    def get_client():
        return current.client

    monkeypatch.setattr(jit_budget, '_client', get_client)
    return clients, current, store


def _reserve(*, run_id='run-1'):
    return jit_budget.reserve_jit_provider_attempt(
        owner_uid='qa-user',
        run_id=run_id,
        contract_version='jit-cloud-qa-v1',
        max_attempts=3,
        max_spend_micro_usd=50_000,
        provider='openai',
        model='gpt-5.6-luna',
        input_tokens=100,
        cached_input_tokens=0,
        output_tokens=10,
        cache_write_tokens=0,
    )


def test_two_independent_clients_share_one_unsettled_reservation(fake_clients):
    clients, current, _ = fake_clients
    results = []
    barrier = threading.Barrier(2)

    def worker(client):
        current.client = client
        barrier.wait()
        results.append(_reserve())

    threads = [threading.Thread(target=worker, args=(client,)) for client in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(result is not None for result in results) == 1
    reservation = next(result for result in results if result is not None)
    current.client = clients[1]
    assert jit_budget.settle_jit_provider_attempt(reservation=reservation, cost_micro_usd=10, status='succeeded')


def test_three_settled_attempts_allow_no_fourth(fake_clients):
    clients, current, _ = fake_clients
    current.client = clients[0]
    for ordinal in range(1, 4):
        reservation = _reserve(run_id='run-three')
        assert reservation is not None
        assert reservation.ordinal == ordinal
        assert jit_budget.settle_jit_provider_attempt(reservation=reservation, cost_micro_usd=10, status='succeeded')
    assert _reserve(run_id='run-three') is None


def test_unknown_cost_keeps_reservation_and_blocks_next_attempt(fake_clients):
    clients, current, _ = fake_clients
    current.client = clients[0]
    reservation = _reserve(run_id='run-unknown')
    assert reservation is not None
    assert not jit_budget.settle_jit_provider_attempt(reservation=reservation, cost_micro_usd=None, status='failed')
    assert _reserve(run_id='run-unknown') is None


def test_failed_known_cost_also_blocks_next_attempt(fake_clients):
    clients, current, _ = fake_clients
    current.client = clients[0]
    reservation = _reserve(run_id='run-failed')
    assert reservation is not None
    assert not jit_budget.settle_jit_provider_attempt(reservation=reservation, cost_micro_usd=0, status='failed')
    assert _reserve(run_id='run-failed') is None


def test_providerless_deadline_release_returns_reservation_to_budget(fake_clients):
    clients, current, store = fake_clients
    current.client = clients[0]
    reservation = _reserve(run_id='run-providerless-release')
    assert reservation is not None

    assert jit_budget.settle_jit_provider_attempt(
        reservation=reservation,
        cost_micro_usd=0,
        status='released',
    )
    assert _reserve(run_id='run-providerless-release') is not None
    document = next(iter(store.documents.values()))
    assert document['blocked'] is False
    assert document['active_reservation'] is not None


def test_late_known_settlement_cannot_reopen_unknown_block(fake_clients):
    clients, current, _ = fake_clients
    current.client = clients[0]
    reservation = _reserve(run_id='run-late-known')
    assert reservation is not None
    assert not jit_budget.settle_jit_provider_attempt(reservation=reservation, cost_micro_usd=None, status='failed')
    assert not jit_budget.settle_jit_provider_attempt(reservation=reservation, cost_micro_usd=10, status='succeeded')
    assert _reserve(run_id='run-late-known') is None


def test_trusted_overspend_is_recorded_without_clamping(fake_clients):
    clients, current, store = fake_clients
    current.client = clients[0]
    reservation = _reserve(run_id='run-overspend')
    assert reservation is not None
    actual_cost = 50_001
    assert not jit_budget.settle_jit_provider_attempt(
        reservation=reservation, cost_micro_usd=actual_cost, status='succeeded'
    )
    document = next(iter(store.documents.values()))
    assert document['settled_spend_micro_usd'] == actual_cost
    assert document['blocked'] is True


def test_wrong_owner_run_or_token_cannot_settle(fake_clients):
    clients, current, _ = fake_clients
    current.client = clients[0]
    reservation = _reserve(run_id='run-identity')
    assert reservation is not None
    for forged in (
        replace(reservation, owner_uid='other-user'),
        replace(reservation, run_id='other-run'),
        replace(reservation, reservation_token='forged-token'),
    ):
        assert not jit_budget.settle_jit_provider_attempt(reservation=forged, cost_micro_usd=10, status='succeeded')
    assert jit_budget.settle_jit_provider_attempt(reservation=reservation, cost_micro_usd=10, status='succeeded')


def test_unpriced_model_fails_closed_without_local_fallback(fake_clients):
    clients, current, _ = fake_clients
    current.client = clients[0]
    with pytest.raises(ValueError, match='no trusted rate card'):
        jit_budget.reserve_jit_provider_attempt(
            owner_uid='qa-user',
            run_id='run-unpriced',
            contract_version='jit-cloud-qa-v1',
            max_attempts=3,
            max_spend_micro_usd=50_000,
            provider='openai',
            model='unpriced-model',
            input_tokens=100,
            cached_input_tokens=0,
            output_tokens=10,
            cache_write_tokens=0,
        )
