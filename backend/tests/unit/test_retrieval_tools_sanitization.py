"""Unit tests for exception sanitization across core retrieval tools.

Ensures that internal exceptions, tracebacks, database errors, and sensitive tokens
are never disclosed in tool outputs returned to the agent context.
"""

import importlib
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from tests.unit.memory_import_isolation import AutoMockModule, restore_sys_modules, snapshot_sys_modules

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_STUB_MODULES = [
    "pinecone",
    "typesense",
    "stripe",
    "pycountry",
    "firebase_admin",
    "firebase_admin.auth",
    "firebase_admin.firestore",
    "google.cloud.firestore",
    "database._client",
    "database.vector_db",
    "database.conversations",
    "database.memories",
    "database.users",
    "database.notifications",
    "database.chat",
    "database.action_items",
    "utils.encryption",
    "utils.conversations.factory",
    "utils.conversations.render",
    "utils.conversations.search",
    "utils.llm.clients",
    "utils.other.chat_file",
    "utils.stripe",
    "utils.apps",
    "utils.app_integrations",
]

_SYS_SNAPSHOT = snapshot_sys_modules(_STUB_MODULES)

# Install AutoMockModule stubs for non-present modules
for name in _STUB_MODULES:
    if name not in sys.modules:
        sys.modules[name] = AutoMockModule(name)

# Mock specific functions needed by retrieval tools
sys.modules["database.notifications"].get_user_time_zone = MagicMock(return_value="America/Los_Angeles")
sys.modules["database.conversations"].get_conversations = MagicMock(return_value=[])
sys.modules["database.conversations"].get_conversation = MagicMock(return_value=None)
sys.modules["database.users"].get_user_name = MagicMock(return_value="Test User")
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])

# Import retrieval tools
from utils.retrieval.tools import (
    calendar_tools,
    conversation_tools,
    file_tools,
    gmail_tools,
    memory_tools,
)

# Unload action_item_tools from sys.modules so sibling test test_action_item_date_validation.py can load its own stubbed copy
sys.modules.pop("utils.retrieval.tools.action_item_tools", None)

CONFIG = {"configurable": {"user_id": "test-user-123", "chat_session_id": "session-456"}}


# ==============================================================================
# 1. conversation_tools Tests
# ==============================================================================
class TestConversationToolsSanitization:
    def test_get_conversations_invalid_start_date(self):
        res = conversation_tools.get_conversations_tool.invoke(
            {"start_date": "not-a-valid-date"},
            config=CONFIG,
        )
        assert "Error: Invalid start_date format" in res
        assert "ValueError" not in res
        assert "Traceback" not in res

    def test_get_conversations_invalid_end_date(self):
        res = conversation_tools.get_conversations_tool.invoke(
            {"start_date": "2026-09-20T10:00:00-08:00", "end_date": "invalid-end"},
            config=CONFIG,
        )
        assert "Error: Invalid end_date format" in res
        assert "ValueError" not in res
        assert "Traceback" not in res

    def test_get_conversations_formatting_exception_sanitized(self):
        with patch.object(
            conversation_tools.conversations_db,
            "get_conversations",
            return_value=[{"id": "conv-1", "created_at": "2026-09-20T10:00:00Z"}],
        ), patch.object(
            conversation_tools,
            "conversations_to_string",
            side_effect=RuntimeError("FATAL: postgresql://admin:secret123@db.internal:5432/omi"),
        ):
            res = conversation_tools.get_conversations_tool.invoke({}, config=CONFIG)
            assert "encountered an error formatting them" in res
            assert "secret123" not in res
            assert "postgresql://" not in res
            assert "RuntimeError" not in res

    def test_search_conversations_invalid_dates(self):
        res_start = conversation_tools.search_conversations_tool.invoke(
            {"query": "meeting", "start_date": "bad-date"},
            config=CONFIG,
        )
        assert "Error: Invalid start_date format" in res_start
        assert "ValueError" not in res_start

        res_end = conversation_tools.search_conversations_tool.invoke(
            {"query": "meeting", "start_date": "2026-09-20T10:00:00-08:00", "end_date": "bad-date"},
            config=CONFIG,
        )
        assert "Error: Invalid end_date format" in res_end
        assert "ValueError" not in res_end


# ==============================================================================
# 2. memory_tools Tests
# ==============================================================================
class TestMemoryToolsSanitization:
    def test_get_memories_invalid_dates(self):
        res = memory_tools.get_memories_tool.invoke(
            {"start_date": "not-valid-date"},
            config=CONFIG,
        )
        assert "Error: Invalid start_date format" in res
        assert "ValueError" not in res

    def test_get_memories_invalid_temporal_read_arguments(self):
        res = memory_tools.get_memories_tool.invoke(
            {"as_of": "invalid-iso-date"},
            config=CONFIG,
        )
        assert res == "Error: Invalid temporal read arguments."
        assert "ValueError" not in res

    def test_search_memories_invalid_temporal_arguments(self):
        res = memory_tools.search_memories_tool.invoke(
            {"query": "birthday", "as_of": "not-a-valid-as-of"},
            config=CONFIG,
        )
        assert res == "Error: Invalid temporal read arguments."

    def test_search_memories_exception_sanitized(self):
        with patch.object(
            memory_tools,
            "MemoryService",
            side_effect=RuntimeError("Pinecone internal error: cluster unreachable key=secret_key_abc"),
        ):
            res = memory_tools.search_memories_tool.invoke(
                {"query": "vacation"},
                config=CONFIG,
            )
            assert res == "Error searching memories. Please try again."
            assert "secret_key_abc" not in res
            assert "Pinecone internal error" not in res


# ==============================================================================
# 3. calendar_tools Tests
# ==============================================================================
class TestCalendarToolsSanitization:
    @pytest.mark.asyncio
    async def test_create_calendar_event_invalid_start_time(self):
        res = await calendar_tools.create_calendar_event_tool.ainvoke(
            {"title": "Sync", "start_time": "invalid-time", "end_time": "2026-09-24T15:00:00-07:00"},
            config=CONFIG,
        )
        assert "Error: Invalid start_time format" in res
        assert "ValueError" not in res

    @pytest.mark.asyncio
    async def test_create_calendar_event_unexpected_exception_sanitized(self):
        with patch.object(
            calendar_tools,
            "prepare_access",
            return_value=("test-user-123", {"connected": True}, "valid_token", None),
        ), patch.object(
            calendar_tools,
            "create_google_calendar_event",
            side_effect=RuntimeError("Google Cal API auth fail secret_token_xyz"),
        ):
            res = await calendar_tools.create_calendar_event_tool.ainvoke(
                {
                    "title": "Meeting",
                    "start_time": "2026-09-24T14:00:00-07:00",
                    "end_time": "2026-09-24T15:00:00-07:00",
                },
                config=CONFIG,
            )
            assert res == "Unexpected error creating calendar event. Please try again."
            assert "secret_token_xyz" not in res

    @pytest.mark.asyncio
    async def test_get_calendar_events_unexpected_exception_sanitized(self):
        with patch.object(
            calendar_tools,
            "prepare_access",
            return_value=("test-user-123", {"connected": True}, "valid_token", None),
        ), patch.object(
            calendar_tools,
            "get_google_calendar_events",
            side_effect=RuntimeError("Socket hangup db=10.0.0.1"),
        ):
            res = await calendar_tools.get_calendar_events_tool.ainvoke({}, config=CONFIG)
            assert res == "Error fetching calendar events. Please try again."
            assert "10.0.0.1" not in res

    @pytest.mark.asyncio
    async def test_delete_calendar_event_by_id_unexpected_exception_sanitized(self):
        with patch.object(
            calendar_tools,
            "prepare_access",
            return_value=("test-user-123", {"connected": True}, "valid_token", None),
        ), patch.object(
            calendar_tools,
            "delete_google_calendar_event",
            side_effect=RuntimeError("Internal GSuite leak key=leak123"),
        ):
            res = await calendar_tools.delete_calendar_event_tool.ainvoke(
                {"event_id": "ev_123"},
                config=CONFIG,
            )
            assert res == "Error deleting calendar event. Please try again."
            assert "leak123" not in res

    @pytest.mark.asyncio
    async def test_delete_calendar_event_search_batch_mutation_sanitized(self):
        with patch.object(
            calendar_tools,
            "prepare_access",
            return_value=("test-user-123", {"connected": True}, "valid_token", None),
        ), patch.object(
            calendar_tools,
            "get_google_calendar_events",
            return_value=[{"id": "ev_123", "summary": "Private Meeting"}],
        ), patch.object(
            calendar_tools,
            "delete_google_calendar_event",
            side_effect=RuntimeError("Database down: postgres://root:pass@internal/prod"),
        ):
            res = await calendar_tools.delete_calendar_event_tool.ainvoke(
                {"event_title": "Private Meeting"},
                config=CONFIG,
            )
            assert "Failed to delete" in res
            assert "Failed to delete event" in res
            assert "postgres://" not in res
            assert "pass@internal" not in res

    @pytest.mark.asyncio
    async def test_update_calendar_event_unexpected_exception_sanitized(self):
        with patch.object(
            calendar_tools,
            "prepare_access",
            return_value=("test-user-123", {"connected": True}, "valid_token", None),
        ), patch.object(
            calendar_tools,
            "get_google_calendar_event",
            side_effect=RuntimeError("Event corrupted in Firestore doc_id=456"),
        ):
            res = await calendar_tools.update_calendar_event_tool.ainvoke(
                {"event_id": "ev_456", "title": "Updated Title"},
                config=CONFIG,
            )
            assert res == "Error getting calendar event. Please try again."
            assert "Firestore doc_id=456" not in res


# ==============================================================================
# 4. file_tools Tests
# ==============================================================================
class TestFileToolsSanitization:
    def test_search_files_config_error_sanitized(self):
        res = file_tools.search_files_tool.func(
            question="What is in the file?",
            config={"configurable": 12345},  # Non-dict triggers AttributeError on .get()
        )
        assert res == "Error: Configuration error."

    def test_search_files_session_error_sanitized(self):
        with patch.object(
            file_tools.chat_db,
            "get_chat_session_by_id",
            side_effect=ValueError("Invalid session ID format: hex decode failure 0xDEADBEEF"),
        ):
            res = file_tools.search_files_tool.invoke(
                {"question": "Summary"},
                config=CONFIG,
            )
            assert res == "Session error occurred. Please try again."
            assert "0xDEADBEEF" not in res

    def test_search_files_unexpected_error_sanitized(self):
        with patch.object(
            file_tools.chat_db,
            "get_chat_session_by_id",
            side_effect=RuntimeError("Storage bucket connection refused secret_key_file"),
        ):
            res = file_tools.search_files_tool.invoke(
                {"question": "Summary"},
                config=CONFIG,
            )
            assert (
                res == "I encountered an error while searching the files. Please try again or rephrase your question."
            )
            assert "secret_key_file" not in res


# ==============================================================================
# 5. gmail_tools Tests
# ==============================================================================
class TestGmailToolsSanitization:
    @pytest.mark.asyncio
    async def test_get_gmail_messages_unexpected_exception_sanitized(self):
        with patch.object(
            gmail_tools,
            "prepare_access",
            return_value=("test-user-123", {"connected": True}, "token_123", None),
        ), patch.object(
            gmail_tools,
            "google_integration_has_scope",
            return_value=True,
        ), patch.object(
            gmail_tools,
            "retry_on_auth_async",
            side_effect=RuntimeError("OAuth token expired: Bearer ya29.secret_auth_token"),
        ):
            res = await gmail_tools.get_gmail_messages_tool.ainvoke(
                {"query": "important"},
                config=CONFIG,
            )
            assert res == "Unexpected error fetching Gmail messages. Please try again."
            assert "secret_auth_token" not in res
