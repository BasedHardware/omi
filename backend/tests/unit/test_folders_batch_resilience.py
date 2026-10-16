import os
import sys
import types
from pathlib import Path
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _setup_preflight_stubs():
    for p in ["google", "google.api_core", "google.cloud"]:
        _pkg(p)

    _exc = _mod("google.api_core.exceptions")
    if not hasattr(_exc, "NotFound"):
        _exc.NotFound = type("NotFound", (Exception,), {})
    if not hasattr(_exc, "InvalidArgument"):
        _exc.InvalidArgument = type("InvalidArgument", (Exception,), {})

    _fs = _mod("google.cloud.firestore")
    if not hasattr(_fs, "Query"):
        _fs.Query = MagicMock()
    if not hasattr(_fs, "Client"):
        _fs.Client = MagicMock
    if not hasattr(_fs, "transactional"):
        _fs.transactional = lambda fn: fn

    class _FakeFieldFilter:
        def __init__(self, field_path: str, op: str, value: Any):
            self.field_path = field_path
            self.op = op
            self.value = value

    if not hasattr(_fs, "FieldFilter"):
        _fs.FieldFilter = _FakeFieldFilter

    _fs_v1 = _mod("google.cloud.firestore_v1")
    if not hasattr(_fs_v1, "FieldFilter"):
        _fs_v1.FieldFilter = _FakeFieldFilter


_setup_preflight_stubs()

import database.folders as folders


class _ContentionDetectingFakeBatch:
    """Mock Firestore batch that enforces real Firestore single-commit uniqueness rules.
    If multiple operations target the same document reference within a single commit batch,
    it raises a simulated 400 Multiple operations error.
    """

    def __init__(self):
        self._writes = []
        self.commit_calls = 0

    def update(self, reference, values):
        self._writes.append((reference, values))

    def commit(self):
        self.commit_calls += 1
        seen_paths = set()
        for reference, _ in self._writes:
            path = getattr(reference, 'path', str(reference))
            if path in seen_paths:
                raise ValueError(f"400 Multiple operations on document in a single commit: {path}")
            seen_paths.add(path)
        for reference, values in self._writes:
            reference.update(values)
        self._writes = []


class _FakeSnapshot:
    def __init__(self, doc_id, data, reference=None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = reference

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, doc_id, path=None):
        self._store = store
        self.id = doc_id
        self.path = path or f"documents/users/u1/{doc_id}"

    def get(self):
        return _FakeSnapshot(self.id, self._store.get(self.id), reference=self)

    def update(self, values):
        if self.id not in self._store:
            self._store[self.id] = {}
        self._store[self.id].update(values)

    def delete(self):
        self._store.pop(self.id, None)


class _FakeQuery:
    def __init__(self, store, predicates=None):
        self._store = store
        self._predicates = predicates or []

    def where(self, filter=None):
        return _FakeQuery(self._store, self._predicates + [(filter.field_path, filter.value)])

    def order_by(self, _field, direction=None):
        return self

    def select(self, _fields):
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
            yield _FakeSnapshot(doc_id, data, reference=_FakeDocRef(self._store, doc_id, f"documents/{doc_id}"))

    def count(self):
        total = len(self._matching())
        return MagicMock(get=lambda: [[MagicMock(value=total)]])


class _FakeCollection(_FakeQuery):
    def __init__(self, store, prefix=""):
        super().__init__(store, [])
        self._prefix = prefix

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id, path=f"{self._prefix}/{doc_id}")


class _FakeUserRef:
    def __init__(self, collections):
        self._collections = collections

    def collection(self, name):
        return _FakeCollection(self._collections.setdefault(name, {}), prefix=f"users/u1/{name}")


class _FakeTransaction:
    def __init__(self):
        self.updates = []

    def update(self, reference, values):
        self.updates.append((reference, values))
        reference.update(values)


class _FakeDb:
    def __init__(self, conversations, folders_store):
        self._collections = {'conversations': conversations, 'folders': folders_store}
        self.last_batch = None
        self.last_transaction = None

    def collection(self, _name):
        mock_users = MagicMock()
        mock_users.document.return_value = _FakeUserRef(self._collections)
        return mock_users

    def batch(self):
        b = _ContentionDetectingFakeBatch()
        self.last_batch = b
        return b

    def transaction(self):
        t = _FakeTransaction()
        self.last_transaction = t
        return t

    def get_all(self, references, *, field_paths=None, transaction=None):
        return [reference.get() for reference in references]


class TestFoldersBatchResilience(unittest.TestCase):
    def _patch_db(self, fake_db):
        return patch.multiple(folders, db=fake_db, get_firestore_client=lambda: fake_db)

    def test_bulk_move_deduplicates_conversation_ids_and_avoids_commit_contention(self):
        """Duplicate conversation IDs in bulk move must be deduplicated to avoid Firestore 400 commit contention."""
        conversations = {
            'conv-1': {'folder_id': 'old-folder', 'discarded': False},
            'conv-2': {'folder_id': 'old-folder', 'discarded': False},
        }
        folders_store = {
            'old-folder': {'conversation_count': 2},
            'work': {'conversation_count': 0},
        }
        fake_db = _FakeDb(conversations, folders_store)

        with self._patch_db(fake_db):
            # Pass duplicates: ['conv-1', 'conv-2', 'conv-1', 'conv-2']
            moved = folders.bulk_move_conversations_to_folder('u1', ['conv-1', 'conv-2', 'conv-1', 'conv-2'], 'work')

        # Count must accurately reflect unique moved conversations
        self.assertEqual(moved, 2)
        self.assertEqual(conversations['conv-1']['folder_id'], 'work')
        self.assertEqual(conversations['conv-2']['folder_id'], 'work')
        self.assertEqual(folders_store['work']['conversation_count'], 2)

    def test_bulk_move_filters_malformed_and_slash_ids(self):
        """Malformed, empty, non-string, and slash-containing conversation IDs must be skipped cleanly."""
        conversations = {'conv-1': {'folder_id': 'old', 'discarded': False}}
        folders_store = {'target': {'conversation_count': 0}}
        fake_db = _FakeDb(conversations, folders_store)

        with self._patch_db(fake_db):
            moved = folders.bulk_move_conversations_to_folder(
                'u1', ['', '   ', None, 'conv-1', 'conv/malformed', 123], 'target'  # type: ignore
            )

        self.assertEqual(moved, 1)
        self.assertEqual(conversations['conv-1']['folder_id'], 'target')

    def test_bulk_move_empty_or_invalid_inputs(self):
        """bulk_move_conversations_to_folder returns 0 on invalid uid, empty conversation list, or empty folder."""
        fake_db = _FakeDb({}, {})
        with self._patch_db(fake_db):
            self.assertEqual(folders.bulk_move_conversations_to_folder('', ['c1'], 'f1'), 0)
            self.assertEqual(folders.bulk_move_conversations_to_folder('   ', ['c1'], 'f1'), 0)
            self.assertEqual(folders.bulk_move_conversations_to_folder('u1', [], 'f1'), 0)
            self.assertEqual(folders.bulk_move_conversations_to_folder('u1', ['c1'], ''), 0)
            self.assertEqual(folders.bulk_move_conversations_to_folder('u1', ['c1'], '   '), 0)

    def test_reorder_folders_deduplicates_folder_ids_and_avoids_commit_contention(self):
        """reorder_folders must deduplicate folder IDs to prevent multiple operations on the same doc in one commit."""
        folders_store = {
            'f1': {'order': 0},
            'f2': {'order': 1},
            'f3': {'order': 2},
        }
        fake_db = _FakeDb({}, folders_store)

        with self._patch_db(fake_db):
            # Pass duplicate 'f1'
            success = folders.reorder_folders('u1', ['f1', 'f2', 'f1', 'f3'])

        self.assertTrue(success)
        self.assertEqual(folders_store['f1']['order'], 0)
        self.assertEqual(folders_store['f2']['order'], 1)
        self.assertEqual(folders_store['f3']['order'], 2)

    def test_reorder_folders_chunks_over_450_items(self):
        """reorder_folders commits batches in chunks of 450 items to stay strictly below Firestore's 500 limit."""
        folders_store = {f"f{i}": {'order': 0} for i in range(500)}
        fake_db = _FakeDb({}, folders_store)

        committed_batch_calls = 0
        real_commit = _ContentionDetectingFakeBatch.commit

        def counting_commit(batch_self):
            nonlocal committed_batch_calls
            committed_batch_calls += 1
            real_commit(batch_self)

        with self._patch_db(fake_db), patch.object(_ContentionDetectingFakeBatch, 'commit', counting_commit):
            folder_ids = [f"f{i}" for i in range(500)]
            success = folders.reorder_folders('u1', folder_ids)

        self.assertTrue(success)
        # 500 items chunked at 450 -> 2 batch commits (450 + 50)
        self.assertEqual(committed_batch_calls, 2)

    def test_reorder_folders_empty_or_invalid_inputs(self):
        """reorder_folders returns False on empty uid or invalid folder_ids."""
        fake_db = _FakeDb({}, {})
        with self._patch_db(fake_db):
            self.assertFalse(folders.reorder_folders('', ['f1']))
            self.assertFalse(folders.reorder_folders('   ', ['f1']))
            self.assertFalse(folders.reorder_folders('u1', []))
            self.assertFalse(folders.reorder_folders('u1', ['', '   ', 'f/slash']))

    def test_delete_folder_self_targeting_prevents_tombstone(self):
        """delete_folder with move_to_folder_id pointing to itself must not repoint to the deleted folder."""
        conversations = {'conv-1': {'folder_id': 'doomed', 'discarded': False}}
        folders_store = {'doomed': {'conversation_count': 1}}
        fake_db = _FakeDb(conversations, folders_store)

        with self._patch_db(fake_db):
            # Target is the same as the folder being deleted
            success = folders.delete_folder('u1', 'doomed', move_to_folder_id='doomed')

        self.assertTrue(success)
        self.assertNotIn('doomed', folders_store)
        # Conversation must be unfiled (None) instead of left pointing to 'doomed'
        self.assertIsNone(conversations['conv-1']['folder_id'])

    def test_move_conversation_empty_guards(self):
        """move_conversation_to_folder returns False on empty uid or empty conversation_id."""
        fake_db = _FakeDb({}, {})
        with self._patch_db(fake_db):
            self.assertFalse(folders.move_conversation_to_folder('', 'c1', 'f1'))
            self.assertFalse(folders.move_conversation_to_folder('   ', 'c1', 'f1'))
            self.assertFalse(folders.move_conversation_to_folder('u1', '', 'f1'))
            self.assertFalse(folders.move_conversation_to_folder('u1', '   ', 'f1'))

    def test_folder_readers_guard_empty_uid(self):
        """get_folders and get_folder safely handle empty/whitespace uid without Firestore errors."""
        fake_db = _FakeDb({}, {})
        with self._patch_db(fake_db):
            self.assertEqual(folders.get_folders(''), [])
            self.assertEqual(folders.get_folders('   '), [])
            self.assertIsNone(folders.get_folder('', 'f1'))
            self.assertIsNone(folders.get_folder('u1', ''))


if __name__ == '__main__':
    unittest.main()
