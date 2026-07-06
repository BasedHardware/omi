from dataclasses import dataclass
from datetime import datetime, timezone
import sys
import types

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception as exc:  # pragma: no cover - system pytest env without backend deps
    pytest.skip(f'FastAPI/TestClient route proof requires backend venv dependencies: {exc}', allow_module_level=True)

from config.memory_rollout import MemoryRolloutMode
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import DEFAULT_READ_ROLLOUT_SCHEMA_VERSION
from utils.memory.v3_composed_get_service import (
    V3ComposedRequestParams,
    V3ComposedResponse,
    compose_v3_get,
)
from utils.memory.v3_production_runtime import build_v3_production_runtime

pytestmark = pytest.mark.slow


@dataclass
class FakeSnapshot:
    data: dict | None
    exists: bool = True
    id: str = 'snapshot'

    def to_dict(self):
        return self.data


class FakeDoc:
    def __init__(self, path, db):
        self.path = path
        self.db = db

    def get(self, timeout=None):
        self.db.reads.append((self.path, timeout))
        if self.path not in self.db.docs:
            return FakeSnapshot(None, exists=False, id=self.path.rsplit('/', 1)[-1])
        return FakeSnapshot(self.db.docs[self.path], id=self.path.rsplit('/', 1)[-1])


class FakeQuery:
    def __init__(self, db, path):
        self.db = db
        self.path = path
        self.limit_value = None

    def order_by(self, *args, **kwargs):
        self.db.query_ops.append(('order_by', args, kwargs))
        return self

    def start_after(self, value):
        self.db.query_ops.append(('start_after', value))
        return self

    def limit(self, value):
        self.limit_value = value
        self.db.query_ops.append(('limit', value))
        return self

    def stream(self):
        self.db.streams.append((self.path, self.limit_value))
        docs = self.db.collections.get(self.path, [])
        if self.limit_value is not None:
            docs = docs[: self.limit_value]
        return [FakeSnapshot(data, id=doc_id) for doc_id, data in docs]


class FakeDb:
    def __init__(self, docs=None, collections=None):
        self.docs = docs or {}
        self.collections = collections or {}
        self.reads = []
        self.streams = []
        self.query_ops = []
        self.writes = []

    def document(self, path):
        return FakeDoc(path, self)

    def collection(self, path):
        return FakeQuery(self, path)


def _control_doc(uid='uid-a'):
    return {
        'uid': uid,
        'schema_version': DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        'mode': MemoryRolloutMode.read.value,
        'mode_epoch': 2,
        'cutover_epoch': 2,
        'account_generation': 7,
        'fallback_projection_ready': True,
        'persistent_memory_writes_started': True,
        'writes_blocked': False,
        'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
        'grants': {'omi_chat': {'default_memory': True, 'archive': False}},
    }


def _state_head(uid='uid-a', account_generation=7):
    return {
        'uid': uid,
        'schema_version': 1,
        'source': 'memory_state_head',
        'account_generation': account_generation,
        'head_commit_id': 'head-7',
        'commit_sequence': account_generation,
    }


def _projection_state(uid='uid-a'):
    return {
        'schema_version': 1,
        'ready': True,
        'uid': uid,
        'source': 'memory_items_projection',
        'account_generation': 7,
        'projection_generation': 7,
        'freshness_fence_generation': 7,
        'tombstone_fence_generation': 7,
        'vector_cleanup_fence_generation': 7,
        'source_commit_id': 'source-commit-7',
        'projection_commit_id': 'commit-7',
        'source_evidence_fence': 'evidence-7',
        'projection_evidence_fence': 'evidence-7',
        'projection_version': 'v3_memorydb_compatibility',
        'source_version': 'source-v7',
        'write_convergence_complete': True,
        'delete_convergence_complete': True,
        'tombstone_convergence_complete': True,
        'empty_projection': False,
    }


def _projection_item(memory_id='m1'):
    now = datetime(2026, 6, 21, tzinfo=timezone.utc)
    return {
        'uid': 'uid-a',
        'memory_id': memory_id,
        'schema_version': 1,
        'source': 'memory_items_projection',
        'account_generation': 7,
        'projection_generation': 7,
        'source_commit_id': 'source-commit-7',
        'projection_commit_id': 'commit-7',
        'projection_evidence_fence': 'evidence-7',
        'freshness_fence_generation': 7,
        'tombstone_fence_generation': 7,
        'write_convergence_complete': True,
        'delete_convergence_complete': True,
        'tombstone_convergence_complete': True,
        'memorydb': {
            'id': memory_id,
            'uid': 'uid-a',
            'content': 'memory visible memory',
            'category': 'system',
            'visibility': 'private',
            'tags': [],
            'created_at': now,
            'updated_at': now,
            'memory_tier': 'long_term',
            'reviewed': True,
            'user_review': None,
            'manually_added': False,
            'edited': False,
            'conversation_id': None,
            'data_protection_level': 'standard',
        },
    }


def _ready_db(uid='uid-a'):
    paths = MemoryCollections(uid=uid)
    return FakeDb(
        docs={
            paths.memory_control_state: _control_doc(uid),
            paths.memory_state_head: _state_head(uid),
            'memory_control/global_read_gate': {
                'memory_reads_enabled': True,
                'kill_switch_active': False,
            },
            'memory_control/write_convergence_gate': {
                'durable_outbox_enabled': True,
                'dual_write_projection_ready': True,
                'delete_convergence_ready': True,
                'idempotency_contract_ready': True,
            },
            paths.v3_compatibility_projection_state: _projection_state(uid),
        },
        collections={paths.v3_compatibility_projection_items: [('m1', _projection_item('m1'))]},
    )


def _route_client(monkeypatch, db, legacy_calls):
    monkeypatch.setenv('ENCRYPTION_SECRET', 'memory-test-encryption-secret-32bytes!!')
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test-memory-route-proof')
    fake_storage = types.ModuleType('utils.other.storage')
    setattr(fake_storage, 'list_audio_chunks', lambda *args, **kwargs: [])
    setattr(fake_storage, 'delete_conversation_audio_files', lambda *args, **kwargs: None)
    setattr(fake_storage, 'storage_client', None)
    setattr(fake_storage, 'private_cloud_sync_bucket', None)
    setattr(fake_storage, '_get_extension_for_path', lambda path: '')
    monkeypatch.setitem(sys.modules, 'utils.other.storage', fake_storage)
    import routers.memories as memories_router

    monkeypatch.setattr(memories_router.db_client_module, 'db', db)

    def legacy_get(uid, limit, offset):
        legacy_calls.append({'uid': uid, 'limit': limit, 'offset': offset})
        return [
            {
                'id': 'legacy-id',
                'uid': uid,
                'content': 'legacy memory',
                'category': 'system',
                'visibility': 'private',
                'tags': [],
                'created_at': datetime(2026, 6, 21, tzinfo=timezone.utc),
                'updated_at': datetime(2026, 6, 21, tzinfo=timezone.utc),
                'reviewed': True,
                'manually_added': False,
                'edited': False,
                'conversation_id': None,
                'data_protection_level': 'standard',
                'memory_tier': 'short_term',
            }
        ]

    monkeypatch.setattr(memories_router.memories_db, 'get_memories', legacy_get)
    app = FastAPI()
    app.dependency_overrides[memories_router.auth.get_current_user_uid] = lambda: 'uid-a'
    app.include_router(memories_router.router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.slow
def test_real_router_uses_actual_builder_and_does_zero_db_reads_while_v3_gate_off(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    monkeypatch.delenv('MEMORY_V3_GET_ENABLED', raising=False)
    db = _ready_db()
    legacy_calls = []
    client = _route_client(monkeypatch, db, legacy_calls)

    response = client.get('/v3/memories?limit=3')

    assert response.status_code == 200
    body = response.json()
    assert body[0]['id'] == 'legacy-id'
    assert 'layer' not in body[0]
    assert 'memory_tier' not in body[0]
    assert legacy_calls == [{'uid': 'uid-a', 'limit': 5000, 'offset': 0}]
    assert db.reads == []
    assert db.streams == []


def test_real_router_uses_actual_builder_for_enrolled_memory_read_and_never_calls_legacy(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    db = _ready_db()
    legacy_calls = []
    client = _route_client(monkeypatch, db, legacy_calls)

    response = client.get('/v3/memories?limit=1&offset=0')

    assert response.status_code == 200
    assert response.json()[0]['id'] == 'm1'
    assert response.json()[0]['layer'] == 'long_term'
    assert legacy_calls == []
    assert any(path == 'users/uid-a/memory_state/head' for path, _ in db.reads)
    assert db.streams == [('users/uid-a/v3_compatibility_projection_items', 12)]
    assert db.writes == []


def test_real_router_actual_builder_fail_closed_does_not_call_legacy(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    db = _ready_db()
    del db.docs['memory_control/global_read_gate']
    legacy_calls = []
    client = _route_client(monkeypatch, db, legacy_calls)

    response = client.get('/v3/memories?limit=1')

    assert response.status_code == 503
    assert response.json()['detail'] == 'infrastructure_failure'
    assert legacy_calls == []
    assert db.streams == []
    assert db.writes == []


def test_real_router_cursor_read_requires_cursor_secret_and_never_calls_legacy(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    monkeypatch.delenv('MEMORY_V3_CURSOR_SECRET', raising=False)
    db = _ready_db()
    legacy_calls = []
    client = _route_client(monkeypatch, db, legacy_calls)

    response = client.get('/v3/memories?cursor=opaque')

    assert response.status_code == 503
    assert response.json()['detail'] == 'infrastructure_failure'
    assert legacy_calls == []
    assert db.streams == []
    assert db.writes == []


def test_default_env_stays_disabled_and_does_not_read_firestore(monkeypatch):
    monkeypatch.delenv('MEMORY_MODE', raising=False)
    monkeypatch.delenv('MEMORY_ENABLED_USERS', raising=False)
    monkeypatch.delenv('MEMORY_V3_GET_ENABLED', raising=False)
    db = _ready_db()

    runtime = build_v3_production_runtime(uid='uid-a', db_client=db)

    assert runtime.enabled is False
    assert runtime.source_decision == 'disabled'
    assert db.reads == []


def test_route_specific_gate_is_default_false_even_when_global_memory_env_is_read(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    monkeypatch.delenv('MEMORY_V3_GET_ENABLED', raising=False)
    db = _ready_db()

    runtime = build_v3_production_runtime(uid='uid-a', db_client=db)

    assert runtime.enabled is False
    assert runtime.source_decision == 'disabled'
    assert db.reads == []


def test_route_specific_gate_requires_exact_true(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', '1')
    db = _ready_db()

    runtime = build_v3_production_runtime(uid='uid-a', db_client=db)

    assert runtime.enabled is False
    assert runtime.source_decision == 'disabled'
    assert db.reads == []


def test_non_read_modes_and_malformed_mode_do_not_enable_runtime(monkeypatch):
    for mode in ('shadow', 'write', 'unknown'):
        monkeypatch.setenv('MEMORY_MODE', mode)
        monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
        monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
        db = _ready_db()

        runtime = build_v3_production_runtime(uid='uid-a', db_client=db)

        assert runtime.enabled is False
        assert runtime.source_decision == 'disabled'
        assert db.reads == []


def test_non_enrolled_runtime_is_legacy_primary_without_firestore_read(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'other-user')
    db = _ready_db()

    runtime = build_v3_production_runtime(uid='uid-a', db_client=db)

    assert runtime.enabled is True
    assert runtime.source_decision == 'legacy_primary'
    assert db.reads == []


def test_whitelisted_ready_user_uses_real_memory_projection_and_never_writes(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    db = _ready_db()

    runtime = build_v3_production_runtime(uid='uid-a', db_client=db)
    response = runtime.service(V3ComposedRequestParams(limit=1, offset=0), runtime.adapters)

    assert runtime.enabled is True
    assert runtime.source_decision == 'memory_read'
    assert isinstance(response, V3ComposedResponse)
    assert response.http_status == 200
    assert response.body[0]['id'] == 'm1'
    assert response.body[0]['content'] == 'memory visible memory'
    assert db.writes == []
    assert any(path == 'users/uid-a/memory_control/state' for path, _ in db.reads)
    assert any(path == 'users/uid-a/memory_state/head' for path, _ in db.reads)
    assert any(path == 'users/uid-a/v3_compatibility_projection/state' for path, _ in db.reads)
    assert db.streams == [('users/uid-a/v3_compatibility_projection_items', 12)]


def test_trusted_state_head_mismatch_fails_before_projection_item_query(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    db = _ready_db()
    db.docs['users/uid-a/memory_state/head'] = _state_head(account_generation=8)

    runtime = build_v3_production_runtime(uid='uid-a', db_client=db)
    response = compose_v3_get(V3ComposedRequestParams(limit=1), runtime.adapters)

    assert response.http_status == 503
    assert response.public_error == 'infrastructure_failure'
    assert db.streams == []
    assert db.writes == []


def test_enrolled_unavailable_db_fails_closed_without_legacy_fallback(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')

    runtime = build_v3_production_runtime(uid='uid-a', db_client=None)
    response = compose_v3_get(V3ComposedRequestParams(limit=1), runtime.adapters)

    assert runtime.enabled is True
    assert runtime.source_decision == 'memory_read'
    assert response.http_status == 503
    assert response.public_error == 'infrastructure_failure'


def test_missing_global_gate_for_whitelisted_read_mode_fails_closed_no_legacy_fallback(monkeypatch):
    monkeypatch.setenv('MEMORY_MODE', 'read')
    monkeypatch.setenv('MEMORY_V3_GET_ENABLED', 'true')
    monkeypatch.setenv('MEMORY_ENABLED_USERS', 'uid-a')
    db = _ready_db()
    del db.docs['memory_control/global_read_gate']

    runtime = build_v3_production_runtime(uid='uid-a', db_client=db)
    response = compose_v3_get(V3ComposedRequestParams(limit=1), runtime.adapters)

    assert runtime.enabled is True
    assert runtime.source_decision == 'memory_read'
    assert response.http_status == 503
    assert response.public_error == 'infrastructure_failure'
    assert db.streams == []
    assert db.writes == []
