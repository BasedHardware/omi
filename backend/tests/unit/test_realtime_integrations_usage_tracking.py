"""
Unit tests for LLM usage tracking in realtime integrations fallback path.

Verifies that trigger_realtime_integrations wraps LLM calls (get_proactive_message,
generate_embedding) with track_usage(uid, Features.REALTIME_INTEGRATIONS).
"""

import os
import sys
import types
from enum import Enum
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


langchain_core_mod = _stub_module("langchain_core")
langchain_core_mod.__path__ = []
langchain_callbacks_mod = _stub_module("langchain_core.callbacks")
langchain_outputs_mod = _stub_module("langchain_core.outputs")


class BaseCallbackHandler:
    pass


class LLMResult:
    def __init__(self, generations=None, llm_output=None, **kwargs):
        self.generations = generations or []
        self.llm_output = llm_output


langchain_callbacks_mod.BaseCallbackHandler = BaseCallbackHandler
langchain_outputs_mod.LLMResult = LLMResult
setattr(langchain_core_mod, "callbacks", langchain_callbacks_mod)
setattr(langchain_core_mod, "outputs", langchain_outputs_mod)


# Replace models.* stubs unconditionally so stale partial modules from earlier
# collection cannot hide the minimal classes this import sandbox requires.
models_mod = _stub_module("models")
models_mod.__path__ = []
models_app_mod = _stub_module("models.app")
models_chat_mod = _stub_module("models.chat")
models_conversation_mod = _stub_module("models.conversation")
models_conversation_enums_mod = _stub_module("models.conversation_enums")
models_notification_mod = _stub_module("models.notification_message")


class App:
    pass


class ProactiveNotification:
    pass


class UsageHistoryType(str, Enum):
    transcript_processed = 'transcript_processed'


class Message:
    pass


class Conversation:
    pass


class ConversationSource(str, Enum):
    workflow = 'workflow'
    unknown = 'unknown'


class NotificationMessage:
    pass


models_app_mod.App = App
models_app_mod.ProactiveNotification = ProactiveNotification
models_app_mod.UsageHistoryType = UsageHistoryType
models_chat_mod.Message = Message
models_conversation_mod.Conversation = Conversation
models_conversation_enums_mod.ConversationSource = ConversationSource
models_notification_mod.NotificationMessage = NotificationMessage
setattr(models_mod, "app", models_app_mod)
setattr(models_mod, "chat", models_chat_mod)
setattr(models_mod, "conversation", models_conversation_mod)
setattr(models_mod, "conversation_enums", models_conversation_enums_mod)
setattr(models_mod, "notification_message", models_notification_mod)


# Stub database package and submodules
database_mod = _stub_module("database")
database_mod.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'database'))]
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
    "webhook_health",
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
apps_mod.get_app_by_id_db = MagicMock(return_value=None)

llm_usage_mod = sys.modules["database.llm_usage"]
llm_usage_mod.record_llm_usage = MagicMock()

client_mod = sys.modules["database._client"]
client_mod.document_id_from_seed = MagicMock(return_value="doc-id")
client_mod.db = MagicMock()

redis_mod = sys.modules["database.redis_db"]
redis_mod.get_generic_cache = MagicMock(return_value=None)
redis_mod.set_generic_cache = MagicMock()
redis_mod.delete_app_cache_by_id = MagicMock()
redis_mod.r = MagicMock()
redis_mod.get_proactive_noti_sent_at = MagicMock(return_value=None)
redis_mod.set_proactive_noti_sent_at = MagicMock()
redis_mod.incr_daily_notification_count = MagicMock()
redis_mod.get_daily_notification_count = MagicMock(return_value=0)
redis_mod.get_proactive_noti_sent_at_ttl = MagicMock(return_value=0)

goals_mod = sys.modules["database.goals"]
goals_mod.get_user_goals = MagicMock(return_value=[])

auth_mod = sys.modules["database.auth"]
auth_mod.get_user_name = MagicMock(return_value="Test User")

users_mod = sys.modules["database.users"]
users_mod.get_user_language_preference = MagicMock(return_value="en")

webhook_health_mod = sys.modules["database.webhook_health"]
webhook_health_mod.record_app_webhook_failure = MagicMock(return_value=0)
webhook_health_mod.record_app_webhook_success = MagicMock()
webhook_health_mod.is_app_webhook_disabled = MagicMock(return_value=False)
webhook_health_mod.disable_app_in_firestore = MagicMock()

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
    "utils.conversations",
    "utils.conversations.factory",
    "utils.conversations.render",
    "utils.executors",
    "utils.async_tasks",
    "utils.llm.clients",
    "utils.llm.proactive_notification",
    "utils.mentor_notifications",
    "utils.http_client",
    "utils.log_sanitizer",
    "utils.llms",
    "utils.llms.memory",
    "utils.subscription",
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

# Ensure executor/async task stubs have correct attributes
sys.modules["utils.executors"].db_executor = MagicMock()


async def _run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


async def _gather_safe(*aws, **_kwargs):
    return await _asyncio.gather(*aws)


sys.modules["utils.executors"].run_blocking = _run_blocking
sys.modules["utils.async_tasks"].gather_safe = _gather_safe

# Ensure log_sanitizer stubs have correct attributes
sys.modules["utils.log_sanitizer"].sanitize = MagicMock(side_effect=lambda x: x)
sys.modules["utils.log_sanitizer"].sanitize_pii = MagicMock(side_effect=lambda x: x)

# Ensure llms.memory stub has correct attributes
sys.modules["utils.llms.memory"].get_prompt_memories = MagicMock(return_value=[])

sys.modules["utils.subscription"].is_trial_paywalled = MagicMock(return_value=False)

utils_conversations = sys.modules["utils.conversations"]
utils_conversations.__path__ = []
utils_conversations_factory = sys.modules["utils.conversations.factory"]
utils_conversations_factory.deserialize_conversations = MagicMock(return_value=[])
utils_conversations_render = sys.modules["utils.conversations.render"]
utils_conversations_render.conversations_to_string = MagicMock(return_value="")
utils_conversations_render.conversation_to_dict = MagicMock(return_value={})
utils_conversations_render.serialize_datetimes = MagicMock(side_effect=lambda value: value)

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
