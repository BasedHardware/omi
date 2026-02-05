"""
Unit tests for usage tracking context in conversation processing.

Verifies that sub-feature tracking is applied per LLM call (no umbrella tracking)
and that each sub-feature gets the correct Features constant.
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
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub database package and submodules to avoid heavy imports.
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

from utils.llm import usage_tracker

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

process_conversation = importlib.import_module("utils.conversations.process_conversation")


def test_sub_feature_constants_exist():
    """Verify all sub-feature tracking constants are defined."""
    assert hasattr(usage_tracker.Features, 'CONVERSATION_DISCARD')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_STRUCTURE')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_ACTION_ITEMS')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_FOLDER')
    assert hasattr(usage_tracker.Features, 'CONVERSATION_APPS')
    # Verify they're distinct from the umbrella
    assert usage_tracker.Features.CONVERSATION_DISCARD != usage_tracker.Features.CONVERSATION_PROCESSING
    assert usage_tracker.Features.CONVERSATION_STRUCTURE != usage_tracker.Features.CONVERSATION_PROCESSING


def test_discard_call_uses_discard_feature_tracking():
    """Verify should_discard_conversation is called within CONVERSATION_DISCARD context."""
    captured = {}

    def fake_discard(*args, **kwargs):
        captured["ctx"] = usage_tracker.get_current_context()
        return False  # Don't discard

    # Create a minimal conversation mock without external_data triggering CalendarMeetingContext
    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "short transcript"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None  # Prevent CalendarMeetingContext parsing

    # Mock notification_db
    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    # Mock action_items_db
    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    # Patch on the process_conversation module (where it's imported/bound)
    with patch.object(process_conversation, "should_discard_conversation", fake_discard), patch.object(
        process_conversation, "get_transcript_structure", MagicMock()
    ):
        try:
            process_conversation._get_structured("user-1", "en", conversation)
        except Exception:
            pass  # We only care about the context capture

    assert captured.get("ctx") is not None
    assert captured["ctx"].feature == usage_tracker.Features.CONVERSATION_DISCARD
    assert captured["ctx"].uid == "user-1"


def test_track_usage_context_resets_after_call():
    """Verify context is properly reset after each sub-feature tracking block."""
    assert usage_tracker.get_current_context() is None

    with usage_tracker.track_usage("user-test", usage_tracker.Features.CONVERSATION_STRUCTURE):
        ctx = usage_tracker.get_current_context()
        assert ctx.feature == usage_tracker.Features.CONVERSATION_STRUCTURE

    # Context should be reset after exiting
    assert usage_tracker.get_current_context() is None


def test_track_usage_context_resets_on_exception():
    """Verify context is properly reset even when an exception occurs."""
    assert usage_tracker.get_current_context() is None

    with pytest.raises(RuntimeError):
        with usage_tracker.track_usage("user-err", usage_tracker.Features.CONVERSATION_DISCARD):
            raise RuntimeError("boom")

    assert usage_tracker.get_current_context() is None


def test_no_umbrella_conversation_processing_tracking():
    """Verify _get_structured no longer wraps everything in CONVERSATION_PROCESSING."""
    captured_contexts = []

    # Patch track_usage on the process_conversation module (where it's imported)
    original_track = process_conversation.track_usage

    from contextlib import contextmanager

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append(feature)
        with original_track(uid, feature):
            yield

    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "short transcript"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None

    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    llm_conv.should_discard_conversation = MagicMock(return_value=False)
    llm_conv.get_transcript_structure = MagicMock()

    with patch.object(process_conversation, "track_usage", spy_track_usage):
        try:
            process_conversation._get_structured("user-2", "en", conversation)
        except Exception:
            pass

    # The umbrella CONVERSATION_PROCESSING should NOT appear
    assert usage_tracker.Features.CONVERSATION_PROCESSING not in captured_contexts
    # Sub-features should appear
    assert (
        usage_tracker.Features.CONVERSATION_DISCARD in captured_contexts
        or usage_tracker.Features.CONVERSATION_STRUCTURE in captured_contexts
    )
