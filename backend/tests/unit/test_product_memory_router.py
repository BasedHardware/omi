import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


class _HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _APIRouter:
    def __init__(self):
        self.routes = []

    def get(self, path, **kwargs):
        def decorator(func):
            self.routes.append(("GET", path, kwargs, func))
            return func

        return decorator

    def post(self, path, **kwargs):
        def decorator(func):
            self.routes.append(("POST", path, kwargs, func))
            return func

        return decorator


def _identity(default=None, **_kwargs):
    return default


fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.APIRouter = _APIRouter
fastapi_stub.Depends = _identity
fastapi_stub.HTTPException = _HTTPException
fastapi_stub.Query = _identity
fastapi_stub.Request = type("Request", (), {})
auth_stub = types.ModuleType("utils.other.endpoints")
auth_stub.get_current_user_uid = lambda: "u1"

import pytest

from tests.unit.memory_import_isolation import (
    install_memory_product_router_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

_ROUTER_STUB_NAMES = (
    "fastapi",
    "database._client",
    "database.vector_db",
    "utils.other.endpoints",
    "routers.memory_product",
)


@pytest.fixture(scope="module", autouse=True)
def _memory_product_router_import_isolation():
    saved = snapshot_sys_modules(_ROUTER_STUB_NAMES)
    for name in ("routers.memory_product", "routers.memory_product"):
        sys.modules.pop(name, None)
    existing_fastapi = sys.modules.get("fastapi")
    if existing_fastapi is not None and getattr(existing_fastapi, "APIRouter", None) is not fastapi_stub.APIRouter:
        sys.modules.pop("fastapi", None)
    install_memory_product_router_stubs(fastapi_stub, auth_stub)
    import routers.memory_product as memory_product
    import routers.memory_product as memory_product

    globals()["memory_product"] = memory_product
    globals()["memory_product"] = memory_product
    yield
    restore_sys_modules(saved)
    for name in ("routers.memory_product", "routers.memory_product"):
        sys.modules.pop(name, None)
    globals()["memory_product"] = None
    globals()["memory_product"] = None


from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS

memory_product = None  # populated by _memory_product_router_import_isolation
memory_product = None  # canonical implementation module for monkeypatch targets


class _Snapshot:
    def __init__(self, data=None, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return dict(self._data or {})


class _CollectionRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def stream(self):
        prefix = f'{self.path}/'
        snapshots = []
        for path, data in sorted(self._db_client.docs.items()):
            if path.startswith(prefix) and '/' not in path[len(prefix) :]:
                snapshots.append(_Snapshot(data))
        return snapshots


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.collection_paths = []
        self.document_paths = []

    def collection(self, path):
        self.collection_paths.append(path)
        return _CollectionRef(self, path)

    def document(self, path):
        self.document_paths.append(path)
        return _DocumentRef(self, path)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self):
        data = self._db_client.docs.get(self.path)
        return _Snapshot(data, exists=data is not None)

    def set(self, data):
        self._db_client.docs[self.path] = dict(data)


class _VectorCandidateResult:
    def __init__(self, hits, rejected_count=0):
        self.hits = hits
        self.rejected_count = rejected_count


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers concise product memory endpoints.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, now=None, captured_at=None, content=None, **overrides):
    now = now or datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    captured_at = captured_at or (now - timedelta(days=1))
    data = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': tier,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.processed,
        'content': content or f'{memory_id} coffee preference',
        'evidence': [_evidence(f'{memory_id}-source')],
        'source_state': SourceState.active,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': captured_at,
        'updated_at': captured_at,
        'expires_at': (
            captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS) if tier == MemoryTier.short_term else None
        ),
        'ledger_commit_id': 'commit-1' if tier == MemoryTier.long_term else None,
        'ledger_sequence': 1 if tier == MemoryTier.long_term else None,
        'item_revision': 1,
        'source_commit_id': f'source-commit-{memory_id}',
        'content_hash': f'content-hash-{memory_id}',
        'account_generation': 3,
    }
    data.update(overrides)
    return MemoryItem(**data)


def _stored_item(item):
    return item.model_dump(mode='json')


def test_product_router_registers_default_memory_search_route():
    assert any(
        method == "GET" and path == "/memory/search" for method, path, _kwargs, _func in memory_product.router.routes
    )


def test_product_router_registers_capability_gated_archive_search_route():
    assert any(
        method == "GET" and path == "/memory/archive/search"
        for method, path, _kwargs, _func in memory_product.router.routes
    )


def test_product_router_registers_default_memory_vector_search_route():
    assert any(
        method == "GET" and path == "/memory/vector/search"
        for method, path, _kwargs, _func in memory_product.router.routes
    )


def test_product_router_exposes_only_canonical_memory_paths():
    memory_paths = {
        path
        for method, path, _kwargs, _func in memory_product.router.routes
        if isinstance(path, str) and path.startswith("/memory/")
    }
    assert memory_paths == {
        "/memory/search",
        "/memory/vector/search",
        "/memory/archive/search",
    }


def test_main_registers_neutral_product_memory_router():
    main_py = os.path.join(os.path.dirname(__file__), "..", "..", "main.py")
    with open(main_py, encoding="utf-8") as handle:
        contents = handle.read()

    assert "memory_product" in contents
    assert "app.include_router(memory_product.router)" in contents
    legacy_router_import = "v" + "17_memory_product"
    assert legacy_router_import not in contents


def _global_read_gate_doc(enabled=True, kill_switch=False):
    return {'memory_reads_enabled': enabled, 'kill_switch_active': kill_switch}


def _global_read_gate_path():
    return memory_product.GLOBAL_READ_GATE_PATH


def test_product_search_endpoint_uses_default_policy_and_excludes_stale_short_term_and_archive(monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    db_client = _FirestoreFake(
        {
            _global_read_gate_path(): _global_read_gate_doc(),
            'users/u1/memory_control/state': {
                'schema_version': 1,
                'uid': 'u1',
                'mode': 'read',
                'fallback_projection_ready': True,
                'vector_projection_commit_id': 'projection-1',
                'account_generation': 3,
                'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                'grants': {'omi_chat': {'default_memory': True}},
            },
            **{
                f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
                for item in [stale_short_term, archive, fresh_short_term, long_term]
            },
        }
    )
    monkeypatch.setattr(memory_product, "db", db_client)
    monkeypatch.setattr(memory_product, "_current_time", lambda: now)

    response = memory_product.search_product_memory(query='coffee', limit=25, offset=0, uid='u1')

    assert db_client.document_paths == [_global_read_gate_path(), 'users/u1/memory_control/state']
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['memory_id'] for item in response['items']] == ['fresh-short-term', 'long-term']
    assert response['uid'] == 'u1'
    assert response['query'] == 'coffee'
    assert response['total_count'] == 2
    assert response['returned_count'] == 2
    assert response['limit'] == 25
    assert response['offset'] == 0
    assert response['policy']['consumer'] == 'omi_chat'
    assert response['policy']['app_has_default_memory_grant'] is True
    assert response['policy']['archive_capability'] is False
    assert response['archive_default_visible'] is False


def test_product_routes_reject_global_kill_switch_before_per_user_rollout_vector_or_memory_reads(monkeypatch):
    db_client = _FirestoreFake({_global_read_gate_path(): _global_read_gate_doc(enabled=True, kill_switch=True)})
    vector_query = MagicMock()
    monkeypatch.setattr(memory_product, "db", db_client)
    monkeypatch.setattr(memory_product, "fetch_default_product_memory_search", MagicMock())
    monkeypatch.setattr(memory_product, "fetch_archive_product_memory_search", MagicMock())

    route_calls = [
        lambda: memory_product.search_product_memory(query='coffee', limit=25, offset=0, uid='u1'),
        lambda: memory_product.search_vector_memory(query='coffee', limit=10, uid='u1', vector_query=vector_query),
        lambda: memory_product.search_archive_memory(
            query='coffee', limit=25, offset=0, include_archive=True, uid='u1'
        ),
    ]

    for call_route in route_calls:
        try:
            call_route()
        except _HTTPException as exc:
            assert exc.status_code == 403
            assert exc.detail['read_decision'] == 'DENY_MEMORY'
            assert exc.detail['fallback_reason'] == 'global_memory_read_kill_switch_active'
        else:
            raise AssertionError('expected global memory read kill switch to deny product route')

    assert db_client.document_paths == [_global_read_gate_path(), _global_read_gate_path(), _global_read_gate_path()]
    assert db_client.collection_paths == []
    vector_query.assert_not_called()
    memory_product.fetch_default_product_memory_search.assert_not_called()
    memory_product.fetch_archive_product_memory_search.assert_not_called()


def test_product_routes_reject_missing_global_gate_before_per_user_rollout_vector_or_memory_reads(monkeypatch):
    db_client = _FirestoreFake({'users/u1/memory_control/state': {'uid': 'u1', 'mode': 'read'}})
    vector_query = MagicMock()
    monkeypatch.setattr(memory_product, "db", db_client)
    monkeypatch.setattr(memory_product, "fetch_default_product_memory_search", MagicMock())
    monkeypatch.setattr(memory_product, "fetch_archive_product_memory_search", MagicMock())

    route_calls = [
        lambda: memory_product.search_product_memory(query='coffee', limit=25, offset=0, uid='u1'),
        lambda: memory_product.search_vector_memory(query='coffee', limit=10, uid='u1', vector_query=vector_query),
        lambda: memory_product.search_archive_memory(
            query='coffee', limit=25, offset=0, include_archive=True, uid='u1'
        ),
    ]

    for call_route in route_calls:
        try:
            call_route()
        except _HTTPException as exc:
            assert exc.status_code == 403
            assert exc.detail['read_decision'] == 'DENY_MEMORY'
            assert exc.detail['fallback_reason'] == 'missing_global_read_gate'
        else:
            raise AssertionError('expected missing global memory read gate to deny product route')

    assert db_client.document_paths == [_global_read_gate_path(), _global_read_gate_path(), _global_read_gate_path()]
    assert db_client.collection_paths == []
    vector_query.assert_not_called()
    memory_product.fetch_default_product_memory_search.assert_not_called()
    memory_product.fetch_archive_product_memory_search.assert_not_called()


def test_product_search_endpoint_rejects_disabled_missing_malformed_and_no_grant_before_memory_items(monkeypatch):
    cases = [
        ({}, 'missing_rollout_state'),
        (
            {
                'users/u1/memory_control/state': {
                    'schema_version': 1,
                    'uid': 'u1',
                    'mode': 'off',
                    'grants': {'omi_chat': {'default_memory': True}},
                }
            },
            'memory_reads_disabled',
        ),
        (
            {'users/u1/memory_control/state': {'schema_version': 1, 'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}},
            'malformed_rollout_state',
        ),
        (
            {
                'users/u1/memory_control/state': {
                    'schema_version': 1,
                    'uid': 'u1',
                    'mode': 'read',
                    'fallback_projection_ready': True,
                    'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                    'grants': {'omi_chat': {}},
                }
            },
            'missing_chat_default_memory_grant',
        ),
    ]
    monkeypatch.setattr(memory_product, "fetch_default_product_memory_search", MagicMock())

    for docs, expected_reason in cases:
        db_client = _FirestoreFake({_global_read_gate_path(): _global_read_gate_doc(), **docs})
        monkeypatch.setattr(memory_product, "db", db_client)
        try:
            memory_product.search_product_memory(query='coffee', limit=25, offset=0, uid='u1')
        except _HTTPException as exc:
            assert exc.status_code == 403
            assert exc.detail['read_decision'] == 'DENY_MEMORY'
            assert exc.detail['fallback_reason'] == expected_reason
        else:
            raise AssertionError(f'expected product search to fail closed for {expected_reason}')

        assert db_client.document_paths == [_global_read_gate_path(), 'users/u1/memory_control/state']
        assert db_client.collection_paths == []

    memory_product.fetch_default_product_memory_search.assert_not_called()


def test_product_search_endpoint_rejects_invalid_pagination(monkeypatch):
    monkeypatch.setattr(memory_product, "fetch_default_product_memory_search", MagicMock())

    for kwargs in ({"limit": 0, "offset": 0}, {"limit": 501, "offset": 0}, {"limit": 25, "offset": -1}):
        try:
            memory_product.search_product_memory(query='coffee', uid='u1', **kwargs)
        except _HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"expected invalid pagination failure for {kwargs}")

    memory_product.fetch_default_product_memory_search.assert_not_called()


def test_archive_search_endpoint_rejects_missing_archive_intent_before_firestore(monkeypatch):
    monkeypatch.setattr(memory_product, "fetch_archive_product_memory_search", MagicMock())

    try:
        memory_product.search_archive_memory(query='coffee', limit=25, offset=0, include_archive=False, uid='u1')
    except _HTTPException as exc:
        assert exc.status_code == 403
        assert 'archive capability' in exc.detail
    else:
        raise AssertionError('expected archive route to reject missing capability')

    memory_product.fetch_archive_product_memory_search.assert_not_called()


def test_archive_search_endpoint_rejects_missing_malformed_disabled_and_no_server_archive_grant_before_memory_items(
    monkeypatch,
):
    cases = [
        ({}, 'missing_rollout_state'),
        (
            {
                'users/u1/memory_control/state': {
                    'schema_version': 1,
                    'uid': 'u1',
                    'mode': 'read',
                    'fallback_projection_ready': True,
                    'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                    'grants': {'omi_chat': {'default_memory': True}},
                }
            },
            'missing_chat_archive_capability',
        ),
        (
            {
                'users/u1/memory_control/state': {
                    'schema_version': 1,
                    'uid': 'u1',
                    'mode': 'read',
                    'fallback_projection_ready': True,
                    'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                    'grants': {'omi_chat': {'default_memory': True, 'archive': 'yes'}},
                }
            },
            'malformed_archive_capability',
        ),
        (
            {
                'users/u1/memory_control/state': {
                    'schema_version': 1,
                    'uid': 'u1',
                    'mode': 'off',
                    'grants': {'omi_chat': {'default_memory': True, 'archive': True}},
                }
            },
            'memory_reads_disabled',
        ),
        (
            {
                'users/u1/memory_control/state': {
                    'schema_version': 1,
                    'uid': 'u1',
                    'mode': 'read',
                    'fallback_projection_ready': True,
                    'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                    'grants': {'omi_chat': {'archive': True}},
                }
            },
            'missing_chat_default_memory_grant',
        ),
    ]
    monkeypatch.setattr(memory_product, "fetch_archive_product_memory_search", MagicMock())

    for docs, expected_reason in cases:
        db_client = _FirestoreFake({_global_read_gate_path(): _global_read_gate_doc(), **docs})
        monkeypatch.setattr(memory_product, "db", db_client)
        try:
            memory_product.search_archive_memory(query='coffee', limit=25, offset=0, include_archive=True, uid='u1')
        except _HTTPException as exc:
            assert exc.status_code == 403
            assert exc.detail['read_decision'] == 'DENY_MEMORY'
            assert exc.detail['fallback_reason'] == expected_reason
            assert exc.detail['archive_capability'] is False
        else:
            raise AssertionError(f'expected archive route to fail closed for {expected_reason}')

        assert db_client.document_paths == [_global_read_gate_path(), 'users/u1/memory_control/state']
        assert db_client.collection_paths == []

    memory_product.fetch_archive_product_memory_search.assert_not_called()


def test_archive_search_endpoint_requires_explicit_intent_and_server_capability_and_only_returns_archive(monkeypatch):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    db_client = _FirestoreFake(
        {
            _global_read_gate_path(): _global_read_gate_doc(),
            'users/u1/memory_control/state': {
                'schema_version': 1,
                'uid': 'u1',
                'mode': 'read',
                'fallback_projection_ready': True,
                'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                'grants': {'omi_chat': {'default_memory': True, 'archive': True}},
            },
            **{
                f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
                for item in [fresh_short_term, long_term, archive]
            },
        }
    )
    monkeypatch.setattr(memory_product, "db", db_client)
    monkeypatch.setattr(memory_product, "_current_time", lambda: now)

    response = memory_product.search_archive_memory(query='coffee', limit=25, offset=0, include_archive=True, uid='u1')

    assert db_client.document_paths == [_global_read_gate_path(), 'users/u1/memory_control/state']
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['memory_id'] for item in response['items']] == ['archive']
    assert response['policy']['consumer'] == 'omi_chat'
    assert response['policy']['archive_capability'] is True
    assert response['rollout']['archive_capability'] is True
    assert response['archive_capability_required'] is True
    assert response['archive_capability_granted'] is True
    assert response['archive_default_visible'] is False


def test_vector_search_endpoint_requires_persisted_rollout_before_vector_or_memory_item_reads(monkeypatch):
    db_client = _FirestoreFake({_global_read_gate_path(): _global_read_gate_doc()})
    vector_query = MagicMock()
    monkeypatch.setattr(memory_product, "db", db_client)

    try:
        memory_product.search_vector_memory(query='coffee', limit=10, uid='u1', vector_query=vector_query)
    except _HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail['fallback_reason'] == 'missing_rollout_state'
    else:
        raise AssertionError('expected disabled persisted rollout to fail closed')

    assert db_client.document_paths == [_global_read_gate_path(), 'users/u1/memory_control/state']
    assert db_client.collection_paths == []
    vector_query.assert_not_called()


def test_vector_search_endpoint_uses_persisted_default_policy_and_excludes_stale_short_term_and_archive(monkeypatch):
    from models.memory_search_gateway import SearchMode, SearchVectorHit

    now = datetime.now(timezone.utc).replace(microsecond=0)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    db_client = _FirestoreFake(
        {
            _global_read_gate_path(): _global_read_gate_doc(),
            'users/u1/memory_control/state': {
                'schema_version': 1,
                'uid': 'u1',
                'mode': 'read',
                'fallback_projection_ready': True,
                'vector_projection_commit_id': 'projection-1',
                'account_generation': 3,
                'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                'grants': {'omi_chat': {'default_memory': True}},
            },
            **{
                f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
                for item in [stale_short_term, archive, fresh_short_term, long_term]
            },
        }
    )
    monkeypatch.setattr(memory_product, "db", db_client)

    def hit(item, score):
        return SearchVectorHit(
            memory_id=item.memory_id,
            score=score,
            projection_commit_id='projection-1',
            vector_updated_at=item.updated_at + timedelta(minutes=1),
            uid=item.uid,
            account_generation=item.account_generation,
            item_revision=item.item_revision,
            source_commit_id=item.source_commit_id,
            content_hash=item.content_hash,
        )

    vector_calls = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(
            hits=[hit(stale_short_term, 0.99), hit(archive, 0.98), hit(long_term, 0.90), hit(fresh_short_term, 0.80)],
            rejected_count=1,
        )

    response = memory_product.search_vector_memory(query='coffee', limit=10, uid='u1', vector_query=fake_vector_query)

    assert db_client.document_paths == [
        _global_read_gate_path(),
        'users/u1/memory_control/state',
        'users/u1/memory_items/stale-short-term',
        'users/u1/memory_items/archive',
        'users/u1/memory_items/long-term',
        'users/u1/memory_items/fresh-short-term',
    ]
    assert db_client.collection_paths == []
    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 30}]
    assert [item['memory_id'] for item in response['items']] == ['long-term', 'fresh-short-term']
    assert response['scores_by_memory_id'] == {'long-term': 0.9, 'fresh-short-term': 0.8}
    assert response['decisions']['stale-short-term'] == 'access_denied'
    assert response['decisions']['archive'] == 'access_denied'
    assert response['policy']['consumer'] == 'omi_chat'
    assert response['policy']['archive_capability'] is False
    assert response['rollout']['enabled'] is True
    assert response['vector_rejected_count'] == 1
    assert response['archive_default_visible'] is False


def test_vector_search_endpoint_does_not_persist_repair_outbox_without_server_flag(monkeypatch):
    from models.memory_search_gateway import SearchMode, SearchVectorHit

    now = datetime.now(timezone.utc).replace(microsecond=0)
    stale_projection = _memory_item('stale-projection', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake(
        {
            _global_read_gate_path(): _global_read_gate_doc(),
            'users/u1/memory_control/state': {
                'schema_version': 1,
                'uid': 'u1',
                'mode': 'read',
                'fallback_projection_ready': True,
                'vector_projection_commit_id': 'projection-1',
                'account_generation': 3,
                'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                'grants': {'omi_chat': {'default_memory': True}},
            },
            f'users/u1/memory_items/{stale_projection.memory_id}': _stored_item(stale_projection),
        }
    )
    monkeypatch.setattr(memory_product, "db", db_client)

    def fake_vector_query(uid, query, *, mode, limit):
        assert mode == SearchMode.default
        return _VectorCandidateResult(
            hits=[
                SearchVectorHit(
                    memory_id=stale_projection.memory_id,
                    score=0.99,
                    projection_commit_id='projection-old',
                    vector_updated_at=stale_projection.updated_at + timedelta(minutes=1),
                    vector_id='memvec:stale-projection',
                    uid=stale_projection.uid,
                    account_generation=stale_projection.account_generation,
                    item_revision=stale_projection.item_revision,
                    source_commit_id=stale_projection.source_commit_id,
                    content_hash=stale_projection.content_hash,
                )
            ]
        )

    response = memory_product.search_vector_memory(query='coffee', limit=10, uid='u1', vector_query=fake_vector_query)

    assert response['items'] == []
    assert response['repair_purge_outbox_record_count'] == 1
    assert response['rollout']['vector_repair_outbox_enabled'] is False
    assert not any(path.startswith('users/u1/memory_outbox/') for path in db_client.docs)


def test_vector_search_endpoint_persists_repair_outbox_only_with_server_flag(monkeypatch):
    from models.memory_search_gateway import SearchMode, SearchVectorHit

    now = datetime.now(timezone.utc).replace(microsecond=0)
    stale_projection = _memory_item('stale-projection', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake(
        {
            _global_read_gate_path(): _global_read_gate_doc(),
            'users/u1/memory_control/state': {
                'schema_version': 1,
                'uid': 'u1',
                'mode': 'read',
                'fallback_projection_ready': True,
                'vector_projection_commit_id': 'projection-1',
                'vector_repair_outbox_enabled': True,
                'account_generation': 3,
                'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
                'grants': {'omi_chat': {'default_memory': True}},
            },
            f'users/u1/memory_items/{stale_projection.memory_id}': _stored_item(stale_projection),
        }
    )
    monkeypatch.setattr(memory_product, "db", db_client)

    def fake_vector_query(uid, query, *, mode, limit):
        assert mode == SearchMode.default
        return _VectorCandidateResult(
            hits=[
                SearchVectorHit(
                    memory_id=stale_projection.memory_id,
                    score=0.99,
                    projection_commit_id='projection-old',
                    vector_updated_at=stale_projection.updated_at + timedelta(minutes=1),
                    vector_id='memvec:stale-projection',
                    uid=stale_projection.uid,
                    account_generation=stale_projection.account_generation,
                    item_revision=stale_projection.item_revision,
                    source_commit_id=stale_projection.source_commit_id,
                    content_hash=stale_projection.content_hash,
                )
            ]
        )

    response = memory_product.search_vector_memory(query='coffee', limit=10, uid='u1', vector_query=fake_vector_query)

    record = response['repair_purge_outbox_records'][0]
    outbox_path = f"users/u1/memory_outbox/{record['record_id']}"
    assert response['items'] == []
    assert response['rollout']['vector_repair_outbox_enabled'] is True
    assert record['outbox_path'] == outbox_path
    assert db_client.docs[outbox_path]['record_id'] == record['record_id']
    assert db_client.docs[outbox_path]['idempotency_key'] == record['record_id']
