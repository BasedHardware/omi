"""Regression tests for #5668: empty LLM title must not silently discard conversations.

These tests are pure — no DB, no network, no LLM calls. They verify that
`_get_conversation_obj` accepts an explicit `discarded` parameter and respects
it instead of re-deriving from `structured.title == ''`.
"""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# -- Module stubbing (mirrors test_process_conversation_usage_context.py) --
# `utils.conversations.process_conversation` transitively imports heavy DB/LLM
# packages (google-cloud-firestore, Pinecone, etc.) that are not installed in
# the unit-test env. We stub them here so the module under test can be imported.
def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


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


# -- Test fixtures --
from models.conversation import CreateConversation
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations.process_conversation import (
    _fallback_title_for_empty_llm_response,
    _get_conversation_obj,
)


def _make_create_conversation(transcript_text: str = "Some real content.") -> CreateConversation:
    """Build a minimal CreateConversation with one transcript segment."""
    now = datetime.now(timezone.utc)
    segment = TranscriptSegment(
        text=transcript_text,
        is_user=False,
        start=0.0,
        end=1.0,
    )
    return CreateConversation(
        started_at=now,
        finished_at=now,
        transcript_segments=[segment],
    )


class TestGetConversationObjRespectsDiscardedParam:
    """Regression tests for signal-loss fix in _get_conversation_obj."""

    def test_empty_title_with_discarded_false_preserves_conversation(self):
        """Key regression test for #5668: valid conversation with empty LLM title must not be discarded."""
        structured = Structured(title='', overview='Real conversation content')
        conv = _make_create_conversation()

        result = _get_conversation_obj('uid_1', structured, conv, discarded=False)

        assert result.discarded is False, (
            "Conversation was silently discarded despite explicit discarded=False. "
            "This is the #5668 bug: title == '' was used as a discard proxy."
        )

    def test_empty_title_with_discarded_true_marks_conversation_discarded(self):
        """Protect the legitimate discard path — explicit discarded=True must still mark the conversation as discarded."""
        structured = Structured(title='', emoji='🎉')
        conv = _make_create_conversation()

        result = _get_conversation_obj('uid_1', structured, conv, discarded=True)

        assert result.discarded is True

    def test_get_conversation_obj_default_discarded_is_false(self):
        """Safety net: verify default parameter value with a valid LLM response preserves the conversation."""
        structured = Structured(title='Valid title from LLM', overview='Some content')
        conv = _make_create_conversation()

        result = _get_conversation_obj('uid_1', structured, conv)

        assert result.discarded is False


class TestFallbackTitleForEmptyLlmResponse:
    """Unit tests for the deterministic fallback title helper."""

    def test_fallback_prefers_overview_first_sentence(self):
        structured = Structured(title='', overview='Budget meeting notes. Discussed Q2 goals and budget cuts.')
        started_at = datetime(2026, 4, 15, tzinfo=timezone.utc)

        result = _fallback_title_for_empty_llm_response(structured, started_at)

        assert result == 'Budget meeting notes'

    def test_fallback_uses_date_when_overview_empty(self):
        structured = Structured(title='', overview='')
        started_at = datetime(2026, 4, 15, tzinfo=timezone.utc)

        result = _fallback_title_for_empty_llm_response(structured, started_at)

        assert result == 'Conversation on Apr 15, 2026'

    def test_fallback_skips_overly_long_overview_first_sentence(self):
        """Long overview first sentence should fall through to date fallback rather than becoming a noisy title."""
        long_sentence = 'This is an unusually long first sentence of the overview that exceeds sixty characters of text'
        structured = Structured(title='', overview=f"{long_sentence}. Rest.")
        started_at = datetime(2026, 4, 15, tzinfo=timezone.utc)

        result = _fallback_title_for_empty_llm_response(structured, started_at)

        assert result == 'Conversation on Apr 15, 2026'

    def test_fallback_handles_missing_started_at(self):
        structured = Structured(title='', overview='')

        result = _fallback_title_for_empty_llm_response(structured, None)

        assert result == 'Untitled Conversation'

    def test_fallback_skips_single_word_first_sentence(self):
        """Avoid noisy one-word titles from abbreviations ('Dr. Smith...') or decimals ('Scored 3.5...')."""
        structured = Structured(title='', overview='Dr. Smith met with the team.')
        started_at = datetime(2026, 4, 15, tzinfo=timezone.utc)

        result = _fallback_title_for_empty_llm_response(structured, started_at)

        assert result == 'Conversation on Apr 15, 2026'
