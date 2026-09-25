"""PATCH /v1/conversations/{id}/folder must survive a conversation whose old folder was deleted.

Prod signature (2026-08-18, image c5b0b5d): three 500s on that route, all from
database/folders.py:update_folder_conversation_count ->
`google.api_core.exceptions.NotFound: 404 No document to update: .../folders/852e33fd-...`.

Two defects made that reachable:

1. delete_folder repointed its conversations only `if target_folder_id` — and
   target_folder_id is None for every account created after the 'Other' system
   folder was removed (no folder carries is_default; see
   test_conversation_folder_assignment). Those conversations kept the deleted
   folder's id.
2. The next move of such a conversation wrote the new folder_id, then refreshed
   the *old* folder's count. The router validates only the target folder, so the
   refresh hit a tombstone and raised. The move had already committed, so the
   user saw a permanent 500 on a write that actually succeeded, and every retry
   500'd the same way.

The fake below models the one server behavior that matters here: `update()` on a
missing document raises NotFound.
"""

from unittest.mock import patch

from google.api_core.exceptions import NotFound

import database.folders as folders


class _FakeSnapshot:
    def __init__(self, doc_id, data, reference=None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = reference

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        return _FakeSnapshot(self.id, self._store.get(self.id), reference=self)

    def update(self, values):
        if self.id not in self._store:
            raise NotFound(f"404 No document to update: {self.id}")
        self._store[self.id].update(values)

    def delete(self):
        self._store.pop(self.id, None)


class _FakeAggregate:
    def __init__(self, total):
        self._total = total

    def get(self):
        return [[type('AggregationResult', (), {'value': self._total})()]]


class _FakeQuery:
    def __init__(self, store, predicates):
        self._store = store
        self._predicates = predicates

    def where(self, filter=None):
        return _FakeQuery(self._store, self._predicates + [(filter.field_path, filter.value)])

    def order_by(self, _field, direction=None):
        return self

    def offset(self, _n):
        return self

    def limit(self, _n):
        return self

    def _matching(self):
        return [
            (doc_id, data)
            for doc_id, data in self._store.items()
            if all(data.get(field) == value for field, value in self._predicates)
        ]

    def stream(self):
        for doc_id, data in self._matching():
            yield _FakeSnapshot(doc_id, data, reference=_FakeDocRef(self._store, doc_id))

    def count(self):
        return _FakeAggregate(len(self._matching()))


class _FakeCollection(_FakeQuery):
    def __init__(self, store):
        super().__init__(store, [])

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)


class _FakeUserRef:
    def __init__(self, collections):
        self._collections = collections

    def collection(self, name):
        return _FakeCollection(self._collections.setdefault(name, {}))


class _FakeUsersCollection:
    def __init__(self, collections):
        self._collections = collections

    def document(self, _uid):
        return _FakeUserRef(self._collections)


class _FakeBatch:
    def __init__(self):
        self._writes = []

    def update(self, reference, values):
        self._writes.append((reference, values))

    def commit(self):
        for reference, values in self._writes:
            reference.update(values)
        self._writes = []


class _FakeDb:
    def __init__(self, conversations, folders_store):
        self._collections = {'conversations': conversations, 'folders': folders_store}

    def collection(self, _name):
        return _FakeUsersCollection(self._collections)

    def batch(self):
        return _FakeBatch()

    def get_all(self, references):
        return [reference.get() for reference in references]


def test_move_off_a_deleted_folder_does_not_500():
    conversations = {'conv-1': {'folder_id': 'deleted-folder', 'discarded': False}}
    folders_store = {'work': {'conversation_count': 0}}

    with patch.object(folders, 'db', _FakeDb(conversations, folders_store)):
        # Pre-fix this raised NotFound from the old folder's count refresh.
        assert folders.move_conversation_to_folder('u1', 'conv-1', 'work') is True

    assert conversations['conv-1']['folder_id'] == 'work'
    assert conversations['conv-1']['folder_user_set'] is True
    assert folders_store['work']['conversation_count'] == 1


def test_bulk_move_off_a_deleted_folder_does_not_500():
    conversations = {
        'conv-1': {'folder_id': 'deleted-folder', 'discarded': False},
        'conv-2': {'folder_id': 'deleted-folder', 'discarded': False},
    }
    folders_store = {'work': {'conversation_count': 0}}

    with patch.object(folders, 'db', _FakeDb(conversations, folders_store)):
        assert folders.bulk_move_conversations_to_folder('u1', ['conv-1', 'conv-2'], 'work') == 2

    assert folders_store['work']['conversation_count'] == 2


def test_delete_folder_without_a_default_target_unfiles_instead_of_orphaning():
    conversations = {'conv-1': {'folder_id': 'doomed', 'discarded': False}}
    # No folder carries is_default — the post-'Other' account shape.
    folders_store = {'doomed': {'conversation_count': 1, 'order': 0}}

    with patch.object(folders, 'db', _FakeDb(conversations, folders_store)):
        assert folders.delete_folder('u1', 'doomed') is True

    assert 'doomed' not in folders_store
    # Pre-fix this stayed 'doomed' and poisoned every later move.
    assert conversations['conv-1']['folder_id'] is None


def test_delete_folder_still_moves_conversations_to_the_default_folder():
    conversations = {'conv-1': {'folder_id': 'doomed', 'discarded': False}}
    folders_store = {
        'doomed': {'conversation_count': 1, 'order': 0},
        'other': {'is_default': True, 'conversation_count': 0, 'order': 1},
    }

    with patch.object(folders, 'db', _FakeDb(conversations, folders_store)):
        assert folders.delete_folder('u1', 'doomed') is True

    assert conversations['conv-1']['folder_id'] == 'other'
    assert folders_store['other']['conversation_count'] == 1
