"""Hermetic unit tests for backend/database/dream_history.py resilience."""

from types import SimpleNamespace

import pytest

from database import dream_history


class _FakeQuery:
    def __init__(self, ids=(), count_rows=None):
        self.ids = list(ids)
        self.count_rows = [[SimpleNamespace(value=len(self.ids))]] if count_rows is None else count_rows
        self.after_doc = None
        self.start_at_doc = None
        self.bound = None

    def collection(self, name):
        self.collection_name = name
        return self

    def document(self, key):
        return SimpleNamespace(id=key, collection=lambda name: self)

    def order_by(self, field):
        return self

    def select(self, fields):
        return self

    def start_after(self, cursor):
        self.after_doc = cursor['__name__'].id
        return self

    def start_at(self, cursor):
        cloned = _FakeQuery(ids=self.ids, count_rows=self.count_rows)
        cloned.start_at_doc = cursor['__name__'].id
        return cloned

    def limit(self, n):
        self.bound = n
        return self

    def stream(self, timeout=None):
        items = self.ids
        if self.after_doc in items:
            idx = items.index(self.after_doc)
            items = items[idx + 1 :]
        elif self.start_at_doc is not None:
            items = [i for i in items if i >= self.start_at_doc]
        if self.bound is not None:
            items = items[: self.bound]
        return iter([SimpleNamespace(id=i) for i in items])

    def count(self):
        return SimpleNamespace(get=lambda timeout=None: self.count_rows)


class _FakeClient:
    def __init__(self, query=None, snapshots=()):
        self.query = query or _FakeQuery()
        self.snapshots = list(snapshots)

    def collection(self, name):
        return self.query

    def get_all(self, refs, timeout=None):
        return iter(self.snapshots)


@pytest.mark.parametrize(
    'bad_uid',
    ['', '   ', 'user/sub', 'user\\sub', 'user..1', 'a' * 129, None, 123],
)
def test_history_collection_rejects_invalid_uid(bad_uid):
    with pytest.raises(ValueError, match='dream_history_uid'):
        dream_history.history_collection(bad_uid, 'conversations', firestore_client=_FakeClient())


@pytest.mark.parametrize('bad_collection', ['', '   ', 'folders', 'users', None, 123])
def test_history_collection_rejects_invalid_collection(bad_collection):
    with pytest.raises(ValueError, match='dream_history_collection'):
        dream_history.history_collection('user_1', bad_collection, firestore_client=_FakeClient())


@pytest.mark.parametrize('bad_limit', [True, False, 1.5, '10', None])
def test_history_page_rejects_boolean_or_non_int_limit(bad_limit):
    with pytest.raises(ValueError, match='dream_history_limit'):
        dream_history.history_page('user_1', 'conversations', limit=bad_limit, firestore_client=_FakeClient())


@pytest.mark.parametrize('bad_after', ['   ', 'doc/sub', 'doc\\sub', 'doc..1', 'a' * 129, 123])
def test_history_page_rejects_unsafe_after_cursor(bad_after):
    with pytest.raises(ValueError, match='dream_history_key'):
        dream_history.history_page('user_1', 'conversations', after=bad_after, firestore_client=_FakeClient())


def test_history_page_clamps_limit_and_trims_after_cursor():
    query = _FakeQuery(ids=['c1', 'c2', 'c3'])
    client = _FakeClient(query=query)
    res = dream_history.history_page('  user_1  ', '  memories  ', after='  c1  ', limit=999, firestore_client=client)
    assert res == ['c2', 'c3']
    assert query.bound == 40
    assert query.after_doc == 'c1'


@pytest.mark.parametrize(
    ('count_rows', 'expected'),
    [
        ([[SimpleNamespace(value=12)]], 12),
        ([[SimpleNamespace(value=-5)]], 0),
        ([[SimpleNamespace(value=True)]], 0),
        ([[SimpleNamespace(value=None)]], 0),
        ([[]], 0),
        ([], 0),
    ],
)
def test_history_count_handles_empty_or_malformed_aggregation(count_rows, expected):
    client = _FakeClient(query=_FakeQuery(count_rows=count_rows))
    assert dream_history.history_count('user_1', 'conversations', firestore_client=client) == expected


@pytest.mark.parametrize(
    'bad_key',
    ['', '   ', 'k/1', 'k\\1', 'k..1', 'k\x001', 'a' * 129, None, 123],
)
def test_history_from_key_rejects_invalid_key(bad_key):
    with pytest.raises(ValueError, match='dream_history_key'):
        dream_history.history_from_key('user_1', 'conversations', bad_key, firestore_client=_FakeClient())


def test_history_from_key_trims_key_and_wraps_around():
    query = _FakeQuery(ids=['10', '20', '30'])
    client = _FakeClient(query=query)
    assert dream_history.history_from_key('user_1', 'conversations', '  15  ', firestore_client=client) == '20'
    query2 = _FakeQuery(ids=['10', '20'])
    assert (
        dream_history.history_from_key('user_1', 'conversations', '99', firestore_client=_FakeClient(query=query2))
        == '10'
    )


@pytest.mark.parametrize('bad_ref', ['', '   ', None, 123])
def test_review_id_rejects_blank_or_non_string_ref(bad_ref):
    with pytest.raises(ValueError, match='dream_review_ref'):
        dream_history.review_id(bad_ref)


def test_review_states_rejects_raw_string_refs_and_handles_non_dict_snapshots():
    with pytest.raises(ValueError, match='dream_review_refs'):
        dream_history.review_states('user_1', 'conversations/c1', firestore_client=_FakeClient())

    ref1 = 'conversations/c1'
    ref2 = 'conversations/c2'
    snap1 = SimpleNamespace(id=dream_history.review_id(ref1), exists=True, to_dict=lambda: {'state': 'approved'})
    snap2 = SimpleNamespace(id=dream_history.review_id(ref2), exists=True, to_dict=lambda: ['corrupt-non-dict'])
    snap_unknown = SimpleNamespace(id='unknown_id', exists=True, to_dict=lambda: {'state': 'ignored'})

    client = _FakeClient(snapshots=[snap1, snap2, snap_unknown])
    states = dream_history.review_states('  user_1  ', [f'  {ref1}  ', ref2], firestore_client=client)
    assert states == {ref1: {'state': 'approved'}, ref2: {}}
