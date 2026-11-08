"""Home member memo: bounded staleness, isolated users, and the unchanged off path."""

from collections import OrderedDict
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.episodes import home_read


class Ref:
    def __init__(self, path=()):
        self.path = path

    def collection(self, name):
        return Ref((*self.path, name))

    def document(self, name):
        return Ref((*self.path, name))


class Store(Ref):
    def __init__(self):
        super().__init__()
        self.rows = {}
        self.calls = []
        self.error = None
        self.after_read = lambda: None

    def get_all(self, refs, *, field_paths):
        self.calls.append(([ref.path for ref in refs], list(field_paths)))
        if self.error:
            raise self.error
        snapshots = [
            SimpleNamespace(
                id=ref.path[-1],
                exists=ref.path in self.rows,
                to_dict=lambda path=ref.path: deepcopy(self.rows.get(path)),
            )
            for ref in refs
        ]
        self.after_read()
        return snapshots

    def put(self, uid, cid, **row):
        self.rows[('users', uid, 'conversations', cid)] = row


@pytest.fixture
def memo(monkeypatch):
    store = Store()
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"episode_members_cache":100}')
    monkeypatch.setattr(home_read, '_members_cache', OrderedDict())
    monkeypatch.setattr(home_read, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(home_read, 'get_firestore_client', lambda: store)
    prepare = Mock(side_effect=lambda row, uid: None if row.get('unreadable') else row)
    monkeypatch.setattr(home_read.conversations, 'prepare_conversation_for_read', prepare)
    return store, clock, prepare


def read(uid='u1', ids=('b', 'a', 'b'), **kwargs):
    return home_read._read_members(uid, [{'conversation_ids': list(ids)}], **kwargs)


def test_hit_uses_sorted_unique_member_set_and_miss_uses_new_set(memo):
    store, _, prepare = memo
    store.put('u1', 'a', structured={'title': 'first'})
    first = read()
    assert first == {'a': {'id': 'a', 'structured': {'title': 'first'}}}
    store.put('u1', 'a', structured={'title': 'edited'})
    assert read(ids=('a', 'b')) == first
    assert len(store.calls) == 1 and prepare.call_count == 1
    assert read(ids=('a',))['a']['structured']['title'] == 'edited'
    assert len(store.calls) == 2


def test_expiry_is_exact_and_hits_do_not_extend_staleness(memo):
    store, clock, _ = memo
    store.put('u1', 'a', deleted=False)
    assert not read()['a']['deleted']
    store.put('u1', 'a', deleted=True)
    clock.now = 159.999
    assert not read()['a']['deleted']  # Caller explicitly accepts stale visibility when enabled.
    clock.now = 160.0
    assert read()['a']['deleted']
    assert len(store.calls) == 2


def test_uid_isolation(memo):
    store, _, _ = memo
    store.put('u1', 'a', user_title='one')
    store.put('u2', 'a', user_title='two')
    assert read()['a']['user_title'] == 'one'
    assert read('u2')['a']['user_title'] == 'two'
    assert read()['a']['user_title'] == 'one'
    assert len(store.calls) == 2


def test_callers_cannot_mutate_memo_on_miss_or_hit(memo):
    store, _, _ = memo
    store.put('u1', 'a', structured={'title': 'original'})
    read()['a']['structured']['title'] = 'miss caller edit'
    hit = read()
    assert hit['a']['structured']['title'] == 'original'
    hit['a']['structured']['title'] = 'hit caller edit'
    assert read()['a']['structured']['title'] == 'original'
    assert len(store.calls) == 1


def test_missing_and_unreadable_members_are_memoized(memo):
    store, _, prepare = memo
    store.put('u1', 'b', unreadable=True)
    assert read() == {}
    store.put('u1', 'a', user_title='new')
    assert read() == {}
    assert len(store.calls) == prepare.call_count == 1


@pytest.mark.parametrize('raw', [None, '{}', '{"episode_members_cache":0}'])
@pytest.mark.parametrize('injected', [False, True])
def test_off_keeps_exact_legacy_batches_fields_order_and_preparation(memo, monkeypatch, raw, injected):
    store, _, prepare = memo
    rows = [{'conversation_ids': ['b', 'a', 'b']}, {'conversation_ids': ['missing', 'a']}, {}]
    # Even an already-warm memo is ignored by the kill switch.
    home_read._read_members('u1', rows)
    store.calls.clear()
    prepare.reset_mock()
    if raw is None:
        monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    else:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)
    monkeypatch.setattr(home_read.episodes, 'MEMBERSHIP_BATCH_LIMIT', 2)
    store.put('u1', 'a', user_title='first')
    store.put('u1', 'b', unreadable=True)
    kwargs = {'firestore_client': store} if injected else {}
    assert home_read._read_members('u1', rows, **kwargs) == {'a': {'id': 'a', 'user_title': 'first'}}
    store.put('u1', 'a', user_title='changed')
    assert home_read._read_members('u1', rows, **kwargs) == {'a': {'id': 'a', 'user_title': 'changed'}}
    expected = [
        ([('users', 'u1', 'conversations', cid) for cid in ['b', 'a']], home_read.MEMBER_FIELDS),
        ([('users', 'u1', 'conversations', 'missing')], home_read.MEMBER_FIELDS),
    ]
    assert store.calls == expected * 2
    assert [call.args for call in prepare.call_args_list] == [
        ({'unreadable': True, 'id': 'b'}, 'u1'),
        ({'user_title': 'first', 'id': 'a'}, 'u1'),
        ({'unreadable': True, 'id': 'b'}, 'u1'),
        ({'user_title': 'changed', 'id': 'a'}, 'u1'),
    ]


def test_expired_snapshot_is_not_served_on_error_and_failures_are_not_cached(memo):
    store, clock, _ = memo
    store.put('u1', 'a', user_title='old')
    read()
    clock.now += 60
    store.error = RuntimeError('read failed')
    with pytest.raises(RuntimeError, match='read failed'):
        read()
    store.error = None
    store.put('u1', 'a', user_title='new')
    assert read()['a']['user_title'] == 'new'
    assert len(store.calls) == 3


def test_read_latency_counts_against_ttl(memo):
    store, clock, _ = memo
    store.after_read = lambda: setattr(clock, 'now', clock.now + 60)
    read()
    read()
    assert len(store.calls) == 2
    assert not home_read._members_cache


def test_entry_cap_evicts_oldest_member_set(memo, monkeypatch):
    store, _, _ = memo
    monkeypatch.setattr(home_read, 'MEMBERS_CACHE_MAX_ENTRIES', 2)
    read(ids=('a',))
    read(ids=('b',))
    read(ids=('a',))  # Recently used entries survive.
    read(ids=('c',))
    read(ids=('b',))
    assert len(store.calls) == 4
    assert len(home_read._members_cache) == 2


def test_large_sets_bypass_memo_and_empty_rows_do_not_read(memo, monkeypatch):
    store, _, _ = memo
    monkeypatch.setattr(home_read, 'MEMBERS_CACHE_MAX_IDS', 1)
    read()
    read()
    assert len(store.calls) == 2
    assert not home_read._members_cache
    assert home_read._read_members('u1', [], firestore_client=store) == {}
    assert len(store.calls) == 2
