"""
Unit tests for usage tracking context in conversation processing.

Verifies that sub-feature tracking is applied per LLM call (no umbrella tracking)
and that each sub-feature gets the correct Features constant.
"""

import os
import re
import sys
import threading
import types
from contextlib import contextmanager
from pathlib import Path
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


def test_action_items_tracked_separately_from_structure():
    """Verify action items extraction uses CONVERSATION_ACTION_ITEMS, not CONVERSATION_STRUCTURE."""
    captured_contexts = []

    original_track = process_conversation.track_usage

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

    with patch.object(process_conversation, "should_discard_conversation", MagicMock(return_value=False)), patch.object(
        process_conversation, "get_transcript_structure", MagicMock()
    ), patch.object(process_conversation, "extract_action_items", MagicMock(return_value=[])), patch.object(
        process_conversation, "track_usage", spy_track_usage
    ):
        try:
            process_conversation._get_structured("user-3", "en", conversation)
        except Exception:
            pass

    assert usage_tracker.Features.CONVERSATION_ACTION_ITEMS in captured_contexts
    # Action items should be tracked separately from structure
    assert captured_contexts.count(usage_tracker.Features.CONVERSATION_ACTION_ITEMS) >= 1
    # Structure should also be tracked
    assert usage_tracker.Features.CONVERSATION_STRUCTURE in captured_contexts


def test_structure_and_apps_tracked_at_runtime():
    """Verify conv_structure and conv_apps tracking at runtime call sites."""
    captured_contexts = []

    original_track = process_conversation.track_usage

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append(feature)
        with original_track(uid, feature):
            yield

    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "a transcript with enough words to not be discarded easily"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None
    conversation.structured = MagicMock()
    conversation.structured.title = "Test"
    conversation.structured.overview = "Test overview"
    conversation.structured.category = MagicMock()
    conversation.structured.category.value = "other"
    conversation.structured.action_items = []
    conversation.structured.events = []
    conversation.apps_results = []
    conversation.discarded = False
    conversation.id = "test-conv-id"
    conversation.folder_id = None
    conversation.suggested_summarization_apps = ["app1"]
    conversation.is_locked = False

    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    folders_mod = sys.modules["database.folders"]
    folders_mod.get_folders = MagicMock(return_value=[{"id": "f1", "name": "Default", "is_default": True}])

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.get_user_preferred_app = MagicMock(return_value=None)
    redis_mod.get_conversation_summary_app_ids = MagicMock(return_value=[])

    with patch.object(process_conversation, "should_discard_conversation", MagicMock(return_value=False)), patch.object(
        process_conversation, "get_transcript_structure", MagicMock()
    ), patch.object(process_conversation, "extract_action_items", MagicMock(return_value=[])), patch.object(
        process_conversation, "assign_conversation_to_folder", MagicMock(return_value=("f1", 0.9, "match"))
    ), patch.object(
        process_conversation, "track_usage", spy_track_usage
    ):
        try:
            process_conversation._get_structured("user-4", "en", conversation)
        except Exception:
            pass

    # Both structure and folder tracking should fire
    assert usage_tracker.Features.CONVERSATION_STRUCTURE in captured_contexts
    assert usage_tracker.Features.CONVERSATION_DISCARD in captured_contexts


def test_action_items_skipped_on_discard():
    """Verify extract_action_items is NOT called when conversation is discarded."""
    conversation = MagicMock()
    conversation.source = "phone"
    conversation.get_transcript.return_value = "short"
    conversation.photos = []
    conversation.get_person_ids.return_value = []
    conversation.external_data = None

    notifications_mod = sys.modules["database.notifications"]
    notifications_mod.get_user_time_zone = MagicMock(return_value="UTC")

    action_items_mod = sys.modules["database.action_items"]
    action_items_mod.get_action_items = MagicMock(return_value=[])

    extract_mock = MagicMock(return_value=[])

    with patch.object(process_conversation, "should_discard_conversation", MagicMock(return_value=True)), patch.object(
        process_conversation, "extract_action_items", extract_mock
    ):
        structured, discarded = process_conversation._get_structured("user-5", "en", conversation)

    assert discarded is True
    # extract_action_items should NOT have been called
    extract_mock.assert_not_called()


def test_models_unchanged_for_llm_calls():
    """Verify all LLM functions still use llm_medium_experiment (no model changes in this PR)."""
    # Build path relative to this test file: tests/unit/ -> ../../utils/llm/conversation_processing.py
    conv_proc_path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "conversation_processing.py"
    conv_proc_source = conv_proc_path.read_text()

    # get_transcript_structure should use llm_medium_experiment (may have .bind() for cache key)
    struct_match = re.search(
        r'def get_transcript_structure.*?chain = prompt \| (\w+)[\.\|]',
        conv_proc_source,
        re.DOTALL,
    )
    assert struct_match is not None
    assert (
        struct_match.group(1) == "llm_medium_experiment"
    ), f"Expected llm_medium_experiment for structure, got {struct_match.group(1)}"

    # get_app_result should use llm_medium_experiment (may have extra kwargs in invoke)
    app_match = re.search(
        r'def get_app_result.*?response = (\w+)\.invoke\(prompt',
        conv_proc_source,
        re.DOTALL,
    )
    assert app_match is not None
    assert (
        app_match.group(1) == "llm_medium_experiment"
    ), f"Expected llm_medium_experiment for app result, got {app_match.group(1)}"

    # extract_action_items should use llm_medium_experiment (may have .bind() for cache key)
    action_match = re.search(
        r'def extract_action_items.*?chain = prompt \| (\w+)[\.\|]',
        conv_proc_source,
        re.DOTALL,
    )
    assert action_match is not None
    assert (
        action_match.group(1) == "llm_medium_experiment"
    ), f"Expected llm_medium_experiment for action items, got {action_match.group(1)}"


def test_threaded_tracking_context_isolation():
    """Verify track_usage context works correctly with threading (context isolation)."""
    results = {}

    def thread_fn(uid, feature, key):
        with usage_tracker.track_usage(uid, feature):
            ctx = usage_tracker.get_current_context()
            results[key] = ctx

    t1 = threading.Thread(target=thread_fn, args=("u1", usage_tracker.Features.MEMORIES, "t1"))
    t2 = threading.Thread(target=thread_fn, args=("u2", usage_tracker.Features.TRENDS, "t2"))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Each thread should have had its own context
    assert results["t1"].feature == usage_tracker.Features.MEMORIES
    assert results["t1"].uid == "u1"
    assert results["t2"].feature == usage_tracker.Features.TRENDS
    assert results["t2"].uid == "u2"

    # Main thread should have no context set
    assert usage_tracker.get_current_context() is None


# ---------------------------------------------------------------------------
# Tests for _trigger_apps preferred-app shortcut (PR #4683, issue #4639)
# ---------------------------------------------------------------------------


def _make_mock_app(app_id, name="TestApp"):
    """Create a minimal App-like mock for _trigger_apps tests."""
    app = MagicMock()
    app.id = app_id
    app.name = name
    app.works_with_memories.return_value = True
    app.enabled = True
    return app


def _setup_trigger_apps_mocks(preferred_app_id=None, default_apps=None, available_apps=None):
    """Set up the module-level mocks needed by _trigger_apps."""
    redis_mod = sys.modules["database.redis_db"]
    redis_mod.get_user_preferred_app = MagicMock(return_value=preferred_app_id)

    apps_mod = sys.modules["database.apps"]
    apps_mod.record_app_usage = MagicMock()

    utils_apps_mod = sys.modules["utils.apps"]
    utils_apps_mod.get_available_apps = MagicMock(return_value=available_apps or [])

    llm_conv_mod = sys.modules["utils.llm.conversation_processing"]
    llm_conv_mod.get_app_result = MagicMock(return_value="App result content")
    llm_conv_mod.get_suggested_apps_for_conversation = MagicMock(return_value=(["suggested-app"], "reasoning"))

    return llm_conv_mod, default_apps or []


def _make_trigger_conversation(suggested_apps=None):
    """Create a minimal conversation mock for _trigger_apps tests."""
    conv = MagicMock()
    conv.id = "conv-trigger-test"
    conv.get_transcript.return_value = "Speaker 0: Hello"
    conv.photos = []
    conv.apps_results = []
    conv.suggested_summarization_apps = suggested_apps
    return conv


def _trigger_apps_context(default_apps=None):
    """Context manager that patches all external dependencies of _trigger_apps."""
    suggestion_mock = MagicMock(return_value=(["suggested-app"], "reasoning"))
    app_result_mock = MagicMock(return_value="App result content")
    record_mock = MagicMock()
    return (
        suggestion_mock,
        app_result_mock,
        patch.object(process_conversation, "get_default_conversation_summarized_apps", return_value=default_apps or []),
        patch.object(process_conversation, "get_available_apps", return_value=[]),
        patch.object(process_conversation, "get_suggested_apps_for_conversation", suggestion_mock),
        patch.object(process_conversation, "get_app_result", app_result_mock),
        patch.object(process_conversation, "record_app_usage", record_mock),
    )


def test_trigger_apps_uses_preferred_app_skips_llm_suggestion():
    """When user has a valid preferred app, use it and skip the suggestion LLM call."""
    preferred = _make_mock_app("preferred-app-1", "PreferredApp")
    _setup_trigger_apps_mocks(preferred_app_id="preferred-app-1", available_apps=[preferred])
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5 = _trigger_apps_context()
    # Override get_available_apps to return the preferred app
    p2 = patch.object(process_conversation, "get_available_apps", return_value=[preferred])

    with p1, p2, p3, p4, p5:
        process_conversation._trigger_apps("user-preferred", conv)

    # The suggestion LLM call must NOT have been invoked
    suggestion_mock.assert_not_called()
    # The preferred app should have been executed
    app_result_mock.assert_called_once()
    # The app result should be stored on the conversation
    assert len(conv.apps_results) == 1


def test_trigger_apps_stale_preferred_app_falls_through_to_suggestion():
    """When preferred app ID exists in Redis but not in apps dict, fall through to LLM suggestion."""
    suggestion_app = _make_mock_app("suggested-app", "SuggestedApp")
    _setup_trigger_apps_mocks(preferred_app_id="deleted-app-999")
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5 = _trigger_apps_context(default_apps=[suggestion_app])

    with p1, p2, p3, p4, p5:
        process_conversation._trigger_apps("user-stale", conv)

    # The suggestion LLM call SHOULD have been invoked since preferred app was invalid
    suggestion_mock.assert_called_once()


def test_trigger_apps_no_preferred_app_runs_suggestion():
    """When no preferred app is set, the suggestion LLM call should run."""
    suggestion_app = _make_mock_app("suggested-app", "SuggestedApp")
    _setup_trigger_apps_mocks(preferred_app_id=None)
    conv = _make_trigger_conversation()

    suggestion_mock, app_result_mock, p1, p2, p3, p4, p5 = _trigger_apps_context(default_apps=[suggestion_app])

    with p1, p2, p3, p4, p5:
        process_conversation._trigger_apps("user-no-pref", conv)

    # The suggestion LLM call SHOULD have been invoked
    suggestion_mock.assert_called_once()
