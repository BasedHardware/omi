"""
Tests for the proactive mentor notification system.

Tests cover:
- MessageBuffer buffering behavior
- process_mentor_notification() return type (list of messages)
- 3-step pipeline: evaluate_relevance, generate_notification, validate_notification
- _process_mentor_proactive_notification() end-to-end with mocks
- Source-level checks (no raw OpenAI client)
- Legacy evaluate_proactive_notification (kept for eval backward compatibility)
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

# Stub _client.db for auth.py top-level import
sys.modules["database._client"].db = MagicMock()

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
redis_mod.cache_user_name = MagicMock()
redis_mod.get_cached_user_name = MagicMock(return_value=None)

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
    conv_db_mod.get_conversations = MagicMock(return_value=[])

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


def _make_segments(count: int) -> list:
    """Helper to generate enough segments to trigger analysis (MIN_NEW_SEGMENTS=10)."""
    segments = []
    for i in range(count):
        is_user = i % 2 == 0
        text = f"Segment number {i} with some conversation content about topic {i}"
        segments.append({"text": text, "start": 1000 + i, "is_user": is_user})
    return segments


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


def test_proactive_notification_has_3step_pipeline():
    """proactive_notification.py should have Gate, Generate, and Critic steps."""
    source = _read_proactive_source()
    assert "def evaluate_relevance" in source
    assert "def generate_notification" in source
    assert "def validate_notification" in source
    assert "RelevanceResult" in source
    assert "NotificationDraft" in source
    assert "ValidationResult" in source


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


def test_integrations_uses_3step_imports():
    """app_integrations.py should import the 3-step pipeline functions."""
    source = _read_integrations_source()
    assert "evaluate_relevance" in source
    assert "generate_notification" in source
    assert "validate_notification" in source


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
    assert data['messages_at_last_analysis'] == 0


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
    """process_mentor_notification should return a list of message dicts when enough segments accumulate."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    # Need 10+ segments to trigger (MIN_NEW_SEGMENTS_FOR_ANALYSIS = 10)
    segments = _make_segments(12)

    result = process_mentor_notification("test_uid_list", segments)

    assert result is not None
    assert isinstance(result, list)
    assert len(result) >= 10
    for msg in result:
        assert 'text' in msg
        assert 'timestamp' in msg
        assert 'is_user' in msg


def test_process_mentor_notification_disabled():
    """process_mentor_notification returns None when frequency is 0."""
    sys.modules["database.notifications"].get_mentor_notification_frequency.return_value = 0

    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = _make_segments(12)

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


def test_process_mentor_notification_accumulates():
    """process_mentor_notification should accumulate across calls and not clear on evaluation."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    # First batch: 5 segments (not enough)
    segments1 = _make_segments(5)
    result1 = process_mentor_notification("test_uid_accum", segments1)
    assert result1 is None

    # Second batch: 6 more segments (total 11, enough)
    segments2 = [{"text": f"More conversation {i}", "start": 2000 + i, "is_user": i % 2 == 0} for i in range(6)]
    result2 = process_mentor_notification("test_uid_accum", segments2)
    assert result2 is not None
    assert len(result2) >= 10  # Should contain all accumulated messages

    # Third batch: only 3 new segments (not enough new since last analysis)
    segments3 = [{"text": f"Third batch {i}", "start": 3000 + i, "is_user": True} for i in range(3)]
    result3 = process_mentor_notification("test_uid_accum", segments3)
    assert result3 is None  # Not enough NEW segments since last analysis


def test_process_mentor_notification_no_prompt_or_triggers():
    """process_mentor_notification result should NOT have prompt/triggers/params keys."""
    from utils.mentor_notifications import process_mentor_notification, message_buffer

    message_buffer.buffers.clear()

    segments = _make_segments(12)

    result = process_mentor_notification("test_uid_no_prompt", segments)
    assert result is not None
    assert isinstance(result, list)
    # Should be a plain list, not a dict with prompt/triggers
    assert not isinstance(result, dict)


# ── 3-step pipeline tests ──


def test_evaluate_relevance():
    """evaluate_relevance should return RelevanceResult."""
    from utils.llm.proactive_notification import RelevanceResult, evaluate_relevance

    mock_result = RelevanceResult(
        is_relevant=True,
        relevance_score=0.85,
        reasoning="User is about to agree to a bad deal.",
        context_summary="User discussing business negotiation.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = evaluate_relevance(
        user_name="TestUser",
        user_facts="TestUser runs a startup.",
        goals=[{"title": "Close Series A"}],
        current_messages=[{"text": "I think we should accept their terms", "is_user": True}],
        recent_notifications=[],
    )

    assert result.is_relevant is True
    assert result.relevance_score == 0.85
    assert "bad deal" in result.reasoning


def test_evaluate_relevance_rejects():
    """evaluate_relevance should return is_relevant=False for generic conversation."""
    from utils.llm.proactive_notification import RelevanceResult, evaluate_relevance

    mock_result = RelevanceResult(
        is_relevant=False,
        relevance_score=0.20,
        reasoning="Generic lunch conversation, no actionable insight.",
        context_summary="User discussing lunch plans.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = evaluate_relevance(
        user_name="TestUser",
        user_facts="TestUser likes hiking.",
        goals=[],
        current_messages=[{"text": "Had a great lunch today", "is_user": True}],
        recent_notifications=[],
    )

    assert result.is_relevant is False
    assert result.relevance_score < 0.5


def test_generate_notification():
    """generate_notification should return NotificationDraft."""
    from utils.llm.proactive_notification import NotificationDraft, generate_notification

    mock_result = NotificationDraft(
        notification_text="Their offer is 30% below market — push back on valuation",
        reasoning="User's Series A target is $10M but the offer discussed is $7M.",
        confidence=0.90,
        category="mistake_prevention",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = generate_notification(
        user_name="TestUser",
        user_facts="TestUser targeting $10M Series A.",
        goals=[{"title": "Close Series A at $10M+"}],
        past_conversations_str="Past: discussed valuation targets.",
        current_messages=[{"text": "They offered $7M", "is_user": True}],
        recent_notifications=[],
        frequency=3,
        gate_reasoning="User about to accept below-target valuation.",
    )

    assert result.confidence == 0.90
    assert "30%" in result.notification_text or "valuation" in result.notification_text


def test_validate_notification_approves():
    """validate_notification should approve high-quality notifications."""
    from utils.llm.proactive_notification import ValidationResult, validate_notification

    mock_result = ValidationResult(
        approved=True,
        reasoning="This is genuinely useful — user would miss this valuation gap.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = validate_notification(
        user_name="TestUser",
        notification_text="Their offer is 30% below market",
        draft_reasoning="User's target is $10M, offer is $7M.",
        current_messages=[{"text": "They offered $7M", "is_user": True}],
        goals=[{"title": "Close Series A at $10M+"}],
    )

    assert result.approved is True


def test_validate_notification_rejects():
    """validate_notification should reject low-quality notifications."""
    from utils.llm.proactive_notification import ValidationResult, validate_notification

    mock_result = ValidationResult(
        approved=False,
        reasoning="This is just restating what the user already knows.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=mock_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    result = validate_notification(
        user_name="TestUser",
        notification_text="You're discussing gym plans",
        draft_reasoning="User mentioned gym.",
        current_messages=[{"text": "Going to the gym later", "is_user": True}],
        goals=[{"title": "Exercise 3x per week"}],
    )

    assert result.approved is False


# ── Legacy evaluate_proactive_notification tests (kept for eval backward compat) ──


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


# ── _process_mentor_proactive_notification tests (3-step pipeline) ──


def test_process_mentor_proactive_notification_sends():
    """_process_mentor_proactive_notification should send notification when all 3 steps pass."""
    mock_send = _setup_app_integrations_stubs()

    from utils.llm.proactive_notification import RelevanceResult, NotificationDraft, ValidationResult

    # Mock the 3 sequential LLM calls
    gate_result = RelevanceResult(
        is_relevant=True,
        relevance_score=0.85,
        reasoning="User is skipping gym despite their 3x/week goal.",
        context_summary="User discussing skipping exercise.",
    )
    draft_result = NotificationDraft(
        notification_text="You've been skipping gym — remember your 3x/week goal!",
        reasoning="User's goal is 'Exercise 3x per week' and they mentioned skipping today.",
        confidence=0.82,
        category="goal_connection",
    )
    critic_result = ValidationResult(
        approved=True,
        reasoning="This is a concrete reminder tied to a specific goal and current action.",
    )

    # with_structured_output is called 3 times; return different parsers each time
    call_count = [0]
    results = [gate_result, draft_result, critic_result]

    def side_effect_structured_output(model_class):
        parser = MagicMock()
        parser.invoke = MagicMock(return_value=results[min(call_count[0], len(results) - 1)])
        call_count[0] += 1
        return parser

    mock_llm_mini.with_structured_output = MagicMock(side_effect=side_effect_structured_output)

    # Reset rate limit mocks
    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 0

    # Force reimport to pick up stubs
    if "utils.app_integrations" in sys.modules:
        del sys.modules["utils.app_integrations"]
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


def test_process_mentor_proactive_notification_gate_rejects():
    """_process_mentor_proactive_notification should return None when gate rejects."""
    _setup_app_integrations_stubs()

    from utils.llm.proactive_notification import RelevanceResult

    gate_result = RelevanceResult(
        is_relevant=False,
        relevance_score=0.20,
        reasoning="Generic conversation, nothing actionable.",
        context_summary="Casual chat.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=gate_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 0

    if "utils.app_integrations" in sys.modules:
        del sys.modules["utils.app_integrations"]
    import utils.app_integrations as app_int

    messages = [{"text": "Just chatting about the weather", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_gate", messages)

    assert result is None


def test_process_mentor_proactive_notification_critic_rejects():
    """_process_mentor_proactive_notification should return None when critic rejects."""
    _setup_app_integrations_stubs()

    from utils.llm.proactive_notification import RelevanceResult, NotificationDraft, ValidationResult

    gate_result = RelevanceResult(
        is_relevant=True,
        relevance_score=0.80,
        reasoning="Some connection found.",
        context_summary="User discussing work.",
    )
    draft_result = NotificationDraft(
        notification_text="Ensure you prioritize your tasks",
        reasoning="User has goals.",
        confidence=0.75,
        category="productivity",
    )
    critic_result = ValidationResult(
        approved=False,
        reasoning="This is generic advice that applies to anyone. Rejected.",
    )

    call_count = [0]
    results = [gate_result, draft_result, critic_result]

    def side_effect(model_class):
        parser = MagicMock()
        parser.invoke = MagicMock(return_value=results[min(call_count[0], len(results) - 1)])
        call_count[0] += 1
        return parser

    mock_llm_mini.with_structured_output = MagicMock(side_effect=side_effect)

    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 0

    if "utils.app_integrations" in sys.modules:
        del sys.modules["utils.app_integrations"]
    import utils.app_integrations as app_int

    messages = [{"text": "Working on stuff", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_critic", messages)

    assert result is None


def test_process_mentor_proactive_notification_rate_limited():
    """_process_mentor_proactive_notification should return None when rate-limited."""
    _setup_app_integrations_stubs()

    # Set rate limit as hit
    mem_mod.get_proactive_noti_sent_at.return_value = int(time.time())  # Just sent
    redis_mod.get_proactive_noti_sent_at.return_value = None

    if "utils.app_integrations" in sys.modules:
        del sys.modules["utils.app_integrations"]
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

    if "utils.app_integrations" in sys.modules:
        del sys.modules["utils.app_integrations"]
    import utils.app_integrations as app_int

    messages = [{"text": "test", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_cap", messages)

    assert result is None

    # Reset
    redis_mod.get_daily_notification_count.return_value = 0


def test_process_mentor_proactive_notification_below_threshold():
    """_process_mentor_proactive_notification should reject when gate score below threshold."""
    _setup_app_integrations_stubs()

    from utils.llm.proactive_notification import RelevanceResult

    # Gate passes is_relevant=True but score is below threshold for frequency 3 (0.78)
    gate_result = RelevanceResult(
        is_relevant=True,
        relevance_score=0.50,  # Below threshold for frequency 3
        reasoning="Marginal connection.",
        context_summary="User chatting casually.",
    )

    mock_parser = MagicMock()
    mock_parser.invoke = MagicMock(return_value=gate_result)
    mock_llm_mini.with_structured_output = MagicMock(return_value=mock_parser)

    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 0

    if "utils.app_integrations" in sys.modules:
        del sys.modules["utils.app_integrations"]
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

    if "utils.app_integrations" in sys.modules:
        del sys.modules["utils.app_integrations"]
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


def test_relevance_result_model():
    """RelevanceResult should validate correctly."""
    from utils.llm.proactive_notification import RelevanceResult

    result = RelevanceResult(
        is_relevant=True,
        relevance_score=0.88,
        reasoning="User about to make a mistake.",
        context_summary="Business negotiation.",
    )
    assert result.is_relevant is True
    assert result.relevance_score == 0.88


def test_notification_draft_model():
    """NotificationDraft should validate correctly."""
    from utils.llm.proactive_notification import NotificationDraft

    draft = NotificationDraft(
        notification_text="Push back on the $7M offer",
        reasoning="Target was $10M.",
        confidence=0.90,
        category="mistake_prevention",
    )
    assert draft.notification_text == "Push back on the $7M offer"
    assert draft.confidence == 0.90
    assert draft.category == "mistake_prevention"


def test_validation_result_model():
    """ValidationResult should validate correctly."""
    from utils.llm.proactive_notification import ValidationResult

    result = ValidationResult(
        approved=True,
        reasoning="This would genuinely help the user.",
    )
    assert result.approved is True
