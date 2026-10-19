"""Desktop↔backend contracts: GET include_archive and PATCH /v3/memories/{id}/read."""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    MAX_MEMORY_ARGUMENTS_JSON_BYTES,
    MemoryItem,
    MemoryItemStatus,
    MemoryLayer,
    ProcessingState,
)
from utils.memory.canonical_memory_adapter import memory_item_to_memorydb, read_canonical_memories
from utils.memory.memory_service import CanonicalMemoryBackend, truncate_locked_memory_preview
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS

_STUB = (
    "database",
    "utils",
    "firebase_admin",
    "google",
    "pinecone",
    "typesense",
    "opuslib",
    "pydub",
    "pusher",
    "modal",
    "ulid",
    "langchain",
    "langchain_core",
    "stripe",
    "openai",
    "anthropic",
    "redis",
    "sentry_sdk",
    "requests",
)


def _is_stubbed_name(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in _STUB)


def _snapshot_stubbed_modules():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear_stubbed_modules():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore_stubbed_modules(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


def _install_python_multipart_stub() -> bool:
    if "python_multipart" in sys.modules:
        return False
    if importlib.util.find_spec("python_multipart") is not None:
        return False
    mod = types.ModuleType("python_multipart")
    mod.__version__ = "0.0.20"
    sys.modules["python_multipart"] = mod
    return True


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in _STUB):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


def _load_memories_router():
    finder = _Finder()
    snapshot = _snapshot_stubbed_modules()
    _clear_stubbed_modules()
    remove_multipart = _install_python_multipart_stub()
    sys.meta_path.insert(0, finder)
    try:
        from routers import memories as mem_mod

        return mem_mod
    finally:
        sys.meta_path.remove(finder)
        _restore_stubbed_modules(snapshot)
        if remove_multipart:
            sys.modules.pop("python_multipart", None)


def _evidence(source_id: str = "src-1") -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=f"ev-{source_id}",
        source_id=source_id,
        source_type="conversation",
        source_version="v1",
        quote_refs=[{"text": "sample"}],
        content_hash="hash1",
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _item(
    memory_id: str,
    *,
    tier: MemoryLayer,
    content: str,
    updated_at: datetime,
    is_locked: bool = False,
    promotion: dict | None = None,
) -> MemoryItem:
    captured = updated_at - timedelta(hours=1)
    data = {
        "memory_id": memory_id,
        "uid": "uid-1",
        "version": 1,
        "tier": tier,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": content,
        "evidence": [_evidence(memory_id)],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": captured,
        "updated_at": updated_at,
        "expires_at": (
            captured + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS) if tier == MemoryLayer.short_term else None
        ),
        "ledger_commit_id": "commit-1" if tier in {MemoryLayer.long_term, MemoryLayer.archive} else None,
        "ledger_sequence": 1 if tier in {MemoryLayer.long_term, MemoryLayer.archive} else None,
        "promotion": promotion or ({"is_locked": True} if is_locked else None),
    }
    return MemoryItem(**data)


def test_read_canonical_memories_excludes_archive_unless_explicit(monkeypatch):
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    short = _item("mem-short", tier=MemoryLayer.short_term, content="short", updated_at=now)
    archive = _item("mem-archive", tier=MemoryLayer.archive, content="archived", updated_at=now - timedelta(days=1))
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
        lambda **_kwargs: [short, archive],
    )

    default_page = read_canonical_memories("uid-1", limit=10, offset=0, now=now)
    assert [memory.id for memory in default_page] == ["mem-short"]

    with_archive = read_canonical_memories("uid-1", limit=10, offset=0, include_archive=True, now=now)
    assert [memory.id for memory in with_archive] == ["mem-short", "mem-archive"]
    assert with_archive[1].memory_tier == MemoryLayer.archive


def test_memory_item_projection_preserves_canonical_arguments():
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    item = _item("mem-arguments", tier=MemoryLayer.long_term, content="Lives in Austin", updated_at=now)
    item = item.model_copy(
        update={
            "ledger_schema_version": "knowledge_ledger.v1",
            "arguments": {"location": "Austin", "aliases": ["ATX"]},
        }
    )

    projected = memory_item_to_memorydb(item)

    assert projected.arguments == {"location": "Austin", "aliases": ["ATX"]}
    projected.arguments["aliases"].append("Austin")
    assert item.arguments == {"location": "Austin", "aliases": ["ATX"]}

    oversized = item.model_copy(update={"arguments": {"detail": "x" * MAX_MEMORY_ARGUMENTS_JSON_BYTES}})
    assert memory_item_to_memorydb(oversized).arguments == {}


def test_include_archive_pagination_and_locked_privacy(monkeypatch):
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    locked_archive = _item(
        "mem-locked-archive",
        tier=MemoryLayer.archive,
        content="L" * 120,
        updated_at=now,
        is_locked=True,
    )
    newer_short = _item("mem-short", tier=MemoryLayer.short_term, content="short", updated_at=now + timedelta(hours=1))
    short_row = memory_item_to_memorydb(newer_short)
    locked_row = memory_item_to_memorydb(locked_archive)
    slots = [
        (short_row, (newer_short.updated_at, newer_short.memory_id)),
        (locked_row, (locked_archive.updated_at, locked_archive.memory_id)),
    ]

    def _forbid_full_fetch(**_kwargs):
        raise AssertionError("offset read must not stream the canonical collection")

    def _scan(_uid, **kwargs):
        assert kwargs.get("include_archive") is True
        return slots, True

    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
        _forbid_full_fetch,
    )
    monkeypatch.setattr("utils.memory.memory_service.read_canonical_scan_page", _scan)
    monkeypatch.setattr(
        "utils.memory.memory_service.fetch_authoritative_product_memory_items",
        _forbid_full_fetch,
        raising=False,
    )

    page = CanonicalMemoryBackend().read(
        "uid-1",
        limit=1,
        offset=0,
        include_archive=True,
        now=now + timedelta(hours=1),
    )
    assert [memory.id for memory in page] == ["mem-short"]

    second = CanonicalMemoryBackend().read(
        "uid-1",
        limit=1,
        offset=1,
        include_archive=True,
        now=now + timedelta(hours=1),
    )
    assert [memory.id for memory in second] == ["mem-locked-archive"]
    assert second[0].is_locked is True
    assert second[0].content.endswith("...")
    assert len(second[0].content) == 73


def test_get_memories_forwards_include_archive():
    mem_mod = _load_memories_router()
    service = MagicMock()
    service.read_page.return_value = types.SimpleNamespace(memories=[], next_cursor=None, truncated=False)
    scope_request = types.SimpleNamespace(device_scope="all", client_device_id=None)
    with (
        patch.object(mem_mod, "MemoryService", return_value=service),
        patch.object(mem_mod, "_resolve_get_memories_device_scope", return_value=scope_request),
        patch.object(mem_mod, "_validate_device_scope_request"),
    ):
        mem_mod.get_memories(
            response=MagicMock(),
            limit=50,
            offset=0,
            include_archive=True,
            uid="uid-1",
            device_scope="all",
            client_device_id=None,
            x_app_platform=None,
            x_device_id_hash=None,
        )
    assert service.read_page.call_args.kwargs["include_archive"] is True


def test_ledger_history_route_is_explicit_owner_scoped_and_bounded():
    mem_mod = _load_memories_router()
    service = MagicMock()
    service.read_ledger_history_page.return_value = types.SimpleNamespace(
        memories=(), truncated=True, scanned_count=501
    )
    budget = MagicMock(truncated=False)
    response_headers = {}

    def capture_response(values, _exposure, headers=None):
        response_headers.update(headers or {})
        return values

    with (
        patch.object(mem_mod, "MemoryService", return_value=service),
        patch.object(mem_mod, "list_read_budget_for_request", return_value=budget),
        patch.object(mem_mod, "memory_list_response", side_effect=capture_response),
    ):
        result = mem_mod.get_ledger_history(
            response=MagicMock(),
            request=None,
            limit=50,
            offset=2,
            uid="uid-1",
        )

    assert result == ()
    service.read_ledger_history_page.assert_called_once_with(
        "uid-1",
        limit=50,
        offset=2,
        budget=budget,
    )
    budget.observe.assert_called_once_with("truncated")
    assert response_headers[mem_mod.OMI_LIST_TRUNCATED_HEADER] == mem_mod.OMI_LIST_TRUNCATED_VALUE


def test_ledger_history_route_signs_and_consumes_keyset_cursor(monkeypatch):
    """A bounded history sentinel must resume after the raw provider row."""
    mem_mod = _load_memories_router()
    service = MagicMock()
    boundary = (datetime(2026, 8, 23, tzinfo=timezone.utc), 'history-boundary')
    service.read_ledger_history_page.return_value = types.SimpleNamespace(
        memories=(), truncated=True, scanned_count=501, next_start_after=boundary
    )
    response_headers = {}

    def capture_response(values, _exposure, headers=None):
        response_headers.clear()
        response_headers.update(headers or {})
        return values

    monkeypatch.setenv('MEMORY_V3_CURSOR_SECRET', 'history-cursor-test-secret')
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, 'list_read_budget_for_request', return_value=MagicMock(truncated=False)),
        patch.object(mem_mod, 'cursor_secret', return_value=b'history-cursor-test-secret'),
        patch.object(mem_mod, 'cursor_ttl_seconds', return_value=86_400),
        patch.object(mem_mod, 'memory_list_response', side_effect=capture_response),
    ):
        mem_mod.get_ledger_history(response=MagicMock(), request=None, limit=500, offset=0, uid='uid-1')
        cursor = response_headers[mem_mod._MEMORY_NEXT_CURSOR_HEADER]
        service.read_ledger_history_page.reset_mock()
        mem_mod.get_ledger_history(
            response=MagicMock(), request=None, limit=500, offset=500, cursor=cursor, uid='uid-1'
        )

    assert service.read_ledger_history_page.call_args.kwargs == {
        'limit': 500,
        'offset': 0,
        'budget': service.read_ledger_history_page.call_args.kwargs['budget'],
        'start_after': boundary,
    }


def test_update_memory_read_status_persists_through_service():
    mem_mod = _load_memories_router()
    service = MagicMock()
    memory = MagicMock()
    service.update_read_status.return_value = memory
    response = MagicMock()
    with (
        patch.object(mem_mod, "MemoryService", return_value=service),
        patch.object(mem_mod, "_validate_mutable_memory", return_value={"id": "mem-1"}),
        patch.object(mem_mod, "_memory_response", return_value=response) as memory_response,
    ):
        result = mem_mod.update_memory_read_status(
            memory_id="mem-1",
            request=mem_mod.MemoryReadStatusRequest(is_read=True, is_dismissed=True),
            uid="uid-1",
        )
    assert result is response
    service.update_read_status.assert_called_once_with(
        "uid-1",
        "mem-1",
        is_read=True,
        is_dismissed=True,
    )
    memory_response.assert_called_once_with(memory)


def test_update_memory_read_status_requires_a_field():
    mem_mod = _load_memories_router()
    with pytest.raises(Exception) as exc:
        mem_mod.update_memory_read_status(
            memory_id="mem-1",
            request=mem_mod.MemoryReadStatusRequest(),
            uid="uid-1",
        )
    assert getattr(exc.value, "status_code", None) == 422


def test_memory_item_to_memorydb_round_trips_read_dismiss_state():
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    item = _item(
        "mem-tip",
        tier=MemoryLayer.short_term,
        content="tip",
        updated_at=now,
        promotion={"tags": ["tips"], "is_read": True, "is_dismissed": True},
    )
    memory = memory_item_to_memorydb(item)
    assert memory.is_read is True
    assert memory.is_dismissed is True
    assert truncate_locked_memory_preview(memory).content == "tip"


def test_memory_item_to_memorydb_preserves_canonical_alias_for_portability():
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    item = _item(
        "alias-row",
        tier=MemoryLayer.long_term,
        content="legacy alias",
        updated_at=now,
    ).model_copy(update={"canonical_memory_id": "canonical-row"})

    projected = memory_item_to_memorydb(item)

    assert projected.canonical_memory_id == "canonical-row"
    assert projected.model_dump(mode="json")["canonical_memory_id"] == "canonical-row"


@pytest.mark.parametrize('asynchronous', [False, True])
def test_memories_router_503_structured_fields_and_no_sensitive_details(asynchronous, caplog):
    import hashlib
    from fastapi import APIRouter, FastAPI, HTTPException
    from fastapi.testclient import TestClient

    mem_mod = _load_memories_router()

    def fail(uid: str):
        raise HTTPException(503, 'sensitive details') from ValueError('sensitive memory content')

    async def fail_async(uid: str):
        fail(uid)

    app = FastAPI()
    router = APIRouter(route_class=mem_mod.MemoriesRoute)
    router.add_api_route('/v3/memories', fail_async if asynchronous else fail)
    parent = APIRouter()
    parent.include_router(router)
    app.include_router(parent)
    with TestClient(app) as client:
        result = client.get('/v3/memories', params={'uid': 'private-uid'})
    assert result.status_code == 503
    records = [r for r in caplog.records if getattr(r, 'event', None) == 'memories_503']
    assert len(records) == 1
    record = records[0]
    assert record.endpoint == '/v3/memories'
    assert record.uid_hashed == hashlib.sha256(b'private-uid').hexdigest()[:16]
    assert record.exception_class == 'ValueError'
    assert record.elapsed_ms >= 0
    assert 'private-uid' not in record.getMessage()
    assert 'sensitive' not in record.getMessage()


@pytest.mark.parametrize('params', [{'cursor': 'opaque'}, {'offset': 10}, {}])
def test_get_memories_http_503_logs_cursor_offset_and_first_page_failure(params, caplog):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    mem_mod = _load_memories_router()
    service = MagicMock()
    service.read_page.side_effect = HTTPException(503, 'memory unavailable')
    service.read.side_effect = HTTPException(503, 'memory unavailable')

    class BackingStoreUnavailable(HTTPException):
        pass

    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    app = FastAPI()
    app.include_router(mem_mod.router)
    route = next(r for r in app.routes if getattr(r, 'path', None) == '/v3/memories' and 'GET' in r.methods)
    for dependency in route.dependant.dependencies:
        app.dependency_overrides[dependency.call] = lambda: 'private-uid'
    with (
        patch.object(mem_mod, 'MemoryService', return_value=service),
        patch.object(mem_mod, 'MemoryBackingStoreUnavailable', BackingStoreUnavailable),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'list_read_budget_for_request', return_value=MagicMock(truncated=False)),
        TestClient(app) as client,
    ):
        result = client.get('/v3/memories', params=params)
    assert result.status_code == 503
    records = [r for r in caplog.records if getattr(r, 'event', None) == 'memories_503']
    assert len(records) == 1
    assert records[0].endpoint == '/v3/memories'
    assert records[0].uid_hashed != 'unknown'


def test_memory_router_cursor_offset_fallback_uses_at_most_two_whole_operation_attempts(monkeypatch):
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from google.api_core.exceptions import ServiceUnavailable
    from utils.memory import read_resilience
    from utils.other.list_budget import ListReadBudget

    mem_mod = _load_memories_router()
    calls = []
    now = [10.0]
    clock = lambda: now[0]
    bucket = read_resilience.RetryAllowance(clock=clock)
    policy_class = read_resilience.MemoryReadResilience
    monkeypatch.setattr(
        read_resilience,
        'MemoryReadResilience',
        lambda: policy_class(clock=clock, sleep=lambda seconds: now.__setitem__(0, now[0] + seconds), allowance=bucket),
    )

    class Unavailable(HTTPException):
        stream = 'canonical'

    def fail(operation):
        calls.append(operation)
        raise Unavailable(503, 'Canonical memory unavailable') from ServiceUnavailable('temporary')

    class Service:
        def __init__(self, **kwargs):
            pass

        @read_resilience.resilient_memory_read
        def read_page(self, uid, **kwargs):
            return fail('read_page')

        @read_resilience.resilient_memory_read
        def read(self, uid, **kwargs):
            return fail('read')

    app = FastAPI()
    app.include_router(mem_mod.router)
    route = next(r for r in app.routes if getattr(r, 'path', None) == '/v3/memories' and 'GET' in r.methods)
    for dependency in route.dependant.dependencies:
        app.dependency_overrides[dependency.call] = lambda: 'private-uid'
    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    budget = ListReadBudget(deadline_monotonic=12, clock=clock)
    with (
        patch.object(mem_mod, 'MemoryService', Service),
        patch.object(mem_mod, 'MemoryBackingStoreUnavailable', Unavailable),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(mem_mod, 'list_read_budget_for_request', return_value=budget),
        TestClient(app) as client,
    ):
        result = client.get('/v3/memories')
    assert result.status_code == 503
    assert calls == ['read_page', 'read_page']  # previously two page + two offset calls
    assert budget.remaining_seconds > 1.8  # time budget alone WOULD admit offset retries


def _exercise_router_admission(monkeypatch, *, concurrent_requests):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from google.api_core.exceptions import ServiceUnavailable
    from utils.memory import read_resilience
    from utils.other.list_budget import ListReadBudget

    mem_mod = _load_memories_router()
    clock = lambda: 10.0  # no refill during the concurrent burst
    bucket = read_resilience.RetryAllowance(clock=clock)
    monkeypatch.setattr(read_resilience, '_retry_allowance', bucket)
    policy_class = read_resilience.MemoryReadResilience
    monkeypatch.setattr(
        read_resilience,
        'MemoryReadResilience',
        lambda: policy_class(clock=clock, sleep=lambda _: None, jitter=lambda *_: 0),
    )
    calls = []
    entries = []
    lock = threading.Lock()
    start = threading.Barrier(concurrent_requests)
    pages_started = threading.Event()
    release_pages = threading.Event()

    class Unavailable(HTTPException):
        stream = 'canonical'

    def fail(operation):
        with lock:
            calls.append(operation)
            if calls.count('read_page') == 8:
                pages_started.set()
        if concurrent_requests > 1:
            assert release_pages.wait(timeout=10)
        raise Unavailable(503, 'Canonical memory unavailable') from ServiceUnavailable('temporary')

    class Service:
        def __init__(self, **kwargs):
            pass

        def read_page(self, uid, **kwargs):
            with lock:
                entries.append('read_page')
            return self._page(uid, **kwargs)

        def read(self, uid, **kwargs):
            with lock:
                entries.append('read')
            return self._offset(uid, **kwargs)

        @read_resilience.resilient_memory_read
        def _page(self, uid, **kwargs):
            return fail('read_page')

        @read_resilience.resilient_memory_read
        def _offset(self, uid, **kwargs):
            return fail('read')

    app = FastAPI()
    app.include_router(mem_mod.router)
    route = next(r for r in app.routes if getattr(r, 'path', None) == '/v3/memories' and 'GET' in r.methods)
    for dependency in route.dependant.dependencies:
        app.dependency_overrides[dependency.call] = lambda: 'private-uid'
    scope = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod, 'MemoryService', Service),
        patch.object(
            mem_mod, 'MemoryBackingStoreUnavailable', (Unavailable, read_resilience.MemoryReadAdmissionDenied)
        ),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope),
        patch.object(mem_mod, '_validate_device_scope_request'),
        patch.object(
            mem_mod,
            'list_read_budget_for_request',
            side_effect=lambda *args, **_: ListReadBudget(deadline_monotonic=12, clock=clock),
        ),
        TestClient(app) as client,
        ThreadPoolExecutor(max_workers=concurrent_requests) as pool,
    ):

        def request():
            start.wait(timeout=10)
            return client.get('/v3/memories').status_code

        pending = [pool.submit(request) for _ in range(concurrent_requests)]
        try:
            if concurrent_requests > 1:
                assert pages_started.wait(timeout=10)
        finally:
            release_pages.set()
        assert [future.result(timeout=10) for future in pending] == [503] * concurrent_requests
    return calls, entries


def test_memory_router_cursor_offset_burst_zero_executes_zero_store_operations(monkeypatch):
    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '0')
    calls, entries = _exercise_router_admission(monkeypatch, concurrent_requests=1)
    assert entries == ['read_page', 'read']  # both actual router paths entered and denied
    assert len(calls) == 0


def test_memory_router_24_concurrent_cursor_offset_requests_never_exceed_32_store_operations(monkeypatch):
    monkeypatch.delenv('OMI_MEMORY_READ_RETRY_BURST', raising=False)  # production default: eight
    calls, entries = _exercise_router_admission(monkeypatch, concurrent_requests=24)
    assert entries.count('read_page') == 24
    assert entries.count('read') > 0  # exercise actual offset fallback
    assert len(calls) <= 24 + 8  # hard reviewer bound, includes every store operation
    assert len(calls) == 8  # first attempts consume tokens too, so this is tighter
