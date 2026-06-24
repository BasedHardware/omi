"""reorder_folders must not 500 when the client supplies a stale/foreign folder id.

On main, reorder_folders blindly calls batch.update(...) for every client-supplied folder_id with
no existence check. Firestore's batch.update on a missing document raises google NotFound at
batch.commit() time -> unhandled 500 for the whole reorder request (one stale client id pollutes the
entire batch).

The fix scopes the reorder to ids that actually belong to the user (via get_folders) and skips unknown
ids, so a ghost id is simply ignored and the surviving folders still get sequential order values.

This is a behavioral test on database.folders.reorder_folders directly. We import the REAL module while
stubbing only its heavy transitive deps (google cloud SDK, models, the Firestore singleton in
database._client). To make the "500" concrete, the fake batch raises NotFound from update() for any
ref whose id is not in the valid set -- so on main (no existence check) the call raises, and with the
fix (ghost skipped) it commits cleanly and update() is invoked exactly for the valid ids.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub the heavy transitive deps of database.folders, but NOT 'database'/'database.folders' themselves
# (we want the real reorder_folders). database._client (Firestore singleton) and models.* are stubbed.
_STUB = (
    'database._client',
    'models',
    'google',
    'firebase_admin',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from database import folders as folders_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


class _NotFound(Exception):
    """Stand-in for google.api_core.exceptions.NotFound (a missing doc in batch.update)."""


class _FakeDocRef:
    def __init__(self, doc_id):
        self.id = doc_id


class _FakeFolderRef:
    """folders_ref: .document(id) returns a ref carrying that id."""

    def document(self, doc_id):
        return _FakeDocRef(doc_id)


class _FakeUserRef:
    def collection(self, name):
        assert name == 'folders'
        return _FakeFolderRef()


class _FakeBatch:
    """Simulates a Firestore WriteBatch: update() on a ref whose id is unknown raises (like NotFound)."""

    def __init__(self, valid_ids):
        self._valid_ids = valid_ids
        self.updated = []  # list of (folder_id, order)
        self.commit_calls = 0

    def update(self, ref, data):
        if ref.id not in self._valid_ids:
            # Firestore surfaces this at commit time, but raising here is a strictly harder failure
            # and still proves the unguarded path touches the ghost id.
            raise _NotFound(f"No document to update: {ref.id}")
        self.updated.append((ref.id, data['order']))

    def commit(self):
        self.commit_calls += 1


class _FakeDb:
    def __init__(self, valid_ids):
        self._valid_ids = valid_ids
        self.last_batch = None

    def collection(self, name):
        assert name == 'users'
        m = MagicMock()
        m.document.return_value = _FakeUserRef()
        return m

    def batch(self):
        self.last_batch = _FakeBatch(self._valid_ids)
        return self.last_batch


def _run(folder_ids, valid_ids, monkeypatch):
    fake_db = _FakeDb(set(valid_ids))
    monkeypatch.setattr(folders_mod, 'db', fake_db)
    monkeypatch.setattr(folders_mod, 'get_folders', lambda uid: [{'id': i} for i in valid_ids])
    result = folders_mod.reorder_folders('uid', folder_ids)
    return result, fake_db.last_batch


def test_reorder_skips_ghost_id_without_raising(monkeypatch):
    # 'ghost' is not a real folder for this user. On main this hits batch.update -> NotFound (500).
    # With the fix it's skipped and the remaining folders are reordered cleanly.
    result, batch = _run(['a', 'ghost', 'b'], valid_ids=['a', 'b'], monkeypatch=monkeypatch)

    assert result is True
    assert batch.commit_calls == 1
    # Only the two real folders were written, with sequential order values, and never the ghost id.
    assert batch.updated == [('a', 0), ('b', 1)]
    assert 'ghost' not in [fid for fid, _ in batch.updated]


def test_reorder_all_valid_ids_still_works(monkeypatch):
    result, batch = _run(['b', 'a'], valid_ids=['a', 'b'], monkeypatch=monkeypatch)

    assert result is True
    assert batch.commit_calls == 1
    assert batch.updated == [('b', 0), ('a', 1)]
