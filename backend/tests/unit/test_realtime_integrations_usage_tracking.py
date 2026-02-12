"""
Unit tests for LLM usage tracking in realtime integrations fallback path.

Verifies that trigger_realtime_integrations wraps LLM calls (get_proactive_message,
generate_embedding) with track_usage(uid, Features.REALTIME_INTEGRATIONS).
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

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

chat_mod = sys.modules["database.chat"]
chat_mod.add_app_message = MagicMock(return_value={"id": "msg-1"})
chat_mod.get_app_messages = MagicMock(return_value=[])

notifications_mod = sys.modules["database.notifications"]
notifications_mod.get_token_only = MagicMock(return_value=None)

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
]:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

utils_apps = sys.modules["utils.apps"]
utils_apps.get_available_apps = MagicMock(return_value=[])

utils_notifications = sys.modules["utils.notifications"]
utils_notifications.send_notification = MagicMock()

llm_clients = sys.modules["utils.llm.clients"]
llm_clients.generate_embedding = MagicMock(return_value=[0] * 3072)

llm_proactive = sys.modules["utils.llm.proactive_notification"]
llm_proactive.get_proactive_message = MagicMock(return_value="Test notification message here")

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


def test_mentor_notification_tracked_under_realtime_integrations():
    """Verify mentor notification LLM call is tracked under REALTIME_INTEGRATIONS."""
    captured_contexts = []

    original_track = usage_tracker.track_usage

    from contextlib import contextmanager

    @contextmanager
    def spy_track_usage(uid, feature):
        captured_contexts.append((uid, feature))
        with original_track(uid, feature):
            yield

    # Make mentor notification fire
    mentor_mod.process_mentor_notification = MagicMock(return_value={'prompt': 'test prompt', 'params': []})

    with patch.object(app_integrations, "track_usage", spy_track_usage), patch.object(
        app_integrations, "send_app_notification", MagicMock()
    ), patch.object(app_integrations, "add_app_message", MagicMock(return_value={"id": "msg-1"})):
        app_integrations._trigger_realtime_integrations("user-rt-1", [{"text": "hello"}], "conv-1")

    # Should have tracked under REALTIME_INTEGRATIONS
    features_tracked = [f for _, f in captured_contexts]
    assert usage_tracker.Features.REALTIME_INTEGRATIONS in features_tracked

    # Reset
    mentor_mod.process_mentor_notification = MagicMock(return_value=None)


def test_no_tracking_when_no_llm_calls():
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
        app_integrations._trigger_realtime_integrations("user-rt-2", [{"text": "hello"}], "conv-2")

    assert len(captured_contexts) == 0


def test_track_usage_context_available_during_proactive_message():
    """Verify the track_usage context is active when get_proactive_message is called."""
    captured_ctx = {}

    original_get_proactive = app_integrations.get_proactive_message

    def spy_get_proactive(*args, **kwargs):
        captured_ctx["ctx"] = usage_tracker.get_current_context()
        return "Test notification"

    mentor_mod.process_mentor_notification = MagicMock(return_value={'prompt': 'test', 'params': []})

    with patch.object(app_integrations, "get_proactive_message", spy_get_proactive), patch.object(
        app_integrations, "send_app_notification", MagicMock()
    ), patch.object(app_integrations, "add_app_message", MagicMock(return_value={"id": "msg-1"})):
        app_integrations._trigger_realtime_integrations("user-rt-3", [{"text": "hello"}], "conv-3")

    assert captured_ctx.get("ctx") is not None
    assert captured_ctx["ctx"].feature == usage_tracker.Features.REALTIME_INTEGRATIONS
    assert captured_ctx["ctx"].uid == "user-rt-3"

    # Reset
    mentor_mod.process_mentor_notification = MagicMock(return_value=None)
