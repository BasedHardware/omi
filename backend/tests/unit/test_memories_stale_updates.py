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


def _load_memories_module(memory_ref):
    client_mod = types.ModuleType('database._client')
    client_mod.db = _FakeDb(memory_ref)
    sys.modules['database._client'] = client_mod
    sys.modules.pop('database.memories', None)
    return importlib.import_module('database.memories')


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
