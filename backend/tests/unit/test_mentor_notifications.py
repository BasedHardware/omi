"""
Tests for mentor_notifications.py — verifies extract_topics() uses llm_mini (gpt-4.1-mini)
instead of the legacy raw OpenAI gpt-4 client (#4671), and proactive tool calling (#4728-#4730).
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

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

sys.modules["database.llm_usage"].record_llm_usage = MagicMock()
sys.modules["database.notifications"].get_mentor_notification_frequency = MagicMock(return_value=3)

# Stub goals
mock_get_user_goals = MagicMock(
    return_value=[
        {"title": "Exercise 3x per week", "is_active": True},
        {"title": "Read 2 books per month", "is_active": True},
    ]
)
sys.modules["database.goals"].get_user_goals = mock_get_user_goals

# --- Stub LLM clients ---
mock_llm_mini = MagicMock()
mock_llm_mini.invoke = MagicMock(return_value=MagicMock(content='["AI", "machine learning", "startups"]'))

clients_mod = _stub_module("utils.llm.clients")
clients_mod.llm_mini = mock_llm_mini

# Stub usage tracker
llm_mod = _stub_module("utils.llm")
if not hasattr(llm_mod, '__path__'):
    llm_mod.__path__ = []
tracker_mod = _stub_module("utils.llm.usage_tracker")
tracker_mod.get_usage_callback = MagicMock(return_value=[])

# Stub utils.llms.memory (get_prompt_memories)
llms_mod = _stub_module("utils.llms")
if not hasattr(llms_mod, '__path__'):
    llms_mod.__path__ = []
memory_mod = _stub_module("utils.llms.memory")
mock_get_prompt_memories = MagicMock(return_value=("TestUser", "TestUser likes hiking and coding."))
memory_mod.get_prompt_memories = mock_get_prompt_memories


# ── Source-level tests ──


def _read_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "mentor_notifications.py").read_text()


def test_no_raw_openai_client():
    """Verify mentor_notifications.py no longer imports or uses the raw OpenAI client."""
    source = _read_source()
    assert "from openai import OpenAI" not in source, "Should not import raw OpenAI client"
    assert "client.chat.completions.create" not in source, "Should not use raw OpenAI completions API"
    assert 'model="gpt-4"' not in source, "Should not reference gpt-4 model"


def test_uses_llm_mini():
    """Verify extract_topics() uses the shared llm_mini client."""
    source = _read_source()
    assert "from utils.llm.clients import llm_mini" in source, "Should import llm_mini from shared clients"
    assert "llm_mini.invoke" in source, "Should call llm_mini.invoke()"


# ── Functional tests ──


def test_extract_topics_returns_valid_list():
    """extract_topics() should return a list of topic strings from llm_mini."""
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["AI", "machine learning", "startups"]')

    from utils.mentor_notifications import extract_topics

    topics = extract_topics("We talked about AI and machine learning for startups")

    assert isinstance(topics, list)
    assert topics == ["AI", "machine learning", "startups"]
    mock_llm_mini.invoke.assert_called_once()

    prompt_arg = mock_llm_mini.invoke.call_args[0][0]
    assert "Extract all topics" in prompt_arg
    assert "AI and machine learning" in prompt_arg


def test_extract_topics_handles_invalid_json():
    """extract_topics() should return empty list on malformed LLM response."""
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content="not valid json")

    from utils.mentor_notifications import extract_topics

    topics = extract_topics("some discussion")

    assert topics == []


def test_extract_topics_handles_llm_exception():
    """extract_topics() should return empty list when llm_mini raises."""
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.side_effect = Exception("API error")

    from utils.mentor_notifications import extract_topics

    topics = extract_topics("some discussion")

    assert topics == []
    mock_llm_mini.invoke.side_effect = None


def test_process_mentor_notification_no_client_guard_removed():
    """process_mentor_notification should not check for a raw OpenAI client."""
    source = _read_source()
    assert "if not client:" not in source, "Should not guard on raw OpenAI client existence"


def test_create_notification_data_uses_extract_topics():
    """create_notification_data should call extract_topics and include topics in output."""
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["budgeting", "savings"]')

    from utils.mentor_notifications import create_notification_data

    messages = [
        {'text': 'I need to save more money', 'timestamp': 1000, 'is_user': True},
        {'text': 'Have you tried budgeting?', 'timestamp': 1001, 'is_user': False},
        {'text': 'Not really, how do I start?', 'timestamp': 1002, 'is_user': True},
    ]

    result = create_notification_data(messages, frequency=3)

    assert "topics" in result["context"]["filters"]
    assert result["context"]["filters"]["topics"] == ["budgeting", "savings"]
    assert "prompt" in result
    assert "params" in result


# ── Proactive tool calling tests (#4728, #4729, #4730) ──


def test_proactive_tools_defined():
    """PROACTIVE_TOOLS should contain 3 tool definitions in OpenAI format."""
    from utils.mentor_notifications import PROACTIVE_TOOLS

    assert len(PROACTIVE_TOOLS) == 3

    names = [t["function"]["name"] for t in PROACTIVE_TOOLS]
    assert "trigger_argument_perspective" in names
    assert "trigger_goal_misalignment" in names
    assert "trigger_emotional_support" in names

    for tool in PROACTIVE_TOOLS:
        assert tool["type"] == "function"
        params = tool["function"]["parameters"]
        assert "notification_text" in params["properties"]
        assert "confidence" in params["properties"]
        assert params["additionalProperties"] is False


def test_proactive_tools_required_fields():
    """Each tool should require notification_text and confidence."""
    from utils.mentor_notifications import PROACTIVE_TOOLS

    for tool in PROACTIVE_TOOLS:
        required = tool["function"]["parameters"]["required"]
        assert "notification_text" in required, f"{tool['function']['name']} missing notification_text"
        assert "confidence" in required, f"{tool['function']['name']} missing confidence"


def test_try_proactive_tools_triggered():
    """_try_proactive_tools should return notification data when tool fires with high confidence."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Alice", "Alice is a software engineer who values honesty.")

    # Mock the LLM to return a tool call
    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "Hey Alice, sounds like a tough day. Try a 10-min walk outside?",
                "detected_emotion": "frustration",
                "suggested_action": "Take a short walk",
                "confidence": 0.85,
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [
        {"text": "Ugh everything is going wrong today", "timestamp": 1000, "is_user": True},
        {"text": "What happened?", "timestamp": 1001, "is_user": False},
        {"text": "I feel so frustrated with work", "timestamp": 1002, "is_user": True},
    ]

    results = _try_proactive_tools("test_uid", messages, frequency=3)

    assert len(results) == 1
    assert results[0]["tool_name"] == "trigger_emotional_support"
    assert "tough day" in results[0]["notification_text"]
    assert results[0]["tool_args"]["confidence"] == 0.85

    # Verify bind_tools was called with our tool defs
    mock_llm_mini.bind_tools.assert_called_once()
    call_args = mock_llm_mini.bind_tools.call_args
    assert len(call_args[0][0]) == 3  # 3 tools passed
    assert call_args[1]["tool_choice"] == "auto"


def test_try_proactive_tools_no_trigger():
    """_try_proactive_tools should return None when LLM makes no tool call."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Bob", "Bob likes cooking.")

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = []  # No tool calls

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [
        {"text": "Nice weather today", "timestamp": 1000, "is_user": True},
        {"text": "Yeah pretty sunny", "timestamp": 1001, "is_user": False},
    ]

    results = _try_proactive_tools("test_uid", messages, frequency=3)
    assert results == []


def test_try_proactive_tools_low_confidence():
    """_try_proactive_tools should return empty list when confidence is below threshold."""
    from utils.mentor_notifications import _try_proactive_tools, PROACTIVE_CONFIDENCE_THRESHOLD

    mock_get_prompt_memories.return_value = ("Carol", "Carol is a teacher.")

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_argument_perspective",
            "args": {
                "notification_text": "Maybe consider their point of view?",
                "other_person": "coworker",
                "confidence": 0.4,  # Below threshold
                "rationale": "Slight disagreement detected",
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [
        {"text": "My coworker said something I disagree with", "timestamp": 1000, "is_user": True},
    ]

    results = _try_proactive_tools("test_uid", messages, frequency=3)
    assert results == []
    assert PROACTIVE_CONFIDENCE_THRESHOLD == 0.7


def test_try_proactive_tools_goal_misalignment():
    """_try_proactive_tools should detect goal misalignment with high confidence."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Dave", "Dave wants to get fit.")
    mock_get_user_goals.return_value = [{"title": "Exercise 3x per week", "is_active": True}]

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_goal_misalignment",
            "args": {
                "notification_text": "Dave, skipping gym this week conflicts with your 3x/week goal. Maybe a short workout?",
                "goal_name": "Exercise 3x per week",
                "conflict_description": "Planning to skip exercise contradicts fitness goal",
                "confidence": 0.9,
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [
        {"text": "I think I'll just skip the gym this whole week", "timestamp": 1000, "is_user": True},
        {"text": "You sure? You seemed motivated", "timestamp": 1001, "is_user": False},
        {"text": "Yeah I just don't feel like it", "timestamp": 1002, "is_user": True},
    ]

    results = _try_proactive_tools("test_uid", messages, frequency=3)

    assert len(results) == 1
    assert results[0]["tool_name"] == "trigger_goal_misalignment"
    assert results[0]["tool_args"]["goal_name"] == "Exercise 3x per week"
    # Verify goals were fetched
    mock_get_user_goals.assert_called_with("test_uid")


def test_try_proactive_tools_handles_exception():
    """_try_proactive_tools should return None and log on exception."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.side_effect = Exception("DB connection failed")

    messages = [{"text": "hello", "timestamp": 1000, "is_user": True}]
    results = _try_proactive_tools("test_uid", messages, frequency=3)

    assert results == []
    mock_get_prompt_memories.side_effect = None


def test_try_proactive_tools_empty_notification_text():
    """_try_proactive_tools should return None when notification_text is empty."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Eve", "Eve is a designer.")

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "",  # Empty text
                "detected_emotion": "sadness",
                "confidence": 0.9,
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [{"text": "I feel sad", "timestamp": 1000, "is_user": True}]
    results = _try_proactive_tools("test_uid", messages, frequency=3)

    assert results == []


def test_process_mentor_notification_tries_tools_first():
    """process_mentor_notification should try proactive tools and always include notification_data."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    # Reset buffer
    message_buffer.buffers.clear()

    mock_get_prompt_memories.return_value = ("Frank", "Frank is a manager.")

    # Mock tool calling to return a result
    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_argument_perspective",
            "args": {
                "notification_text": "Frank, she has a valid point about the deadline.",
                "other_person": "wife",
                "confidence": 0.88,
                "rationale": "Clear disagreement about priorities",
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    # Mock extract_topics (called by create_notification_data)
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["work-life balance", "priorities"]')

    segments = [
        {"text": "She keeps saying I work too much", "start": 1000, "is_user": True},
        {"text": "Do you think she's right?", "start": 1001, "is_user": False},
        {"text": "No way, I need to hit my targets", "start": 1002, "is_user": True},
        {"text": "But maybe balance matters too", "start": 1003, "is_user": False},
    ]

    result = process_mentor_notification("test_uid_frank", segments)

    assert result is not None
    assert result.get("source") == "tool"
    assert len(result["notifications"]) == 1
    assert result["notifications"][0]["tool_name"] == "trigger_argument_perspective"
    noti_text = result["notifications"][0]["notification_text"]
    assert "deadline" in noti_text or "valid point" in noti_text
    # create_notification_data always called — prompt/params/context present
    assert "prompt" in result
    assert "params" in result
    assert "context" in result


def test_process_mentor_notification_falls_back_to_prompt():
    """process_mentor_notification should fall back to prompt dict when no tool fires."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    # Reset buffer
    message_buffer.buffers.clear()

    mock_get_prompt_memories.return_value = ("Grace", "Grace likes gardening.")

    # Mock tool calling to return NO tool calls
    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = []

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    # Reset regular llm_mini for extract_topics fallback
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["gardening", "spring"]')

    segments = [
        {"text": "I should plant tomatoes this spring", "start": 1000, "is_user": True},
        {"text": "Great idea", "start": 1001, "is_user": False},
        {"text": "Yeah and maybe some herbs too", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_grace", segments)

    assert result is not None
    assert "source" not in result  # Not tool-based
    assert "prompt" in result  # Existing prompt dict format
    assert "params" in result


def test_goals_included_in_tool_context():
    """_try_proactive_tools should include user goals in the LLM prompt."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Helen", "Helen is a student.")
    mock_get_user_goals.return_value = [
        {"title": "Graduate with honors", "is_active": True},
        {"title": "Learn Spanish", "is_active": True},
    ]

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = []

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [{"text": "I should study more", "timestamp": 1000, "is_user": True}]

    _try_proactive_tools("test_uid_helen", messages, frequency=3)

    # Check that the user message sent to LLM includes goals
    invoke_call = mock_bound.invoke.call_args[0][0]
    user_msg_content = invoke_call[1].content  # HumanMessage is second
    assert "Graduate with honors" in user_msg_content
    assert "Learn Spanish" in user_msg_content


def test_no_goals_shows_placeholder():
    """_try_proactive_tools should handle users with no goals."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Ian", "Ian is new.")
    mock_get_user_goals.return_value = []  # No goals

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = []

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [{"text": "hello world", "timestamp": 1000, "is_user": True}]

    _try_proactive_tools("test_uid_ian", messages, frequency=3)

    invoke_call = mock_bound.invoke.call_args[0][0]
    user_msg_content = invoke_call[1].content
    assert "No goals set" in user_msg_content


def test_multiple_tool_calls():
    """_try_proactive_tools should return multiple results when multiple tools fire."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Jane", "Jane is stressed about work and fitness.")
    mock_get_user_goals.return_value = [{"title": "Exercise daily", "is_active": True}]

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "Jane, sounds like a rough day. Try a 5-min breathing exercise?",
                "detected_emotion": "stress",
                "suggested_action": "Breathing exercise",
                "confidence": 0.9,
            },
        },
        {
            "name": "trigger_goal_misalignment",
            "args": {
                "notification_text": "Jane, skipping your workout goes against your daily exercise goal.",
                "goal_name": "Exercise daily",
                "conflict_description": "Canceling workout contradicts exercise goal",
                "confidence": 0.85,
            },
        },
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [
        {"text": "I'm so stressed today, I'm canceling my workout", "timestamp": 1000, "is_user": True},
        {"text": "Are you sure?", "timestamp": 1001, "is_user": False},
        {"text": "Yeah I just can't deal with anything right now", "timestamp": 1002, "is_user": True},
    ]

    results = _try_proactive_tools("test_uid_jane", messages, frequency=3)

    assert len(results) == 2
    assert results[0]["tool_name"] == "trigger_emotional_support"
    assert results[1]["tool_name"] == "trigger_goal_misalignment"


def test_multiple_tools_mixed_confidence():
    """Only tool calls above confidence threshold should be included."""
    from utils.mentor_notifications import _try_proactive_tools

    mock_get_prompt_memories.return_value = ("Kim", "Kim is a developer.")
    mock_get_user_goals.return_value = []

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "Kim, take a break.",
                "detected_emotion": "frustration",
                "confidence": 0.8,  # Above threshold
            },
        },
        {
            "name": "trigger_argument_perspective",
            "args": {
                "notification_text": "Maybe they have a point.",
                "other_person": "manager",
                "confidence": 0.3,  # Below threshold
                "rationale": "Mild disagreement",
            },
        },
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    messages = [{"text": "My manager is annoying and I'm frustrated", "timestamp": 1000, "is_user": True}]

    results = _try_proactive_tools("test_uid_kim", messages, frequency=3)

    assert len(results) == 1
    assert results[0]["tool_name"] == "trigger_emotional_support"


def test_process_mentor_notification_multiple_tools():
    """process_mentor_notification should return multiple notifications in the result."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    mock_get_prompt_memories.return_value = ("Lisa", "Lisa is a busy parent.")
    mock_get_user_goals.return_value = [{"title": "Spend more time with kids", "is_active": True}]

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_goal_misalignment",
            "args": {
                "notification_text": "Lisa, working late again conflicts with your family time goal.",
                "goal_name": "Spend more time with kids",
                "conflict_description": "Working late reduces family time",
                "confidence": 0.92,
            },
        },
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "Lisa, you sound overwhelmed. Can you delegate one task today?",
                "detected_emotion": "overwhelm",
                "suggested_action": "Delegate one task",
                "confidence": 0.78,
            },
        },
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    # Mock extract_topics (called by create_notification_data)
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["parenting", "work-life balance"]')

    segments = [
        {"text": "I have to work late again tonight", "start": 1000, "is_user": True},
        {"text": "The kids will miss you", "start": 1001, "is_user": False},
        {"text": "I know, I feel terrible about it", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_lisa", segments)

    assert result is not None
    assert result["source"] == "tool"
    assert len(result["notifications"]) == 2
    assert result["notifications"][0]["tool_name"] == "trigger_goal_misalignment"
    assert result["notifications"][1]["tool_name"] == "trigger_emotional_support"
    # create_notification_data always called — prompt/params/context present
    assert "prompt" in result
    assert "params" in result
