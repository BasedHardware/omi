"""Only simultaneous identical reads share work; completed data is never reused."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import firestore_read_levers as levers
from utils.episodes import home_read


class Ref:
    def __init__(self, path=()):
        self.path = path

    def collection(self, name):
        return Ref((*self.path, name))

    def document(self, name):
        return Ref((*self.path, name))


class Store(Ref):
    project = 'test-project'
    _database = '(default)'

    def __init__(self):
        super().__init__()
        self.calls = []
        self.rows = {'a': {'structured': {'title': 'fresh'}}, 'b': {'deleted': True}}
        self.before_read = lambda: None

    def get_all(self, refs, *, field_paths):
        self.calls.append(([ref.path for ref in refs], field_paths))
        self.before_read()
        return [
            SimpleNamespace(
                id=ref.path[-1],
                exists=ref.path[-1] in self.rows,
                to_dict=lambda cid=ref.path[-1]: deepcopy(self.rows[cid]),
            )
            for ref in refs
        ]


def read(store, uid='u', ids=('b', 'a', 'b', 'missing')):
    return home_read._read_members(uid, [{'conversation_ids': list(ids)}], firestore_client=store)


@pytest.fixture
def flight(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    monkeypatch.setattr(home_read, '_members_flights', {})
    monkeypatch.setattr(home_read, '_members_flight_local', threading.local())
    monkeypatch.setattr(home_read.conversations, 'prepare_conversation_for_read', lambda row, uid: row)
    joined = threading.Event()
    metric = Mock(side_effect=lambda namespace, result: joined.set() if result == 'coalesced' else None)
    monkeypatch.setattr(home_read, 'record_request', metric)
    yield Store(), joined, metric
    assert not home_read._members_flights


def overlap(store, joined, second, *, error=None):
    entered, release = threading.Event(), threading.Event()

    def block():
        entered.set()
        assert release.wait(5), 'test failed to release owner'
        if error is not None:
            raise error

    store.before_read = block
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(read, store)
        try:
            assert entered.wait(5)
            waiter = pool.submit(second)
            assert joined.wait(5), 'waiter did not join active read'
        finally:
            release.set()
        if error is not None:
            for future in (owner, waiter):
                with pytest.raises(type(error)) as caught:
                    future.result(timeout=5)
                assert caught.value is error
            return None
        return owner.result(timeout=5), waiter.result(timeout=5)


def test_concurrent_sorted_unique_ids_share_one_rpc_and_private_nested_results(flight):
    store, joined, metric = flight
    owner, waiter = overlap(store, joined, lambda: read(store, ids=('missing', 'a', 'b')))
    assert len(store.calls) == 1
    assert store.calls[0] == (
        [('users', 'u', 'conversations', cid) for cid in ('b', 'a', 'missing')],
        home_read.MEMBER_FIELDS,
    )
    assert owner == waiter
    assert list(owner) == ['b', 'a']  # Same SDK snapshot order, including hidden/extant rows.
    owner['a']['structured']['title'] = 'owner edit'
    assert waiter['a']['structured']['title'] == 'fresh'
    waiter['a']['structured']['title'] = 'waiter edit'
    assert store.rows['a']['structured']['title'] == 'fresh'
    metric.assert_any_call('fsr_episode_members_flight', 'owner')
    metric.assert_any_call('fsr_episode_members_flight', 'coalesced')


def test_sequential_reads_see_edits_deletions_and_missing_rows_immediately(flight):
    store, _, _ = flight
    assert read(store)['a']['structured']['title'] == 'fresh'
    store.rows['a']['deleted'] = True
    store.rows['b']['deleted'] = False
    store.rows['missing'] = {'structured': {'title': 'new'}}
    result = read(store)
    assert result['a']['deleted'] and not result['b']['deleted'] and 'missing' in result
    del store.rows['a']
    assert 'a' not in read(store)
    assert len(store.calls) == 3
    assert not home_read._members_cache


@pytest.mark.parametrize('difference', ['uid', 'project', 'database', 'members', 'opaque_client'])
def test_concurrent_keys_are_isolated(flight, difference):
    store, _, _ = flight
    other = Store()
    uid, ids = 'u', ('b', 'a', 'b', 'missing')
    if difference == 'uid':
        uid = 'other'
    elif difference == 'project':
        other.project = 'other-project'
    elif difference == 'database':
        other._database = 'other-database'
    elif difference == 'members':
        ids = ('a',)
    else:
        store.project = other.project = None  # Unknown plane falls back to client identity.
    entered, release = threading.Event(), threading.Event()
    store.before_read = lambda: (entered.set(), release.wait(5))
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(read, store)
        try:
            assert entered.wait(5)
            pool.submit(read, other, uid, ids).result(timeout=5)
            assert len(other.calls) == 1
        finally:
            release.set()
        owner.result(timeout=5)


@pytest.mark.parametrize('error', [RuntimeError('read failed'), asyncio.CancelledError('owner cancelled')])
def test_owner_and_waiter_receive_same_error_then_retry_fresh(flight, error):
    store, joined, _ = flight
    overlap(store, joined, lambda: read(store), error=error)
    store.before_read = lambda: None
    assert read(store)['a']['structured']['title'] == 'fresh'
    assert len(store.calls) == 2


def test_full_map_bypasses_new_keys_but_still_joins_existing_key(flight, monkeypatch):
    store, joined, _ = flight
    monkeypatch.setattr(home_read, 'MEMBERS_FLIGHT_MAX_ENTRIES', 1)
    original = store.before_read

    def second():
        other = Store()
        assert read(other, uid='different')
        assert len(home_read._members_flights) == 1
        return read(store)

    overlap(store, joined, second)
    store.before_read = original
    assert len(store.calls) == 1


def test_large_member_sets_bypass_without_truncation(flight, monkeypatch):
    store, _, metric = flight
    monkeypatch.setattr(home_read, 'MEMBERS_FLIGHT_MAX_IDS', 1)
    assert list(read(store)) == ['b', 'a']
    assert len(store.calls[0][0]) == 3
    metric.assert_called_with('fsr_episode_members_flight', 'bypass')


@pytest.mark.parametrize('ids', [('a',), ('different',)])
def test_reentrant_reads_bypass_all_flights_without_deadlock(flight, ids):
    store, _, metric = flight
    nested = []

    def reenter():
        store.before_read = lambda: None
        nested.append(read(store, ids=ids))

    store.before_read = reenter
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(read, store).result(timeout=5)
    assert len(nested) == 1 and len(store.calls) == 2
    metric.assert_any_call('fsr_episode_members_flight', 'bypass')


def test_kill_switch_restores_independent_reads_even_with_active_owner(flight, monkeypatch):
    store, _, _ = flight
    entered, release = threading.Event(), threading.Event()
    store.before_read = lambda: (entered.set(), release.wait(5))
    with ThreadPoolExecutor(max_workers=1) as pool:
        owner = pool.submit(read, store)
        try:
            assert entered.wait(5)
            monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"episode_members_singleflight":0}')
            other = Store()  # Same plane/uid/member set, but cannot join the active read.
            assert read(other)
            assert len(other.calls) == 1
        finally:
            release.set()
        owner.result(timeout=5)
    assert levers.lever_percent('episode_members_cache') == 0


def test_empty_rows_never_register_flights_or_read(flight):
    store, _, _ = flight
    assert home_read._read_members('u', [], firestore_client=store) == {}
    assert not store.calls


def test_waiter_cancellation_does_not_cancel_owner_or_other_waiters(flight):
    store, joined, _ = flight
    entered, release = threading.Event(), threading.Event()
    store.before_read = lambda: (entered.set(), release.wait(5))
    with ThreadPoolExecutor(max_workers=3) as pool:
        owner = pool.submit(read, store)
        try:
            assert entered.wait(5)

            async def cancel_waiter():
                waiter = asyncio.wrap_future(pool.submit(read, store))
                assert await asyncio.to_thread(joined.wait, 5)
                waiter.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await waiter

            asyncio.run(cancel_waiter())
            joined.clear()
            remaining = pool.submit(read, store)
            assert joined.wait(5)
        finally:
            release.set()
        assert remaining.result(timeout=5) == owner.result(timeout=5)
    assert len(store.calls) == 1


def test_equivalent_clients_share_by_plane_not_object_identity(flight):
    store, joined, _ = flight
    other = Store()
    owner, waiter = overlap(store, joined, lambda: read(other))
    assert owner == waiter and len(store.calls) == 1 and not other.calls


def test_broken_observation_does_not_change_read_or_leak_flight(flight, monkeypatch):
    store, _, _ = flight
    monkeypatch.setattr(home_read, 'record_request', Mock(side_effect=RuntimeError('observer failed')))
    assert read(store)
    assert not home_read._members_flights
