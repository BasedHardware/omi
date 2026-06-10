"""Offline tests for memory evidence persistence helpers."""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_test_secret_key_for_unit_tests_only_000000000000000000')


class _FakeQuery:
    DESCENDING = 'DESCENDING'


class _FakeDB:
    def collection(self, *args, **kwargs):
        return MagicMock()

    def transaction(self):
        return MagicMock()


def _transactional(func):
    return func


google_stub = sys.modules.setdefault('google', types.ModuleType('google'))
cloud_stub = sys.modules.setdefault('google.cloud', types.ModuleType('google.cloud'))

firestore_stub = sys.modules.setdefault('google.cloud.firestore', types.ModuleType('google.cloud.firestore'))
firestore_stub.Query = _FakeQuery
cloud_stub.firestore = firestore_stub
google_stub.cloud = cloud_stub

firestore_v1_stub = sys.modules.setdefault('google.cloud.firestore_v1', types.ModuleType('google.cloud.firestore_v1'))
firestore_v1_stub.FieldFilter = MagicMock
firestore_v1_stub.transactional = _transactional

if 'database._client' not in sys.modules:
    client_stub = types.ModuleType('database._client')
    client_stub.db = _FakeDB()
    client_stub.document_id_from_seed = lambda seed: 'id-' + str(abs(hash(seed)) % (10**12))
    sys.modules['database._client'] = client_stub
else:
    sys.modules['database._client'].db = getattr(sys.modules['database._client'], 'db', _FakeDB())

for mod_name in ['database.users', 'database.redis_db']:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

encryption_stub = types.ModuleType('utils.encryption')
encryption_stub.encrypt = lambda data, uid: f"encrypted:{uid}:{data}"
encryption_stub.decrypt = lambda data, uid: data.removeprefix(f"encrypted:{uid}:")
sys.modules['utils.encryption'] = encryption_stub

from database import memories as memories_db  # noqa: E402


def _memory(evidence, *, content='memory', created_at=None, level='standard'):
    now = created_at or datetime.now(timezone.utc)
    return {
        'id': 'memory-1',
        'uid': 'uid-1',
        'content': content,
        'created_at': now,
        'updated_at': now,
        'data_protection_level': level,
        'evidence': evidence,
    }


def test_merge_memory_for_write_accumulates_standard_evidence():
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    existing = _memory([{'evidence_id': 'ev1', 'source_id': 'conv1'}], content='old', created_at=old_time)
    incoming = _memory(
        [
            {'evidence_id': 'ev1', 'source_id': 'conv1'},
            {'evidence_id': 'ev2', 'source_id': 'gmail:msg1'},
        ],
        content='new',
    )

    merged = memories_db._merge_memory_for_write('uid-1', existing, incoming)

    assert merged['content'] == 'new'
    assert merged['created_at'] == old_time
    assert [item['evidence_id'] for item in merged['evidence']] == ['ev1', 'ev2']


def test_merge_memory_for_write_round_trips_enhanced_evidence():
    existing = memories_db._prepare_data_for_write(
        _memory([{'evidence_id': 'ev1', 'source_id': 'conv1'}], content='old', level='enhanced'),
        'uid-1',
        'enhanced',
    )
    incoming = memories_db._prepare_data_for_write(
        _memory([{'evidence_id': 'ev2', 'source_id': 'gmail:msg1'}], content='new', level='enhanced'),
        'uid-1',
        'enhanced',
    )

    merged = memories_db._merge_memory_for_write('uid-1', existing, incoming)

    assert isinstance(merged['content'], str)
    assert merged['content'] != 'new'
    assert isinstance(merged['evidence'], str)

    plaintext = memories_db._prepare_memory_for_read(merged, 'uid-1')
    assert plaintext['content'] == 'new'
    assert [item['evidence_id'] for item in plaintext['evidence']] == ['ev1', 'ev2']


def test_coalesce_memory_writes_preserves_same_batch_evidence():
    first = _memory([{'evidence_id': 'ev1', 'source_id': 'conv1'}], content='old')
    second = _memory([{'evidence_id': 'ev2', 'source_id': 'gmail:msg1'}], content='new')

    coalesced = memories_db._coalesce_memory_writes('uid-1', [first, second])

    assert len(coalesced) == 1
    assert coalesced[0]['content'] == 'new'
    assert [item['evidence_id'] for item in coalesced[0]['evidence']] == ['ev1', 'ev2']
