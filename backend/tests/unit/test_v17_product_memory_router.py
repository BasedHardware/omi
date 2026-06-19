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


def _identity(default=None, **_kwargs):
    return default


fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.APIRouter = _APIRouter
fastapi_stub.Depends = _identity
fastapi_stub.HTTPException = _HTTPException
fastapi_stub.Query = _identity
sys.modules["fastapi"] = fastapi_stub
sys.modules["database._client"] = MagicMock()

auth_stub = types.ModuleType("utils.other.endpoints")
auth_stub.get_current_user_uid = lambda: "u1"
sys.modules["utils.other.endpoints"] = auth_stub

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_product_memory import MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS

import routers.v17_memory_product as v17_memory_product


class _Snapshot:
    def __init__(self, data=None):
        self._data = data

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

    def collection(self, path):
        self.collection_paths.append(path)
        return _CollectionRef(self, path)


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
        'processing_state': ProcessingState.pending if tier == MemoryTier.short_term else ProcessingState.processed,
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
    }
    data.update(overrides)
    return V17MemoryItem(**data)


def _stored_item(item):
    return item.model_dump(mode='json')


def test_product_router_registers_concrete_default_v17_search_route():
    assert any(
        method == "GET" and path == "/v17/memory/search"
        for method, path, _kwargs, _func in v17_memory_product.router.routes
    )


def test_main_registers_v17_product_memory_router():
    main_py = os.path.join(os.path.dirname(__file__), "..", "..", "main.py")
    with open(main_py, encoding="utf-8") as handle:
        contents = handle.read()

    assert "v17_memory_product" in contents
    assert "app.include_router(v17_memory_product.router)" in contents


def test_product_search_endpoint_uses_default_policy_and_excludes_stale_short_term_and_archive(monkeypatch):
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term', now=now, captured_at=now - timedelta(days=45), content='coffee stale short term'
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [stale_short_term, archive, fresh_short_term, long_term]
        }
    )
    monkeypatch.setattr(v17_memory_product, "db", db_client)
    monkeypatch.setattr(v17_memory_product, "_current_time", lambda: now)

    response = v17_memory_product.search_v17_product_memory(query='coffee', limit=25, offset=0, uid='u1')

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


def test_product_search_endpoint_rejects_invalid_pagination(monkeypatch):
    monkeypatch.setattr(v17_memory_product, "fetch_default_product_memory_search", MagicMock())

    for kwargs in ({"limit": 0, "offset": 0}, {"limit": 501, "offset": 0}, {"limit": 25, "offset": -1}):
        try:
            v17_memory_product.search_v17_product_memory(query='coffee', uid='u1', **kwargs)
        except _HTTPException as exc:
            assert exc.status_code == 400
        else:
            raise AssertionError(f"expected invalid pagination failure for {kwargs}")

    v17_memory_product.fetch_default_product_memory_search.assert_not_called()
