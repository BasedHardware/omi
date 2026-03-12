"""
Tests for HIGH priority LLM usage tracking (issue #4619).

Verifies that track_usage context managers are properly placed around LLM calls in:
- goals.py (suggest_goal, get_goal_advice, extract_and_update_goal_progress)
- knowledge_graph.py (extract_knowledge_from_memory, rebuild_knowledge_graph.process_memory)
- external_integrations.py (get_conversation_summary, generate_comprehensive_daily_summary)
- notifications.py (generate_notification_message, generate_credit_limit_notification)
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
import asyncio

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# --- Stub database package and submodules ---
# Use _stub_module which only creates if not already loaded
database_mod = _stub_module("database")
if not hasattr(database_mod, '__path__'):
    database_mod.__path__ = []
for submodule in [
    "redis_db",
    "memories",
    "conversations",
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
    "goals",
    "knowledge_graph",
    "daily_summaries",
    "mem_db",
    "notifications",
]:
    mod = _stub_module(f"database.{submodule}")
    setattr(database_mod, submodule, mod)

# Set needed attributes on db stubs
sys.modules["database.llm_usage"].record_llm_usage = MagicMock()
sys.modules["database.goals"].get_user_goal = MagicMock(return_value=None)
sys.modules["database.goals"].get_user_goals = MagicMock(return_value=[])
sys.modules["database.goals"].update_goal_progress = MagicMock()
sys.modules["database.memories"].get_memories = MagicMock(return_value=[])
sys.modules["database.conversations"].get_conversations = MagicMock(return_value=[])
sys.modules["database.conversations"].get_conversations_by_id = MagicMock(return_value=[])
sys.modules["database.chat"].get_messages = MagicMock(return_value=[])
sys.modules["database.vector_db"].query_vectors = MagicMock(return_value=[])
sys.modules["database.knowledge_graph"].get_knowledge_nodes = MagicMock(return_value=[])
sys.modules["database.knowledge_graph"].get_knowledge_graph = MagicMock(return_value={'nodes': [], 'edges': []})
sys.modules["database.knowledge_graph"].upsert_knowledge_node = MagicMock(return_value={'id': 'n1', 'label': 'test'})
sys.modules["database.knowledge_graph"].upsert_knowledge_edge = MagicMock(return_value={'id': 'e1'})
sys.modules["database.knowledge_graph"].delete_knowledge_graph = MagicMock()
sys.modules["database.users"].get_user_profile = MagicMock(return_value={'time_zone': 'UTC'})
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])
sys.modules["database.action_items"].get_action_items = MagicMock(return_value=[])
sys.modules["database.daily_summaries"].create_daily_summary = MagicMock(return_value="summary-1")
sys.modules["database.notifications"].get_user_time_zone = MagicMock(return_value="UTC")
sys.modules["database.notifications"].get_token_only = MagicMock(return_value=None)

# --- Don't stub models — it's a real package on disk ---
# Only add missing attributes if the real modules can't be loaded

# --- Stub utils.llms.memory ---
llms_mod = _stub_module("utils.llms")
if not hasattr(llms_mod, '__path__'):
    llms_mod.__path__ = []
_stub_module("utils.llms.memory")
sys.modules["utils.llms.memory"].get_prompt_memories = MagicMock(return_value=("TestUser", "some memories"))

# --- Import real usage_tracker ---
from utils.llm.usage_tracker import _usage_context, Features

# --- Stub LLM clients (AFTER importing usage_tracker so it's already loaded) ---
mock_llm_mini = MagicMock()
mock_llm_mini.invoke = MagicMock(
    return_value=MagicMock(
        content='{"suggested_title": "test", "suggested_type": "scale", "suggested_target": 10, "suggested_min": 0, "suggested_max": 10, "reasoning": "test"}'
    )
)
mock_llm_mini.ainvoke = AsyncMock(return_value=MagicMock(content="test response"))
mock_llm_mini.with_structured_output = MagicMock(return_value=mock_llm_mini)

mock_llm_medium = MagicMock()
mock_llm_medium.invoke = MagicMock(return_value=MagicMock(content="test advice"))
mock_llm_medium.ainvoke = AsyncMock(return_value=MagicMock(content="test notification body"))

mock_llm_medium_experiment = MagicMock()
mock_llm_medium_experiment.invoke = MagicMock(
    return_value=MagicMock(
        content='{"headline": "Test Day", "overview": "test", "day_emoji": "📅", "highlights": [], "unresolved_questions": [], "decisions_made": [], "knowledge_nuggets": []}'
    )
)

mock_parser = MagicMock()

# Replace clients module with stubs
clients_mod = _stub_module("utils.llm.clients")
clients_mod.llm_mini = mock_llm_mini
clients_mod.llm_medium = mock_llm_medium
clients_mod.llm_medium_experiment = mock_llm_medium_experiment
clients_mod.parser = mock_parser


# ── Source-level tests: verify track_usage wraps every LLM call ──


def _read_source(relative_path: str) -> str:
    """Read a source file relative to the backend directory."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / relative_path).read_text()


class TestGoalsTracking:
    """Verify track_usage(uid, Features.GOALS) wraps LLM calls in goals.py."""

    def test_suggest_goal_has_tracking(self):
        source = _read_source("utils/llm/goals.py")
        assert "track_usage(uid, Features.GOALS)" in source

    def test_all_three_goal_functions_tracked(self):
        source = _read_source("utils/llm/goals.py")
        count = source.count("with track_usage(uid, Features.GOALS):")
        assert count == 3, f"Expected 3 track_usage(GOALS) wrappers, found {count}"

    def test_suggest_goal_sets_context(self):
        """Verify suggest_goal actually sets the usage context during LLM call."""
        captured_ctx = {}
        original_invoke = mock_llm_mini.invoke

        def capturing_invoke(prompt):
            ctx = _usage_context.get()
            if ctx:
                captured_ctx['uid'] = ctx.uid
                captured_ctx['feature'] = ctx.feature
            return MagicMock(
                content='{"suggested_title": "test", "suggested_type": "scale", "suggested_target": 10, "suggested_min": 0, "suggested_max": 10, "reasoning": "test"}'
            )

        mock_llm_mini.invoke = capturing_invoke
        # Provide memories so suggest_goal doesn't return early with default
        sys.modules["database.memories"].get_memories = MagicMock(return_value=[{'content': 'User is learning Python'}])
        try:
            from utils.llm.goals import suggest_goal

            suggest_goal("test-uid-123")
            assert captured_ctx.get('feature') == Features.GOALS
            assert captured_ctx.get('uid') == "test-uid-123"
        finally:
            mock_llm_mini.invoke = original_invoke

    def test_get_goal_advice_sets_context(self):
        """Verify get_goal_advice sets the usage context during LLM call."""
        captured_ctx = {}
        original_invoke = mock_llm_medium.invoke

        def capturing_invoke(prompt):
            ctx = _usage_context.get()
            if ctx:
                captured_ctx['uid'] = ctx.uid
                captured_ctx['feature'] = ctx.feature
            return MagicMock(content="Focus on one thing at a time.")

        mock_llm_medium.invoke = capturing_invoke
        _goal = {
            'id': 'goal-1',
            'title': 'Read 20 books',
            'current_value': 5,
            'target_value': 20,
            'goal_type': 'numeric',
        }
        sys.modules["database.goals"].get_user_goal = MagicMock(return_value=_goal)
        sys.modules["database.goals"].get_user_goals = MagicMock(return_value=[_goal])
        try:
            from utils.llm.goals import get_goal_advice

            get_goal_advice("test-uid-456", "goal-1")
            assert captured_ctx.get('feature') == Features.GOALS
            assert captured_ctx.get('uid') == "test-uid-456"
        finally:
            mock_llm_medium.invoke = original_invoke

    def test_extract_and_update_goal_progress_sets_context(self):
        """Verify extract_and_update_goal_progress sets context during LLM call."""
        captured_ctx = {}
        original_invoke = mock_llm_mini.invoke

        def capturing_invoke(prompt):
            ctx = _usage_context.get()
            if ctx:
                captured_ctx['uid'] = ctx.uid
                captured_ctx['feature'] = ctx.feature
            return MagicMock(content='{"found": false, "value": null, "reasoning": "no progress"}')

        mock_llm_mini.invoke = capturing_invoke
        _goal = {
            'id': 'goal-1',
            'title': 'Save $10000',
            'current_value': 2000,
            'target_value': 10000,
            'goal_type': 'numeric',
        }
        sys.modules["database.goals"].get_user_goal = MagicMock(return_value=_goal)
        sys.modules["database.goals"].get_user_goals = MagicMock(return_value=[_goal])
        try:
            from utils.llm.goals import extract_and_update_goal_progress

            extract_and_update_goal_progress("test-uid-789", "I saved another $500 today")
            assert captured_ctx.get('feature') == Features.GOALS
            assert captured_ctx.get('uid') == "test-uid-789"
        finally:
            mock_llm_mini.invoke = original_invoke


class TestKnowledgeGraphTracking:
    """Verify track_usage(uid, Features.KNOWLEDGE_GRAPH) wraps LLM calls."""

    def test_extract_knowledge_has_tracking(self):
        source = _read_source("utils/llm/knowledge_graph.py")
        assert "with track_usage(uid, Features.KNOWLEDGE_GRAPH):" in source

    def test_both_llm_calls_tracked(self):
        source = _read_source("utils/llm/knowledge_graph.py")
        count = source.count("with track_usage(uid, Features.KNOWLEDGE_GRAPH):")
        assert count == 2, f"Expected 2 track_usage(KNOWLEDGE_GRAPH) wrappers, found {count}"

    def test_extract_knowledge_sets_context(self):
        """Verify extract_knowledge_from_memory sets context during LLM call."""
        captured_ctx = {}
        original_invoke = mock_llm_mini.invoke

        def capturing_invoke(prompt):
            ctx = _usage_context.get()
            if ctx:
                captured_ctx['uid'] = ctx.uid
                captured_ctx['feature'] = ctx.feature
            return MagicMock(content='{"nodes": [], "edges": []}')

        mock_llm_mini.invoke = capturing_invoke
        try:
            from utils.llm.knowledge_graph import extract_knowledge_from_memory

            extract_knowledge_from_memory("test-uid-kg", "User likes pizza", "mem-1", "TestUser")
            assert captured_ctx.get('feature') == Features.KNOWLEDGE_GRAPH
            assert captured_ctx.get('uid') == "test-uid-kg"
        finally:
            mock_llm_mini.invoke = original_invoke


class TestExternalIntegrationsTracking:
    """Verify track_usage wraps LLM calls in external_integrations.py."""

    def test_get_conversation_summary_has_tracking(self):
        source = _read_source("utils/llm/external_integrations.py")
        assert "with track_usage(uid, Features.DAILY_SUMMARY):" in source

    def test_both_daily_summary_calls_tracked(self):
        source = _read_source("utils/llm/external_integrations.py")
        count = source.count("with track_usage(uid, Features.DAILY_SUMMARY):")
        assert count == 2, f"Expected 2 track_usage(DAILY_SUMMARY) wrappers, found {count}"

    def test_get_conversation_summary_sets_context(self):
        """Verify get_conversation_summary sets context during LLM call."""
        captured_ctx = {}
        original_invoke = mock_llm_mini.invoke

        def capturing_invoke(prompt):
            ctx = _usage_context.get()
            if ctx:
                captured_ctx['uid'] = ctx.uid
                captured_ctx['feature'] = ctx.feature
            return MagicMock(content="Summary: Do X, Y, Z")

        mock_llm_mini.invoke = capturing_invoke
        try:
            from utils.llm.external_integrations import get_conversation_summary

            get_conversation_summary("test-uid-summary", [])
            assert captured_ctx.get('feature') == Features.DAILY_SUMMARY
            assert captured_ctx.get('uid') == "test-uid-summary"
        finally:
            mock_llm_mini.invoke = original_invoke


class TestNotificationsTracking:
    """Verify track_usage wraps LLM calls in notifications.py."""

    def test_both_notification_calls_tracked(self):
        source = _read_source("utils/llm/notifications.py")
        count = source.count("with track_usage(uid, Features.SUBSCRIPTION_NOTIFICATION):")
        assert count == 2, f"Expected 2 track_usage(SUBSCRIPTION_NOTIFICATION) wrappers, found {count}"

    def test_generate_notification_message_sets_context(self):
        """Verify generate_notification_message sets context during async LLM call."""
        captured_ctx = {}

        async def capturing_ainvoke(prompt):
            ctx = _usage_context.get()
            if ctx:
                captured_ctx['uid'] = ctx.uid
                captured_ctx['feature'] = ctx.feature
            return MagicMock(content="Hey there! Welcome!")

        original_ainvoke = mock_llm_medium.ainvoke
        mock_llm_medium.ainvoke = capturing_ainvoke
        try:
            from utils.llm.notifications import generate_notification_message

            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(generate_notification_message("test-uid-notif", "Alice", "unlimited"))
            loop.close()
            assert captured_ctx.get('feature') == Features.SUBSCRIPTION_NOTIFICATION
            assert captured_ctx.get('uid') == "test-uid-notif"
            assert result[0] == "omi"
        finally:
            mock_llm_medium.ainvoke = original_ainvoke

    def test_generate_credit_limit_notification_sets_context(self):
        """Verify generate_credit_limit_notification sets context during async LLM call."""
        captured_ctx = {}

        async def capturing_ainvoke(prompt):
            ctx = _usage_context.get()
            if ctx:
                captured_ctx['uid'] = ctx.uid
                captured_ctx['feature'] = ctx.feature
            return MagicMock(content="You've been using transcription a lot!")

        original_ainvoke = mock_llm_medium.ainvoke
        mock_llm_medium.ainvoke = capturing_ainvoke
        try:
            from utils.llm.notifications import generate_credit_limit_notification

            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(generate_credit_limit_notification("test-uid-credit", "Bob"))
            loop.close()
            assert captured_ctx.get('feature') == Features.SUBSCRIPTION_NOTIFICATION
            assert captured_ctx.get('uid') == "test-uid-credit"
            assert result[0] == "omi"
        finally:
            mock_llm_medium.ainvoke = original_ainvoke


class TestFeatureConstants:
    """Verify all new feature constants exist."""

    def test_daily_summary_constant(self):
        assert Features.DAILY_SUMMARY == "daily_summary"

    def test_subscription_notification_constant(self):
        assert Features.SUBSCRIPTION_NOTIFICATION == "subscription_notification"

    def test_knowledge_graph_constant(self):
        assert Features.KNOWLEDGE_GRAPH == "knowledge_graph"

    def test_goals_constant_exists(self):
        assert Features.GOALS == "goals"


class TestNoDoubleWrapping:
    """Verify there's no double-wrapping of track_usage at caller + callee."""

    def test_other_notifications_no_track_usage(self):
        """utils/other/notifications.py should NOT wrap generate_comprehensive_daily_summary
        since tracking is now inside the function itself."""
        source = _read_source("utils/other/notifications.py")
        assert (
            "track_usage" not in source
        ), "utils/other/notifications.py should not import or use track_usage (tracking is in the LLM function)"
