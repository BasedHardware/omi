"""Only callers enrolled before the owner fetch may share its future snapshot."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import contextmanager
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
        # Capture a real independent snapshot at RPC time, not when to_dict is
        # later called. Preparation may pause while the stored document changes.
        snapshots = []
        for ref in refs:
            cid = ref.path[-1]
            raw = deepcopy(self.rows.get(cid))
            snapshots.append(SimpleNamespace(id=cid, exists=raw is not None, to_dict=lambda raw=raw: deepcopy(raw)))
        return snapshots


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


@contextmanager
def enrollment_barrier(metric):
    """Pause the owner metric before it closes enrollment, never inside the RPC.

    No production sleep/grace is added. This exposes the natural pre-fetch
    scheduling interval deterministically; only callers in that interval share.
    """
    entered, release = threading.Event(), threading.Event()
    observe = metric.side_effect

    def pause_owner(namespace, result):
        if result == 'owner' and not entered.is_set():
            entered.set()
            assert release.wait(5), 'test failed to release enrollment'
        observe(namespace, result)

    metric.side_effect = pause_owner
    try:
        yield entered, release
    finally:
        release.set()
        metric.side_effect = observe


def overlap(store, joined, metric, second, *, error=None):
    def fetch_error():
        if error is not None:
            raise error

    store.before_read = fetch_error
    with enrollment_barrier(metric) as (entered, release), ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(read, store)
        try:
            assert entered.wait(5)
            waiter = pool.submit(second)
            assert joined.wait(5), 'waiter did not enroll before owner fetch'
            assert not store.calls  # Sharing must be decided before any underlying RPC starts.
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
    owner, waiter = overlap(store, joined, metric, lambda: read(store, ids=('missing', 'a', 'b')))
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
    store, _, metric = flight
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
    with enrollment_barrier(metric) as (entered, release), ThreadPoolExecutor(max_workers=2) as pool:
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
    store, joined, metric = flight
    overlap(store, joined, metric, lambda: read(store), error=error)
    store.before_read = lambda: None
    assert read(store)['a']['structured']['title'] == 'fresh'
    assert len(store.calls) == 2


def test_full_map_bypasses_new_keys_but_still_joins_existing_key(flight, monkeypatch):
    store, joined, metric = flight
    monkeypatch.setattr(home_read, 'MEMBERS_FLIGHT_MAX_ENTRIES', 1)
    original = store.before_read

    def second():
        other = Store()
        assert read(other, uid='different')
        assert len(home_read._members_flights) == 1
        return read(store)

    overlap(store, joined, metric, second)
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
    store, _, metric = flight
    with enrollment_barrier(metric) as (entered, release), ThreadPoolExecutor(max_workers=1) as pool:
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
    store, joined, metric = flight
    with enrollment_barrier(metric) as (entered, release), ThreadPoolExecutor(max_workers=3) as pool:
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
    store, joined, metric = flight
    other = Store()
    owner, waiter = overlap(store, joined, metric, lambda: read(other))
    assert owner == waiter and len(store.calls) == 1 and not other.calls


def test_broken_observation_does_not_change_read_or_leak_flight(flight, monkeypatch):
    store, _, _ = flight
    monkeypatch.setattr(home_read, 'record_request', Mock(side_effect=RuntimeError('observer failed')))
    assert read(store)
    assert not home_read._members_flights


@pytest.mark.parametrize('mutation', ['delete', 'edit', 'soft_delete'])
def test_late_arrival_after_captured_snapshot_reads_current_state(flight, monkeypatch, mutation):
    """A completed mutation before this request requires its own fresh read.

    Pausing preparation is deliberately after the owner RPC captured its
    snapshot. Such callers must not enroll, even though the owner is unfinished.
    """
    store, _, metric = flight
    captured, release = threading.Event(), threading.Event()
    first = True

    def prepare(row, uid):
        nonlocal first
        if first:
            first = False
            captured.set()
            assert release.wait(5), 'test failed to release preparation'
        return row

    monkeypatch.setattr(home_read.conversations, 'prepare_conversation_for_read', prepare)
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(read, store, 'u', ('a',))
        try:
            assert captured.wait(5)
            original_flight = next(iter(home_read._members_flights.values()))
            if mutation == 'delete':
                del store.rows['a']
                expected = {}
            else:
                store.rows['a'] = {'structured': {'title': 'current'}, 'deleted': mutation == 'soft_delete'}
                expected = {'a': {**deepcopy(store.rows['a']), 'id': 'a'}}
            late = pool.submit(read, store, 'u', ('a',))
            assert late.result(timeout=3) == expected  # Completes without releasing the old snapshot.
            assert not owner.done()
            assert len(store.calls) == 2
            assert len(home_read._members_flights) == 1
            assert next(iter(home_read._members_flights.values())) is original_flight
            metric.assert_any_call('fsr_episode_members_flight', 'bypass')
        finally:
            release.set()
        assert owner.result(timeout=5) == {'a': {'structured': {'title': 'fresh'}, 'id': 'a'}}


def test_closed_flight_counts_toward_capacity_and_cannot_be_replaced(flight, monkeypatch):
    store, _, metric = flight
    monkeypatch.setattr(home_read, 'MEMBERS_FLIGHT_MAX_ENTRIES', 1)
    entered, release = threading.Event(), threading.Event()
    store.before_read = lambda: (entered.set(), release.wait(5))
    with ThreadPoolExecutor(max_workers=1) as pool:
        owner = pool.submit(read, store)
        try:
            assert entered.wait(5)
            original_flight = next(iter(home_read._members_flights.values()))
            assert not original_flight.accepting
            other = Store()
            assert read(other)  # Same key: fresh bypass, no replacement owner.
            assert read(other, uid='different')  # New key: capacity still full.
            assert len(other.calls) == 2
            assert len(home_read._members_flights) == 1
            assert next(iter(home_read._members_flights.values())) is original_flight
            assert not original_flight.future.done()
        finally:
            release.set()
        assert owner.result(timeout=5)
    assert len(store.calls) == 1
    assert [call.args for call in metric.call_args_list].count(('fsr_episode_members_flight', 'bypass')) == 2
