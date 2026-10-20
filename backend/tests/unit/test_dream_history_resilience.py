"""Unit tests for the dream-history input and result hardening.

Verifies:
- Owner uids, cursors and keys that cannot address a document are rejected with a
  stable ``ValueError`` instead of becoming query paths.
- Boolean and non-integer ``limit`` values are normalized into ``[1, 40]``.
- A malformed count aggregation returns ``0`` rather than raising ``IndexError``.
- Unusable review references are skipped, duplicate references are read once and the
  forty-reference read cap still applies.
"""

import pytest

import database.dream_history as dream_history


class _Snap:
    def __init__(self, doc_id, payload=None):
        self.id = doc_id
        self._payload = payload

    def to_dict(self):
        return self._payload


class _Query:
    def __init__(self, rows, recorder):
        self._rows = rows
        self._recorder = recorder

    def _clone(self):
        return _Query(self._rows, self._recorder)

    def order_by(self, field):
        self._recorder['order_by'] = field
        return self

    def select(self, fields):
        self._recorder['select'] = fields
        return self

    def start_after(self, cursor):
        self._recorder['start_after'] = cursor
        return self._clone()

    def start_at(self, cursor):
        self._recorder['start_at'] = cursor
        return self._clone()

    def limit(self, count):
        self._recorder['limit'] = count
        return self

    def stream(self, timeout=None):
        self._recorder['timeout'] = timeout
        return iter(self._rows)


class _CountValue:
    def __init__(self, value):
        self.value = value


class _Count:
    def __init__(self, aggregation):
        self._aggregation = aggregation

    def get(self, timeout=None):
        return self._aggregation


class _Doc:
    def __init__(self, db, path, doc_id):
        self._db = db
        self._path = path
        self.id = doc_id

    def collection(self, name):
        full = (*self._path, self.id, name)
        self._db.paths.append(full)
        return _Collection(self._db, full)


class _Collection:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def document(self, doc_id):
        self._db.documents.append((*self.path, doc_id))
        return _Doc(self._db, self.path, doc_id)

    def order_by(self, field):
        return _Query(self._db.rows, self._db.recorder).order_by(field)

    def count(self):
        return _Count(self._db.count_result)


class _Database:
    def __init__(self, rows=None, count_result=None, all_rows=None):
        self.rows = rows or []
        self.count_result = count_result if count_result is not None else [[_CountValue(0)]]
        self.all_rows = all_rows or []
        self.paths = []
        self.documents = []
        self.recorder = {}

    def collection(self, name):
        self.paths.append((name,))
        return _Collection(self, (name,))

    def get_all(self, refs, timeout=None):
        self.documents.append(('get_all', [r.id for r in refs]))
        return self.all_rows


@pytest.fixture(autouse=True)
def _canonical(monkeypatch):
    monkeypatch.setattr(
        'models.agent_refs.canonical_collection',
        lambda name: name if name in dream_history.COLLECTIONS else str(name),
        raising=False,
    )


def _db(rows=None, count_result=None, all_rows=None):
    return _Database(rows=rows, count_result=count_result, all_rows=all_rows)


@pytest.mark.parametrize('uid', ['', '   ', None, True, 7, 'a/b', 'a\\b', '..', 'a..b', 'u' * 129, 'a\x00b', 'a\x7fb'])
def test_unusable_uids_are_rejected(uid):
    with pytest.raises(ValueError):
        dream_history.history_collection(uid, 'conversations', firestore_client=_db())


def test_unknown_collections_are_rejected():
    with pytest.raises(ValueError):
        dream_history.history_collection('u1', 'secrets', firestore_client=_db())


def test_history_collection_builds_the_owner_scoped_path():
    db = _db()
    dream_history.history_collection('u1', 'conversations', firestore_client=db)
    assert db.paths == [('users',), ('users', 'u1', 'conversations')]


def test_history_page_returns_ids_and_bounds_the_limit():
    db = _db(rows=[_Snap('c1'), _Snap('c2')])
    assert dream_history.history_page('u1', 'conversations', limit=500, firestore_client=db) == ['c1', 'c2']
    assert db.recorder['limit'] == 40


def test_history_page_clamps_a_small_limit():
    db = _db(rows=[])
    dream_history.history_page('u1', 'conversations', limit=0, firestore_client=db)
    assert db.recorder['limit'] == 1


@pytest.mark.parametrize('limit', [True, False, None, '10', 3.5])
def test_history_page_falls_back_on_unusable_limits(limit):
    db = _db(rows=[])
    dream_history.history_page('u1', 'conversations', limit=limit, firestore_client=db)
    assert db.recorder['limit'] == 40


def test_history_page_pages_after_a_cursor():
    db = _db(rows=[_Snap('c3')])
    dream_history.history_page('u1', 'conversations', after='c2', firestore_client=db)
    assert db.recorder['start_after']['__name__'].id == 'c2'
    assert ('users', 'u1', 'conversations', 'c2') in db.documents


@pytest.mark.parametrize('after', ['', '   ', '/x', 'a/b', 'a\\b', '..', 'a..b', 'c' * 129, 'a\x00b', True, 5])
def test_history_page_rejects_unusable_cursors(after):
    with pytest.raises(ValueError):
        dream_history.history_page('u1', 'conversations', after=after, firestore_client=_db())


def test_history_page_without_cursor_does_not_start_after():
    db = _db(rows=[])
    dream_history.history_page('u1', 'conversations', after=None, firestore_client=db)
    assert 'start_after' not in db.recorder


def test_history_count_reads_the_aggregation():
    db = _db(count_result=[[_CountValue(12)]])
    assert dream_history.history_count('u1', 'conversations', firestore_client=db) == 12


@pytest.mark.parametrize('aggregation', [[], [[]], [[None]], [[_CountValue('many')]]])
def test_history_count_degrades_on_a_malformed_aggregation(aggregation):
    db = _db(count_result=aggregation)
    assert dream_history.history_count('u1', 'conversations', firestore_client=db) == 0


def test_history_from_key_returns_the_exact_key():
    db = _db(rows=[_Snap('c5')])
    assert dream_history.history_from_key('u1', 'conversations', 'c5', firestore_client=db) == 'c5'


def test_history_from_key_falls_back_to_the_first_row():
    db = _db(rows=[_Snap('c1')])
    assert dream_history.history_from_key('u1', 'conversations', 'c9', firestore_client=db) == 'c1'


@pytest.mark.parametrize('key', ['', '   ', None, True, 3, '/x', 'a\\b', '..', 'a..b', 'k' * 129, 'a\x1fb'])
def test_history_from_key_rejects_unusable_keys(key):
    with pytest.raises(ValueError):
        dream_history.history_from_key('u1', 'conversations', key, firestore_client=_db())


@pytest.mark.parametrize('ref', [None, 5, True, ['a']])
def test_review_id_rejects_non_strings(ref):
    with pytest.raises(ValueError):
        dream_history.review_id(ref)


def test_review_id_is_stable():
    assert dream_history.review_id('conv-1') == dream_history.review_id('conv-1')
    assert len(dream_history.review_id('conv-1')) == 64


def test_review_states_maps_ids_back_to_references():
    key = dream_history.review_id('conv-1')
    other = dream_history.review_id('conv-2')
    db = _db(all_rows=[_Snap(key, {'reviewed': True}), _Snap(other, None)])
    states = dream_history.review_states('u1', ['conv-1', 'conv-2'], firestore_client=db)
    assert states == {'conv-1': {'reviewed': True}, 'conv-2': {}}


def test_review_states_skips_unusable_references():
    db = _db(all_rows=[])
    assert dream_history.review_states('u1', ['conv-1', None, 7, True], firestore_client=db) == {}
    assert db.documents[-1][1] == [dream_history.review_id('conv-1')]


def test_review_states_reads_a_reference_once():
    db = _db(all_rows=[_Snap(dream_history.review_id('conv-1'), {'reviewed': True})])
    dream_history.review_states('u1', ['conv-1', 'conv-1', 'conv-1'], firestore_client=db)
    assert db.documents[-1][1] == [dream_history.review_id('conv-1')]


def test_review_states_caps_the_read():
    with pytest.raises(ValueError):
        dream_history.review_states('u1', [f'conv-{i}' for i in range(41)], firestore_client=_db())


def test_review_states_allows_the_cap():
    assert dream_history.review_states('u1', [f'conv-{i}' for i in range(40)], firestore_client=_db()) == {}


def test_review_states_rejects_a_non_iterable():
    with pytest.raises(ValueError):
        dream_history.review_states('u1', None, firestore_client=_db())


def test_review_states_rejects_a_bare_string():
    with pytest.raises(ValueError):
        dream_history.review_states('u1', 'conv-1', firestore_client=_db())
