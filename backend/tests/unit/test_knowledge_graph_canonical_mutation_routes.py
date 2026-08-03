"""Public graph mutations preserve canonical derived-state ownership."""

from fastapi import BackgroundTasks, HTTPException
import pytest

from routers import knowledge_graph as kg_router
from utils.memory.memory_system import MemorySystem

UID = "uid-knowledge-graph-route"


def test_canonical_delete_route_returns_conflict_without_deleting_projection(monkeypatch):
    delete_calls: list[str] = []
    monkeypatch.setattr(kg_router, "pin_memory_system", lambda *_args, **_kwargs: MemorySystem.CANONICAL)
    monkeypatch.setattr(kg_router.kg_db, "delete_knowledge_graph", lambda uid: delete_calls.append(uid))

    with pytest.raises(HTTPException) as error:
        kg_router.delete_knowledge_graph(uid=UID)

    assert error.value.status_code == 409
    assert error.value.detail == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert delete_calls == []


def test_canonical_sync_route_returns_conflict_without_merging(monkeypatch):
    merge_calls: list[tuple] = []
    fallback_calls: list[dict] = []
    monkeypatch.setattr(kg_router, "pin_memory_system", lambda *_args, **_kwargs: MemorySystem.CANONICAL)
    monkeypatch.setattr(
        kg_router.kg_sync,
        "merge_synced_local_kg",
        lambda *args, **kwargs: merge_calls.append((args, kwargs)) or {},
    )
    monkeypatch.setattr(kg_router, "record_fallback", lambda **kwargs: fallback_calls.append(kwargs))

    with pytest.raises(HTTPException) as error:
        kg_router.sync_local_knowledge_graph(
            payload=kg_router.LocalKgSyncRequest(
                table="local_kg_nodes",
                rows=[{"nodeId": "n1", "label": "Test"}],
                source_namespace="macos_test",
            ),
            uid=UID,
        )

    assert error.value.status_code == 409
    assert error.value.detail == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert merge_calls == []
    assert fallback_calls == [
        {
            "component": "agent_tools",
            "from_mode": "cloud_promotion",
            "to_mode": "local_only",
            "reason": "policy",
            "outcome": "degraded",
        }
    ]


def test_canonical_rebuild_route_returns_conflict_without_deleting_or_scheduling(monkeypatch):
    delete_calls: list[str] = []
    user_name_calls: list[str] = []
    background_tasks = BackgroundTasks()
    monkeypatch.setattr(kg_router, "pin_memory_system", lambda *_args, **_kwargs: MemorySystem.CANONICAL)
    monkeypatch.setattr(kg_router.kg_db, "delete_knowledge_graph", lambda uid: delete_calls.append(uid))
    monkeypatch.setattr(
        kg_router,
        "get_user_name",
        lambda uid: user_name_calls.append(uid) or "Canonical User",
    )

    with pytest.raises(HTTPException) as error:
        kg_router.rebuild_graph(background_tasks=background_tasks, uid=UID)

    assert error.value.status_code == 409
    assert error.value.detail == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert delete_calls == []
    assert user_name_calls == []
    assert background_tasks.tasks == []


def test_retained_assertions_block_mutation_when_rollout_now_selects_legacy(monkeypatch):
    delete_calls: list[str] = []
    background_tasks = BackgroundTasks()
    monkeypatch.setattr(kg_router, "pin_memory_system", lambda *_args, **_kwargs: MemorySystem.LEGACY)
    monkeypatch.setattr(kg_router.kg_db, "has_stored_memory_graph_assertions", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(kg_router.kg_db, "delete_knowledge_graph", lambda uid: delete_calls.append(uid))

    with pytest.raises(HTTPException) as delete_error:
        kg_router.delete_knowledge_graph(uid=UID)
    with pytest.raises(HTTPException) as rebuild_error:
        kg_router.rebuild_graph(background_tasks=background_tasks, uid=UID)

    assert delete_error.value.status_code == 409
    assert rebuild_error.value.status_code == 409
    assert delete_calls == []
    assert background_tasks.tasks == []


def test_legacy_delete_and_rebuild_routes_preserve_projection_mutations(monkeypatch):
    delete_calls: list[str] = []
    background_tasks = BackgroundTasks()
    monkeypatch.setattr(kg_router, "pin_memory_system", lambda *_args, **_kwargs: MemorySystem.LEGACY)
    monkeypatch.setattr(kg_router.kg_db, "has_stored_memory_graph_assertions", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(kg_router.kg_db, "delete_knowledge_graph", lambda uid: delete_calls.append(uid))
    monkeypatch.setattr(kg_router, "get_user_name", lambda _uid: "Legacy User")

    delete_response = kg_router.delete_knowledge_graph(uid=UID)
    rebuild_response = kg_router.rebuild_graph(background_tasks=background_tasks, uid=UID)

    assert delete_response == {"status": "deleted"}
    assert rebuild_response.status == "rebuilding"
    assert delete_calls == [UID, UID]
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].func is kg_router._rebuild_graph_task
    assert background_tasks.tasks[0].args == (UID, "Legacy User")


@pytest.mark.parametrize("ownership_change", ["canonical", "retained_assertion"])
def test_queued_legacy_rebuild_aborts_when_graph_ownership_changes_before_execution(
    monkeypatch,
    ownership_change,
):
    state = {
        "memory_system": MemorySystem.LEGACY,
        "has_assertion": False,
    }
    read_calls: list[str] = []
    rebuild_calls: list[tuple[str, list[dict], str]] = []
    background_tasks = BackgroundTasks()
    monkeypatch.setattr(
        kg_router,
        "pin_memory_system",
        lambda *_args, **_kwargs: state["memory_system"],
    )
    monkeypatch.setattr(
        kg_router.kg_db,
        "has_stored_memory_graph_assertions",
        lambda *_args, **_kwargs: state["has_assertion"],
    )
    monkeypatch.setattr(kg_router.kg_db, "delete_knowledge_graph", lambda _uid: None)
    monkeypatch.setattr(kg_router, "get_user_name", lambda _uid: "Legacy User")
    monkeypatch.setattr(
        kg_router.memories_db,
        "get_memories",
        lambda uid, **_kwargs: read_calls.append(uid) or [],
    )
    monkeypatch.setattr(
        kg_router,
        "_run_rebuild_knowledge_graph",
        lambda uid, memories, user_name: rebuild_calls.append((uid, memories, user_name)) or {},
    )

    kg_router.rebuild_graph(background_tasks=background_tasks, uid=UID)
    if ownership_change == "canonical":
        state["memory_system"] = MemorySystem.CANONICAL
    else:
        state["has_assertion"] = True

    task = background_tasks.tasks[0]
    task.func(*task.args, **task.kwargs)

    assert read_calls == []
    assert rebuild_calls == []


def test_legacy_rebuild_rechecks_assertion_ownership_after_read(monkeypatch):
    has_assertion = False
    rebuild_calls: list[tuple[str, list[dict], str]] = []
    monkeypatch.setattr(kg_router, "pin_memory_system", lambda *_args, **_kwargs: MemorySystem.LEGACY)
    monkeypatch.setattr(
        kg_router.kg_db,
        "has_stored_memory_graph_assertions",
        lambda *_args, **_kwargs: has_assertion,
    )

    def get_memories(_uid, **_kwargs):
        nonlocal has_assertion
        has_assertion = True
        return [{"id": "legacy-memory", "content": "Legacy fact"}]

    monkeypatch.setattr(kg_router.memories_db, "get_memories", get_memories)
    monkeypatch.setattr(
        kg_router,
        "_run_rebuild_knowledge_graph",
        lambda uid, memories, user_name: rebuild_calls.append((uid, memories, user_name)) or {},
    )

    kg_router._rebuild_graph_task(UID, "Legacy User")

    assert rebuild_calls == []
