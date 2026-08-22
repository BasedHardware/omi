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
    monkeypatch.setattr(
        "utils.memory.canonical_memory_adapter.fetch_authoritative_product_memory_items",
        lambda **_kwargs: [locked_archive, newer_short],
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
