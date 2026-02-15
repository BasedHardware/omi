"""
Tests for mentor_notifications.py and the proactive trigger flow (#4728-#4730).

mentor_notifications.py: buffering, topic extraction, notification data creation.
app_integrations._process_triggers: generic trigger evaluation with confidence gating.
app_integrations._build_trigger_context: scope-aware context building for trigger evaluation.
app_integrations._process_proactive_notification: notification delivery with has_triggers flag.
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


def _setup_app_integrations_stubs():
    """Stub all app_integrations dependencies so it can be imported in tests."""
    apps_mod = sys.modules.get("database.apps") or _stub_module("database.apps")
    apps_mod.record_app_usage = MagicMock()
    chat_db_mod = sys.modules.get("database.chat") or _stub_module("database.chat")
    chat_db_mod.add_app_message = MagicMock()
    chat_db_mod.get_app_messages = MagicMock(return_value=[])
    redis_mod = sys.modules.get("database.redis_db") or _stub_module("database.redis_db")
    redis_mod.get_generic_cache = MagicMock(return_value=None)
    redis_mod.set_generic_cache = MagicMock()
    redis_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)
    redis_mod.set_proactive_noti_sent_at = MagicMock()
    redis_mod.get_proactive_noti_sent_at_ttl = MagicMock(return_value=0)
    mem_mod = sys.modules.get("database.mem_db") or _stub_module("database.mem_db")
    mem_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)
    mem_mod.set_proactive_noti_sent_at = MagicMock()
    vec_mod = sys.modules.get("database.vector_db") or _stub_module("database.vector_db")
    vec_mod.query_vectors_by_metadata = MagicMock(return_value=[])
    conv_db_mod = sys.modules.get("database.conversations") or _stub_module("database.conversations")
    conv_db_mod.get_conversations_by_id = MagicMock(return_value=[])

    noti_msg_mod = _stub_module("models.notification_message")
    mock_noti_msg = MagicMock()
    mock_noti_msg.get_message_as_dict = MagicMock(return_value={})
    noti_msg_mod.NotificationMessage = mock_noti_msg

    conv_mod = sys.modules.get("models.conversation") or _stub_module("models.conversation")
    if not hasattr(conv_mod, 'Conversation'):
        conv_mod.Conversation = MagicMock()
    if not hasattr(conv_mod, 'ConversationSource'):
        conv_mod.ConversationSource = MagicMock()

    chat_mod = sys.modules.get("models.chat") or _stub_module("models.chat")
    if not hasattr(chat_mod, 'Message'):
        chat_mod.Message = MagicMock()

    apps_util_mod = _stub_module("utils.apps")
    apps_util_mod.get_available_apps = MagicMock(return_value=[])

    notifications_util_mod = _stub_module("utils.notifications")
    mock_send = MagicMock()
    notifications_util_mod.send_notification = mock_send

    proactive_noti_mod = _stub_module("utils.llm.proactive_notification")
    proactive_noti_mod.get_proactive_message = MagicMock()

    clients_mod_existing = sys.modules.get("utils.llm.clients") or _stub_module("utils.llm.clients")
    if not hasattr(clients_mod_existing, 'generate_embedding'):
        clients_mod_existing.generate_embedding = MagicMock(return_value=[0] * 3072)

    tracker_mod_existing = sys.modules.get("utils.llm.usage_tracker") or _stub_module("utils.llm.usage_tracker")
    if not hasattr(tracker_mod_existing, 'track_usage'):
        tracker_mod_existing.track_usage = MagicMock()
    if not hasattr(tracker_mod_existing, 'Features'):
        tracker_mod_existing.Features = MagicMock()

    return mock_send


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


def test_create_notification_data_includes_tools():
    """create_notification_data should include tools and messages in output."""
    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["tech"]')

    from utils.mentor_notifications import create_notification_data, PROACTIVE_TRIGGERS

    messages = [
        {'text': 'I love coding', 'timestamp': 1000, 'is_user': True},
        {'text': 'Me too', 'timestamp': 1001, 'is_user': False},
        {'text': 'Lets build something', 'timestamp': 1002, 'is_user': True},
    ]

    result = create_notification_data(messages, frequency=3)

    assert "triggers" in result
    assert result["triggers"] == PROACTIVE_TRIGGERS
    assert "messages" in result
    assert result["messages"] == messages


# ── Proactive trigger definitions tests ──


def test_proactive_tools_defined():
    """PROACTIVE_TRIGGERS should contain 3 tool definitions in OpenAI format."""
    from utils.mentor_notifications import PROACTIVE_TRIGGERS

    assert len(PROACTIVE_TRIGGERS) == 3

    names = [t["function"]["name"] for t in PROACTIVE_TRIGGERS]
    assert "trigger_argument_perspective" in names
    assert "trigger_goal_misalignment" in names
    assert "trigger_emotional_support" in names

    for tool in PROACTIVE_TRIGGERS:
        assert tool["type"] == "function"
        params = tool["function"]["parameters"]
        assert "notification_text" in params["properties"]
        assert "confidence" in params["properties"]
        assert params["additionalProperties"] is False


def test_proactive_tools_required_fields():
    """Each tool should require notification_text and confidence."""
    from utils.mentor_notifications import PROACTIVE_TRIGGERS

    for tool in PROACTIVE_TRIGGERS:
        required = tool["function"]["parameters"]["required"]
        assert "notification_text" in required, f"{tool['function']['name']} missing notification_text"
        assert "confidence" in required, f"{tool['function']['name']} missing confidence"


# ── Tool calling tests (app_integrations._process_triggers) ──


def test_process_triggers_triggered():
    """_process_triggers should return notification data when trigger fires with high confidence."""
    _setup_app_integrations_stubs()

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

    from utils.mentor_notifications import PROACTIVE_TRIGGERS, PROACTIVE_CONFIDENCE_THRESHOLD
    import utils.app_integrations as app_int

    results = app_int._process_triggers(
        "test_uid", "system prompt", "user message", PROACTIVE_TRIGGERS, PROACTIVE_CONFIDENCE_THRESHOLD
    )

    assert len(results) == 1
    assert results[0]["trigger_name"] == "trigger_emotional_support"
    assert "tough day" in results[0]["notification_text"]
    assert results[0]["trigger_args"]["confidence"] == 0.85

    mock_llm_mini.bind_tools.assert_called_once()
    call_args = mock_llm_mini.bind_tools.call_args
    assert len(call_args[0][0]) == 3  # 3 tools passed
    assert call_args[1]["tool_choice"] == "auto"


def test_process_triggers_no_trigger():
    """_process_triggers should return empty list when no trigger fires."""
    _setup_app_integrations_stubs()

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = []

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    from utils.mentor_notifications import PROACTIVE_TRIGGERS
    import utils.app_integrations as app_int

    results = app_int._process_triggers("test_uid", "system prompt", "user message", PROACTIVE_TRIGGERS, 0.7)
    assert results == []


def test_process_triggers_low_confidence():
    """_process_triggers should return empty list when confidence is below threshold."""
    _setup_app_integrations_stubs()

    from utils.mentor_notifications import PROACTIVE_TRIGGERS, PROACTIVE_CONFIDENCE_THRESHOLD

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

    import utils.app_integrations as app_int

    results = app_int._process_triggers(
        "test_uid", "system prompt", "user message", PROACTIVE_TRIGGERS, PROACTIVE_CONFIDENCE_THRESHOLD
    )
    assert results == []
    assert PROACTIVE_CONFIDENCE_THRESHOLD == 0.7


def test_process_triggers_handles_exception():
    """_process_triggers should return empty list on LLM exception."""
    _setup_app_integrations_stubs()

    mock_llm_mini.bind_tools = MagicMock(side_effect=Exception("LLM error"))

    from utils.mentor_notifications import PROACTIVE_TRIGGERS
    import utils.app_integrations as app_int

    results = app_int._process_triggers("test_uid", "system prompt", "user message", PROACTIVE_TRIGGERS, 0.7)

    assert results == []
    mock_llm_mini.bind_tools.side_effect = None


def test_process_triggers_empty_notification_text():
    """_process_triggers should skip when notification_text is empty."""
    _setup_app_integrations_stubs()

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "",
                "detected_emotion": "sadness",
                "confidence": 0.9,
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    from utils.mentor_notifications import PROACTIVE_TRIGGERS
    import utils.app_integrations as app_int

    results = app_int._process_triggers("test_uid", "system prompt", "user message", PROACTIVE_TRIGGERS, 0.7)
    assert results == []


def test_process_triggers_empty_tools_list():
    """_process_triggers should return empty list when no tools provided."""
    _setup_app_integrations_stubs()

    import utils.app_integrations as app_int

    results = app_int._process_triggers("test_uid", "system prompt", "user message", [], 0.7)
    assert results == []


# ── Tool context tests (app_integrations._build_trigger_context) ──


def _make_mentor_app():
    from models.app import App, ProactiveNotification

    return App(
        id='mentor',
        name='Omi',
        category='productivity',
        author='Omi',
        description='AI mentor',
        image='/test.png',
        capabilities={'proactive_notification'},
        enabled=True,
        proactive_notification=ProactiveNotification(scopes={'user_name', 'user_facts', 'user_context', 'user_chat'}),
    )


def test_build_trigger_context_includes_goals():
    """_build_trigger_context should include user goals in the user message."""
    _setup_app_integrations_stubs()

    mock_get_user_goals.return_value = [{"title": "Exercise 3x per week", "is_active": True}]

    import utils.app_integrations as app_int

    data = {
        "prompt": "You are Dave's proactive AI mentor.",
        "messages": [
            {"text": "I think I'll skip the gym", "timestamp": 1000, "is_user": True},
            {"text": "You sure?", "timestamp": 1001, "is_user": False},
        ],
    }

    system_prompt, user_message = app_int._build_trigger_context(
        "test_uid",
        "Dave",
        "Dave wants to get fit.",
        None,
        [],
        data.get('messages', []),
        data,
    )

    assert "mentor" in system_prompt.lower()
    assert "Exercise 3x per week" in user_message
    assert "[Dave]: I think I'll skip the gym" in user_message
    mock_get_user_goals.assert_called_with("test_uid")


def test_process_mentor_notification_returns_tools_and_messages():
    """process_mentor_notification should include tools and messages in notification_data."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer, PROACTIVE_TRIGGERS

    message_buffer.buffers.clear()

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
    # No longer has source/notifications — trigger evaluation is downstream
    assert "source" not in result
    assert "notifications" not in result
    # Has tools and messages for downstream processing
    assert "triggers" in result
    assert result["triggers"] == PROACTIVE_TRIGGERS
    assert "messages" in result
    assert len(result["messages"]) > 0
    # Still has prompt/params/context
    assert "prompt" in result
    assert "params" in result
    assert "context" in result


def test_process_mentor_notification_falls_back_to_prompt():
    """process_mentor_notification should return prompt dict with tools included."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["gardening", "spring"]')

    segments = [
        {"text": "I should plant tomatoes this spring", "start": 1000, "is_user": True},
        {"text": "Great idea", "start": 1001, "is_user": False},
        {"text": "Yeah and maybe some herbs too", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_grace", segments)

    assert result is not None
    assert "source" not in result
    assert "prompt" in result
    assert "params" in result
    assert "triggers" in result
    assert "messages" in result


def test_build_trigger_context_multiple_goals():
    """_build_trigger_context should include multiple goals in the user message."""
    _setup_app_integrations_stubs()

    mock_get_user_goals.return_value = [
        {"title": "Graduate with honors", "is_active": True},
        {"title": "Learn Spanish", "is_active": True},
    ]

    import utils.app_integrations as app_int

    data = {
        "prompt": "You are a mentor.",
        "messages": [{"text": "I should study more", "timestamp": 1000, "is_user": True}],
    }

    system_prompt, user_message = app_int._build_trigger_context(
        "test_uid_helen",
        "Helen",
        "Helen is a student.",
        None,
        [],
        data.get('messages', []),
        data,
    )

    assert "Graduate with honors" in user_message
    assert "Learn Spanish" in user_message


def test_build_trigger_context_no_goals():
    """_build_trigger_context with no goals should not include goals section."""
    _setup_app_integrations_stubs()

    mock_get_user_goals.return_value = []

    import utils.app_integrations as app_int

    data = {
        "prompt": "You are a mentor.",
        "messages": [{"text": "hello world", "timestamp": 1000, "is_user": True}],
    }

    system_prompt, user_message = app_int._build_trigger_context(
        "test_uid_ian",
        "Ian",
        "Ian is new.",
        None,
        [],
        data.get('messages', []),
        data,
    )

    assert "goals" not in user_message.lower()


def test_multiple_tool_calls():
    """_process_triggers should return multiple results when multiple tools fire."""
    _setup_app_integrations_stubs()

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

    from utils.mentor_notifications import PROACTIVE_TRIGGERS
    import utils.app_integrations as app_int

    results = app_int._process_triggers("test_uid_jane", "system prompt", "user message", PROACTIVE_TRIGGERS, 0.7)

    assert len(results) == 2
    assert results[0]["trigger_name"] == "trigger_emotional_support"
    assert results[1]["trigger_name"] == "trigger_goal_misalignment"


def test_multiple_tools_mixed_confidence():
    """Only tool calls above confidence threshold should be included."""
    _setup_app_integrations_stubs()

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "Kim, take a break.",
                "detected_emotion": "frustration",
                "confidence": 0.8,
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

    from utils.mentor_notifications import PROACTIVE_TRIGGERS
    import utils.app_integrations as app_int

    results = app_int._process_triggers("test_uid_kim", "system prompt", "user message", PROACTIVE_TRIGGERS, 0.7)

    assert len(results) == 1
    assert results[0]["trigger_name"] == "trigger_emotional_support"


# ── Tool delivery through _process_proactive_notification ──


def test_process_proactive_notification_tool_delivery():
    """_process_proactive_notification with has_triggers=True sends trigger notifications AND the main notification."""
    _setup_app_integrations_stubs()

    import utils.app_integrations as app_int

    app_int._hit_proactive_notification_rate_limits = MagicMock(return_value=False)
    app_int._set_proactive_noti_sent_at = MagicMock()

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    # Mock _process_triggers to return results
    original_process_triggers = app_int._process_triggers
    app_int._process_triggers = MagicMock(
        return_value=[
            {"notification_text": "Hey, take a break!", "trigger_name": "trigger_emotional_support"},
            {"notification_text": "This conflicts with your goal.", "trigger_name": "trigger_goal_misalignment"},
        ]
    )

    # Prompt-based path also runs
    app_int.get_proactive_message = MagicMock(return_value="Main prompt notification")

    from models.app import App, ProactiveNotification

    mentor_app = App(
        id='mentor',
        name='Omi',
        category='productivity',
        author='Omi',
        description='AI mentor',
        image='/test.png',
        capabilities={'proactive_notification'},
        enabled=True,
        proactive_notification=ProactiveNotification(scopes={'user_name', 'user_facts', 'user_context', 'user_chat'}),
    )

    triggers = [{"type": "function", "function": {"name": "test"}}]
    data = {
        "messages": [{"text": "test", "timestamp": 1000, "is_user": True}],
        "prompt": "Some prompt",
        "params": ["user_name"],
        "context": {"filters": {"topics": ["stress"]}},
    }

    try:
        result = app_int._process_proactive_notification(
            "test_uid",
            mentor_app,
            data,
            triggers=triggers,
            has_triggers=True,
        )

        # Trigger notifications sent as extra (2) + main prompt notification (1) = 3
        assert mock_send_app.call_count == 3
        # Result is the main prompt message
        assert result == "Main prompt notification"
    finally:
        app_int._process_triggers = original_process_triggers


def test_process_proactive_notification_tool_rate_limited():
    """_process_proactive_notification should skip trigger notifications when rate-limited."""
    _setup_app_integrations_stubs()

    import utils.app_integrations as app_int

    app_int._hit_proactive_notification_rate_limits = MagicMock(return_value=True)

    mock_send = MagicMock()
    app_int.send_app_notification = mock_send

    from models.app import App, ProactiveNotification

    mentor_app = App(
        id='mentor',
        name='Omi',
        category='productivity',
        author='Omi',
        description='AI mentor',
        image='/test.png',
        capabilities={'proactive_notification'},
        enabled=True,
        proactive_notification=ProactiveNotification(scopes={'user_name', 'user_facts', 'user_context', 'user_chat'}),
    )

    data = {
        "messages": [{"text": "test", "timestamp": 1000, "is_user": True}],
    }
    triggers = [{"type": "function", "function": {"name": "test"}}]

    result = app_int._process_proactive_notification("test_uid", mentor_app, data, triggers=triggers, has_triggers=True)

    assert result is None
    mock_send.assert_not_called()


def test_process_proactive_notification_has_triggers_false_skips_triggers():
    """_process_proactive_notification with has_triggers=False should NOT call triggers."""
    _setup_app_integrations_stubs()

    import utils.app_integrations as app_int

    app_int._hit_proactive_notification_rate_limits = MagicMock(return_value=False)
    app_int._set_proactive_noti_sent_at = MagicMock()

    mock_process_triggers = MagicMock()
    original_process_triggers = app_int._process_triggers
    app_int._process_triggers = mock_process_triggers

    # Patch get_proactive_message directly on the module (from-import binding)
    app_int.get_proactive_message = MagicMock(return_value="Prompt-based advice here")

    from models.app import App, ProactiveNotification

    some_app = App(
        id='some-other-app',
        name='Other App',
        category='productivity',
        author='Third Party',
        description='Not mentor',
        image='/test.png',
        capabilities={'proactive_notification'},
        enabled=True,
        proactive_notification=ProactiveNotification(scopes={'user_name', 'user_facts'}),
    )

    data = {
        "messages": [{"text": "test", "timestamp": 1000, "is_user": True}],
        "prompt": "Some prompt",
        "params": ["user_name", "user_facts"],
        "context": {"filters": {"topics": []}},
    }
    triggers = [{"type": "function", "function": {"name": "test"}}]

    try:
        result = app_int._process_proactive_notification(
            "test_uid", some_app, data, triggers=triggers
        )  # has_triggers defaults to False

        # Triggers should NOT be called
        mock_process_triggers.assert_not_called()
        # Should fall through to prompt-based path
        assert result is not None
    finally:
        app_int._process_triggers = original_process_triggers


def test_process_proactive_notification_no_tool_results_still_sends_prompt():
    """When triggers don't fire, only the main prompt notification is sent."""
    _setup_app_integrations_stubs()

    import utils.app_integrations as app_int

    app_int._hit_proactive_notification_rate_limits = MagicMock(return_value=False)
    app_int._set_proactive_noti_sent_at = MagicMock()

    original_process_triggers = app_int._process_triggers
    app_int._process_triggers = MagicMock(return_value=[])  # No trigger results

    app_int.get_proactive_message = MagicMock(return_value="Main prompt advice")

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    from models.app import App, ProactiveNotification

    mentor_app = App(
        id='mentor',
        name='Omi',
        category='productivity',
        author='Omi',
        description='AI mentor',
        image='/test.png',
        capabilities={'proactive_notification'},
        enabled=True,
        proactive_notification=ProactiveNotification(scopes={'user_name', 'user_facts', 'user_context', 'user_chat'}),
    )

    triggers = [{"type": "function", "function": {"name": "test"}}]
    data = {
        "messages": [{"text": "test", "timestamp": 1000, "is_user": True}],
        "prompt": "Some prompt",
        "params": ["user_name", "user_facts", "user_context", "user_chat"],
        "context": {"filters": {"topics": []}},
    }

    try:
        result = app_int._process_proactive_notification(
            "test_uid", mentor_app, data, triggers=triggers, has_triggers=True
        )

        app_int._process_triggers.assert_called_once()
        assert result == "Main prompt advice"
        assert mock_send_app.call_count == 1  # Only the main prompt notification
    finally:
        app_int._process_triggers = original_process_triggers


# ── Boundary tests ──


def test_confidence_at_exact_threshold():
    """Tool call with confidence == PROACTIVE_CONFIDENCE_THRESHOLD should be accepted."""
    _setup_app_integrations_stubs()

    from utils.mentor_notifications import PROACTIVE_TRIGGERS, PROACTIVE_CONFIDENCE_THRESHOLD

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "Hey, you seem stressed. Take a moment.",
                "detected_emotion": "stress",
                "confidence": PROACTIVE_CONFIDENCE_THRESHOLD,
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    import utils.app_integrations as app_int

    results = app_int._process_triggers(
        "test_uid",
        "You are a mentor.",
        "I'm stressed",
        PROACTIVE_TRIGGERS,
        PROACTIVE_CONFIDENCE_THRESHOLD,
    )

    assert len(results) == 1
    assert results[0]["trigger_args"]["confidence"] == PROACTIVE_CONFIDENCE_THRESHOLD


def test_notification_text_too_short():
    """Tool call with notification_text < 5 chars should be rejected."""
    _setup_app_integrations_stubs()

    mock_tool_response = MagicMock()
    mock_tool_response.tool_calls = [
        {
            "name": "trigger_emotional_support",
            "args": {
                "notification_text": "Hey",  # Only 3 chars
                "detected_emotion": "stress",
                "confidence": 0.9,
            },
        }
    ]

    mock_bound = MagicMock()
    mock_bound.invoke = MagicMock(return_value=mock_tool_response)
    mock_llm_mini.bind_tools = MagicMock(return_value=mock_bound)

    from utils.mentor_notifications import PROACTIVE_TRIGGERS, PROACTIVE_CONFIDENCE_THRESHOLD
    import utils.app_integrations as app_int

    results = app_int._process_triggers(
        "test_uid",
        "You are a mentor.",
        "I'm stressed",
        PROACTIVE_TRIGGERS,
        PROACTIVE_CONFIDENCE_THRESHOLD,
    )
    assert results == []


def test_empty_tool_results_falls_through_to_prompt():
    """When trigger results are empty, process_mentor_notification returns data for prompt-based path."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    mock_llm_mini.invoke.reset_mock()
    mock_llm_mini.invoke.return_value = MagicMock(content='["writing"]')

    segments = [
        {"text": "I should write more", "start": 1000, "is_user": True},
        {"text": "You should", "start": 1001, "is_user": False},
        {"text": "But I have no inspiration", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_faye", segments)

    # No source key — downstream _process_proactive_notification handles trigger evaluation
    assert result is not None
    assert "source" not in result
    assert "prompt" in result
    assert "params" in result
    assert "triggers" in result
    assert "messages" in result
