import importlib
import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from utils.memory.memory_system import MemorySystem, resolve_memory_system


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self, timeout=None):
        if self.path not in self._db_client.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db_client.docs[self.path], exists=True)


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


def _load_memory_service(monkeypatch):
    sys.modules.pop("utils.memory.memory_service", None)

    memory_db_mod = types.ModuleType("database.memories")
    memory_db_mod.get_memories = lambda *args, **kwargs: []
    memory_db_mod.get_memories_by_ids = lambda *args, **kwargs: []
    memory_db_mod.create_memory = lambda *args, **kwargs: None
    memory_db_mod.delete_memory = lambda *args, **kwargs: None
    memory_db_mod.delete_all_memories = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "database.memories", memory_db_mod)

    vector_db_mod = types.ModuleType("database.vector_db")
    vector_db_mod.find_similar_memories = lambda *args, **kwargs: []
    monkeypatch.setitem(sys.modules, "database.vector_db", vector_db_mod)

    return importlib.import_module("utils.memory.memory_service")


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)


class TestResolveMemorySystem:
    @pytest.mark.parametrize("uid", ["", "uid-a", "uid-b", "v17-dogfood-user"])
    def test_defaults_to_legacy_for_arbitrary_uids(self, uid):
        assert resolve_memory_system(uid, db_client=_FirestoreFake()) == MemorySystem.LEGACY

    def test_v17_control_state_read_mode_still_resolves_legacy(self, monkeypatch):
        monkeypatch.setenv("V17_MODE", "read")
        monkeypatch.setenv("V17_MEMORY_ENABLED_USERS", "uid-v17")
        db = _FirestoreFake(
            {
                "users/uid-v17/memory_control/state": {
                    "mode": "read",
                    "fallback_projection_ready": True,
                    "stage_gates": {"shadow": "passed", "write": "passed", "read": "passed"},
                }
            }
        )
        assert resolve_memory_system("uid-v17", db_client=db) == MemorySystem.LEGACY

    def test_explicit_canonical_env_assignment(self, monkeypatch):
        monkeypatch.setenv("MEMORY_CANONICAL_USERS", "uid-canonical,uid-other")
        assert resolve_memory_system("uid-canonical", db_client=_FirestoreFake()) == MemorySystem.CANONICAL
        assert resolve_memory_system("uid-not-canonical", db_client=_FirestoreFake()) == MemorySystem.LEGACY

    def test_persisted_canonical_control_state(self):
        db = _FirestoreFake(
            {
                "users/uid-persisted/memory_control/state": {
                    "memory_system": "canonical",
                }
            }
        )
        assert resolve_memory_system("uid-persisted", db_client=db) == MemorySystem.CANONICAL


class TestMemoryServiceParity:
    def test_read_matches_direct_legacy_helper(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memories = [_sample_memory_dict("mem-1"), _sample_memory_dict("mem-2")]

        with patch.object(service_mod.memories_db, "get_memories", return_value=memories) as get_memories:
            service = service_mod.MemoryService()
            via_service = service.read("uid-test", limit=25, offset=10)
            direct = service_mod._legacy_read_memories("uid-test", limit=25, offset=10)

        assert get_memories.call_count == 2
        get_memories.assert_called_with("uid-test", 25, 10)
        assert via_service == direct

    def test_read_first_page_uses_router_limit_cap(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memories = [_sample_memory_dict()]

        with patch.object(service_mod.memories_db, "get_memories", return_value=memories) as get_memories:
            service = service_mod.MemoryService()
            via_service = service.read("uid-test", limit=25, offset=0)
            direct = service_mod._legacy_read_memories("uid-test", limit=25, offset=0)

        assert get_memories.call_count == 2
        get_memories.assert_called_with("uid-test", 5000, 0)
        assert via_service == direct

    def test_search_matches_direct_legacy_helper(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        vector_matches = [
            {"memory_id": "mem-1", "score": 0.91},
            {"memory_id": "mem-2", "score": 0.82},
        ]
        memories = [_sample_memory_dict("mem-1"), _sample_memory_dict("mem-2")]

        with (
            patch.object(service_mod.vector_db, "find_similar_memories", return_value=vector_matches) as find_similar,
            patch.object(service_mod.memories_db, "get_memories_by_ids", return_value=memories) as get_by_ids,
        ):
            service = service_mod.MemoryService()
            via_service = service.search("uid-test", "hiking", limit=5)
            direct = service_mod._legacy_search_memories("uid-test", "hiking", limit=5)

        assert find_similar.call_count == 2
        find_similar.assert_called_with("uid-test", "hiking", threshold=0.0, limit=5)
        assert get_by_ids.call_count == 2
        get_by_ids.assert_called_with("uid-test", ["mem-1", "mem-2"])
        assert via_service == direct

    def test_canonical_backend_raises_not_implemented(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        backend = service_mod.CanonicalMemoryBackend()
        message = "canonical backend lands in WS-B/WS-C/WS-I"

        with pytest.raises(NotImplementedError, match=message):
            backend.read("uid-test")
        with pytest.raises(NotImplementedError, match=message):
            backend.search("uid-test", "query")
        with pytest.raises(NotImplementedError, match=message):
            backend.write("uid-test", {"id": "mem-1"})
        with pytest.raises(NotImplementedError, match=message):
            backend.delete("uid-test", "mem-1")
        with pytest.raises(NotImplementedError, match=message):
            backend.delete_all("uid-test")

    def test_memory_service_uses_legacy_backend_by_default(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memories = [_sample_memory_dict()]

        with patch.object(service_mod.memories_db, "get_memories", return_value=memories):
            service = service_mod.MemoryService(db_client=_FirestoreFake())
            result = service.read("uid-test")

        assert len(result) == 1
        assert result[0].id == "mem-1"
