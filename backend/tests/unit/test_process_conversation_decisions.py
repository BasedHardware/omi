"""Wiring tests for the Decisions lens inside `process_conversation`.

These tests don't run the full conversation pipeline; they patch every
external collaborator and assert on the wiring of `is_dogfood_uid` /
`extract_decisions` into `structured.decisions`.
"""

import os
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------------------------------------------------------------------------
# Stub external dependencies the module imports at top-level.
# ---------------------------------------------------------------------------
if "fastapi" not in sys.modules:
    fastapi_stub = _stub_module("fastapi")
    fastapi_stub.HTTPException = type("HTTPException", (Exception,), {})


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

redis_db_stub = sys.modules["database.redis_db"]
redis_db_stub.get_conversation_meeting_id = MagicMock(return_value=None)
redis_db_stub.get_user_preferred_app = MagicMock(return_value=None)
redis_db_stub.get_conversation_summary_app_ids = MagicMock(return_value=[])

calendar_meetings_stub = sys.modules["database.calendar_meetings"]
calendar_meetings_stub.get_meeting = MagicMock(return_value=None)

users_stub = sys.modules["database.users"]
users_stub.get_people_by_ids = MagicMock(return_value=[])

folders_stub = sys.modules["database.folders"]
folders_stub.get_folders = MagicMock(return_value=[])
folders_stub.initialize_system_folders = MagicMock(return_value=[])
folders_stub.update_folder_conversation_count = MagicMock()

conversations_stub = sys.modules["database.conversations"]
conversations_stub.upsert_conversation = MagicMock()
conversations_stub.create_audio_files_from_chunks = MagicMock(return_value=[])
conversations_stub.update_conversation = MagicMock()

client_mod = sys.modules["database._client"]
client_mod.document_id_from_seed = MagicMock(return_value="doc-id")
client_mod.db = MagicMock()

# Pre-stub utils submodules pulled in by process_conversation.
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
    "utils.other.storage",
    "utils.retrieval.rag",
    "utils.webhooks",
    "utils.task_sync",
    "utils.llm.usage_tracker",
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
llm_clients.llm_medium_experiment = MagicMock()
llm_clients.llm_mini = MagicMock()
llm_clients.llm_high = MagicMock()
llm_clients.parser = MagicMock()

# Real module — usage_tracker is tested elsewhere; reuse the live one.
import importlib  # noqa: E402

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure usage_tracker is the real module (process_conversation uses it).
sys.modules.pop("utils.llm.usage_tracker", None)
from utils.llm import usage_tracker  # noqa: E402

utils_notifications = sys.modules["utils.notifications"]
for attr in [
    "send_notification",
    "send_important_conversation_message",
    "send_action_item_data_message",
]:
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

# Now safe to import process_conversation.
process_conversation = importlib.import_module("utils.conversations.process_conversation")

from models.conversation import (  # noqa: E402
    ActionItem,
    Decision,
    DecisionStatus,
    Structured,
)


def _make_conversation_mock():
    conversation = MagicMock()
    conversation.id = "conv-decisions-test"
    conversation.discarded = False
    conversation.folder_id = None
    conversation.private_cloud_sync_enabled = False
    conversation.suggested_summarization_apps = []
    conversation.is_locked = False
    conversation.apps_results = []
    conversation.transcript_segments = []
    conversation.photos = []
    conversation.external_data = None
    conversation.status = None
    conversation.started_at = None
    conversation.finished_at = None
    conversation.get_person_ids = MagicMock(return_value=[])
    conversation.get_transcript = MagicMock(return_value="speaker 0: we agree on Postgres")
    return conversation


def _make_structured_with_action_items() -> Structured:
    return Structured(
        title="Test",
        overview="Overview",
        action_items=[ActionItem(description="Migrate db"), ActionItem(description="Notify team")],
    )


def _silence_threads():
    """Replace threading.Thread with a no-op so we don't fork during tests."""

    class _NoopThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def join(self, *args, **kwargs):
            pass

    return patch.object(process_conversation.threading, "Thread", _NoopThread)


def test_allowlisted_uid_populates_decisions():
    conversation = _make_conversation_mock()
    structured = _make_structured_with_action_items()

    fake_decisions = [
        Decision(id="abc", statement="Use Postgres.", related_action_item_ids=[0]),
        Decision(id="def", statement="Notify the team.", related_action_item_ids=[1]),
    ]
    extract_mock = MagicMock(return_value=fake_decisions)

    # _get_conversation_obj should attach structured to the conversation.
    def fake_get_conversation_obj(uid, structured_arg, conversation_arg):
        conversation_arg.structured = structured_arg
        conversation_arg.discarded = False
        return conversation_arg

    with _silence_threads(), patch.object(
        process_conversation, "_get_structured", MagicMock(return_value=(structured, False))
    ), patch.object(process_conversation, "_get_conversation_obj", side_effect=fake_get_conversation_obj), patch.object(
        process_conversation, "_trigger_apps", MagicMock()
    ), patch.object(
        process_conversation, "is_dogfood_uid", MagicMock(return_value=True)
    ), patch.object(
        process_conversation, "extract_decisions", extract_mock
    ):
        result = process_conversation.process_conversation(
            uid="user-allow",
            language_code="en",
            conversation=conversation,
        )

    extract_mock.assert_called_once()
    assert result.structured.decisions == fake_decisions
    assert len(result.structured.decisions) == 2


def test_allowlisted_uid_extract_decisions_failure_is_swallowed():
    conversation = _make_conversation_mock()
    structured = _make_structured_with_action_items()
    extract_mock = MagicMock(side_effect=RuntimeError("upstream timeout"))

    def fake_get_conversation_obj(uid, structured_arg, conversation_arg):
        conversation_arg.structured = structured_arg
        conversation_arg.discarded = False
        return conversation_arg

    with _silence_threads(), patch.object(
        process_conversation, "_get_structured", MagicMock(return_value=(structured, False))
    ), patch.object(process_conversation, "_get_conversation_obj", side_effect=fake_get_conversation_obj), patch.object(
        process_conversation, "_trigger_apps", MagicMock()
    ), patch.object(
        process_conversation, "is_dogfood_uid", MagicMock(return_value=True)
    ), patch.object(
        process_conversation, "extract_decisions", extract_mock
    ):
        result = process_conversation.process_conversation(
            uid="user-allow",
            language_code="en",
            conversation=conversation,
        )

    extract_mock.assert_called_once()
    # Fail-open: decisions stays at its default empty list on the structured object.
    assert result.structured.decisions == []
    # The pipeline must still complete successfully.
    conversations_stub.upsert_conversation.assert_called()


def test_non_allowlisted_uid_skips_extract_decisions():
    conversation = _make_conversation_mock()
    structured = _make_structured_with_action_items()
    extract_mock = MagicMock(return_value=[])

    def fake_get_conversation_obj(uid, structured_arg, conversation_arg):
        conversation_arg.structured = structured_arg
        conversation_arg.discarded = False
        return conversation_arg

    with _silence_threads(), patch.object(
        process_conversation, "_get_structured", MagicMock(return_value=(structured, False))
    ), patch.object(process_conversation, "_get_conversation_obj", side_effect=fake_get_conversation_obj), patch.object(
        process_conversation, "_trigger_apps", MagicMock()
    ), patch.object(
        process_conversation, "is_dogfood_uid", MagicMock(return_value=False)
    ), patch.object(
        process_conversation, "extract_decisions", extract_mock
    ):
        process_conversation.process_conversation(
            uid="user-not-allowed",
            language_code="en",
            conversation=conversation,
        )

    extract_mock.assert_not_called()
