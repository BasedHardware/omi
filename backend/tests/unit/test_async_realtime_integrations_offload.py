"""Regression test: _async_trigger_realtime_integrations must offload its
blocking Firestore-backed calls (get_available_apps, record_app_usage) to a
thread pool via run_blocking(db_executor, ...) instead of calling them directly
on the event loop.

Without the fix, get_available_apps(uid) is invoked directly (a sync Firestore
read) and record_app_usage is called bare inside the per-app coroutine, both of
which block the asyncio event loop. The fix wraps them in
`await run_blocking(db_executor, fn, ...)`.

The harness below mirrors the proven module-stub sandbox used by
test_async_app_integrations.py so the heavy router-tier imports resolve without
real Firestore / Redis / langchain / httpx packages.
"""

import os
import sys
import types
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

_database_stubs = [
    "database",
    "database._client",
    "database.mem_db",
    "database.redis_db",
    "database.memories",
    "database.conversations",
    "database.notifications",
    "database.users",
    "database.tasks",
    "database.trends",
    "database.action_items",
    "database.folders",
    "database.calendar_meetings",
    "database.vector_db",
    "database.apps",
    "database.llm_usage",
    "database.chat",
    "database.goals",
    "database.webhook_health",
]
_utils_stubs = [
    "utils.apps",
    "utils.notifications",
    "utils.conversations",
    "utils.conversations.factory",
    "utils.conversations.render",
    "utils.llm",
    "utils.llm.clients",
    "utils.llm.proactive_notification",
    "utils.llm.usage_tracker",
    "utils.llms",
    "utils.llms.memory",
    "utils.mentor_notifications",
    "utils.log_sanitizer",
    "utils.http_client",
    "utils.subscription",
    "utils.executors",
]
_RESTORED_MODULES = tuple(_database_stubs + _utils_stubs + ["utils.app_integrations"])
_MISSING = object()
_saved_modules = {name: sys.modules.get(name, _MISSING) for name in _RESTORED_MODULES}


def _ensure_package(name, path):
    module = sys.modules.get(name)
    if not isinstance(module, types.ModuleType) or not hasattr(module, '__path__'):
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [path]
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr, module)
    return module


def _install_module(name, module):
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr, module)


def _restore_stub_modules():
    for name in sorted(_RESTORED_MODULES, key=lambda module_name: module_name.count('.'), reverse=True):
        current = sys.modules.get(name)
        original = _saved_modules[name]
        if original is _MISSING:
            sys.modules.pop(name, None)
            if '.' in name:
                parent_name, attr = name.rsplit('.', 1)
                parent = sys.modules.get(parent_name)
                if parent is not None and getattr(parent, attr, _MISSING) is current:
                    delattr(parent, attr)
        else:
            sys.modules[name] = original
            if '.' in name:
                parent_name, attr = name.rsplit('.', 1)
                parent = sys.modules.get(parent_name)
                if parent is not None:
                    setattr(parent, attr, original)


_ensure_package("utils", os.path.join(_BACKEND_DIR, "utils"))

# Stub database modules
_db_pkg = types.ModuleType("database")
_db_pkg.__path__ = [os.path.join(_BACKEND_DIR, "database")]
_install_module("database", _db_pkg)
_install_module("database._client", MagicMock())

for submod in [
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
    "chat",
    "goals",
    "webhook_health",
]:
    mod = types.ModuleType(f"database.{submod}")
    _install_module(f"database.{submod}", mod)

_install_module("database.mem_db", types.ModuleType("database.mem_db"))
sys.modules["database.mem_db"].get_proactive_noti_sent_at = MagicMock(return_value=None)
sys.modules["database.mem_db"].set_proactive_noti_sent_at = MagicMock()
sys.modules["database.redis_db"].get_generic_cache = MagicMock(return_value=None)
sys.modules["database.redis_db"].set_generic_cache = MagicMock()
sys.modules["database.redis_db"].delete_app_cache_by_id = MagicMock()
sys.modules["database.redis_db"].r = MagicMock()
sys.modules["database.redis_db"].get_proactive_noti_sent_at = MagicMock(return_value=None)
sys.modules["database.redis_db"].set_proactive_noti_sent_at = MagicMock()
sys.modules["database.redis_db"].get_proactive_noti_sent_at_ttl = MagicMock(return_value=0)
sys.modules["database.redis_db"].incr_daily_notification_count = MagicMock()
sys.modules["database.redis_db"].get_daily_notification_count = MagicMock(return_value=0)
sys.modules["database.vector_db"].query_vectors_by_metadata = MagicMock(return_value=[])
sys.modules["database.apps"].record_app_usage = MagicMock()
sys.modules["database.apps"].get_app_by_id_db = MagicMock(return_value=None)
sys.modules["database.llm_usage"].record_llm_usage = MagicMock()
sys.modules["database.chat"].add_app_message = MagicMock(return_value={"id": "msg-1"})
sys.modules["database.chat"].get_app_messages = MagicMock(return_value=[])
sys.modules["database.notifications"].get_token_only = MagicMock(return_value=None)
sys.modules["database.notifications"].get_mentor_notification_frequency = MagicMock(return_value=0)
sys.modules["database.conversations"].get_conversations_by_id = MagicMock(return_value=[])
sys.modules["database.goals"].get_user_goals = MagicMock(return_value=[])
sys.modules["database.users"].get_user_language_preference = MagicMock(return_value="en")
sys.modules["database.webhook_health"].record_app_webhook_failure = MagicMock(return_value=0)
sys.modules["database.webhook_health"].record_app_webhook_success = MagicMock()
sys.modules["database.webhook_health"].is_app_webhook_disabled = MagicMock(return_value=False)
sys.modules["database.webhook_health"].disable_app_in_firestore = MagicMock()
sys.modules["database.webhook_health"].record_dev_webhook_failure = MagicMock(return_value=False)
sys.modules["database.webhook_health"].record_dev_webhook_success = MagicMock()
sys.modules["database.webhook_health"]._DEV_FAILURE_THRESHOLD = 100

_utils_pkg = sys.modules.get("utils")
if _utils_pkg is None:
    _utils_pkg = types.ModuleType("utils")
    sys.modules["utils"] = _utils_pkg
_utils_pkg.__path__ = [os.path.join(_BACKEND_DIR, "utils")]

for name in _utils_stubs:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
    _install_module(name, module)

sys.modules["utils.conversations"].__path__ = [os.path.join(_BACKEND_DIR, "utils", "conversations")]

sys.modules["utils.apps"].get_available_apps = MagicMock(return_value=[])
sys.modules["utils.notifications"].send_notification = MagicMock()
sys.modules["utils.conversations.factory"].deserialize_conversations = MagicMock(return_value=[])
sys.modules["utils.conversations.render"].conversations_to_string = MagicMock(return_value="")
sys.modules["utils.conversations.render"].conversation_to_dict = MagicMock(return_value={})
sys.modules["utils.conversations.render"].populate_speaker_names = MagicMock()
sys.modules["utils.conversations.render"].populate_folder_names = MagicMock()
sys.modules["utils.conversations.render"].serialize_datetimes = MagicMock(side_effect=lambda value: value)
sys.modules["utils.llm.clients"].generate_embedding = MagicMock(return_value=[0] * 3072)
sys.modules["utils.mentor_notifications"].process_mentor_notification = MagicMock(return_value=None)
sys.modules["utils.log_sanitizer"].sanitize = MagicMock(side_effect=lambda x: x)
sys.modules["utils.log_sanitizer"].sanitize_pii = MagicMock(side_effect=lambda x: x)
sys.modules["utils.subscription"].is_trial_paywalled = MagicMock(return_value=False)

# Stub proactive_notification named imports
_proactive_mod = sys.modules["utils.llm.proactive_notification"]
_proactive_mod.evaluate_relevance = MagicMock(return_value=0.0)
_proactive_mod.generate_notification = MagicMock(return_value="")
_proactive_mod.validate_notification = MagicMock(return_value=False)
_proactive_mod.FREQUENCY_TO_BASE_THRESHOLD = {1: 0.5, 2: 0.4, 3: 0.3}
_proactive_mod.MAX_DAILY_NOTIFICATIONS = 10

# Stub usage tracker
_usage_mod = sys.modules["utils.llm.usage_tracker"]
from contextlib import contextmanager as _cm


@_cm
def _noop_track(uid, feature):
    yield


_usage_mod.track_usage = _noop_track
_usage_mod.get_current_context = MagicMock(return_value=None)
_usage_mod.Features = MagicMock()
_usage_mod.Features.REALTIME_INTEGRATIONS = "realtime_integrations"
_usage_mod.Features.APP_INTEGRATIONS = "app_integrations"
_usage_mod.Features.NOTIFICATIONS = "notifications"

# Stub llms.memory
sys.modules["utils.llms.memory"].get_prompt_memories = MagicMock(return_value=[])

# Stub http_client — only set mock attributes on stub modules (not the real module)
import asyncio as _asyncio

_http_mod = sys.modules.get("utils.http_client")
if _http_mod is not None and not hasattr(_http_mod, '__file__'):
    _http_mod.get_webhook_client = MagicMock()
    _http_mod.get_maps_client = MagicMock()
    _http_mod.get_maps_semaphore = MagicMock(return_value=_asyncio.Semaphore(8))
    _mock_cb = MagicMock()
    _mock_cb.allow_request = MagicMock(return_value=True)
    _mock_cb.record_success = MagicMock()
    _mock_cb.record_failure = MagicMock()
    _http_mod.get_webhook_circuit_breaker = MagicMock(return_value=_mock_cb)
    _http_mod.get_webhook_semaphore = MagicMock(return_value=_asyncio.Semaphore(64))
    _http_mod.latest_wins_start = MagicMock(return_value=1)
    _http_mod.latest_wins_check = MagicMock(return_value=True)

# Stub executors — db_executor is a sentinel; run_blocking is a pass-through that
# actually invokes fn so the production code path runs end to end.
_executors_mod = sys.modules["utils.executors"]
_executors_mod.db_executor = MagicMock(name="db_executor")
_executors_mod.critical_executor = MagicMock(name="critical_executor")
_executors_mod.storage_executor = MagicMock(name="storage_executor")


async def _run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


_executors_mod.run_blocking = _run_blocking

import importlib

app_integrations = importlib.import_module("utils.app_integrations")
_restore_stub_modules()


def _make_app(app_id: str, webhook_url: str, triggers_realtime=True, uid=None):
    app = MagicMock()
    app.id = app_id
    app.name = f"App {app_id}"
    app.uid = uid
    app.enabled = True
    app.external_integration = MagicMock()
    app.external_integration.webhook_url = webhook_url
    app.triggers_realtime.return_value = triggers_realtime
    app.triggers_realtime_audio_bytes.return_value = False
    app.has_capability = MagicMock(return_value=False)
    return app


def _make_tracking_run_blocking():
    """A run_blocking that records (fn, args, kwargs) and still invokes fn so the
    coroutine proceeds normally."""
    calls = []

    async def _tracking(executor, fn, *args, **kwargs):
        calls.append((fn, args, kwargs))
        return fn(*args, **kwargs)

    return _tracking, calls


class TestRealtimeIntegrationsOffload:
    """get_available_apps and record_app_usage must be offloaded via run_blocking."""

    @pytest.mark.asyncio
    async def test_get_available_apps_offloaded_via_run_blocking(self):
        """get_available_apps(uid) must reach run_blocking(db_executor, get_available_apps, uid),
        not be called directly on the event loop."""
        tracking, calls = _make_tracking_run_blocking()
        get_apps = MagicMock(return_value=[])

        with patch.object(app_integrations, "run_blocking", tracking), patch.object(
            app_integrations, "get_available_apps", get_apps
        ), patch.object(app_integrations, "process_mentor_notification", MagicMock(return_value=None)):
            await app_integrations.trigger_realtime_integrations("uid-1", [{"text": "hi"}], "conv-1")

        offloaded_fns = [fn for (fn, _a, _kw) in calls]
        assert get_apps in offloaded_fns, "get_available_apps was not offloaded via run_blocking"
        # And it must have been offloaded with the uid, not called directly.
        offloaded_with_uid = [(a, kw) for (fn, a, kw) in calls if fn is get_apps]
        assert offloaded_with_uid and offloaded_with_uid[0][0] == ("uid-1",)

    @pytest.mark.asyncio
    async def test_record_app_usage_offloaded_via_run_blocking(self):
        """When a third-party app processes a transcript, record_app_usage must be
        offloaded via run_blocking rather than invoked bare in the coroutine."""
        # app.uid != uid (third-party) and conversation_id is not None -> usage recorded.
        app1 = _make_app("a1", "https://app1.test/hook", uid="owner-uid")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.text = ""

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        tracking, calls = _make_tracking_run_blocking()
        record_usage = MagicMock()

        with patch.object(app_integrations, "run_blocking", tracking), patch.object(
            app_integrations, "get_available_apps", MagicMock(return_value=[app1])
        ), patch.object(app_integrations, "process_mentor_notification", MagicMock(return_value=None)), patch.object(
            app_integrations, "get_webhook_client", return_value=mock_client
        ), patch.object(
            app_integrations, "record_app_usage", record_usage
        ):
            await app_integrations.trigger_realtime_integrations("uid-1", [{"text": "hi"}], "conv-1")

        offloaded_fns = [fn for (fn, _a, _kw) in calls]
        assert record_usage in offloaded_fns, "record_app_usage was not offloaded via run_blocking"
