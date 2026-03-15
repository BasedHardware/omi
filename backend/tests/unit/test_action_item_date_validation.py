"""Tests for action item due date validation (issue #4841).

Covers:
1. create_action_item_tool rejects due dates more than 1 day in the past
2. update_action_item_tool rejects due dates more than 1 day in the past
3. extract_action_items passes current_time to prompt and clears past due dates
4. Dates within 1-day grace window are accepted
5. Future dates are accepted unchanged
"""

import importlib
import importlib.util
import inspect
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _stub_package(name):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    return mod


def _load_module_from_file(module_name, file_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Stub heavy dependencies
# ---------------------------------------------------------------------------
for mod_name in [
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.credentials",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.cloud.storage",
    "opuslib",
    "sentry_sdk",
    "database._client",
    "database.redis_db",
    "database.auth",
]:
    if mod_name not in sys.modules:
        _stub_module(mod_name)

# Stub database.action_items
action_items_db = _stub_module("database.action_items")
action_items_db.create_action_item = MagicMock(return_value="test-item-id")
action_items_db.get_action_item = MagicMock(
    return_value={
        'id': 'test-item-id',
        'description': 'Test task',
        'completed': False,
        'due_at': datetime.now(timezone.utc) + timedelta(hours=24),
    }
)
action_items_db.update_action_item = MagicMock(return_value=True)
_stub_package("database")

# Stub notifications
notif_mod = _stub_module("utils.notifications")
notif_mod.send_action_item_completed_notification = MagicMock()
notif_mod.send_action_item_created_notification = MagicMock()
notif_mod.send_action_item_data_message = MagicMock()

# Stub langchain
langchain_core = _stub_package("langchain_core")
langchain_tools = _stub_module("langchain_core.tools")
langchain_runnables = _stub_module("langchain_core.runnables")


class FakeRunnableConfig(dict):
    pass


def fake_tool(func=None, **kwargs):
    if func is not None:
        return func
    return lambda f: f


langchain_tools.tool = fake_tool
langchain_runnables.RunnableConfig = FakeRunnableConfig

# Stub langchain output parsers and prompts
langchain_output_parsers = _stub_module("langchain_core.output_parsers")
langchain_output_parsers.PydanticOutputParser = MagicMock()
langchain_prompts = _stub_module("langchain_core.prompts")
langchain_prompts.ChatPromptTemplate = MagicMock()

# Stub pydantic (already installed, just need BaseModel/Field accessible)
# pydantic is real, no stub needed

# Stub utils packages
_stub_package("utils")
_stub_package("utils.retrieval")
_stub_package("utils.retrieval.tools")
_stub_package("utils.llm")
_stub_package("utils.conversations")

# Stub utils.retrieval.agentic
import contextvars

agentic_stub = _stub_module("utils.retrieval.agentic")
agentic_stub.agent_config_context = contextvars.ContextVar('agent_config', default=None)

# ---------------------------------------------------------------------------
# Load production code
# ---------------------------------------------------------------------------

# Stub utils.llm.clients (conversation_processing imports from .clients)
llm_clients_stub = _stub_module("utils.llm.clients")
llm_clients_stub.llm_mini = MagicMock()
llm_clients_stub.parser = MagicMock()
llm_clients_stub.llm_high = MagicMock()
llm_clients_stub.llm_medium_experiment = MagicMock()

# Load models first
_stub_package("models")
sys.modules["models"].__path__ = [str(BACKEND_DIR / "models")]
_load_module_from_file("models.conversation", BACKEND_DIR / "models" / "conversation.py")
_load_module_from_file("models.app", BACKEND_DIR / "models" / "app.py")

# Load action_item_tools
action_item_tools = _load_module_from_file(
    "utils.retrieval.tools.action_item_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "action_item_tools.py",
)
create_action_item_tool = action_item_tools.create_action_item_tool
update_action_item_tool = action_item_tools.update_action_item_tool


def _make_config(uid="test-user-123"):
    return {"configurable": {"user_id": uid}}


# ===========================================================================
# create_action_item_tool tests
# ===========================================================================


class TestCreateActionItemDateValidation:

    def test_rejects_date_months_in_past(self):
        """Due date from September 2025 should be rejected."""
        result = create_action_item_tool(
            description="Call venue",
            due_at="2025-09-15T10:00:00+00:00",
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_rejects_date_one_year_in_past(self):
        """Due date from a year ago should be rejected."""
        one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Old task",
            due_at=one_year_ago,
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_accepts_future_date(self):
        """Due date in the future should be accepted."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Future task",
            due_at=future_date,
            config=_make_config(),
        )
        assert "Error" not in result
        assert "Added" in result or "✅" in result

    def test_accepts_date_within_grace_window(self):
        """Due date 12 hours ago should be accepted (within 1-day grace)."""
        twelve_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Recent task",
            due_at=twelve_hours_ago,
            config=_make_config(),
        )
        assert "Error" not in result
        assert "Added" in result or "✅" in result

    def test_rejects_date_two_days_in_past(self):
        """Due date 2 days ago should be rejected (beyond 1-day grace)."""
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = create_action_item_tool(
            description="Past task",
            due_at=two_days_ago,
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_error_includes_current_time(self):
        """Error message should include current time so LLM can correct."""
        result = create_action_item_tool(
            description="Past task",
            due_at="2025-06-01T10:00:00+00:00",
            config=_make_config(),
        )
        assert "current time is" in result

    def test_format_validation_still_works(self):
        """Format validation should still reject invalid formats."""
        result = create_action_item_tool(
            description="Bad format",
            due_at="not-a-date",
            config=_make_config(),
        )
        assert "Error" in result
        assert "Invalid due_at format" in result

    def test_no_due_date_defaults_to_24h(self):
        """No due date should default to 24h from now."""
        result = create_action_item_tool(
            description="No due date task",
            due_at=None,
            config=_make_config(),
        )
        assert "in the past" not in result


# ===========================================================================
# update_action_item_tool tests
# ===========================================================================


class TestUpdateActionItemDateValidation:

    def test_rejects_past_date_on_update(self):
        """Updating due date to a past date should be rejected."""
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at="2025-09-15T10:00:00+00:00",
            config=_make_config(),
        )
        assert "Error" in result
        assert "in the past" in result

    def test_accepts_future_date_on_update(self):
        """Updating due date to a future date should work."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at=future_date,
            config=_make_config(),
        )
        assert "Error" not in result or "in the past" not in result
        assert "updated" in result.lower() or "Successfully" in result

    def test_accepts_date_within_grace_window_on_update(self):
        """Due date 12 hours ago on update should be accepted."""
        twelve_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
        result = update_action_item_tool(
            action_item_id="test-item-id",
            due_at=twelve_hours_ago,
            config=_make_config(),
        )
        assert "in the past" not in result


# ===========================================================================
# extract_action_items prompt and post-validation tests
# ===========================================================================


class TestExtractActionItemsPostValidation:

    def test_prompt_contains_current_time_and_staleness_rule(self):
        """The extraction prompt source should contain current_time and staleness logic."""
        # Load conversation_processing to inspect source
        conv_proc = _load_module_from_file(
            "utils.llm.conversation_processing",
            BACKEND_DIR / "utils" / "llm" / "conversation_processing.py",
        )
        source = inspect.getsource(conv_proc.extract_action_items)
        assert 'current_time' in source, "extract_action_items must pass current_time"
        assert '7 days' in source or 'HISTORICAL' in source, "must contain staleness rule"

    def test_clears_past_due_dates_from_extraction(self):
        """Due dates more than 1 day in the past should be cleared after extraction."""
        from models.conversation import ActionItem, ActionItemsExtraction

        past_due = datetime(2025, 9, 15, 10, 0, tzinfo=timezone.utc)
        future_due = datetime.now(timezone.utc) + timedelta(days=3)

        mock_response = ActionItemsExtraction(
            action_items=[
                ActionItem(description="Past task", due_at=past_due),
                ActionItem(description="Future task", due_at=future_due),
            ]
        )

        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_response
        mock_chain.__or__ = MagicMock(return_value=mock_chain)

        conv_proc = sys.modules.get("utils.llm.conversation_processing")
        if conv_proc is None:
            conv_proc = _load_module_from_file(
                "utils.llm.conversation_processing",
                BACKEND_DIR / "utils" / "llm" / "conversation_processing.py",
            )

        with patch.object(conv_proc, 'llm_medium_experiment') as mock_llm, patch.object(
            conv_proc, 'PydanticOutputParser'
        ) as mock_parser_cls, patch.object(conv_proc, 'ChatPromptTemplate') as mock_prompt_cls:

            mock_llm.bind.return_value = mock_llm
            mock_llm.__or__ = MagicMock(return_value=mock_chain)

            mock_parser = MagicMock()
            mock_parser.get_format_instructions.return_value = "format"
            mock_parser_cls.return_value = mock_parser

            mock_prompt = MagicMock()
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            mock_prompt_cls.from_messages.return_value = mock_prompt

            result = conv_proc.extract_action_items(
                transcript="Call venue by Friday, submit report",
                started_at=datetime(2025, 9, 10, 10, 0, tzinfo=timezone.utc),
                language_code="en",
                tz="UTC",
            )

        assert len(result) == 2
        assert result[0].due_at is None, "Past due date should be cleared"
        assert result[1].due_at is not None, "Future due date should be preserved"

    def test_passes_current_time_to_invoke(self):
        """extract_action_items should pass current_time in the invoke payload."""
        from models.conversation import ActionItemsExtraction

        mock_response = ActionItemsExtraction(action_items=[])
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_response
        mock_chain.__or__ = MagicMock(return_value=mock_chain)

        conv_proc = sys.modules.get("utils.llm.conversation_processing")
        if conv_proc is None:
            conv_proc = _load_module_from_file(
                "utils.llm.conversation_processing",
                BACKEND_DIR / "utils" / "llm" / "conversation_processing.py",
            )

        with patch.object(conv_proc, 'llm_medium_experiment') as mock_llm, patch.object(
            conv_proc, 'PydanticOutputParser'
        ) as mock_parser_cls, patch.object(conv_proc, 'ChatPromptTemplate') as mock_prompt_cls:

            mock_llm.bind.return_value = mock_llm
            mock_llm.__or__ = MagicMock(return_value=mock_chain)

            mock_parser = MagicMock()
            mock_parser.get_format_instructions.return_value = "format"
            mock_parser_cls.return_value = mock_parser

            mock_prompt = MagicMock()
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            mock_prompt_cls.from_messages.return_value = mock_prompt

            conv_proc.extract_action_items(
                transcript="Test transcript",
                started_at=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
                language_code="en",
                tz="UTC",
            )

        invoke_args = mock_chain.invoke.call_args[0][0]
        assert 'current_time' in invoke_args, "Must pass current_time to prompt"
        assert 'started_at' in invoke_args, "Must still pass started_at"

    def test_preserves_none_due_dates(self):
        """Action items with no due date should remain unchanged."""
        from models.conversation import ActionItem, ActionItemsExtraction

        mock_response = ActionItemsExtraction(action_items=[ActionItem(description="No due date task", due_at=None)])
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = mock_response
        mock_chain.__or__ = MagicMock(return_value=mock_chain)

        conv_proc = sys.modules.get("utils.llm.conversation_processing")
        if conv_proc is None:
            conv_proc = _load_module_from_file(
                "utils.llm.conversation_processing",
                BACKEND_DIR / "utils" / "llm" / "conversation_processing.py",
            )

        with patch.object(conv_proc, 'llm_medium_experiment') as mock_llm, patch.object(
            conv_proc, 'PydanticOutputParser'
        ) as mock_parser_cls, patch.object(conv_proc, 'ChatPromptTemplate') as mock_prompt_cls:

            mock_llm.bind.return_value = mock_llm
            mock_llm.__or__ = MagicMock(return_value=mock_chain)

            mock_parser = MagicMock()
            mock_parser.get_format_instructions.return_value = "format"
            mock_parser_cls.return_value = mock_parser

            mock_prompt = MagicMock()
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)
            mock_prompt_cls.from_messages.return_value = mock_prompt

            result = conv_proc.extract_action_items(
                transcript="Do something",
                started_at=datetime.now(timezone.utc),
                language_code="en",
                tz="UTC",
            )

        assert len(result) == 1
        assert result[0].due_at is None
