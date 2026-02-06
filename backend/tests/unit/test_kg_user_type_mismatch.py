"""
Tests for issue #4626: AttributeError in knowledge graph extraction.

get_user_store_recording_permission() returns a bool, but the KG extraction
code treated it as a user dict and called .get('name', 'User') on it.
Fix: use get_user_profile() which returns a dict.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub database package and submodules
database_mod = _stub_module("database")
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
    "chat",
]:
    mod = _stub_module(f"database.{submodule}")
    setattr(database_mod, submodule, mod)

vector_db_mod = sys.modules["database.vector_db"]
for attr in [
    "find_similar_memories",
    "upsert_memory_vector",
    "delete_memory_vector",
    "upsert_vector2",
    "update_vector_metadata",
]:
    setattr(vector_db_mod, attr, MagicMock())

apps_mod = sys.modules["database.apps"]
for attr in ["record_app_usage", "get_omi_personas_by_uid_db", "get_app_by_id_db"]:
    setattr(apps_mod, attr, MagicMock())

llm_usage_mod = sys.modules["database.llm_usage"]
llm_usage_mod.record_llm_usage = MagicMock()

client_mod = sys.modules["database._client"]
client_mod.document_id_from_seed = MagicMock(return_value="doc-id")

users_mod = sys.modules["database.users"]
users_mod.get_user_store_recording_permission = MagicMock(return_value=True)
users_mod.get_user_profile = MagicMock(return_value={"name": "Alice", "store_recording_permission": True})

memories_mod = sys.modules["database.memories"]
memories_mod.set_memory_kg_extracted = MagicMock()
memories_mod.get_memory_ids_for_conversation = MagicMock(return_value=[])
memories_mod.delete_memories_for_conversation = MagicMock()
memories_mod.get_memory = MagicMock(return_value=None)
memories_mod.save_memories = MagicMock()
memories_mod.delete_memory = MagicMock()

# Stub utils modules
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
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

utils_apps = sys.modules["utils.apps"]
for attr in ["get_available_apps", "update_personas_async", "sync_update_persona_prompt"]:
    setattr(utils_apps, attr, MagicMock())

utils_analytics = sys.modules["utils.analytics"]
utils_analytics.record_usage = MagicMock()

llm_memories = sys.modules["utils.llm.memories"]
for attr in ["resolve_memory_conflict", "extract_memories_from_text", "new_memories_extractor"]:
    setattr(llm_memories, attr, MagicMock())

llm_conv = sys.modules["utils.llm.conversation_processing"]
for attr in [
    "get_transcript_structure",
    "get_app_result",
    "should_discard_conversation",
    "select_best_app_for_conversation",
    "get_suggested_apps_for_conversation",
    "get_reprocess_transcript_structure",
    "assign_conversation_to_folder",
    "extract_action_items",
]:
    setattr(llm_conv, attr, MagicMock())

llm_external = sys.modules["utils.llm.external_integrations"]
for attr in ["summarize_experience_text", "get_message_structure"]:
    setattr(llm_external, attr, MagicMock())

llm_trends = sys.modules["utils.llm.trends"]
llm_trends.trends_extractor = MagicMock()

llm_goals = sys.modules["utils.llm.goals"]
llm_goals.extract_and_update_goal_progress = MagicMock()

llm_chat = sys.modules["utils.llm.chat"]
for attr in [
    "retrieve_metadata_from_text",
    "retrieve_metadata_from_message",
    "retrieve_metadata_fields_from_transcript",
    "obtain_emotional_message",
]:
    setattr(llm_chat, attr, MagicMock())

llm_clients = sys.modules["utils.llm.clients"]
llm_clients.generate_embedding = MagicMock()

llm_kg = sys.modules["utils.llm.knowledge_graph"]
llm_kg.extract_knowledge_from_memory = MagicMock()

utils_notifications = sys.modules["utils.notifications"]
for attr in ["send_notification", "send_important_conversation_message", "send_action_item_data_message"]:
    setattr(utils_notifications, attr, MagicMock())

utils_hume = sys.modules["utils.other.hume"]
for attr in ["get_hume", "HumeJobCallbackModel", "HumeJobModelPredictionResponseModel"]:
    setattr(utils_hume, attr, MagicMock())

utils_rag = sys.modules["utils.retrieval.rag"]
utils_rag.retrieve_rag_conversation_context = MagicMock()

utils_webhooks = sys.modules["utils.webhooks"]
utils_webhooks.conversation_created_webhook = MagicMock()

utils_task_sync = sys.modules["utils.task_sync"]
utils_task_sync.auto_sync_action_items_batch = MagicMock()

utils_storage = sys.modules["utils.other.storage"]
utils_storage.precache_conversation_audio = MagicMock()

import importlib

process_conversation = importlib.import_module("utils.conversations.process_conversation")
from models.memories import MemoryDB


def _make_conversation_mock():
    """Create a mock Conversation that passes through _extract_memories_inner."""
    conv = MagicMock()
    conv.id = "conv-test"
    conv.source = "audio"  # not external_integration
    conv.transcript_segments = []
    conv.is_locked = False
    return conv


def _make_memory_mock(memory_id="mem-1", content="Test memory", kg_extracted=False):
    """Create a mock that behaves like a MemoryDB for the KG extraction block."""
    m = MagicMock()
    m.id = memory_id
    m.content = content
    m.category.value = "core"
    m.kg_extracted = kg_extracted
    m.is_locked = False
    m.dict.return_value = {"id": memory_id, "content": content, "category": "core"}
    return m


def _setup_extract_memories(memory_mock):
    """Configure stubs so _extract_memories_inner reaches the KG block with one memory."""
    llm_memories.new_memories_extractor.return_value = [MagicMock()]  # raw Memory
    vector_db_mod.find_similar_memories.return_value = []
    memories_mod.get_memory_ids_for_conversation.return_value = []
    memories_mod.save_memories.reset_mock()
    utils_analytics.record_usage.reset_mock()


class TestKnowledgeGraphUserLookup:
    """Tests for #4626: KG extraction must use get_user_profile, not get_user_store_recording_permission."""

    def test_kg_extraction_calls_get_user_profile_not_permission(self):
        """The KG extraction path must call get_user_profile() to get user name."""
        import inspect

        source = inspect.getsource(process_conversation._extract_memories_inner)
        # Must NOT call the bool-returning function for user lookup
        assert "get_user_store_recording_permission" not in source, (
            "KG extraction still calls get_user_store_recording_permission (returns bool); "
            "should use get_user_profile (returns dict)"
        )
        # Must call get_user_profile
        assert "get_user_profile" in source

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_no_attribute_error_when_permission_true(self, mock_from_memory):
        """Regression: calling .get('name') on True raised AttributeError."""
        uid = "test-user-123"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-1", "Test memory content")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        users_mod.get_user_profile.reset_mock()
        users_mod.get_user_profile.return_value = {"name": "Alice", "store_recording_permission": True}
        llm_kg.extract_knowledge_from_memory.reset_mock()
        memories_mod.set_memory_kg_extracted.reset_mock()

        # This would raise AttributeError before the fix (True.get('name'))
        process_conversation._extract_memories_inner(uid, conv)

        # Verify get_user_profile was called (not get_user_store_recording_permission)
        users_mod.get_user_profile.assert_called_once_with(uid)
        # Verify KG extraction was called with the user's name
        llm_kg.extract_knowledge_from_memory.assert_called_once_with(uid, "Test memory content", "mem-1", "Alice")

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_falls_back_to_user_when_no_name(self, mock_from_memory):
        """When user profile has no name field, should default to 'User'."""
        uid = "uid-2"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-2", "Another memory")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        users_mod.get_user_profile.reset_mock()
        users_mod.get_user_profile.return_value = {"store_recording_permission": True}
        llm_kg.extract_knowledge_from_memory.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        llm_kg.extract_knowledge_from_memory.assert_called_once_with(uid, "Another memory", "mem-2", "User")

    @patch("models.memories.MemoryDB.from_memory")
    def test_kg_extraction_handles_empty_profile(self, mock_from_memory):
        """When get_user_profile returns empty dict, should default to 'User'."""
        uid = "uid-3"
        conv = _make_conversation_mock()
        mem_db = _make_memory_mock("mem-3", "Memory three")
        mock_from_memory.return_value = mem_db

        _setup_extract_memories(mem_db)
        users_mod.get_user_profile.reset_mock()
        users_mod.get_user_profile.return_value = {}
        llm_kg.extract_knowledge_from_memory.reset_mock()

        process_conversation._extract_memories_inner(uid, conv)

        llm_kg.extract_knowledge_from_memory.assert_called_once_with(uid, "Memory three", "mem-3", "User")
