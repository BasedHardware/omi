"""
Tests for skipping apps during conversation reprocessing (#4641).

Verifies that:
- _trigger_apps is NOT called when is_reprocess=True
- _trigger_apps IS called when is_reprocess=False (normal processing)
- postprocess path passes is_reprocess=True
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch, call

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub database package and submodules to avoid heavy imports.
if "database" not in sys.modules:
    database_mod = _stub_module("database")
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

# Stub utils modules that pull in external dependencies.
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

pc_module = importlib.import_module("utils.conversations.process_conversation")


def _make_fake_structured():
    """Return a fake structured result that passes the 'not discarded' gate."""
    structured = MagicMock()
    structured.title = "Test conversation"
    structured.overview = "A test overview."
    structured.action_items = []
    structured.events = []
    structured.category = None
    return structured


def _make_fake_conversation():
    """Return a fake Conversation object."""
    conv = MagicMock()
    conv.id = "test-conv-id"
    conv.get_person_ids.return_value = []
    conv.structured = _make_fake_structured()
    conv.apps_results = []
    conv.photos = []
    conv.folder_id = None
    conv.private_cloud_sync_enabled = False
    conv.suggested_summarization_apps = []
    conv.get_transcript.return_value = "Hello world"
    conv.dict.return_value = {}
    return conv


class TestReprocessSkipsApps:
    """Verify _trigger_apps is skipped during reprocessing."""

    def test_trigger_apps_not_called_when_is_reprocess_true(self):
        """When is_reprocess=True, _trigger_apps must NOT be called."""
        conv = _make_fake_conversation()
        fake_structured = (_make_fake_structured(), False)  # (structured, discarded=False)

        with (
            patch.object(pc_module, '_get_structured', return_value=fake_structured),
            patch.object(pc_module, '_get_conversation_obj', return_value=conv),
            patch.object(pc_module, '_trigger_apps') as mock_trigger_apps,
            patch.object(pc_module, 'save_structured_vector'),
            patch.object(pc_module, '_extract_memories'),
            patch.object(pc_module, '_extract_trends'),
            patch.object(pc_module, '_save_action_items'),
            patch.object(pc_module, '_update_goal_progress'),
            patch.object(pc_module, 'conversations_db'),
            patch.object(pc_module, 'redis_db'),
        ):
            pc_module.process_conversation(
                uid="test-uid",
                language_code="en",
                conversation=conv,
                force_process=True,
                is_reprocess=True,
            )
            mock_trigger_apps.assert_not_called()

    def test_trigger_apps_called_when_is_reprocess_false(self):
        """When is_reprocess=False, _trigger_apps MUST be called."""
        conv = _make_fake_conversation()
        fake_structured = (_make_fake_structured(), False)

        with (
            patch.object(pc_module, '_get_structured', return_value=fake_structured),
            patch.object(pc_module, '_get_conversation_obj', return_value=conv),
            patch.object(pc_module, '_trigger_apps') as mock_trigger_apps,
            patch.object(pc_module, 'save_structured_vector'),
            patch.object(pc_module, '_extract_memories'),
            patch.object(pc_module, '_extract_trends'),
            patch.object(pc_module, '_save_action_items'),
            patch.object(pc_module, '_update_goal_progress'),
            patch.object(pc_module, 'conversations_db'),
            patch.object(pc_module, 'redis_db'),
            patch.object(pc_module, 'folders_db'),
            patch.object(pc_module, 'record_usage'),
            patch.object(pc_module, 'conversation_created_webhook'),
            patch.object(pc_module, 'update_personas_async'),
        ):
            pc_module.process_conversation(
                uid="test-uid",
                language_code="en",
                conversation=conv,
                force_process=False,
                is_reprocess=False,
            )
            mock_trigger_apps.assert_called_once()

    def test_trigger_apps_called_for_normal_force_process(self):
        """force_process=True with is_reprocess=False still calls _trigger_apps."""
        conv = _make_fake_conversation()
        fake_structured = (_make_fake_structured(), False)

        with (
            patch.object(pc_module, '_get_structured', return_value=fake_structured),
            patch.object(pc_module, '_get_conversation_obj', return_value=conv),
            patch.object(pc_module, '_trigger_apps') as mock_trigger_apps,
            patch.object(pc_module, 'save_structured_vector'),
            patch.object(pc_module, '_extract_memories'),
            patch.object(pc_module, '_extract_trends'),
            patch.object(pc_module, '_save_action_items'),
            patch.object(pc_module, '_update_goal_progress'),
            patch.object(pc_module, 'conversations_db'),
            patch.object(pc_module, 'redis_db'),
            patch.object(pc_module, 'conversation_created_webhook'),
            patch.object(pc_module, 'update_personas_async'),
            patch.object(pc_module, 'record_usage'),
        ):
            pc_module.process_conversation(
                uid="test-uid",
                language_code="en",
                conversation=conv,
                force_process=True,
                is_reprocess=False,
            )
            mock_trigger_apps.assert_called_once()


class TestPostprocessPassesIsReprocess:
    """Verify postprocess_conversation passes is_reprocess=True."""

    def test_postprocess_source_has_is_reprocess_true(self):
        """The postprocess call site must pass is_reprocess=True."""
        import pathlib

        source_path = (
            pathlib.Path(__file__).resolve().parents[2] / "utils" / "conversations" / "postprocess_conversation.py"
        )
        source = source_path.read_text()
        # Verify the process_conversation call includes is_reprocess=True
        assert "is_reprocess=True" in source, (
            "postprocess_conversation must pass is_reprocess=True to process_conversation "
            "to skip already-completed steps (apps, folder, webhook)"
        )
