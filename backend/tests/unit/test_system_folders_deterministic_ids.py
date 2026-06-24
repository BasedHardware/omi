"""Regression test for fix/system-folders-race.

initialize_system_folders used to assign each system folder a random uuid4 doc
id under a check-then-create pattern. Two concurrent first-access callers both
see an empty collection and both create three folders with different random
ids -> six duplicate system folders.

The fix derives each system folder's doc id deterministically from
uid + category_mapping (via document_id_from_seed), so concurrent creates
converge on the SAME three doc ids and the second .set() is a harmless
overwrite. This test asserts the created doc ids are deterministic for a given
uid (call twice -> identical id set), which is false with random uuids.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub heavy third-party packages. database._client and database.folders are
# imported for real so document_id_from_seed (pure hashlib/uuid) runs for real;
# only the firestore client behind `db` is a MagicMock.
_STUB = (
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'httpx',
)


def _is(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from database import folders as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


def _run_initialize_and_collect_ids(uid):
    """Drive initialize_system_folders with a fresh (empty) mocked Firestore
    and return the list of doc ids passed to folders_ref.document(...)."""
    requested_ids = []

    folders_ref = MagicMock()

    def _document(doc_id):
        requested_ids.append(doc_id)
        return MagicMock()

    folders_ref.document.side_effect = _document
    # Empty collection -> initializer proceeds to create system folders.
    folders_ref.limit.return_value.stream.return_value = iter([])

    user_ref = MagicMock()
    user_ref.collection.return_value = folders_ref

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = user_ref

    # Patch the module-level db so no real Firestore is touched.
    original_db = mod.db
    mod.db = fake_db
    try:
        created = mod.initialize_system_folders(uid)
    finally:
        mod.db = original_db

    return requested_ids, created


def test_system_folder_ids_are_deterministic_per_uid():
    uid = 'user-abc-123'

    ids_first, created_first = _run_initialize_and_collect_ids(uid)
    ids_second, _ = _run_initialize_and_collect_ids(uid)

    # Three system folders created each time.
    assert len(ids_first) == len(mod.SYSTEM_FOLDERS) == 3
    assert len(ids_second) == 3

    # Determinism: two independent first-access runs for the same uid must
    # produce the IDENTICAL set of doc ids. With random uuid4 ids this fails
    # (the two runs would have six distinct ids), which is exactly the race
    # that creates duplicate system folders.
    assert ids_first == ids_second, (
        f"system-folder doc ids are non-deterministic for uid={uid}: " f"{ids_first} != {ids_second}"
    )

    # The returned folder docs carry those same deterministic ids.
    assert [f['id'] for f in created_first] == ids_first

    # Sanity: ids match the seeded derivation contract (uid + category_mapping).
    expected = [
        mod.document_id_from_seed(f"{uid}:system_folder:{cfg['category_mapping']}") for cfg in mod.SYSTEM_FOLDERS
    ]
    assert ids_first == expected


def test_system_folder_ids_differ_across_users():
    ids_a, _ = _run_initialize_and_collect_ids('user-a')
    ids_b, _ = _run_initialize_and_collect_ids('user-b')

    # Different uids must not collide on the same doc ids.
    assert set(ids_a).isdisjoint(set(ids_b))
