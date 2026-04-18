"""
Unit tests for LLM usage tracking in realtime integrations fallback path.

Verifies that trigger_realtime_integrations wraps LLM calls (get_proactive_message,
generate_embedding) with track_usage(uid, Features.REALTIME_INTEGRATIONS).
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# Stub database package and submodules
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
    "chat",
    "goals",
    "auth",
]:
    mod = _stub_module(f"database.{submodule}")
    setattr(database_mod, submodule, mod)

# database.mem_db
mem_db_mod = _stub_module("database.mem_db")
setattr(database_mod, "mem_db", mem_db_mod)
mem_db_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)
mem_db_mod.set_proactive_noti_sent_at = MagicMock()

vector_db_mod = sys.modules["database.vector_db"]
vector_db_mod.query_vectors_by_metadata = MagicMock(return_value=[])

apps_mod = sys.modules["database.apps"]
apps_mod.record_app_usage = MagicMock()

llm_usage_mod = sys.modules["database.llm_usage"]
llm_usage_mod.record_llm_usage = MagicMock()

client_mod = sys.modules["database._client"]
client_mod.document_id_from_seed = MagicMock(return_value="doc-id")

redis_mod = sys.modules["database.redis_db"]
redis_mod.get_generic_cache = MagicMock(return_value=None)
redis_mod.set_generic_cache = MagicMock()
redis_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)
redis_mod.set_proactive_noti_sent_at = MagicMock()
redis_mod.incr_daily_notification_count = MagicMock()
redis_mod.get_daily_notification_count = MagicMock(return_value=0)
redis_mod.get_proactive_noti_sent_at_ttl = MagicMock(return_value=0)

goals_mod = sys.modules["database.goals"]
goals_mod.get_user_goals = MagicMock(return_value=[])

auth_mod = sys.modules["database.auth"]
auth_mod.get_user_name = MagicMock(return_value="Test User")

chat_mod = sys.modules["database.chat"]
chat_mod.add_app_message = MagicMock(return_value={"id": "msg-1"})
chat_mod.get_app_messages = MagicMock(return_value=[])

notifications_mod = sys.modules["database.notifications"]
notifications_mod.get_token_only = MagicMock(return_value=None)
notifications_mod.get_mentor_notification_frequency = MagicMock(return_value=0)

conversations_mod = sys.modules["database.conversations"]
conversations_mod.get_conversations_by_id = MagicMock(return_value=[])

from utils.llm import usage_tracker

# Stub remaining utils modules
for name in [
    "utils.apps",
    "utils.notifications",
    "utils.llm.clients",
    "utils.llm.proactive_notification",
    "utils.mentor_notifications",
    "utils.http_client",
    "utils.log_sanitizer",
    "utils.llms",
    "utils.llms.memory",
]:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

# Ensure http_client stubs have correct attributes
sys.modules["utils.http_client"].get_webhook_client = MagicMock()
sys.modules["utils.http_client"].get_maps_client = MagicMock()
_mock_cb = MagicMock()
_mock_cb.allow_request = MagicMock(return_value=True)
_mock_cb.record_success = MagicMock()
_mock_cb.record_failure = MagicMock()
sys.modules["utils.http_client"].get_webhook_circuit_breaker = MagicMock(return_value=_mock_cb)
import asyncio as _asyncio

sys.modules["utils.http_client"].get_webhook_semaphore = MagicMock(return_value=_asyncio.Semaphore(64))
sys.modules["utils.http_client"].latest_wins_start = MagicMock(return_value=1)
sys.modules["utils.http_client"].latest_wins_check = MagicMock(return_value=True)

# Ensure log_sanitizer stubs have correct attributes
sys.modules["utils.log_sanitizer"].sanitize = MagicMock(side_effect=lambda x: x)
sys.modules["utils.log_sanitizer"].sanitize_pii = MagicMock(side_effect=lambda x: x)

# Ensure llms.memory stub has correct attributes
sys.modules["utils.llms.memory"].get_prompt_memories = MagicMock(return_value=[])

utils_apps = sys.modules["utils.apps"]
utils_apps.get_available_apps = MagicMock(return_value=[])

utils_notifications = sys.modules["utils.notifications"]
utils_notifications.send_notification = MagicMock()

llm_clients = sys.modules["utils.llm.clients"]
llm_clients.generate_embedding = MagicMock(return_value=[0] * 3072)

llm_proactive = sys.modules["utils.llm.proactive_notification"]
llm_proactive.get_proactive_message = MagicMock(return_value="Test notification message here")
llm_proactive.evaluate_relevance = MagicMock(return_value=0.0)
llm_proactive.generate_notification = MagicMock(return_value="")
llm_proactive.validate_notification = MagicMock(return_value=False)
llm_proactive.FREQUENCY_TO_BASE_THRESHOLD = {1: 0.5, 2: 0.4, 3: 0.3}
llm_proactive.MAX_DAILY_NOTIFICATIONS = 10

mentor_mod = sys.modules["utils.mentor_notifications"]
mentor_mod.process_mentor_notification = MagicMock(return_value=None)

import importlib

app_integrations = importlib.import_module("utils.app_integrations")


def test_realtime_integrations_feature_constant_exists():
    """Verify REALTIME_INTEGRATIONS constant is defined in Features."""
    assert hasattr(usage_tracker.Features, 'REALTIME_INTEGRATIONS')
    assert usage_tracker.Features.REALTIME_INTEGRATIONS == "realtime_integrations"
    # Distinct from other features
    assert usage_tracker.Features.REALTIME_INTEGRATIONS != usage_tracker.Features.APP_INTEGRATIONS
    assert usage_tracker.Features.REALTIME_INTEGRATIONS != usage_tracker.Features.NOTIFICATIONS


@pytest.mark.asyncio
async def test_mentor_notification_tracked_under_realtime_integrations():
    """Verify mentor notification LLM call is tracked under REALTIME_INTEGRATIONS."""
    captured_contexts = []

    original_track = usage_tracker.track_usage

    from contextlib import contextmanager

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append((uid, feature))
        with original_track(uid, feature):
            yield

    # Make mentor notification fire — patch on app_integrations since it's a top-level import
    with patch.object(app_integrations, "track_usage", spy_track_usage), patch.object(
        app_integrations, "process_mentor_notification", MagicMock(return_value={'prompt': 'test prompt', 'params': []})
    ), patch.object(app_integrations, "send_app_notification", MagicMock()), patch.object(
        app_integrations, "add_app_message", MagicMock(return_value={"id": "msg-1"})
    ):
        await app_integrations.trigger_realtime_integrations("user-rt-1", [{"text": "hello"}], "conv-1")

    # Should have tracked under REALTIME_INTEGRATIONS
    features_tracked = [f for _, f in captured_contexts]
    assert usage_tracker.Features.REALTIME_INTEGRATIONS in features_tracked


@pytest.mark.asyncio
async def test_no_tracking_when_no_llm_calls():
    """Verify no tracking happens when mentor notification doesn't fire and no apps."""
    captured_contexts = []

    original_track = usage_tracker.track_usage

    from contextlib import contextmanager

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append((uid, feature))
        with original_track(uid, feature):
            yield

    # No mentor notification, no apps
    mentor_mod.process_mentor_notification = MagicMock(return_value=None)
    utils_apps.get_available_apps = MagicMock(return_value=[])

    with patch.object(app_integrations, "track_usage", spy_track_usage):
        await app_integrations.trigger_realtime_integrations("user-rt-2", [{"text": "hello"}], "conv-2")

    assert len(captured_contexts) == 0


@pytest.mark.asyncio
async def test_track_usage_context_entered_around_proactive_message():
    """Verify track_usage context manager is entered before _process_mentor_proactive_notification is called.

    Uses a spy context manager to record entry/exit order without relying on ContextVar state,
    making this test immune to module-level mutations from other test files.
    """
    from contextlib import contextmanager

    call_log = []

    @contextmanager
    def spy_track_usage(uid, feature):
        call_log.append(('enter', uid, feature))
        yield
        call_log.append(('exit', uid, feature))

    def spy_process(*args, **kwargs):
        call_log.append(('process_called',))
        return "Test notification"

    with patch.object(app_integrations, "track_usage", spy_track_usage), patch.object(
        app_integrations, "process_mentor_notification", MagicMock(return_value={'prompt': 'test', 'params': []})
    ), patch.object(app_integrations, "_process_mentor_proactive_notification", spy_process), patch.object(
        app_integrations, "send_app_notification", MagicMock()
    ), patch.object(
        app_integrations, "add_app_message", MagicMock(return_value={"id": "msg-1"})
    ):
        await app_integrations.trigger_realtime_integrations("user-rt-3", [{"text": "hello"}], "conv-3")

    # track_usage must be entered with correct args before spy_process is called
    assert ('enter', 'user-rt-3', 'realtime_integrations') in call_log
    process_idx = next(i for i, e in enumerate(call_log) if e == ('process_called',))
    enter_idx = next(i for i, e in enumerate(call_log) if e == ('enter', 'user-rt-3', 'realtime_integrations'))
    exit_idx = next(i for i, e in enumerate(call_log) if e == ('exit', 'user-rt-3', 'realtime_integrations'))
    assert enter_idx < process_idx < exit_idx
