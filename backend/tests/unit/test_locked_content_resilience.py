"""Hermetic tests for ``database.locked_content`` input and stream hardening.

The real module is exercised directly. Seams: ``database._client.db`` (replaced with a
recording fake), ``database.memory_collections.MemoryCollections`` (returns a fixed
collection name) and ``google.cloud.firestore_v1.FieldFilter`` (a passthrough tuple).
No Firestore emulator and no network access are involved.
"""

import pytest

from database import locked_content as locked


class _Snap:
    def __init__(self, *, has_reference=True, data=None):
        if has_reference:
            self.reference = object()
        self.data = data
        self.exists = True


class _Batch:
    def __init__(self, owner):
        self._owner = owner
        self.pending = []

    def update(self, reference, fields):
        if not fields:
            raise ValueError('At least one field must be updated.')
        self.pending.append((reference, dict(fields)))

    def commit(self):
        self._owner.commits.append(list(self.pending))
        self.pending = []


class _Database:
    def __init__(self):
        self.batches = []
        self.commits = []

    def batch(self):
        batch = _Batch(self)
        self.batches.append(batch)
        return batch


class _Query:
    def __init__(self, snapshots, *, fail=False):
        self._snapshots = snapshots
        self._fail = fail
        self.selected = []
        self.limits = []
        self.streamed = False

    def select(self, fields):
        self.selected.append(list(fields))
        return self

    def limit(self, value):
        self.limits.append(value)
        return self

    def stream(self):
        self.streamed = True
        if self._fail:
            raise RuntimeError('transient stream failure')
        return iter(self._snapshots)


class _Collection:
    def __init__(self, snapshots, *, fail=False):
        self._snapshots = snapshots
        self._fail = fail
        self.last_query = None

    def where(self, filter=None):
        self._filter = filter
        return self

    def select(self, fields):
        query = _Query(self._snapshots, fail=self._fail)
        query.select(fields)
        self.last_query = query
        return query


class _UserCollections:
    def __init__(self, conversations=(), memories=(), action_items=()):
        self._map = {
            'conversations': conversations,
            'memories': memories,
            'action_items': action_items,
        }

    def collection(self, name):
        entry = self._map.get(name, ())
        if isinstance(entry, dict):
            return _Collection(entry.get('snapshots', ()), fail=entry.get('fail', False))
        return _Collection(entry)


class _Client:
    def __init__(self, *, conversations=(), memories=(), action_items=(), memory_items=()):
        self._user = _UserCollections(conversations, memories, action_items)
        self.memory_items = memory_items
        self.document_calls = []

    def collection(self, name):
        if name == 'users':
            client = self

            class _Docs:
                def document(self, uid):
                    client.document_calls.append(uid)
                    return client._user

            return _Docs()
        return _Collection(self.memory_items)


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    class _MemoryCollections:
        def __init__(self, uid=None, **kwargs):
            self.uid = uid

        @property
        def memory_items(self):
            return 'memory_items'

    monkeypatch.setattr(locked, 'MemoryCollections', _MemoryCollections)
    monkeypatch.setattr(locked, 'FieldFilter', lambda field, op, value: (field, op, value))
    return monkeypatch


# --------------------------------------------------------------------------- _validate_limit


def test_validate_limit_accepts_one():
    assert locked._validate_limit(1) == 1


def test_validate_limit_accepts_max():
    assert locked._validate_limit(499) == 499


def test_validate_limit_rejects_true():
    with pytest.raises(ValueError, match='must be an integer'):
        locked._validate_limit(True)


def test_validate_limit_rejects_false():
    with pytest.raises(ValueError, match='must be an integer'):
        locked._validate_limit(False)


def test_validate_limit_rejects_float():
    with pytest.raises(ValueError, match='must be an integer'):
        locked._validate_limit(1.5)


def test_validate_limit_rejects_string():
    with pytest.raises(ValueError, match='must be an integer'):
        locked._validate_limit('10')


def test_validate_limit_rejects_zero():
    with pytest.raises(ValueError, match='between 1 and 499'):
        locked._validate_limit(0)


def test_validate_limit_rejects_five_hundred():
    with pytest.raises(ValueError, match='between 1 and 499'):
        locked._validate_limit(500)


# -------------------------------------------------------------------------- _validate_update


def test_validate_update_accepts_fields():
    payload = {'is_locked': False}
    assert locked._validate_update(payload) is payload


def test_validate_update_rejects_empty_dict():
    with pytest.raises(ValueError, match='must not be empty'):
        locked._validate_update({})


def test_validate_update_rejects_list():
    with pytest.raises(ValueError, match='must be a dict'):
        locked._validate_update([('is_locked', False)])


def test_validate_update_rejects_none():
    with pytest.raises(ValueError, match='must be a dict'):
        locked._validate_update(None)


# ------------------------------------------------------------------------ unlock_query_rows


def test_unlock_updates_every_row():
    database = _Database()
    query = _Query([_Snap(), _Snap(), _Snap()])
    assert locked.unlock_query_rows(database, query, {'is_locked': False}) == 3
    assert len(database.commits) == 1
    assert len(database.commits[0]) == 3


def test_unlock_skips_rows_without_reference():
    database = _Database()
    query = _Query([_Snap(), _Snap(has_reference=False), _Snap()])
    assert locked.unlock_query_rows(database, query, {'is_locked': False}) == 2


def test_unlock_applies_limit_to_query():
    database = _Database()
    query = _Query([_Snap()])
    locked.unlock_query_rows(database, query, {'is_locked': False}, limit=25)
    assert query.limits == [25]
    assert query.selected == [[]]


def test_unlock_rejects_empty_update_before_streaming():
    database = _Database()
    query = _Query([_Snap()])
    with pytest.raises(ValueError, match='must not be empty'):
        locked.unlock_query_rows(database, query, {})
    assert query.streamed is False
    assert database.batches == []


def test_unlock_rejects_boolean_limit_before_streaming():
    database = _Database()
    query = _Query([_Snap()])
    with pytest.raises(ValueError, match='must be an integer'):
        locked.unlock_query_rows(database, query, {'is_locked': False}, limit=True)
    assert query.streamed is False


def test_unlock_commits_in_batches_of_499():
    database = _Database()
    query = _Query([_Snap() for _ in range(500)])
    assert locked.unlock_query_rows(database, query, {'is_locked': False}) == 500
    assert [len(batch) for batch in database.commits] == [499, 1]


def test_unlock_calls_on_commit_after_each_batch():
    database = _Database()
    query = _Query([_Snap() for _ in range(500)])
    calls = []
    locked.unlock_query_rows(database, query, {'is_locked': False}, on_commit=lambda: calls.append(1))
    assert len(calls) == 2


def test_unlock_calls_on_commit_when_limited_probe_finds_nothing():
    database = _Database()
    query = _Query([])
    calls = []
    assert locked.unlock_query_rows(database, query, {'is_locked': False}, limit=10, on_commit=lambda: calls.append(1)) == 0
    assert len(calls) == 1


def test_unlock_does_not_call_on_commit_without_limit():
    database = _Database()
    query = _Query([])
    calls = []
    locked.unlock_query_rows(database, query, {'is_locked': False}, on_commit=lambda: calls.append(1))
    assert calls == []


def test_unlock_returns_zero_for_empty_stream():
    database = _Database()
    assert locked.unlock_query_rows(database, _Query([]), {'is_locked': False}) == 0
    assert database.commits == []


# ---------------------------------------------------------------------------- _sanitize_uid


def test_sanitize_uid_strips_whitespace():
    assert locked._sanitize_uid('  u1 ') == 'u1'


def test_sanitize_uid_rejects_empty():
    with pytest.raises(ValueError, match='must not be empty'):
        locked._sanitize_uid('')


def test_sanitize_uid_rejects_whitespace_only():
    with pytest.raises(ValueError, match='must not be empty'):
        locked._sanitize_uid('   ')


def test_sanitize_uid_rejects_separator():
    with pytest.raises(ValueError, match='path separators'):
        locked._sanitize_uid('a/b')


def test_sanitize_uid_rejects_overlong():
    with pytest.raises(ValueError, match='at most 128'):
        locked._sanitize_uid('u' * 129)


def test_sanitize_uid_rejects_non_string():
    with pytest.raises(ValueError, match='must be a string'):
        locked._sanitize_uid(None)


# ------------------------------------------------------------- has_recoverable_locked_content


def test_probe_finds_locked_row_in_first_collection():
    client = _Client(conversations=[_Snap()])
    assert locked.has_recoverable_locked_content('u1', firestore_client=client) is True


def test_probe_returns_false_when_nothing_is_locked():
    client = _Client()
    assert locked.has_recoverable_locked_content('u1', firestore_client=client) is False


def test_probe_falls_through_failing_collection():
    client = _Client(conversations={'fail': True}, action_items=[_Snap()])
    assert locked.has_recoverable_locked_content('u1', firestore_client=client) is True


def test_probe_rejects_invalid_uid():
    client = _Client()
    with pytest.raises(ValueError, match='must not be empty'):
        locked.has_recoverable_locked_content('', firestore_client=client)
    assert client.document_calls == []


def test_probe_uses_sanitized_uid_for_document_path():
    client = _Client()
    locked.has_recoverable_locked_content('  u1  ', firestore_client=client)
    assert client.document_calls == ['u1']


def test_probe_queries_memory_items_with_sanitized_uid():
    seen = {}

    class _RecordingMemoryCollections:
        def __init__(self, uid=None, **kwargs):
            seen['uid'] = uid

        @property
        def memory_items(self):
            return 'memory_items'

    original = locked.MemoryCollections
    locked.MemoryCollections = _RecordingMemoryCollections
    try:
        locked.has_recoverable_locked_content('  u1 ', firestore_client=_Client())
    finally:
        locked.MemoryCollections = original
    assert seen['uid'] == 'u1'
