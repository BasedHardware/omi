"""
Tests for the proactive notification system overhaul.

Tests cover:
- MessageBuffer behavior (mentor_notifications.py)
- process_mentor_notification() return type (list of messages)
- evaluate_proactive_notification() structured output (proactive_notification.py)
- _process_mentor_proactive_notification() end-to-end (app_integrations.py)
- Source-level checks (no raw OpenAI client)
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

# Ensure backend is on sys.path for real module imports
_backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


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
mock_llm_mini.invoke = MagicMock(return_value=MagicMock(content='test'))

# Stub utils.llm package — set real __path__ so Python can find real submodules
llm_mod = _stub_module("utils.llm")
if not hasattr(llm_mod, '__path__') or not llm_mod.__path__:
    llm_mod.__path__ = [os.path.join(_backend_dir, "utils", "llm")]

# Ensure utils package exists with real __path__
utils_mod = _stub_module("utils")
if not hasattr(utils_mod, '__path__') or not utils_mod.__path__:
    utils_mod.__path__ = [os.path.join(_backend_dir, "utils")]

clients_mod = _stub_module("utils.llm.clients")
clients_mod.llm_mini = mock_llm_mini
clients_mod.generate_embedding = MagicMock(return_value=[0] * 3072)

# Stub usage tracker
tracker_mod = _stub_module("utils.llm.usage_tracker")
tracker_mod.get_usage_callback = MagicMock(return_value=[])

# Stub utils.llms.memory (get_prompt_memories)
llms_mod = _stub_module("utils.llms")
if not hasattr(llms_mod, '__path__'):
    llms_mod.__path__ = []
memory_mod = _stub_module("utils.llms.memory")
mock_get_prompt_memories = MagicMock(return_value=("TestUser", "TestUser likes hiking and coding."))
memory_mod.get_prompt_memories = mock_get_prompt_memories

# Stub models.chat.Message before loading proactive_notification
models_mod = _stub_module("models")
if not hasattr(models_mod, '__path__'):
    models_mod.__path__ = []
chat_model_mod = _stub_module("models.chat")
mock_message_cls = MagicMock()
mock_message_cls.get_messages_as_string = MagicMock(return_value="")
chat_model_mod.Message = mock_message_cls

# Now import the REAL proactive_notification module (it uses stubbed llm_mini, Message, get_prompt_memories)
# Remove any stale stub first
if "utils.llm.proactive_notification" in sys.modules:
    del sys.modules["utils.llm.proactive_notification"]

from utils.llm.proactive_notification import (
    ProactiveAdvice,
    ProactiveNotificationResult,
    evaluate_proactive_notification,
    get_proactive_message,
    FREQUENCY_TO_BASE_THRESHOLD,
    FREQUENCY_GUIDANCE,
    MAX_DAILY_NOTIFICATIONS,
)


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
    redis_mod.get_daily_notification_count = MagicMock(return_value=0)
    redis_mod.incr_daily_notification_count = MagicMock(return_value=1)
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

    app_model_mod = sys.modules.get("models.app") or _stub_module("models.app")
    if not hasattr(app_model_mod, 'App'):
        app_model_mod.App = MagicMock()
    if not hasattr(app_model_mod, 'UsageHistoryType'):
        app_model_mod.UsageHistoryType = MagicMock()

    apps_util_mod = _stub_module("utils.apps")
    apps_util_mod.get_available_apps = MagicMock(return_value=[])

    notifications_util_mod = _stub_module("utils.notifications")
    mock_send = MagicMock()
    notifications_util_mod.send_notification = mock_send

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


def _read_mentor_source() -> str:
    return (Path(_backend_dir) / "utils" / "mentor_notifications.py").read_text()


def _read_proactive_source() -> str:
    return (Path(_backend_dir) / "utils" / "llm" / "proactive_notification.py").read_text()


def test_no_raw_openai_client():
    """Verify mentor_notifications.py does not import or use the raw OpenAI client."""
    source = _read_mentor_source()
    assert "from openai import OpenAI" not in source
    assert "client.chat.completions.create" not in source
    assert 'model="gpt-4"' not in source


def test_proactive_notification_uses_structured_output():
    """Verify proactive_notification.py uses structured output pattern."""
    source = _read_proactive_source()
    assert "with_structured_output" in source
    assert "ProactiveNotificationResult" in source
    assert "ProactiveAdvice" in source


def test_proactive_notification_has_pydantic_models():
    """Verify proactive_notification.py defines proper Pydantic models."""
    source = _read_proactive_source()
    assert "class ProactiveAdvice(BaseModel)" in source
    assert "class ProactiveNotificationResult(BaseModel)" in source
    assert "has_advice" in source
    assert "confidence" in source
    assert "reasoning" in source


def test_proactive_notification_has_frequency_constants():
    """Verify proactive_notification.py has frequency-related constants."""
    source = _read_proactive_source()
    assert "FREQUENCY_TO_BASE_THRESHOLD" in source
    assert "FREQUENCY_GUIDANCE" in source
    assert "MAX_DAILY_NOTIFICATIONS" in source


def test_mentor_notifications_no_triggers():
    """Verify mentor_notifications.py no longer has trigger definitions."""
    source = _read_mentor_source()
    assert "PROACTIVE_TRIGGERS" not in source
    assert "PROACTIVE_CONFIDENCE_THRESHOLD" not in source
    assert "trigger_argument_perspective" not in source
    assert "trigger_goal_misalignment" not in source
    assert "trigger_emotional_support" not in source


def test_mentor_notifications_no_extract_topics():
    """Verify mentor_notifications.py no longer has extract_topics."""
    source = _read_mentor_source()
    assert "def extract_topics" not in source
    assert "def create_notification_data" not in source
    assert "def adjust_prompt_for_frequency" not in source


# ── MessageBuffer tests ──


def test_message_buffer_creates_session():
    """MessageBuffer should create a new session on first access."""
    from utils.mentor_notifications import MessageBuffer

    buf = MessageBuffer()
    data = buf.get_buffer("test_session")
    assert data['messages'] == []
    assert data['silence_detected'] is False
    assert data['words_after_silence'] == 0


def test_message_buffer_silence_detection():
    """MessageBuffer should detect silence after threshold."""
    import time
    from utils.mentor_notifications import MessageBuffer

    buf = MessageBuffer()
    buf.silence_threshold = 0.01  # Very short for testing

    data = buf.get_buffer("test_session_silence")
    data['messages'].append({'text': 'hello', 'timestamp': time.time(), 'is_user': True})

    time.sleep(0.02)  # Exceed silence threshold

    data = buf.get_buffer("test_session_silence")
    assert data['silence_detected'] is True
    assert data['messages'] == []


def test_message_buffer_cleanup():
    """MessageBuffer should clean up old sessions."""
    from utils.mentor_notifications import MessageBuffer

    buf = MessageBuffer()
    buf.buffers["old_session"] = {
        'messages': [],
        'last_analysis_time': 0,
        'last_activity': 0,  # Very old
        'words_after_silence': 0,
        'silence_detected': False,
    }

    buf.cleanup_old_sessions()
    assert "old_session" not in buf.buffers


# ── process_mentor_notification tests ──


def test_process_mentor_notification_returns_none_when_disabled():
    """process_mentor_notification returns None when frequency is 0."""
    sys.modules["database.notifications"].get_mentor_notification_frequency = MagicMock(return_value=0)

    from utils.mentor_notifications import process_mentor_notification

    result = process_mentor_notification("test_uid_disabled", [{"text": "hello", "start": 1000, "is_user": True}])
    assert result is None

    # Reset
    sys.modules["database.notifications"].get_mentor_notification_frequency = MagicMock(return_value=3)


def test_process_mentor_notification_returns_messages_list():
    """process_mentor_notification should return a list of message dicts."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = [
        {"text": "I need to save more money", "start": 1000, "is_user": True},
        {"text": "Have you tried budgeting?", "start": 1001, "is_user": False},
        {"text": "Not really, how do I start?", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_messages", segments)

    assert result is not None
    assert isinstance(result, list)
    assert len(result) >= 3
    for msg in result:
        assert 'text' in msg
        assert 'timestamp' in msg
        assert 'is_user' in msg


def test_process_mentor_notification_no_prompt_or_triggers():
    """process_mentor_notification should NOT return prompt, params, triggers, or context."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = [
        {"text": "She keeps saying I work too much", "start": 1000, "is_user": True},
        {"text": "Do you think she's right?", "start": 1001, "is_user": False},
        {"text": "No way, I need to hit my targets", "start": 1002, "is_user": True},
        {"text": "But maybe balance matters too", "start": 1003, "is_user": False},
    ]

    result = process_mentor_notification("test_uid_notriggers", segments)

    assert result is not None
    assert isinstance(result, list)
    # Should NOT have old-style keys
    assert not isinstance(result, dict)


def test_process_mentor_notification_not_enough_segments():
    """process_mentor_notification returns None when not enough segments."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = [
        {"text": "Hello", "start": 1000, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_short", segments)
    assert result is None


# ── evaluate_proactive_notification tests ──


def test_evaluate_proactive_notification_structured_output():
    """evaluate_proactive_notification should call llm_mini.with_structured_output."""
    mock_result = ProactiveNotificationResult(
        has_advice=True,
        advice=ProactiveAdvice(
            notification_text="Hey, you mentioned saving for a house but you're about to spend $600 on a console. Worth reconsidering?",
            reasoning="User's goal is to save $50k for a house. Current conversation shows intent to buy a $600 gaming console.",
            confidence=0.85,
            category="goal_connection",
        ),
        context_summary="User discussing buying a gaming console while having a house savings goal.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = evaluate_proactive_notification(
        user_name="Jake",
        user_facts="Jake has been saving for a down payment on a house.",
        goals=[{"title": "Save $50,000 for house down payment by December"}],
        past_conversations="Jake mentioned being behind on savings 2 weeks ago.",
        current_conversation="[Jake]: I'm going to buy that new gaming console\n[other]: Nice, which one?\n[Jake]: The latest one, it's only 600 bucks",
        recent_notifications="No recent notifications sent.",
        frequency=3,
    )

    assert result.has_advice is True
    assert result.advice is not None
    assert result.advice.confidence == 0.85
    assert result.advice.category == "goal_connection"
    assert "house" in result.advice.notification_text.lower() or "console" in result.advice.notification_text.lower()

    mock_llm_mini.with_structured_output.assert_called_once_with(ProactiveNotificationResult)


def test_evaluate_proactive_notification_no_advice():
    """evaluate_proactive_notification should return has_advice=False for generic scenarios."""
    mock_result = ProactiveNotificationResult(
        has_advice=False,
        advice=None,
        context_summary="Casual conversation about lunch.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = evaluate_proactive_notification(
        user_name="Jo",
        user_facts="Jo likes trying new restaurants.",
        goals=[],
        past_conversations="",
        current_conversation="[Jo]: Had a great lunch today\n[other]: Nice, where did you go?",
        recent_notifications="",
        frequency=3,
    )

    assert result.has_advice is False
    assert result.advice is None


# ── _process_mentor_proactive_notification end-to-end tests ──


def test_mentor_proactive_notification_sends_when_high_confidence():
    """_process_mentor_proactive_notification should send notification when confidence exceeds threshold."""
    _setup_app_integrations_stubs()

    mock_result = ProactiveNotificationResult(
        has_advice=True,
        advice=ProactiveAdvice(
            notification_text="You said you wanted to exercise 3x per week but you're about to skip the gym again. Third time this week - what changed?",
            reasoning="User's goal is exercise 3x per week. Current conversation shows intent to skip gym. Pattern: skipped twice already this week.",
            confidence=0.88,
            category="goal_connection",
        ),
        context_summary="User discussing skipping gym.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    import utils.app_integrations as app_int

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    messages = [
        {"text": "I think I'll skip the gym today", "timestamp": 1000, "is_user": True},
        {"text": "You sure?", "timestamp": 1001, "is_user": False},
        {"text": "Yeah, I'm too tired", "timestamp": 1002, "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_high", messages)

    assert result is not None
    assert "exercise" in result.lower() or "gym" in result.lower() or "skip" in result.lower()
    mock_send_app.assert_called_once()
    assert mock_send_app.call_args[0][0] == "test_uid_high"
    assert mock_send_app.call_args[0][1] == "Omi"
    assert mock_send_app.call_args[0][2] == "mentor"


def test_mentor_proactive_notification_rejects_low_confidence():
    """_process_mentor_proactive_notification should not send when confidence is below threshold."""
    _setup_app_integrations_stubs()

    mock_result = ProactiveNotificationResult(
        has_advice=True,
        advice=ProactiveAdvice(
            notification_text="Maybe consider budgeting more.",
            reasoning="User mentioned spending money.",
            confidence=0.35,  # Below threshold for frequency=3 (0.60)
            category="timely_nudge",
        ),
        context_summary="User discussing spending.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    import utils.app_integrations as app_int

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    messages = [
        {"text": "I bought a new thing", "timestamp": 1000, "is_user": True},
        {"text": "Cool", "timestamp": 1001, "is_user": False},
        {"text": "Yeah it was pricey", "timestamp": 1002, "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_low", messages)

    assert result is None
    mock_send_app.assert_not_called()


def test_mentor_proactive_notification_respects_rate_limit():
    """_process_mentor_proactive_notification should skip when rate limited."""
    _setup_app_integrations_stubs()

    import time

    # Set mem_db to return a recent timestamp
    mem_mod = sys.modules["database.mem_db"]
    mem_mod.get_proactive_noti_sent_at = MagicMock(return_value=int(time.time()))

    import utils.app_integrations as app_int

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    messages = [
        {"text": "test", "timestamp": 1000, "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_rate", messages)

    assert result is None
    mock_send_app.assert_not_called()

    # Reset
    mem_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)


def test_mentor_proactive_notification_respects_daily_cap():
    """_process_mentor_proactive_notification should skip when daily cap is reached."""
    _setup_app_integrations_stubs()

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.get_daily_notification_count = MagicMock(return_value=12)  # At cap

    import utils.app_integrations as app_int

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    messages = [
        {"text": "test", "timestamp": 1000, "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_cap", messages)

    assert result is None
    mock_send_app.assert_not_called()

    # Reset
    redis_mod.get_daily_notification_count = MagicMock(return_value=0)


def test_mentor_proactive_notification_disabled_frequency():
    """_process_mentor_proactive_notification should skip when frequency is 0."""
    _setup_app_integrations_stubs()

    noti_mod = sys.modules["database.notifications"]
    noti_mod.get_mentor_notification_frequency = MagicMock(return_value=0)

    import utils.app_integrations as app_int

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    messages = [
        {"text": "test", "timestamp": 1000, "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_disabled", messages)

    assert result is None
    mock_send_app.assert_not_called()

    # Reset
    noti_mod.get_mentor_notification_frequency = MagicMock(return_value=3)


def test_mentor_proactive_notification_no_advice():
    """_process_mentor_proactive_notification should not send when LLM says no advice."""
    _setup_app_integrations_stubs()

    mock_result = ProactiveNotificationResult(
        has_advice=False,
        advice=None,
        context_summary="Casual chat, nothing actionable.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    import utils.app_integrations as app_int

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    messages = [
        {"text": "Nice weather today", "timestamp": 1000, "is_user": True},
        {"text": "Yeah it is", "timestamp": 1001, "is_user": False},
        {"text": "Let's go outside", "timestamp": 1002, "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_noadvice", messages)

    assert result is None
    mock_send_app.assert_not_called()


def test_mentor_proactive_notification_increments_daily_count():
    """_process_mentor_proactive_notification should increment daily count on success."""
    _setup_app_integrations_stubs()

    mock_result = ProactiveNotificationResult(
        has_advice=True,
        advice=ProactiveAdvice(
            notification_text="You mentioned wanting to read more. Your friend just recommended that book - maybe grab it today?",
            reasoning="User's goal is to read 2 books per month. Friend just recommended a specific book in conversation.",
            confidence=0.82,
            category="dot_connecting",
        ),
        context_summary="Friend recommending a book to user who has a reading goal.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    redis_mod = sys.modules["database.redis_db"]
    redis_mod.incr_daily_notification_count = MagicMock(return_value=1)

    import utils.app_integrations as app_int

    mock_send_app = MagicMock()
    app_int.send_app_notification = mock_send_app

    messages = [
        {"text": "Have you read any good books lately?", "timestamp": 1000, "is_user": False},
        {"text": "Not recently, been too busy", "timestamp": 1001, "is_user": True},
        {"text": "You should check out Atomic Habits", "timestamp": 1002, "is_user": False},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_count", messages)

    assert result is not None
    redis_mod.incr_daily_notification_count.assert_called_once_with("test_uid_count")
