"""
Unit test for #4626: AttributeError in knowledge graph extraction.

The bug: get_user_store_recording_permission() returns bool, but the code
called .get('name', 'User') on the result, crashing with AttributeError
when the bool was True.

Fix: use get_user_profile() which returns a dict.
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


def test_kg_extraction_uses_get_user_profile_not_permission():
    """Regression test for #4626: verify get_user_profile is used, not get_user_store_recording_permission.

    The old code called get_user_store_recording_permission(uid) which returns a bool,
    then called .get('name', 'User') on it — raising AttributeError for every user
    whose store_recording_permission is True.
    """
    import inspect

    pc = _get_process_conversation()
    source = inspect.getsource(pc._extract_memories_inner)
    assert "get_user_profile" in source, "Should call get_user_profile to get user dict"
    assert (
        "get_user_store_recording_permission" not in source
    ), "Should NOT call get_user_store_recording_permission (returns bool, not dict)"


def test_bool_return_would_crash_with_get():
    """Demonstrate that calling .get() on a bool raises AttributeError (the original bug)."""
    permission_bool = True
    with pytest.raises(AttributeError):
        permission_bool.get('name', 'User')


def test_dict_return_works_with_get():
    """Verify the fix: calling .get() on a dict from get_user_profile works correctly."""
    user_profile = {"name": "Alice", "uid": "u1"}
    assert user_profile.get('name', 'User') == "Alice"

    # Empty dict (user not found) is falsy, defaults correctly
    empty_profile = {}
    user_name = empty_profile.get('name', 'User') if empty_profile else 'User'
    assert user_name == 'User'
