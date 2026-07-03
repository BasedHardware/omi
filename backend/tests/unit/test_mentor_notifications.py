"""
Tests for the proactive mentor notification system.

Tests cover:
- MessageBuffer buffering behavior
- process_mentor_notification() return type (list of messages)
- 3-step pipeline: evaluate_relevance, generate_notification, validate_notification
- _process_mentor_proactive_notification() end-to-end with mocks
- Source-level checks (no raw OpenAI client)
- Legacy evaluate_proactive_notification (kept for eval backward compatibility)

Hermeticity: every runtime fake is wired into the real production modules by the
``_apply_fakes`` autouse fixture via ``monkeypatch`` (auto-restored at teardown), so
no ``sys.modules`` pollution leaks to co-run test files. ``redis_mod``/``mem_mod``
are ``SimpleNamespace`` views over the same mock objects patched at the consumption
sites, so legacy test lines like ``redis_mod.get_daily_notification_count.return_value``
keep working unchanged.
"""

import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import database.conversations as conversations_db
import database.dev_api_key as dev_api_key_db
import database.mem_db as _mem_db_module
import database.notifications as notifications_db
import database.redis_db as _redis_db_module
import utils.app_integrations as app_int
import utils.llm.clients as llm_clients_mod
import utils.llm.proactive_notification as pn_mod
import utils.mentor_notifications as mentor_mod
from utils.llm.proactive_notification import (
    FREQUENCY_GUIDANCE,
    FREQUENCY_TO_BASE_THRESHOLD,
    MAX_DAILY_NOTIFICATIONS,
    NotificationDraft,
    ProactiveAdvice,
    ProactiveNotificationResult,
    RelevanceResult,
    ValidationResult,
    evaluate_proactive_notification,
    evaluate_relevance,
    generate_notification,
    validate_notification,
)
from utils.mentor_notifications import MessageBuffer, message_buffer, process_mentor_notification

_BACKEND = Path(__file__).resolve().parents[2]


# ── Shared runtime mocks ───────────────────────────────────────────────────────
# These are plain mock objects (NOT sys.modules mutation). The autouse fixture
# below wires them into the real consumption sites each test and auto-restores.

mock_llm_mini = MagicMock()
mock_llm_mini.invoke = MagicMock(return_value=MagicMock(content='test'))

mock_get_user_goals = MagicMock(
    return_value=[
        {'title': 'Exercise 3x per week', 'is_active': True},
        {'title': 'Read 2 books per month', 'is_active': True},
    ]
)
mock_get_prompt_memories = MagicMock(return_value=("TestUser", "TestUser likes hiking and coding."))
mock_get_app_messages = MagicMock(return_value=[])
mock_get_user_language = MagicMock(return_value='en')
mock_generate_embedding = MagicMock(return_value=[0] * 3072)
mock_query_vectors = MagicMock(return_value=[])
mock_get_convos_by_id = MagicMock(return_value=[])
mock_get_convos = MagicMock(return_value=[])
mock_deserialize_convos = MagicMock(return_value=[])
mock_convos_to_string = MagicMock(return_value='')
mock_get_available_apps = MagicMock(return_value=[])
mock_is_trial_paywalled = MagicMock(return_value=False)

mock_get_freq = MagicMock(return_value=3)
# Quiet hours off by default so process_mentor_notification exercises the buffering path
# unchanged (an enabled window would suppress and return None before buffering).
mock_get_quiet_hours = MagicMock(return_value={'enabled': False, 'start_hour': 22, 'end_hour': 7, 'time_zone': None})
mock_get_dev_keys = MagicMock(return_value=[])
mock_send_notification = MagicMock()

# redis_mod / mem_mod aggregate the redis/mem-backed mocks. Each attribute is the
# very mock object patched at the consumption site, so legacy test lines such as
# ``redis_mod.get_daily_notification_count.return_value = 9`` work unchanged.
redis_mod = SimpleNamespace(
    get_generic_cache=MagicMock(return_value=None),
    set_generic_cache=MagicMock(),
    get_proactive_noti_sent_at=MagicMock(return_value=None),
    set_proactive_noti_sent_at=MagicMock(),
    get_proactive_noti_sent_at_ttl=MagicMock(return_value=0),
    incr_daily_notification_count=MagicMock(return_value=1),
    get_daily_notification_count=MagicMock(return_value=0),
    cache_user_name=MagicMock(),
    get_cached_user_name=MagicMock(return_value=None),
    delete_app_cache_by_id=MagicMock(),
)
mem_mod = SimpleNamespace(
    get_proactive_noti_sent_at=MagicMock(return_value=None),
    set_proactive_noti_sent_at=MagicMock(),
)


@contextmanager
def _null_context(*args, **kwargs):
    yield


@pytest.fixture(autouse=True)
def _apply_fakes(monkeypatch):
    """Wire the shared mocks into every real consumption site (hermetic)."""
    # mentor_notifications.get_mentor_notification_frequency (local binding) +
    # database.notifications source + app_integrations local binding all share mock_get_freq.
    monkeypatch.setattr(mentor_mod, 'get_mentor_notification_frequency', mock_get_freq)
    monkeypatch.setattr(notifications_db, 'get_mentor_notification_frequency', mock_get_freq)
    monkeypatch.setattr(app_int, 'get_mentor_notification_frequency', mock_get_freq)
    mock_get_freq.return_value = 3

    # process_mentor_notification now consults the quiet-hours window after the frequency gate.
    # Keep it disabled here so these tests exercise the buffering path without touching the cache.
    monkeypatch.setattr(mentor_mod, 'get_quiet_hours', mock_get_quiet_hours)

    # proactive_notification.get_llm -> mock_llm_mini (so the real evaluate_relevance /
    # generate_notification / validate_notification / evaluate_proactive_notification
    # use it when tests configure mock_llm_mini.with_structured_output).
    monkeypatch.setattr(pn_mod, 'get_llm', MagicMock(return_value=mock_llm_mini))
    # utils.llm.clients.get_llm -> fresh chain mock for _process_proactive_notification's
    # in-function `from utils.llm.clients import get_llm`.
    monkeypatch.setattr(llm_clients_mod, 'get_llm', MagicMock())

    # app_integrations local bindings (from X import Y).
    monkeypatch.setattr(app_int, 'get_user_goals', mock_get_user_goals)
    monkeypatch.setattr(app_int, 'get_prompt_memories', mock_get_prompt_memories)
    monkeypatch.setattr(app_int, 'get_app_messages', mock_get_app_messages)
    monkeypatch.setattr(app_int, 'get_user_language_preference', mock_get_user_language)
    monkeypatch.setattr(app_int, 'generate_embedding', mock_generate_embedding)
    monkeypatch.setattr(app_int, 'query_vectors_by_metadata', mock_query_vectors)
    monkeypatch.setattr(app_int, 'conversations_to_string', mock_convos_to_string)
    monkeypatch.setattr(app_int, 'deserialize_conversations', mock_deserialize_convos)
    monkeypatch.setattr(app_int, 'get_available_apps', mock_get_available_apps)
    monkeypatch.setattr(app_int, 'is_trial_paywalled', mock_is_trial_paywalled)
    monkeypatch.setattr(app_int, 'send_notification', mock_send_notification)
    monkeypatch.setattr(app_int, 'incr_daily_notification_count', redis_mod.incr_daily_notification_count)
    monkeypatch.setattr(app_int, 'get_daily_notification_count', redis_mod.get_daily_notification_count)
    monkeypatch.setattr(app_int, 'delete_app_cache_by_id', redis_mod.delete_app_cache_by_id)
    monkeypatch.setattr(app_int, 'NotificationMessage', MagicMock())
    monkeypatch.setattr(app_int, 'Conversation', MagicMock())
    monkeypatch.setattr(app_int, 'ConversationSource', MagicMock())
    monkeypatch.setattr(app_int, 'Message', MagicMock())
    monkeypatch.setattr(app_int, 'get_app_by_id_db', MagicMock(return_value=None))
    monkeypatch.setattr(app_int, 'record_app_usage', MagicMock())
    monkeypatch.setattr(app_int, 'add_app_message', MagicMock())
    monkeypatch.setattr(app_int, 'record_app_webhook_failure', MagicMock(return_value=0))
    monkeypatch.setattr(app_int, 'record_app_webhook_success', MagicMock())
    monkeypatch.setattr(app_int, 'is_app_webhook_disabled', MagicMock(return_value=False))
    monkeypatch.setattr(app_int, 'disable_app_in_firestore', MagicMock())
    monkeypatch.setattr(app_int, 'track_usage', _null_context)
    monkeypatch.setattr(app_int, 'Features', MagicMock())

    # Module-reference targets inside app_integrations (mem_db / redis_db /
    # conversations_db / dev_api_key_db). The same mock objects back redis_mod/mem_mod.
    monkeypatch.setattr(_mem_db_module, 'get_proactive_noti_sent_at', mem_mod.get_proactive_noti_sent_at)
    monkeypatch.setattr(_mem_db_module, 'set_proactive_noti_sent_at', mem_mod.set_proactive_noti_sent_at)
    monkeypatch.setattr(_redis_db_module, 'get_proactive_noti_sent_at', redis_mod.get_proactive_noti_sent_at)
    monkeypatch.setattr(_redis_db_module, 'set_proactive_noti_sent_at', redis_mod.set_proactive_noti_sent_at)
    monkeypatch.setattr(_redis_db_module, 'get_proactive_noti_sent_at_ttl', redis_mod.get_proactive_noti_sent_at_ttl)
    monkeypatch.setattr(_redis_db_module, 'incr_daily_notification_count', redis_mod.incr_daily_notification_count)
    monkeypatch.setattr(_redis_db_module, 'get_daily_notification_count', redis_mod.get_daily_notification_count)
    monkeypatch.setattr(_redis_db_module, 'delete_app_cache_by_id', redis_mod.delete_app_cache_by_id)
    monkeypatch.setattr(conversations_db, 'get_conversations_by_id', mock_get_convos_by_id)
    monkeypatch.setattr(conversations_db, 'get_conversations', mock_get_convos)
    monkeypatch.setattr(dev_api_key_db, 'get_dev_keys_for_user', mock_get_dev_keys)

    yield


def _setup_app_integrations_stubs():
    """Reset the app_integrations-runtime shared mocks to a clean default state."""
    mock_send_notification.reset_mock()
    mock_get_dev_keys.reset_mock()
    mock_get_dev_keys.return_value = []
    mock_get_freq.return_value = 3
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.set_proactive_noti_sent_at.reset_mock()
    redis_mod.get_daily_notification_count.return_value = 0
    redis_mod.incr_daily_notification_count.reset_mock()
    mem_mod.get_proactive_noti_sent_at.return_value = None
    mem_mod.set_proactive_noti_sent_at.reset_mock()
    return mock_send_notification


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
    return (backend_dir / "utils" / "mentor_notifications.py").read_text(encoding="utf-8")


def _read_proactive_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "llm" / "proactive_notification.py").read_text(encoding="utf-8")


def _read_integrations_source() -> str:
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return (backend_dir / "utils" / "app_integrations.py").read_text(encoding="utf-8")


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
    buf = MessageBuffer()
    data = buf.get_buffer("session_1")
    assert data['messages'] == []
    assert data['silence_detected'] is False
    assert data['words_after_silence'] == 0
    assert data['messages_at_last_analysis'] == 0


def test_message_buffer_silence_detection():
    """MessageBuffer should detect silence after threshold."""
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
    notifications_db.get_mentor_notification_frequency.return_value = 0

    message_buffer.buffers.clear()

    segments = _make_segments(12)

    result = process_mentor_notification("test_uid_disabled", segments)
    assert result is None

    # Reset
    notifications_db.get_mentor_notification_frequency.return_value = 3


def test_process_mentor_notification_not_enough_segments():
    """process_mentor_notification returns None with insufficient segments."""
    message_buffer.buffers.clear()

    segments = [
        {"text": "hello", "start": 1000, "is_user": True},
    ]

    result = process_mentor_notification("test_uid_short", segments)
    assert result is None


def test_process_mentor_notification_accumulates():
    """process_mentor_notification should accumulate across calls and not clear on evaluation."""
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

    messages = [{"text": "Just chatting about the weather", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_gate", messages)

    assert result is None


def test_process_mentor_proactive_notification_critic_rejects():
    """_process_mentor_proactive_notification should return None when critic rejects."""
    _setup_app_integrations_stubs()

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

    messages = [{"text": "Working on stuff", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_critic", messages)

    assert result is None


def test_process_mentor_proactive_notification_rate_limited():
    """_process_mentor_proactive_notification should return None when rate-limited."""
    _setup_app_integrations_stubs()

    # Set rate limit as hit
    mem_mod.get_proactive_noti_sent_at.return_value = int(time.time())  # Just sent
    redis_mod.get_proactive_noti_sent_at.return_value = None

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

    messages = [{"text": "test", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_cap", messages)

    assert result is None

    # Reset
    redis_mod.get_daily_notification_count.return_value = 0


def test_process_mentor_proactive_notification_below_threshold():
    """_process_mentor_proactive_notification should reject when gate score below threshold."""
    _setup_app_integrations_stubs()

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

    notifications_db.get_mentor_notification_frequency.return_value = 0

    messages = [{"text": "test", "is_user": True}]
    result = app_int._process_mentor_proactive_notification("test_uid_off", messages)

    assert result is None

    # Reset
    notifications_db.get_mentor_notification_frequency.return_value = 3


# ── Frequency threshold tests ──


def test_frequency_thresholds():
    """FREQUENCY_TO_BASE_THRESHOLD should have correct values."""
    assert FREQUENCY_TO_BASE_THRESHOLD[0] is None
    assert FREQUENCY_TO_BASE_THRESHOLD[1] == 0.92
    assert FREQUENCY_TO_BASE_THRESHOLD[2] == 0.85
    assert FREQUENCY_TO_BASE_THRESHOLD[3] == 0.78
    assert FREQUENCY_TO_BASE_THRESHOLD[4] == 0.70
    assert FREQUENCY_TO_BASE_THRESHOLD[5] == 0.60


def test_max_daily_notifications():
    """MAX_DAILY_NOTIFICATIONS defaults under 10 (the #4859 target) and is env-tunable."""
    assert MAX_DAILY_NOTIFICATIONS == 9
    assert MAX_DAILY_NOTIFICATIONS < 10


def _fresh_app_integrations():
    _setup_app_integrations_stubs()
    # The developer-status cache lives in utils.dev_cache, which persists across
    # tests, so clear it for test isolation.
    app_int.dev_cache._DEV_STATUS_CACHE.clear()
    return app_int


def test_is_developer_detection():
    """A user with any developer API key is a developer; a lookup error fails closed."""
    app_int = _fresh_app_integrations()
    dev_mod = dev_api_key_db

    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[])
    assert app_int._is_developer("u") is False

    app_int.dev_cache._DEV_STATUS_CACHE.clear()
    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[MagicMock()])
    assert app_int._is_developer("u") is True

    app_int.dev_cache._DEV_STATUS_CACHE.clear()
    dev_mod.get_dev_keys_for_user = MagicMock(side_effect=Exception("firestore down"))
    assert app_int._is_developer("u") is False  # fail closed: still apply the cap

    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[])


def test_is_developer_is_cached():
    """The developer lookup is cached, so a second cap check does not re-hit the DB."""
    app_int = _fresh_app_integrations()
    dev_mod = dev_api_key_db
    app_int.dev_cache._DEV_STATUS_CACHE.clear()
    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[])

    assert app_int._is_developer("cached-uid") is False
    assert app_int._is_developer("cached-uid") is False
    dev_mod.get_dev_keys_for_user.assert_called_once()  # second call served from cache


def test_invalidate_developer_cache_takes_effect_immediately():
    """Invalidating after a key change forces the next check to re-read, not serve stale status."""
    app_int = _fresh_app_integrations()
    dev_mod = dev_api_key_db
    app_int.dev_cache._DEV_STATUS_CACHE.clear()

    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[])
    assert app_int._is_developer("u") is False  # cached as non-developer

    # They create their first key; without invalidation the stale False would persist.
    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[MagicMock()])
    assert app_int._is_developer("u") is False  # still serving the cached value
    app_int.dev_cache.invalidate_developer_cache("u")
    assert app_int._is_developer("u") is True  # re-read after invalidation


def test_resolve_daily_cap_bounds():
    """The env override is clamped: invalid falls back to the default, and 0/huge are bounded."""
    assert pn_mod._resolve_daily_cap(default=9) == 9  # env unset in tests
    with patch.dict("os.environ", {"MAX_DAILY_NOTIFICATIONS": "0"}):
        assert pn_mod._resolve_daily_cap(default=9, minimum=1) == 1  # cannot silently disable
    with patch.dict("os.environ", {"MAX_DAILY_NOTIFICATIONS": "-5"}):
        assert pn_mod._resolve_daily_cap(default=9, minimum=1) == 1
    with patch.dict("os.environ", {"MAX_DAILY_NOTIFICATIONS": "999999"}):
        assert pn_mod._resolve_daily_cap(default=9, maximum=1000) == 1000  # cannot remove throttling
    with patch.dict("os.environ", {"MAX_DAILY_NOTIFICATIONS": "not-an-int"}):
        assert pn_mod._resolve_daily_cap(default=9) == 9  # falls back
    with patch.dict("os.environ", {"MAX_DAILY_NOTIFICATIONS": "6"}):
        assert pn_mod._resolve_daily_cap(default=9) == 6  # valid override honored


def test_proactive_daily_cap_helper():
    """The shared cap triggers at/above MAX_DAILY_NOTIFICATIONS, and developers are exempt (#3346)."""
    app_int = _fresh_app_integrations()
    dev_mod = dev_api_key_db
    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[])

    redis_mod.get_daily_notification_count.return_value = 0
    assert app_int._proactive_daily_cap_reached("u") is False

    redis_mod.get_daily_notification_count.return_value = 9  # at the default cap
    assert app_int._proactive_daily_cap_reached("u") is True

    # Developer: exempt even far over the cap.
    app_int.dev_cache._DEV_STATUS_CACHE.clear()
    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[MagicMock()])
    redis_mod.get_daily_notification_count.return_value = 100
    assert app_int._proactive_daily_cap_reached("u") is False

    redis_mod.get_daily_notification_count.return_value = 0
    dev_mod.get_dev_keys_for_user = MagicMock(return_value=[])


def test_app_proactive_notification_respects_daily_cap():
    """Core fix: a third-party app proactive notification is now blocked once the shared daily cap is hit."""
    app_int = _fresh_app_integrations()
    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 9  # at the default cap
    redis_mod.incr_daily_notification_count.reset_mock()
    dev_api_key_db.get_dev_keys_for_user = MagicMock(return_value=[])

    app = MagicMock()
    app.has_capability.return_value = True
    app.id = "app-1"
    app.name = "TestApp"

    result = app_int._process_proactive_notification("uid_cap", app, {"prompt": "hello"})

    assert result is None
    redis_mod.incr_daily_notification_count.assert_not_called()
    redis_mod.get_daily_notification_count.return_value = 0


def test_app_proactive_notification_increments_shared_budget():
    """A delivered app proactive notification increments the same daily counter mentor notifications use."""
    app_int = _fresh_app_integrations()
    mem_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_proactive_noti_sent_at.return_value = None
    redis_mod.get_daily_notification_count.return_value = 0  # under cap
    redis_mod.incr_daily_notification_count.reset_mock()
    dev_api_key_db.get_dev_keys_for_user = MagicMock(return_value=[])
    llm_clients_mod.get_llm.return_value.invoke.return_value.content = "Here is a useful nudge."

    app = MagicMock()
    app.has_capability.return_value = True
    app.id = "app-2"
    app.name = "TestApp"
    app.filter_proactive_notification_scopes.return_value = []

    result = app_int._process_proactive_notification("uid_send", app, {"prompt": "hello", "params": []})

    assert result == "Here is a useful nudge."
    redis_mod.incr_daily_notification_count.assert_called_once_with("uid_send")


def test_frequency_guidance_all_levels():
    """FREQUENCY_GUIDANCE should have entries for levels 1-5."""
    for level in range(1, 6):
        assert level in FREQUENCY_GUIDANCE
        assert isinstance(FREQUENCY_GUIDANCE[level], str)
        assert len(FREQUENCY_GUIDANCE[level]) > 10


# ── Pydantic model tests ──


def test_proactive_advice_model():
    """ProactiveAdvice should validate correctly."""
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
    result = ValidationResult(
        approved=True,
        reasoning="This would genuinely help the user.",
    )
    assert result.approved is True
