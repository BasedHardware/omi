"""Universal MemoryService parity and released-signature compatibility tests."""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.memory_import_isolation import (
    ensure_package_path,
    ensure_test_import_packages_importable,
    install_database_client_stub,
)

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self, **_kwargs):
        if self.path not in self._db_client.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db_client.docs[self.path], exists=True)

    def set(self, payload, **_kwargs):
        self._db_client.docs[self.path] = dict(payload)


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}

    def document(self, path):
        return _DocumentRef(self, path)


def _sample_memory_dict(memory_id: str = "mem-1", *, locked: bool = False) -> dict:
    now = datetime(2026, 1, 15, tzinfo=timezone.utc)
    return {
        "id": memory_id,
        "uid": "uid-test",
        "content": "User enjoys hiking on weekends",
        "category": "interesting",
        "created_at": now,
        "updated_at": now,
        "scoring": "01_00_1736899200",
        "is_locked": locked,
        "manually_added": False,
        "user_review": None,
        "visibility": "private",
    }


def _sample_tiered_memory_dict(memory_id: str = "mem-1") -> dict:
    memory = _sample_memory_dict(memory_id)
    memory.update({"memory_tier": "short_term", "layer": "short_term", "tier": "short_term"})
    return memory


def _purge_stub_memory_modules() -> None:
    import sys

    for name in list(sys.modules):
        if not (name.startswith("utils.memory") or name in {"database.memories", "database.vector_db"}):
            continue
        mod = sys.modules.get(name)
        if not isinstance(getattr(mod, "__file__", None), str):
            sys.modules.pop(name, None)


def _load_memory_service(monkeypatch):
    """Load the real service under the test import-isolation stubs."""
    import sys

    service_mod = sys.modules.get("utils.memory.memory_service")
    memories_db = getattr(service_mod, "memories_db", None) if service_mod is not None else None
    memories_file = getattr(memories_db, "__file__", None)
    if not isinstance(memories_file, str) or not memories_file.endswith("memories.py"):
        ensure_test_import_packages_importable(_BACKEND_DIR)
        ensure_package_path("database", os.path.join(_BACKEND_DIR, "database"))
        ensure_package_path("utils.memory", os.path.join(_BACKEND_DIR, "utils", "memory"))
        install_database_client_stub()
        _purge_stub_memory_modules()
        sys.modules.pop("database.memories", None)
        sys.modules.pop("database.vector_db", None)
        sys.modules.pop("utils.memory.memory_service", None)
        import database.memories as memories_db_mod
        import database.vector_db as vector_db_mod
        import utils.memory.memory_service as service_mod
        import database

        database.memories = memories_db_mod
        database.vector_db = vector_db_mod
    service_mod._prod_get_memories = service_mod.memories_db.get_memories
    service_mod._prod_list_memory_updated_or_created_index = (
        service_mod.memories_db.list_memory_updated_or_created_index
    )
    monkeypatch.setattr(service_mod.memories_db, "get_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        service_mod.memories_db,
        "list_memory_updated_or_created_index",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(service_mod.memories_db, "get_memories_by_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(service_mod.memories_db, "get_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.memories_db, "get_memory_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(service_mod.memories_db, "delete_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.vector_db, "find_similar_memories", lambda *args, **kwargs: [])
    return service_mod


@pytest.fixture(autouse=True)
def _reset_universal_memory(monkeypatch):
    from tests.unit.universal_memory_test_helpers import reset_universal_memory_fixture

    reset_universal_memory_fixture(monkeypatch)


@pytest.fixture
def service_mod(monkeypatch):
    # Import isolation and module graph repair belong to setup, not the unit
    # behavior's measured call phase.
    return _load_memory_service(monkeypatch)


def test_arbitrary_uids_share_one_universal_reader(service_mod):
    service = service_mod.MemoryService(db_client=_FirestoreFake())
    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(return_value=[])

    assert service.read("uid-a") == []
    assert service.read("uid-b") == []
    assert [call.args[0] for call in service._canonical.read.call_args_list] == ["uid-a", "uid-b"]


def test_memory_service_never_consults_per_user_store_selector(monkeypatch, service_mod):
    service = service_mod.MemoryService(db_client=_FirestoreFake())
    service._canonical.read = MagicMock(return_value=[])
    service.history.read = MagicMock(return_value=[])
    monkeypatch.setattr(
        service_mod,
        "resolve_memory_system",
        MagicMock(side_effect=AssertionError("per-user store selector")),
        raising=False,
    )
    assert service.read("uid-a") == []
    assert service.read("uid-b") == []


def test_read_pinned_ignores_released_memory_system_pin(service_mod):
    service = service_mod.MemoryService(db_client=_FirestoreFake())
    service.read = MagicMock(return_value=[])
    assert service.read_pinned("uid-test", service_mod.MemorySystem.LEGACY) == []
    service.read.assert_called_once()


def test_canonical_failure_does_not_fall_back_to_historical_writer(monkeypatch, service_mod):
    service = service_mod.MemoryService(db_client=_FirestoreFake())
    service._canonical.write = MagicMock(side_effect=RuntimeError("canonical unavailable"))
    legacy_create = MagicMock()
    monkeypatch.setattr(service_mod.memories_db, "create_memory", legacy_create)
    memory_db = service_mod.MemoryDB.model_validate(_sample_memory_dict())

    with pytest.raises(RuntimeError, match="canonical unavailable"):
        service.create_external_memory(
            "uid-test",
            memory_db,
            memory_system=service_mod.MemorySystem.LEGACY,
            consumer="mcp",
            operation="create",
        )
    legacy_create.assert_not_called()


def test_canonical_backend_preserves_released_adapter_signatures(service_mod):
    backend = service_mod.CanonicalMemoryBackend()
    with (
        patch.object(service_mod, "read_canonical_memories", return_value=[]),
        patch.object(service_mod, "search_canonical_memories", return_value=[]),
        patch.object(service_mod, "write_canonical_external_memory", return_value="mem-1"),
        patch.object(service_mod, "delete_canonical_memory"),
        patch.object(service_mod, "delete_all_canonical_memories"),
    ):
        assert backend.read("uid-test") == []
        assert backend.search("uid-test", "query") == []
        assert backend.write("uid-test", {"id": "mem-1", "content": "x"}) == "mem-1"
        backend.delete("uid-test", "mem-1")
        backend.delete_all("uid-test")
