import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models.conversation import UpdateActionItemDescriptionRequest
from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]
UID = "uid-merge-cleanup-test"
DUE = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def isolated_modules():
    import ast

    vector_db_source = (_BACKEND / "database" / "vector_db.py").read_text(encoding="utf-8")
    vector_db_tree = ast.parse(vector_db_source)
    real_vector_db_funcs = {
        node.name for node in vector_db_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    fakes: dict[str, ModuleType] = {}

    def add(name: str, mod: ModuleType | None = None) -> ModuleType:
        m = mod if mod is not None else AutoMockModule(name)
        fakes[name] = m
        return m

    database_pkg = ModuleType("database")
    database_pkg.__path__ = [str(_BACKEND / "database")]  # type: ignore[attr-defined]
    add("database", database_pkg)

    client_stub = add("database._client", ModuleType("database._client"))
    client_stub.db = MagicMock(name="db")
    client_stub.get_firestore_client = lambda: client_stub.db
    client_stub.get_data_plane_firestore_client = lambda: client_stub.db
    client_stub.document_id_from_seed = lambda seed: "seed-id"
    client_stub.run_transactional = MagicMock()

    # Strict module stub: only expose functions that actually exist in database/vector_db.py
    vector_db_stub = add("database.vector_db", ModuleType("database.vector_db"))
    for fn_name in real_vector_db_funcs:
        setattr(vector_db_stub, fn_name, MagicMock(name=fn_name))

    for name in (
        "database.conversations",
        "database.conversation_scan",
        "database.conversation_tombstones",
        "database.action_items",
        "database.redis_db",
        "database.users",
        "database.firestore_read_metrics",
        "utils.other.storage",
        "utils.screen_frames.store",
        "utils.conversations.onopen_translation",
        "utils.conversations.mcp_transcript_search",
        "utils.conversations.search",
        "utils.conversations.share_email",
        "utils.conversations.calendar_linking",
        "utils.conversations.calendar_utils",
        "utils.conversations.location",
        "utils.conversations.process_conversation",
        "utils.conversations.lifecycle",
        "utils.conversations.capture_shadow_outcomes",
        "utils.conversations.meeting_receipt",
        "utils.conversations.smart_merge_audit",
        "utils.retrieval.tools.calendar_tools",
        "utils.retrieval.tools.google_utils",
        "utils.llm.conversation_processing",
        "utils.speaker_assignment_teaching",
        "utils.speaker_learning_jobs",
        "utils.app_integrations",
        "services.conversation_frame_evidence",
        "utils.memory.memory_service",
        "utils.memory.retraction_scope",
        "utils.memory.canonical_memory_adapter",
        "utils.cloud_tasks",
    ):
        add(name)

    with stub_modules(fakes):
        merge_mod = load_module_fresh(
            "utils.conversations.merge_conversations",
            os.path.join(str(_BACKEND), "utils", "conversations", "merge_conversations.py"),
        )
        router_mod = load_module_fresh(
            "routers.conversations",
            os.path.join(str(_BACKEND), "routers", "conversations.py"),
        )
        yield SimpleNamespace(
            merge=merge_mod,
            router=router_mod,
            action_items_db=fakes["database.action_items"],
            vector_db=vector_db_stub,
            real_vector_db_funcs=real_vector_db_funcs,
        )


class _StructuredActionItem:
    def __init__(self, description: str):
        self.description = description

    def model_dump(self):
        return {"description": self.description}


def test_validate_merge_compatibility_rejects_duplicate_conversation_ids(isolated_modules):
    merge_conversations = isolated_modules.merge
    c1 = {"id": "conv-1", "status": "completed", "is_locked": False, "deleted": False}
    c2 = {"id": "conv-2", "status": "completed", "is_locked": False, "deleted": False}

    ok, err, warn = merge_conversations.validate_merge_compatibility([c1, dict(c1)])
    assert ok is False
    assert "duplicate" in (err or "").lower()
    assert warn is None

    ok2, err2, warn2 = merge_conversations.validate_merge_compatibility([c1, c2, dict(c1)])
    assert ok2 is False
    assert "duplicate" in (err2 or "").lower()
    assert warn2 is None


def test_delete_conversation_and_related_data_purges_task_and_transcript_chunk_vectors(monkeypatch, isolated_modules):
    merge_conversations = isolated_modules.merge
    action_items_db = isolated_modules.action_items_db

    service = MagicMock()
    monkeypatch.setattr(merge_conversations, "MemoryService", lambda db_client=None: service)
    monkeypatch.setattr(merge_conversations, "retraction_can_be_skipped", lambda *a, **k: True)
    monkeypatch.setattr(
        action_items_db,
        "get_action_items_by_conversation",
        lambda uid, cid: [
            {"id": "task-1", "description": "Follow up", "due_at": DUE, "completed": False},
            {"id": "task-2", "description": "Archive notes", "due_at": None, "completed": True},
        ],
    )
    deleted_tasks_for_conv = []
    monkeypatch.setattr(
        action_items_db,
        "delete_action_items_for_conversation",
        lambda uid, cid: deleted_tasks_for_conv.append((uid, cid)),
    )
    cancelled_reminders = []
    monkeypatch.setattr(
        merge_conversations,
        "_cancel_open_dated_task_reminders",
        lambda uid, items: cancelled_reminders.append((uid, [i["id"] for i in items])),
    )
    deleted_task_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_action_item_vectors_batch",
        lambda uid, ids: deleted_task_vectors.append((uid, list(ids))),
    )
    deleted_conv_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_vector",
        lambda uid, cid: deleted_conv_vectors.append((uid, cid)),
    )
    deleted_chunk_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_transcript_chunk_vectors",
        lambda uid, cid: deleted_chunk_vectors.append((uid, cid)),
    )
    monkeypatch.setattr(merge_conversations.conversations_db, "delete_conversation_photos", lambda *a, **k: None)
    monkeypatch.setattr(merge_conversations, "delete_conversation_audio_files", lambda *a, **k: None)
    monkeypatch.setattr(merge_conversations, "delete_conversation_with_sync_sources", lambda *a, **k: None)
    monkeypatch.setitem(sys.modules, "database.action_items", action_items_db)

    merge_conversations._delete_conversation_and_related_data(UID, "conv-src-1")

    assert deleted_tasks_for_conv == [(UID, "conv-src-1")]
    assert cancelled_reminders == [(UID, ["task-1", "task-2"])]
    assert deleted_task_vectors == [(UID, ["task-1", "task-2"])]
    assert deleted_conv_vectors == [(UID, "conv-src-1")]
    assert deleted_chunk_vectors == [(UID, "conv-src-1")]


def test_delete_conversation_retain_capture_purges_task_and_transcript_chunk_vectors(monkeypatch, isolated_modules):
    merge_conversations = isolated_modules.merge
    action_items_db = isolated_modules.action_items_db

    service = MagicMock()
    monkeypatch.setattr(merge_conversations, "MemoryService", lambda db_client=None: service)
    monkeypatch.setattr(merge_conversations, "retraction_can_be_skipped", lambda *a, **k: True)
    monkeypatch.setattr(
        action_items_db,
        "get_action_items_by_conversation",
        lambda uid, cid: [{"id": "task-bridge-1", "description": "Bridge task", "due_at": None, "completed": False}],
    )
    monkeypatch.setattr(action_items_db, "delete_action_items_for_conversation", lambda *a, **k: None)
    monkeypatch.setattr(merge_conversations, "_cancel_open_dated_task_reminders", lambda *a, **k: None)

    deleted_task_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_action_item_vectors_batch",
        lambda uid, ids: deleted_task_vectors.append((uid, list(ids))),
    )
    deleted_conv_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_vector",
        lambda uid, cid: deleted_conv_vectors.append((uid, cid)),
    )
    deleted_chunk_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_transcript_chunk_vectors",
        lambda uid, cid: deleted_chunk_vectors.append((uid, cid)),
    )
    deleted_search_index = []
    monkeypatch.setattr(
        merge_conversations.conversations_db,
        "_delete_conversation_search_index",
        lambda uid, cid: deleted_search_index.append((uid, cid)),
    )
    monkeypatch.setitem(sys.modules, "database.action_items", action_items_db)

    merge_conversations._delete_conversation_and_related_data(UID, "conv-bridge-1", retain_capture=True)

    assert deleted_task_vectors == [(UID, ["task-bridge-1"])]
    assert deleted_conv_vectors == [(UID, "conv-bridge-1")]
    assert deleted_chunk_vectors == [(UID, "conv-bridge-1")]
    assert deleted_search_index == [(UID, "conv-bridge-1")]


def test_cleanup_merged_target_after_failure_purges_tasks_reminders_and_vectors(monkeypatch, isolated_modules):
    merge_conversations = isolated_modules.merge
    action_items_db = isolated_modules.action_items_db

    service = MagicMock()
    monkeypatch.setattr(merge_conversations, "MemoryService", lambda db_client=None: service)
    monkeypatch.setattr(
        action_items_db,
        "get_action_items_by_conversation",
        lambda uid, cid: [
            {"id": "merged-task-1", "description": "Draft proposal", "due_at": DUE, "completed": False},
        ],
    )
    deleted_tasks_for_conv = []
    monkeypatch.setattr(
        action_items_db,
        "delete_action_items_for_conversation",
        lambda uid, cid: deleted_tasks_for_conv.append((uid, cid)),
    )
    cancelled_reminders = []
    monkeypatch.setattr(
        merge_conversations,
        "_cancel_open_dated_task_reminders",
        lambda uid, items: cancelled_reminders.append((uid, [i["id"] for i in items])),
    )
    deleted_task_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_action_item_vectors_batch",
        lambda uid, ids: deleted_task_vectors.append((uid, list(ids))),
    )
    deleted_conv_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_vector",
        lambda uid, cid: deleted_conv_vectors.append((uid, cid)),
    )
    deleted_chunk_vectors = []
    monkeypatch.setattr(
        merge_conversations,
        "delete_transcript_chunk_vectors",
        lambda uid, cid: deleted_chunk_vectors.append((uid, cid)),
    )
    monkeypatch.setattr(merge_conversations.conversations_db, "delete_conversation_photos", lambda *a, **k: None)
    monkeypatch.setattr(merge_conversations, "delete_conversation_audio_files", lambda *a, **k: None)
    deleted_convs = []
    monkeypatch.setattr(
        merge_conversations.conversations_db,
        "delete_conversation",
        lambda uid, cid: deleted_convs.append((uid, cid)),
    )
    monkeypatch.setitem(sys.modules, "database.action_items", action_items_db)

    ok = merge_conversations._cleanup_merged_target_after_failure(UID, "merged-conv-1")

    assert ok is True
    service.retract_conversation_memories.assert_called_once_with(UID, "merged-conv-1")
    assert deleted_tasks_for_conv == [(UID, "merged-conv-1")]
    assert cancelled_reminders == [(UID, ["merged-task-1"])]
    assert deleted_task_vectors == [(UID, ["merged-task-1"])]
    assert deleted_conv_vectors == [(UID, "merged-conv-1")]
    assert deleted_chunk_vectors == [(UID, "merged-conv-1")]
    assert deleted_convs == [(UID, "merged-conv-1")]


def test_update_conversation_action_item_description_syncs_vector_and_reminder(monkeypatch, isolated_modules):
    conversations_router = isolated_modules.router
    updated_db = []
    updated_vectors = []
    synced_reminders = []

    conversation = SimpleNamespace(structured=SimpleNamespace(action_items=[_StructuredActionItem("Old description")]))
    monkeypatch.setattr(conversations_router, "_get_valid_conversation_by_id", lambda uid, cid: conversation)
    monkeypatch.setattr(conversations_router, "deserialize_conversation", lambda convo: convo)
    monkeypatch.setattr(
        conversations_router.conversations_db,
        "update_conversation_action_items",
        lambda uid, cid, items: None,
    )
    monkeypatch.setattr(
        conversations_router.action_items_db,
        "get_action_items_by_conversation",
        lambda uid, cid: [
            {
                "id": "task-armed",
                "description": "Old description",
                "due_at": DUE,
                "completed": False,
                "status": "accepted",
                "deleted": False,
            },
            {
                "id": "task-completed",
                "description": "Old description",
                "due_at": DUE,
                "completed": True,
            },
        ],
    )
    monkeypatch.setattr(
        conversations_router.action_items_db,
        "update_action_item",
        lambda uid, item_id, payload: updated_db.append((uid, item_id, payload)),
    )
    assert "upsert_action_item_vector" in isolated_modules.real_vector_db_funcs
    assert conversations_router.upsert_action_item_vector is isolated_modules.vector_db.upsert_action_item_vector
    monkeypatch.setattr(
        conversations_router,
        "upsert_action_item_vector",
        lambda uid, item_id, desc: updated_vectors.append((uid, item_id, desc)),
    )
    notifications = ModuleType("utils.notifications")
    notifications.sync_action_item_reminder = lambda **kwargs: synced_reminders.append(kwargs)
    monkeypatch.setitem(sys.modules, "utils.notifications", notifications)

    res = conversations_router.update_action_item_description(
        "conv-1",
        UpdateActionItemDescriptionRequest(old_description="Old description", description="New description"),
        uid=UID,
    )

    assert res == {"status": "Ok"}
    assert updated_db == [
        (UID, "task-armed", {"description": "New description"}),
        (UID, "task-completed", {"description": "New description"}),
    ]
    assert updated_vectors == [
        (UID, "task-armed", "New description"),
        (UID, "task-completed", "New description"),
    ]
    assert synced_reminders == [
        {
            "user_id": UID,
            "action_item_id": "task-armed",
            "description": "New description",
            "completed": False,
            "due_at": DUE,
            "status": "accepted",
            "deleted": False,
        }
    ]
