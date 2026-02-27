"""
Tests for the proactive mentor notification system.

Tests cover:
- MessageBuffer buffering behavior
- process_mentor_notification() return type (list of messages)
- evaluate_proactive_notification() with mocked structured LLM output
- _process_mentor_proactive_notification() end-to-end with mocks
- Source-level checks (no raw OpenAI client)
"""

import os
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Ensure backend root is on sys.path for real imports
_backend_root = str(Path(__file__).resolve().parent.parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


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

# Stub redis_db daily notification functions
redis_mod = sys.modules.get("database.redis_db") or _stub_module("database.redis_db")
redis_mod.get_generic_cache = MagicMock(return_value=None)
redis_mod.set_generic_cache = MagicMock()
redis_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)
redis_mod.set_proactive_noti_sent_at = MagicMock()
redis_mod.get_proactive_noti_sent_at_ttl = MagicMock(return_value=0)
redis_mod.incr_daily_notification_count = MagicMock(return_value=1)
redis_mod.get_daily_notification_count = MagicMock(return_value=0)

# Stub mem_db
mem_mod = sys.modules.get("database.mem_db") or _stub_module("database.mem_db")
mem_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)
mem_mod.set_proactive_noti_sent_at = MagicMock()

# --- Stub LLM clients ---
mock_llm_mini = MagicMock()
mock_llm_mini.invoke = MagicMock(return_value=MagicMock(content='test'))

clients_mod = _stub_module("utils.llm.clients")
clients_mod.llm_mini = mock_llm_mini
clients_mod.generate_embedding = MagicMock(return_value=[0] * 3072)

# Stub usage tracker — set __path__ to real directory so proactive_notification.py can be found
utils_mod = _stub_module("utils")
if not hasattr(utils_mod, '__path__'):
    utils_mod.__path__ = [os.path.join(_backend_root, "utils")]
llm_mod = _stub_module("utils.llm")
if not hasattr(llm_mod, '__path__'):
    llm_mod.__path__ = [os.path.join(_backend_root, "utils", "llm")]
tracker_mod = _stub_module("utils.llm.usage_tracker")
tracker_mod.get_usage_callback = MagicMock(return_value=[])
tracker_mod.track_usage = MagicMock()
tracker_mod.Features = MagicMock()

# Stub utils.llms.memory (get_prompt_memories)
llms_mod = _stub_module("utils.llms")
if not hasattr(llms_mod, '__path__'):
    llms_mod.__path__ = [os.path.join(_backend_root, "utils", "llms")]
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

    # Ensure database.notifications has get_mentor_notification_frequency for app_integrations import
    noti_db_mod = sys.modules.get("database.notifications") or _stub_module("database.notifications")
    if not hasattr(noti_db_mod, 'get_mentor_notification_frequency'):
        noti_db_mod.get_mentor_notification_frequency = MagicMock(return_value=3)

    # Remove any stale stub so the real module loads
    if "utils.llm.proactive_notification" in sys.modules:
        real_mod = sys.modules["utils.llm.proactive_notification"]
        if not hasattr(real_mod, 'ProactiveAdvice'):
            del sys.modules["utils.llm.proactive_notification"]

    return mock_send


# ── Source-level tests ──


def _read_mentor_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "mentor_notifications.py").read_text()


def _read_proactive_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "llm" / "proactive_notification.py").read_text()


def _read_integrations_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "app_integrations.py").read_text()


def test_no_raw_openai_client():
    """Verify mentor_notifications.py does not import or use raw OpenAI client."""
    source = _read_mentor_source()
    assert "from openai import OpenAI" not in source
    assert "client.chat.completions.create" not in source
    assert 'model="gpt-4"' not in source


def test_proactive_notification_uses_structured_output():
    """proactive_notification.py should use with_structured_output pattern."""
    source = _read_proactive_source()
    assert "with_structured_output" in source
    assert "ProactiveNotificationResult" in source
    assert "ProactiveAdvice" in source


def test_no_trigger_tools_in_mentor():
    """mentor_notifications.py should no longer have PROACTIVE_TRIGGERS."""
    source = _read_mentor_source()
    assert "PROACTIVE_TRIGGERS" not in source
    assert "trigger_argument_perspective" not in source
    assert "trigger_goal_misalignment" not in source
    assert "trigger_emotional_support" not in source


def test_no_trigger_functions_in_integrations():
    """app_integrations.py should not have _process_triggers or _build_trigger_context."""
    source = _read_integrations_source()
    assert "def _process_triggers" not in source
    assert "def _build_trigger_context" not in source


def test_integrations_has_mentor_function():
    """app_integrations.py should have _process_mentor_proactive_notification."""
    source = _read_integrations_source()
    assert "def _process_mentor_proactive_notification" in source


def test_no_extract_topics_in_mentor():
    """mentor_notifications.py should no longer have extract_topics."""
    source = _read_mentor_source()
    assert "def extract_topics" not in source


# ── MessageBuffer tests ──


def test_message_buffer_creates_session():
    """MessageBuffer should create a new session buffer."""
    from utils.mentor_notifications import MessageBuffer

    buf = MessageBuffer()
    data = buf.get_buffer("session_1")
    assert data['messages'] == []
    assert data['silence_detected'] is False
    assert data['words_after_silence'] == 0


def test_message_buffer_silence_detection():
    """MessageBuffer should detect silence after threshold."""
    from utils.mentor_notifications import MessageBuffer

    buf = MessageBuffer()
    buf.silence_threshold = 0.1  # Very short for testing

    data = buf.get_buffer("session_2")
    data['last_activity'] = time.time() - 1  # 1 second ago

    time.sleep(0.15)
    data = buf.get_buffer("session_2")
    assert data['silence_detected'] is True
    assert data['messages'] == []


def test_message_buffer_cleanup():
    """MessageBuffer cleanup should remove old sessions."""
    from utils.mentor_notifications import MessageBuffer

    buf = MessageBuffer()
    buf.buffers["old_session"] = {
        'messages': [],
        'last_analysis_time': time.time(),
        'last_activity': time.time() - 7200,  # 2 hours ago
        'words_after_silence': 0,
        'silence_detected': False,
    }

    buf.cleanup_old_sessions()
    assert "old_session" not in buf.buffers


# ── process_mentor_notification tests ──


def test_process_mentor_notification_returns_list():
    """process_mentor_notification should return a list of message dicts."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = [
        {"text": "I need to save more money", "start": 1000, "is_user": True},
        {"text": "Have you tried budgeting?", "start": 1001, "is_user": False},
        {"text": "Not really", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_list", segments)

    assert result is not None
    assert isinstance(result, list)
    assert len(result) >= 3
    for msg in result:
        assert 'text' in msg
        assert 'timestamp' in msg
        assert 'is_user' in msg


def test_process_mentor_notification_disabled():
    """process_mentor_notification returns None when frequency is 0."""
    sys.modules["database.notifications"].get_mentor_notification_frequency.return_value = 0

    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = [
        {"text": "hello", "start": 1000, "is_user": True},
        {"text": "hi", "start": 1001, "is_user": False},
        {"text": "how are you", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_disabled", segments)
    assert result is None

    # Reset
    sys.modules["database.notifications"].get_mentor_notification_frequency.return_value = 3


def test_process_mentor_notification_not_enough_segments():
    """process_mentor_notification returns None with insufficient segments."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = [
        {"text": "hello", "start": 1000, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_short", segments)
    assert result is None


def test_process_mentor_notification_no_prompt_or_triggers():
    """process_mentor_notification result should NOT have prompt/triggers/params keys."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = [
        {"text": "I should plant tomatoes", "start": 1000, "is_user": True},
        {"text": "Great idea", "start": 1001, "is_user": False},
        {"text": "And maybe herbs too", "start": 1002, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_no_prompt", segments)
    assert result is not None
    assert isinstance(result, list)
    # Should be a plain list, not a dict with prompt/triggers
    assert not isinstance(result, dict)


# ── evaluate_proactive_notification tests ──


def test_evaluate_proactive_notification_with_advice():
    """evaluate_proactive_notification should return structured result with advice."""
    from utils.llm.proactive_notification import (
        ProactiveAdvice,
        ProactiveNotificationResult,
        evaluate_proactive_notification,
    )

    mock_result = ProactiveNotificationResult(
        has_advice=True,
        advice=ProactiveAdvice(
            notification_text="You mentioned wanting to save $50k — this $3k vacation might set you back.",
            reasoning="User's goal is 'save $50k for house' and they're discussing a vacation.",
            confidence=0.85,
            category="goal_connection",
        ),
        context_summary="User discussing vacation plans.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = evaluate_proactive_notification(
        user_name="TestUser",
        user_facts="TestUser likes hiking.",
        goals=[{"title": "Save $50k for house"}],
        past_conversations_str="Past: discussed savings goals.",
        current_messages=[{"text": "I'm thinking of going on a vacation", "is_user": True}],
        recent_notifications=[],
        frequency=3,
    )

    assert result.has_advice is True
    assert result.advice is not None
    assert result.advice.confidence == 0.85
    assert "save" in result.advice.notification_text.lower() or "$50k" in result.advice.notification_text


def test_evaluate_proactive_notification_no_advice():
    """evaluate_proactive_notification should return has_advice=False for generic context."""
    from utils.llm.proactive_notification import ProactiveNotificationResult, evaluate_proactive_notification

    mock_result = ProactiveNotificationResult(
        has_advice=False,
        advice=None,
        context_summary="User discussing lunch plans.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = evaluate_proactive_notification(
        user_name="TestUser",
        user_facts="TestUser likes hiking.",
        goals=[],
        past_conversations_str="",
        current_messages=[{"text": "Had a great lunch today", "is_user": True}],
        recent_notifications=[],
        frequency=3,
    )

    assert result.has_advice is False
    assert result.advice is None


# ── _process_mentor_proactive_notification tests ──


def test_process_mentor_proactive_notification_sends():
    """_process_mentor_proactive_notification should send notification on high confidence."""
    mock_send = _setup_app_integrations_stubs()

    from utils.llm.proactive_notification import ProactiveAdvice, ProactiveNotificationResult

    mock_result = ProactiveNotificationResult(
        has_advice=True,
        advice=ProactiveAdvice(
            notification_text="You've been skipping gym — remember your 3x/week goal!",
            reasoning="User's goal is 'Exercise 3x per week' and they mentioned skipping today.",
            confidence=0.82,
            category="goal_connection",
        ),
        context_summary="User discussing skipping exercise.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    # Reset rate limit mocks
    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 0

    import utils.app_integrations as app_int

    messages = [
        {"text": "I'll skip the gym today", "is_user": True},
        {"text": "You sure?", "is_user": False},
        {"text": "Yeah I'm too tired", "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid", messages)

    assert result is not None
    assert "gym" in result.lower() or "3x" in result.lower() or "skip" in result.lower()
    mock_send.assert_called()


def test_process_mentor_proactive_notification_rate_limited():
    """_process_mentor_proactive_notification should return None when rate-limited."""
    _setup_app_integrations_stubs()

    # Set rate limit as hit
    mem_mod.get_proactive_noti_sent_at.return_value = int(time.time())  # Just sent
    redis_mod.get_proactive_noti_sent_at.return_value = None

    import utils.app_integrations as app_int

    messages = [{"text": "test", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_rl", messages)

    assert result is None

    # Reset
    mem_mod.get_proactive_noti_sent_at.return_value = None


def test_process_mentor_proactive_notification_daily_cap():
    """_process_mentor_proactive_notification should return None when daily cap reached."""
    _setup_app_integrations_stubs()

    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 12  # At cap

    import utils.app_integrations as app_int

    messages = [{"text": "test", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_cap", messages)

    assert result is None

    # Reset
    redis_mod.get_daily_notification_count.return_value = 0


def test_process_mentor_proactive_notification_below_threshold():
    """_process_mentor_proactive_notification should reject low confidence notifications."""
    _setup_app_integrations_stubs()

    from utils.llm.proactive_notification import ProactiveAdvice, ProactiveNotificationResult

    mock_result = ProactiveNotificationResult(
        has_advice=True,
        advice=ProactiveAdvice(
            notification_text="Maybe take a break?",
            reasoning="User seems a bit tired.",
            confidence=0.30,  # Below threshold for frequency 3 (0.60)
            category="pattern_insight",
        ),
        context_summary="User chatting casually.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 0

    import utils.app_integrations as app_int

    messages = [
        {"text": "Just chatting", "is_user": True},
        {"text": "Cool", "is_user": False},
        {"text": "Yeah", "is_user": True},
    ]

    result = app_int._process_mentor_proactive_notification("test_uid_low", messages)

    assert result is None


def test_process_mentor_proactive_notification_disabled():
    """_process_mentor_proactive_notification should return None when frequency is 0."""
    _setup_app_integrations_stubs()

    sys.modules["database.notifications"].get_mentor_notification_frequency.return_value = 0

    import utils.app_integrations as app_int

    messages = [{"text": "test", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_off", messages)

    assert result is None

    # Reset
    sys.modules["database.notifications"].get_mentor_notification_frequency.return_value = 3


# ── Frequency threshold tests ──


def test_frequency_thresholds():
    """FREQUENCY_TO_BASE_THRESHOLD should have correct values."""
    from utils.llm.proactive_notification import FREQUENCY_TO_BASE_THRESHOLD

    assert FREQUENCY_TO_BASE_THRESHOLD[0] is None
    assert FREQUENCY_TO_BASE_THRESHOLD[1] == 0.92
    assert FREQUENCY_TO_BASE_THRESHOLD[2] == 0.85
    assert FREQUENCY_TO_BASE_THRESHOLD[3] == 0.78
    assert FREQUENCY_TO_BASE_THRESHOLD[4] == 0.70
    assert FREQUENCY_TO_BASE_THRESHOLD[5] == 0.60


def test_max_daily_notifications():
    """MAX_DAILY_NOTIFICATIONS should be 12."""
    from utils.llm.proactive_notification import MAX_DAILY_NOTIFICATIONS

    assert MAX_DAILY_NOTIFICATIONS == 12


def test_frequency_guidance_all_levels():
    """FREQUENCY_GUIDANCE should have entries for levels 1-5."""
    from utils.llm.proactive_notification import FREQUENCY_GUIDANCE

    for level in range(1, 6):
        assert level in FREQUENCY_GUIDANCE
        assert isinstance(FREQUENCY_GUIDANCE[level], str)
        assert len(FREQUENCY_GUIDANCE[level]) > 10


# ── Pydantic model tests ──


def test_proactive_advice_model():
    """ProactiveAdvice should validate correctly."""
    from utils.llm.proactive_notification import ProactiveAdvice

    advice = ProactiveAdvice(
        notification_text="Test notification",
        reasoning="User's goal X connects to current conversation Y",
        confidence=0.85,
        category="goal_connection",
    )
    assert advice.notification_text == "Test notification"
    assert advice.confidence == 0.85


def test_proactive_notification_result_model():
    """ProactiveNotificationResult should validate correctly."""
    from utils.llm.proactive_notification import ProactiveNotificationResult

    result = ProactiveNotificationResult(
        has_advice=False,
        advice=None,
        context_summary="Just a casual chat.",
    )
    assert result.has_advice is False
    assert result.advice is None
    assert result.context_summary == "Just a casual chat."
