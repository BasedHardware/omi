import importlib
import os
import sys
import types
from unittest.mock import MagicMock

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BACKEND_DIR)


class _FakeNotFound(Exception):
    pass


google_mod = sys.modules.setdefault('google', types.ModuleType('google'))
api_core_mod = sys.modules.setdefault('google.api_core', types.ModuleType('google.api_core'))
exceptions_mod = sys.modules.setdefault('google.api_core.exceptions', types.ModuleType('google.api_core.exceptions'))
exceptions_mod.NotFound = _FakeNotFound
setattr(google_mod, 'api_core', api_core_mod)
setattr(api_core_mod, 'exceptions', exceptions_mod)

cloud_mod = sys.modules.setdefault('google.cloud', types.ModuleType('google.cloud'))
firestore_mod = sys.modules.setdefault('google.cloud.firestore', types.ModuleType('google.cloud.firestore'))
firestore_v1_mod = sys.modules.setdefault('google.cloud.firestore_v1', types.ModuleType('google.cloud.firestore_v1'))
firestore_mod.ArrayUnion = MagicMock
firestore_mod.ArrayRemove = MagicMock
firestore_mod.Increment = MagicMock
firestore_mod.SERVER_TIMESTAMP = object()
firestore_mod.DELETE_FIELD = object()
firestore_mod.Query = MagicMock
firestore_v1_mod.FieldFilter = MagicMock
firestore_v1_mod.transactional = lambda fn: fn
setattr(google_mod, 'cloud', cloud_mod)
setattr(cloud_mod, 'firestore', firestore_mod)
setattr(cloud_mod, 'firestore_v1', firestore_v1_mod)

database_pkg = sys.modules.get('database')
if not isinstance(database_pkg, types.ModuleType):
    database_pkg = types.ModuleType('database')
    sys.modules['database'] = database_pkg
database_pkg.__path__ = [os.path.join(BACKEND_DIR, 'database')]

sys.modules['database.users'] = types.ModuleType('database.users')
sys.modules['database.redis_db'] = types.ModuleType('database.redis_db')
sys.modules['database.redis_db'].get_user_data_protection_level = MagicMock(return_value='standard')
sys.modules['database.redis_db'].set_user_data_protection_level = MagicMock()
sys.modules.setdefault('utils.encryption', types.ModuleType('utils.encryption'))
sys.modules['utils.encryption'].encrypt = lambda value, _uid: value
sys.modules['utils.encryption'].decrypt = lambda value, _uid: value


class _FakeDb:
    def __init__(self, memory_ref):
        self.memory_ref = memory_ref

    def collection(self, _name):
        return self

    def document(self, _name):
        return self

    def update(self, payload):
        return self.memory_ref.update(payload)

    def batch(self):
        return MagicMock()


class _FakeTransaction:
    def update(self, ref, payload):
        return ref.update(payload)


def _append_commit_with_projection(**kwargs):
    projection_writer = kwargs.get('projection_writer')
    if projection_writer:
        projection_writer(_FakeTransaction())
    return None


def _load_memories_module(memory_ref):
    client_mod = types.ModuleType('database._client')
    client_mod.db = _FakeDb(memory_ref)
    setattr(client_mod, 'get_firestore_client', lambda: client_mod.db)
    setattr(client_mod, 'document_id_from_seed', lambda seed: f'doc-{seed}')
    sys.modules['database._client'] = client_mod
    sys.modules.pop('database.memories', None)
    memories = importlib.import_module('database.memories')
    memories.memory_ledger.append_commit = MagicMock(
        side_effect=lambda *args, **kwargs: _append_commit_with_projection(**kwargs)
    )
    return memories


def test_set_memory_kg_extracted_missing_doc_is_idempotent(caplog):
    memory_ref = MagicMock()
    memory_ref.update.side_effect = _FakeNotFound('No document to update: users/u/memories/m')
    memories = _load_memories_module(memory_ref)

    assert memories.set_memory_kg_extracted('uid-abc', 'memory-1') is None

    memory_ref.update.assert_called_once_with({'kg_extracted': True})
    assert 'memory-1' not in caplog.text
    assert 'No document to update' not in caplog.text


def test_invalidate_memory_missing_doc_is_idempotent(caplog):
    memory_ref = MagicMock()
    memory_ref.update.side_effect = _FakeNotFound('No document to update: users/u/memories/m')
    memories = _load_memories_module(memory_ref)

    assert memories.invalidate_memory('uid-abc', 'memory-1', superseded_by='memory-2') is None

    payload = memory_ref.update.call_args.args[0]
    assert 'invalid_at' in payload
    assert payload['superseded_by'] == 'memory-2'
    assert 'memory-1' not in caplog.text
    assert 'memory-2' not in caplog.text
    assert 'No document to update' not in caplog.text


def test_get_memories_by_subject_entity_orders_by_recency():
    # The query intentionally has no Firestore order_by (to avoid a composite index),
    # so the function must sort the active facts by created_at desc in Python before
    # slicing — otherwise the returned subset is arbitrary (document-id order).
    from datetime import datetime, timezone

    memories = _load_memories_module(MagicMock())

    def _doc(mid, day):
        d = {
            'id': mid,
            'content': mid,
            'created_at': datetime(2026, 1, day, tzinfo=timezone.utc),
            'user_review': True,
            'invalid_at': None,
        }
        m = MagicMock()
        m.to_dict.return_value = d
        return m

    docs = [_doc('old', 1), _doc('new', 20), _doc('mid', 10)]  # deliberately unordered

    class _Q:
        applied_limit = None

        def where(self, **kwargs):
            return self

        def limit(self, n):
            _Q.applied_limit = n  # the function now bounds the read with an over-fetch limit
            return self

        def stream(self):
            return iter(docs)

    class _Coll:
        def document(self, _):
            return self

        def collection(self, _):
            return _Q()

    class _Client:
        def collection(self, _):
            return _Coll()

    out = memories.get_memories_by_subject_entity('u', 'sid', limit=10, firestore_client=_Client())
    assert [m['id'] for m in out] == ['new', 'mid', 'old']
    # The Firestore read is bounded (over-fetch), not an unbounded stream of every fact.
    assert _Q.applied_limit is not None and _Q.applied_limit >= 10

    # The limit slice keeps the newest N, not an arbitrary subset.
    out2 = memories.get_memories_by_subject_entity('u', 'sid', limit=2, firestore_client=_Client())
    assert [m['id'] for m in out2] == ['new', 'mid']
