"""
Unit test for #4626: AttributeError in knowledge graph extraction.

Bug: get_user_store_recording_permission(uid) returns bool, code called
.get('name', 'User') on it → AttributeError.

Fix: use get_user_name() from database/auth.py which reads display_name
from Firebase Auth — the canonical way to get user names in this codebase.
"""

import os
import sys
import types
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_stub(name: str) -> types.ModuleType:
    """Get or create a stub module without replacing existing ones."""
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod
    return sys.modules[name]


def _setup_stubs():
    """Set up minimal module stubs needed to import process_conversation."""
    database_mod = _ensure_stub("database")
    if not hasattr(database_mod, "__path__"):
        database_mod.__path__ = []
    for submodule in [
        "redis_db",
        "memories",
        "conversations",
        "notifications",
        "users",
        "tasks",
        "trends",
        "action_items",
        "folders",
        "calendar_meetings",
        "vector_db",
        "apps",
        "llm_usage",
        "_client",
        "auth",
    ]:
        mod = _ensure_stub(f"database.{submodule}")
        setattr(database_mod, submodule, mod)

    vector_db_mod = sys.modules["database.vector_db"]
    for attr in [
        "find_similar_memories",
        "upsert_memory_vector",
        "delete_memory_vector",
        "upsert_vector2",
        "update_vector_metadata",
    ]:
        if not hasattr(vector_db_mod, attr):
            setattr(vector_db_mod, attr, MagicMock())

    apps_mod = sys.modules["database.apps"]
    for attr in ["record_app_usage", "get_omi_personas_by_uid_db", "get_app_by_id_db"]:
        if not hasattr(apps_mod, attr):
            setattr(apps_mod, attr, MagicMock())

    llm_usage_mod = sys.modules["database.llm_usage"]
    if not hasattr(llm_usage_mod, "record_llm_usage"):
        llm_usage_mod.record_llm_usage = MagicMock()

    memories_stub = sys.modules["database.memories"]
    if not hasattr(memories_stub, "set_memory_kg_extracted"):
        memories_stub.set_memory_kg_extracted = MagicMock()

    client_mod = sys.modules["database._client"]
    if not hasattr(client_mod, "document_id_from_seed"):
        client_mod.document_id_from_seed = MagicMock(return_value="doc-id")

    auth_mod = sys.modules["database.auth"]
    if not hasattr(auth_mod, "get_user_name"):
        auth_mod.get_user_name = MagicMock(return_value="The User")
    if not hasattr(auth_mod, "get_user_from_uid"):
        auth_mod.get_user_from_uid = MagicMock()
    # Redis stubs needed by database.auth
    redis_mod = sys.modules["database.redis_db"]
    if not hasattr(redis_mod, "cache_user_name"):
        redis_mod.cache_user_name = MagicMock()
    if not hasattr(redis_mod, "get_cached_user_name"):
        redis_mod.get_cached_user_name = MagicMock(return_value=None)

    for name in [
        "utils.apps",
        "utils.analytics",
        "utils.llm.memories",
        "utils.llm.conversation_processing",
        "utils.llm.external_integrations",
        "utils.llm.trends",
        "utils.llm.goals",
        "utils.llm.chat",
        "utils.llm.clients",
        "utils.llm.knowledge_graph",
        "utils.notifications",
        "utils.other.hume",
        "utils.retrieval.rag",
        "utils.webhooks",
        "utils.task_sync",
        "utils.other.storage",
    ]:
        _ensure_stub(name)

    for mod_name, attrs in [
        ("utils.apps", ["get_available_apps", "update_personas_async", "sync_update_persona_prompt"]),
        ("utils.analytics", ["record_usage"]),
        ("utils.llm.memories", ["resolve_memory_conflict", "extract_memories_from_text", "new_memories_extractor"]),
        (
            "utils.llm.conversation_processing",
            [
                "get_transcript_structure",
                "get_app_result",
                "should_discard_conversation",
                "select_best_app_for_conversation",
                "get_suggested_apps_for_conversation",
                "get_reprocess_transcript_structure",
                "assign_conversation_to_folder",
                "extract_action_items",
            ],
        ),
        ("utils.llm.external_integrations", ["summarize_experience_text", "get_message_structure"]),
        (
            "utils.llm.chat",
            [
                "retrieve_metadata_from_text",
                "retrieve_metadata_from_message",
                "retrieve_metadata_fields_from_transcript",
                "obtain_emotional_message",
            ],
        ),
        (
            "utils.notifications",
            ["send_notification", "send_important_conversation_message", "send_action_item_data_message"],
        ),
        ("utils.other.hume", ["get_hume", "HumeJobCallbackModel", "HumeJobModelPredictionResponseModel"]),
    ]:
        mod = sys.modules[mod_name]
        for attr in attrs:
            if not hasattr(mod, attr):
                setattr(mod, attr, MagicMock())

    for mod_name, attr_name in [
        ("utils.llm.trends", "trends_extractor"),
        ("utils.llm.goals", "extract_and_update_goal_progress"),
        ("utils.llm.clients", "generate_embedding"),
        ("utils.llm.knowledge_graph", "extract_knowledge_from_memory"),
        ("utils.retrieval.rag", "retrieve_rag_conversation_context"),
        ("utils.webhooks", "conversation_created_webhook"),
        ("utils.task_sync", "auto_sync_action_items_batch"),
        ("utils.other.storage", "precache_conversation_audio"),
    ]:
        mod = sys.modules[mod_name]
        if not hasattr(mod, attr_name):
            setattr(mod, attr_name, MagicMock())


def _get_process_conversation():
    """Lazily import process_conversation module."""
    import importlib

    _setup_stubs()
    return importlib.import_module("utils.conversations.process_conversation")


def test_kg_extraction_uses_get_user_name_from_auth():
    """Regression test for #4626: verify get_user_name from database.auth is used.

    The old code called get_user_store_recording_permission(uid) which returns a bool,
    then called .get('name', 'User') on it — raising AttributeError.
    The correct fix uses get_user_name() from database/auth.py which reads
    display_name from Firebase Auth.
    """
    import inspect

    pc = _get_process_conversation()
    source = inspect.getsource(pc._extract_memories_inner)
    assert "get_user_name" in source, "Should call get_user_name from database.auth"
    assert (
        "get_user_store_recording_permission" not in source
    ), "Should NOT call get_user_store_recording_permission (returns bool, not user name)"
    assert (
        "get_user_profile" not in source
    ), "Should NOT call get_user_profile (Firestore users collection has no 'name' field)"


def test_kg_router_uses_get_user_name_from_auth():
    """Verify knowledge_graph router also uses get_user_name, not get_user_profile."""
    from pathlib import Path

    router_path = Path(__file__).resolve().parent.parent.parent / "routers" / "knowledge_graph.py"
    source = router_path.read_text()
    assert "get_user_name" in source, "Router should call get_user_name from database.auth"
    assert "get_user_profile" not in source, "Router should NOT call get_user_profile (Firestore has no 'name' field)"


def test_bool_return_would_crash_with_get():
    """Demonstrate that calling .get() on a bool raises AttributeError (the original bug)."""
    permission_bool = True
    with pytest.raises(AttributeError):
        permission_bool.get('name', 'User')
