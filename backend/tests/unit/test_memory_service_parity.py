import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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
    import utils.memory.memory_service as service_mod

    monkeypatch.setattr(service_mod.memories_db, "get_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(service_mod.memories_db, "get_memories_by_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(service_mod.memories_db, "create_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.memories_db, "delete_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.memories_db, "delete_all_memories", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.vector_db, "find_similar_memories", lambda *args, **kwargs: [])
    return service_mod


@pytest.fixture(autouse=True)
def _clear_canonical_env(monkeypatch):
    monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)


class TestResolveMemorySystem:
    @pytest.mark.parametrize("uid", ["", "uid-a", "uid-b", "v17-dogfood-user"])
    def test_defaults_to_legacy_for_arbitrary_uids(self, uid):
        assert resolve_memory_system(uid, db_client=_FirestoreFake()) == MemorySystem.LEGACY

    def test_v17_control_state_read_mode_still_resolves_legacy(self, monkeypatch):
        monkeypatch.setenv("MEMORY_MODE", "read")
        monkeypatch.setenv("MEMORY_ENABLED_USERS", "uid-v17")
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

    def test_stale_persisted_canonical_without_whitelist_resolves_legacy(self):
        db = _FirestoreFake(
            {
                "users/uid-persisted/memory_control/state": {
                    "memory_system": "canonical",
                }
            }
        )
        assert resolve_memory_system("uid-persisted", db_client=db) == MemorySystem.LEGACY

    def test_whitelist_removal_reverts_stale_persisted_canonical(self, monkeypatch):
        db = _FirestoreFake(
            {
                "users/uid-flip/memory_control/state": {
                    "memory_system": "canonical",
                }
            }
        )
        monkeypatch.setenv("MEMORY_CANONICAL_USERS", "uid-flip")
        assert resolve_memory_system("uid-flip", db_client=db) == MemorySystem.CANONICAL

        monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)
        assert resolve_memory_system("uid-flip", db_client=db) == MemorySystem.LEGACY

    def test_empty_whitelist_is_global_kill_switch(self, monkeypatch):
        monkeypatch.delenv("MEMORY_CANONICAL_USERS", raising=False)
        db = _FirestoreFake(
            {
                "users/uid-a/memory_control/state": {"memory_system": "canonical"},
                "users/uid-b/memory_control/state": {"memory_system": "legacy"},
            }
        )
        assert resolve_memory_system("uid-a", db_client=db) == MemorySystem.LEGACY
        assert resolve_memory_system("uid-b", db_client=db) == MemorySystem.LEGACY


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

    def test_canonical_backend_delegates_to_adapter(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        backend = service_mod.CanonicalMemoryBackend()

        with (
            patch(
                "utils.memory.memory_service.read_canonical_memories",
                return_value=[],
            ) as read_mock,
            patch(
                "utils.memory.memory_service.search_canonical_memories",
                return_value=[],
            ) as search_mock,
            patch(
                "utils.memory.memory_service.write_canonical_extraction_memory",
            ) as write_mock,
            patch(
                "utils.memory.memory_service.delete_canonical_memory",
            ) as delete_mock,
            patch(
                "utils.memory.memory_service.delete_all_canonical_memories",
            ) as delete_all_mock,
        ):
            assert backend.read("uid-test") == []
            assert backend.search("uid-test", "query") == []
            backend.write(
                "uid-test",
                {
                    "id": "mem-1",
                    "content": "x",
                    "conversation_id": "conv-1",
                    "evidence": [{"evidence_id": "e1", "source_id": "conv-1", "source_type": "conversation"}],
                },
            )
            backend.delete("uid-test", "mem-1")
            backend.delete_all("uid-test")

        read_mock.assert_called_once()
        search_mock.assert_called_once()
        write_mock.assert_called_once()
        delete_mock.assert_called_once()
        delete_all_mock.assert_called_once()

    def test_memory_service_uses_legacy_backend_by_default(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memories = [_sample_memory_dict()]

        with patch.object(service_mod.memories_db, "get_memories", return_value=memories):
            service = service_mod.MemoryService(db_client=_FirestoreFake())
            result = service.read("uid-test")

        assert len(result) == 1
        assert result[0].id == "mem-1"

    def test_search_mcp_legacy_fetch_limit_filters_and_rrf(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        vector_matches = [
            {"memory_id": "mem-rejected", "score": 0.99},
            {"memory_id": "mem-ok", "score": 0.80},
        ]
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        memories_by_id = [
            {
                "id": "mem-rejected",
                "uid": "uid-test",
                "content": "rejected",
                "category": "other",
                "created_at": now,
                "updated_at": now,
                "user_review": False,
                "is_locked": False,
            },
            {
                "id": "mem-ok",
                "uid": "uid-test",
                "content": "visible",
                "category": "interesting",
                "created_at": now,
                "updated_at": now,
                "scoring": "01_00_1736899200",
                "is_locked": False,
                "manually_added": False,
                "visibility": "private",
            },
        ]

        with (
            patch.object(service_mod.vector_db, "find_similar_memories", return_value=vector_matches) as find_similar,
            patch.object(service_mod.memories_db, "get_memories_by_ids", return_value=memories_by_id),
            patch.object(
                service_mod, "rrf_rerank", side_effect=lambda query, candidates, limit, k=60: candidates[:limit]
            ) as rerank,
        ):
            direct = service_mod._legacy_search_memories_mcp("uid-test", "visible", limit=10)
            via_service = service_mod.MemoryService(db_client=_FirestoreFake()).search_mcp(
                "uid-test", "visible", limit=10
            )

        assert find_similar.call_count == 2
        find_similar.assert_called_with("uid-test", "visible", threshold=0.0, limit=30)
        assert rerank.call_count == 2
        assert direct == via_service
        assert len(direct) == 1
        assert direct[0]["id"] == "mem-ok"


class TestMemoryServiceUsesRequestPin:
    def test_search_mcp_stays_on_pinned_legacy_backend_when_resolver_flips(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        uid = "uid-service-pin"
        calls = {"count": 0}

        def flipping_resolve(_uid, *, db_client=None):
            calls["count"] += 1
            from utils.memory.memory_system import MemorySystem

            return MemorySystem.LEGACY if calls["count"] == 1 else MemorySystem.CANONICAL

        monkeypatch.setattr("utils.memory.memory_system_pin.resolve_memory_system", flipping_resolve)
        canonical_mock = MagicMock(return_value=[{"id": "canonical-only"}])
        monkeypatch.setattr(service_mod, "_canonical_search_memories_mcp", canonical_mock)

        from utils.memory.memory_system_pin import pin_memory_system

        pin_memory_system(uid)
        service = service_mod.MemoryService(db_client=_FirestoreFake())
        service.search_mcp(uid, "query", limit=5)
        service.search_mcp(uid, "query", limit=5)

        assert calls["count"] == 1
        canonical_mock.assert_not_called()
