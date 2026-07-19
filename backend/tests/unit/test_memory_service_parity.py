import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
import pytest

from tests.unit.memory_import_isolation import (
    ensure_package_path,
    ensure_test_import_packages_importable,
    install_database_client_stub,
)
from utils.memory.memory_system import MemorySystem, resolve_memory_system

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


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
        mod_file = getattr(mod, "__file__", None)
        if not isinstance(mod_file, str):
            sys.modules.pop(name, None)


def _load_memory_service(monkeypatch):
    import importlib
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

    monkeypatch.setattr(service_mod.memories_db, "get_memories", lambda *args, **kwargs: [])
    monkeypatch.setattr(service_mod.memories_db, "get_memories_by_ids", lambda *args, **kwargs: [])
    monkeypatch.setattr(service_mod.memories_db, "create_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.memories_db, "delete_memory", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.memories_db, "delete_all_memories", lambda *args, **kwargs: None)
    monkeypatch.setattr(service_mod.vector_db, "find_similar_memories", lambda *args, **kwargs: [])
    return service_mod


@pytest.fixture(autouse=True)
def _clear_canonical_cohort(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    clear_canonical_cohort(monkeypatch)


class TestResolveMemorySystem:
    @pytest.mark.parametrize("uid", ["", "uid-a", "uid-b", "memory-dogfood-user"])
    def test_defaults_to_legacy_for_arbitrary_uids(self, uid):
        assert resolve_memory_system(uid, db_client=_FirestoreFake()) == MemorySystem.LEGACY

    def test_memory_control_state_read_mode_still_resolves_legacy(self, monkeypatch):
        monkeypatch.setenv("MEMORY_MODE", "read")
        monkeypatch.setenv("MEMORY_ENABLED_USERS", "uid-memory")
        db = _FirestoreFake(
            {
                "users/uid-memory/memory_control/state": {
                    "mode": "read",
                    "fallback_projection_ready": True,
                    "stage_gates": {"shadow": "passed", "write": "passed", "read": "passed"},
                }
            }
        )
        assert resolve_memory_system("uid-memory", db_client=db) == MemorySystem.LEGACY

    def test_explicit_canonical_cohort_assignment(self, monkeypatch):
        from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

        set_canonical_cohort(monkeypatch, "uid-canonical", "uid-other")
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
        from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort, set_canonical_cohort

        db = _FirestoreFake(
            {
                "users/uid-flip/memory_control/state": {
                    "memory_system": "canonical",
                }
            }
        )
        set_canonical_cohort(monkeypatch, "uid-flip")
        assert resolve_memory_system("uid-flip", db_client=db) == MemorySystem.CANONICAL

        clear_canonical_cohort(monkeypatch)
        assert resolve_memory_system("uid-flip", db_client=db) == MemorySystem.LEGACY

    def test_empty_whitelist_is_global_kill_switch(self, monkeypatch):
        from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

        clear_canonical_cohort(monkeypatch)
        db = _FirestoreFake(
            {
                "users/uid-a/memory_control/state": {"memory_system": "canonical"},
                "users/uid-b/memory_control/state": {"memory_system": "legacy"},
            }
        )
        assert resolve_memory_system("uid-a", db_client=db) == MemorySystem.LEGACY
        assert resolve_memory_system("uid-b", db_client=db) == MemorySystem.LEGACY


class TestMemoryServiceParity:
    def test_canonical_write_decision_malformed_rollout_fails_closed_for_code_cohort(self, monkeypatch):
        from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort
        from utils.memory.canonical_activation import canonical_write_decision

        set_canonical_cohort(monkeypatch, "uid-canonical")
        monkeypatch.setenv("MEMORY_MODE", "not-a-valid-mode")

        decision = canonical_write_decision("uid-canonical", db_client=_FirestoreFake())

        assert decision.enabled is False
        assert decision.memory_system == MemorySystem.CANONICAL
        assert decision.fail_closed is True
        assert decision.reason == "invalid_rollout_config"

    def test_canonical_write_decision_missing_db_fails_closed_for_code_cohort(self, monkeypatch):
        from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort
        from utils.memory.canonical_activation import canonical_write_decision

        set_canonical_cohort(monkeypatch, "uid-canonical")

        decision = canonical_write_decision("uid-canonical", db_client=None)

        assert decision.enabled is False
        assert decision.memory_system == MemorySystem.CANONICAL
        assert decision.fail_closed is True
        assert decision.reason == "missing_db_client"

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

    def test_external_canonical_write_gate_failure_does_not_fallback_to_legacy_create(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memory_db = service_mod.MemoryDB.model_validate(_sample_memory_dict())
        create_memory = MagicMock()
        monkeypatch.setattr(service_mod.memories_db, "create_memory", create_memory)
        monkeypatch.setattr(
            service_mod,
            "canonical_write_decision",
            lambda *args, **kwargs: SimpleNamespace(enabled=False, fail_closed=True, reason="malformed_state"),
        )

        with pytest.raises(HTTPException) as exc:
            service_mod.MemoryService(db_client=_FirestoreFake()).create_external_memory(
                "uid-test",
                memory_db,
                memory_system=MemorySystem.CANONICAL,
                consumer="mcp",
                operation="mcp_tool_memory_create",
            )

        assert exc.value.status_code == 503
        create_memory.assert_not_called()

    def test_all_canonical_service_mutations_fail_closed_without_legacy_fallback(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        monkeypatch.setattr(
            service_mod,
            "canonical_write_decision",
            lambda *args, **kwargs: SimpleNamespace(
                enabled=False,
                memory_system=MemorySystem.CANONICAL,
                fail_closed=True,
                reason="rollout_write_not_ready",
            ),
        )
        service = service_mod.MemoryService(db_client=_FirestoreFake())
        legacy = service._legacy
        for method in (
            "write",
            "write_batch",
            "update_content",
            "update_visibility",
            "review",
            "update_product_fields",
            "delete",
            "delete_all",
        ):
            setattr(legacy, method, MagicMock())

        operations = [
            lambda: service.ensure_canonical_mutation_ready("uid-canonical"),
            lambda: service.write("uid-canonical", _sample_memory_dict()),
            lambda: service.write_batch("uid-canonical", [_sample_memory_dict()]),
            lambda: service.update_content("uid-canonical", "memory-id", "updated"),
            lambda: service.update_visibility("uid-canonical", "memory-id", "private"),
            lambda: service.review("uid-canonical", "memory-id", True),
            lambda: service.update_product_fields("uid-canonical", "memory-id", tags=["tag"]),
            lambda: service.delete("uid-canonical", "memory-id"),
            lambda: service.delete_all("uid-canonical"),
            lambda: service.retract_conversation_memories("uid-canonical", "conversation-id"),
        ]

        for operation in operations:
            with pytest.raises(HTTPException) as exc:
                operation()
            assert exc.value.status_code == 503

        for method in (
            "write",
            "write_batch",
            "update_content",
            "update_visibility",
            "review",
            "update_product_fields",
            "delete",
            "delete_all",
        ):
            getattr(legacy, method).assert_not_called()

    def test_external_canonical_create_uses_canonical_backend_without_rechecking_public_write(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memory_db = service_mod.MemoryDB.model_validate(_sample_memory_dict())
        create_memory = MagicMock()
        canonical_write = MagicMock(return_value="mem-1")
        monkeypatch.setattr(service_mod.memories_db, "create_memory", create_memory)
        monkeypatch.setattr(
            service_mod,
            "canonical_write_decision",
            lambda *args, **kwargs: SimpleNamespace(enabled=True, fail_closed=False, reason="ok"),
        )
        monkeypatch.setattr(
            service_mod.MemoryService,
            "write",
            MagicMock(side_effect=AssertionError("external canonical writes must not re-enter public write")),
        )
        monkeypatch.setattr(service_mod, "read_canonical_memory_item", MagicMock(return_value=None))

        service = service_mod.MemoryService(db_client=_FirestoreFake())
        service._canonical.write = canonical_write

        with pytest.raises(HTTPException) as exc:
            service.create_external_memory(
                "uid-test",
                memory_db,
                memory_system=MemorySystem.CANONICAL,
                consumer="mcp",
                operation="mcp_tool_memory_create",
            )

        assert exc.value.status_code == 503
        canonical_write.assert_called_once()
        create_memory.assert_not_called()

    def test_external_canonical_edit_value_error_maps_to_404_without_legacy_fallback(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        edit_memory = MagicMock()
        monkeypatch.setattr(service_mod.memories_db, "edit_memory", edit_memory)
        monkeypatch.setattr(
            service_mod,
            "canonical_write_decision",
            lambda *args, **kwargs: SimpleNamespace(enabled=True, fail_closed=False, reason="ok"),
        )

        service = service_mod.MemoryService(db_client=_FirestoreFake())
        service._canonical.update_content = MagicMock(side_effect=ValueError("memory not found"))

        with pytest.raises(HTTPException) as exc:
            service.update_external_memory_content(
                "uid-test",
                "missing-memory",
                "new content",
                memory_system=MemorySystem.CANONICAL,
                consumer="mcp",
                operation="mcp_tool_memory_edit",
            )

        assert exc.value.status_code == 404
        edit_memory.assert_not_called()

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
                "utils.memory.memory_service.write_canonical_external_memory",
                return_value="mem-1",
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

    def test_legacy_backend_strips_canonical_lifecycle_fields_on_read(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memories = [_sample_tiered_memory_dict()]

        with patch.object(service_mod.memories_db, "get_memories", return_value=memories):
            result = service_mod.MemoryService(db_client=_FirestoreFake()).read("uid-test")

        assert len(result) == 1
        assert result[0].memory_tier is None
        serialized = result[0].model_dump(mode="json")
        assert serialized["memory_tier"] is None
        assert serialized["layer"] is None
        assert "short_term" not in serialized.values()

    def test_legacy_backend_strips_canonical_lifecycle_fields_on_write(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        create_memory = MagicMock()
        monkeypatch.setattr(service_mod.memories_db, "create_memory", create_memory)

        service_mod.MemoryService(db_client=_FirestoreFake()).write("uid-test", _sample_tiered_memory_dict())

        payload = create_memory.call_args.args[1]
        assert "memory_tier" not in payload
        assert "layer" not in payload
        assert "tier" not in payload

    def test_external_legacy_create_strips_canonical_lifecycle_fields(self, monkeypatch):
        service_mod = _load_memory_service(monkeypatch)
        memory_db = service_mod.MemoryDB.model_validate(_sample_tiered_memory_dict())
        create_memory = MagicMock()
        monkeypatch.setattr(service_mod.memories_db, "create_memory", create_memory)
        monkeypatch.setattr(
            service_mod,
            "guard_legacy_memory_write",
            lambda *args, **kwargs: SimpleNamespace(allowed=True, status_code=200, detail=None),
        )

        result = service_mod.MemoryService(db_client=_FirestoreFake()).create_external_memory(
            "uid-test",
            memory_db,
            memory_system=MemorySystem.LEGACY,
            consumer="mcp",
            operation="mcp_tool_memory_create",
            upsert_vector=False,
        )

        payload = create_memory.call_args.args[1]
        assert "memory_tier" not in payload
        assert "layer" not in payload
        assert "tier" not in payload
        assert result.memory_tier is None

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

        import utils.memory.memory_system_pin as memory_system_pin

        monkeypatch.setattr(memory_system_pin, "resolve_memory_system", flipping_resolve)
        canonical_mock = MagicMock(return_value=[{"id": "canonical-only"}])
        monkeypatch.setattr(service_mod, "_canonical_search_memories_mcp", canonical_mock)

        from utils.memory.memory_system_pin import pin_memory_system

        pin_memory_system(uid)
        service = service_mod.MemoryService(db_client=_FirestoreFake())
        service.search_mcp(uid, "query", limit=5)
        service.search_mcp(uid, "query", limit=5)

        canonical_mock.assert_not_called()
