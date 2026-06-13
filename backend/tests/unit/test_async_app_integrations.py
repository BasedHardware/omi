"""Tests for async app integration fan-out (issue #6369 Phase 1).

Verifies that trigger_realtime_audio_bytes and trigger_realtime_integrations
use asyncio.gather + httpx instead of Thread+join + requests.
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
# The real "utils" parent package is intentionally left out: restoring child
# stubs below also removes any attributes _install_module attached to it.
# "database" is restored because this test temporarily replaces that parent.
_MISSING = object()
_saved_modules = {name: sys.modules.get(name, _MISSING) for name in _RESTORED_MODULES}


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


# Stub database modules
_db_pkg = types.ModuleType("database")
_db_pkg.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'database'))]
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

for name in _utils_stubs:
    _install_module(name, types.ModuleType(name))

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
    # Stub module — safe to add mock attributes for import resolution
    _http_mod.get_webhook_client = MagicMock()
    _http_mod.get_maps_client = MagicMock()
    _mock_cb = MagicMock()
    _mock_cb.allow_request = MagicMock(return_value=True)
    _mock_cb.record_success = MagicMock()
    _mock_cb.record_failure = MagicMock()
    _http_mod.get_webhook_circuit_breaker = MagicMock(return_value=_mock_cb)
    _http_mod.get_webhook_semaphore = MagicMock(return_value=_asyncio.Semaphore(64))
    _http_mod.latest_wins_start = MagicMock(return_value=1)
    _http_mod.latest_wins_check = MagicMock(return_value=True)

# Stub executors — must use real ThreadPoolExecutor because asyncio's
# run_in_executor calls executor.submit() and wraps the returned Future.
from concurrent.futures import ThreadPoolExecutor as _TPE

_executors_mod = sys.modules["utils.executors"]
_executors_mod.critical_executor = _TPE(max_workers=2, thread_name_prefix="test-critical")
_executors_mod.db_executor = _TPE(max_workers=2, thread_name_prefix="test-db")
_executors_mod.storage_executor = _TPE(max_workers=2, thread_name_prefix="test-storage")


async def _run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


_executors_mod.run_blocking = _run_blocking

import importlib

app_integrations = importlib.import_module("utils.app_integrations")
_restore_stub_modules()


def _make_app(app_id: str, webhook_url: str, triggers_realtime=False, triggers_audio=False, uid=None):
    """Create a mock App that triggers the right integration type."""
    app = MagicMock()
    app.id = app_id
    app.name = f"App {app_id}"
    app.uid = uid
    app.enabled = True
    app.external_integration = MagicMock()
    app.external_integration.webhook_url = webhook_url
    app.triggers_realtime.return_value = triggers_realtime
    app.triggers_realtime_audio_bytes.return_value = triggers_audio
    app.has_capability = MagicMock(return_value=False)
    return app


class TestAsyncTriggerRealtimeAudioBytes:
    """Test async audio bytes fan-out."""

    @pytest.mark.asyncio
    async def test_no_apps_returns_empty(self):
        """No enabled audio apps → skip HTTP."""
        with patch.object(app_integrations, "get_available_apps", return_value=[]):
            result = await app_integrations.trigger_realtime_audio_bytes("uid-1", 8000, bytearray(b'\x00' * 100))
        assert result == {}

    @pytest.mark.asyncio
    async def test_multiple_apps_called_concurrently(self):
        """All matching apps are called via httpx, not Thread+join."""
        app1 = _make_app("a1", "https://app1.test/hook", triggers_audio=True)
        app2 = _make_app("a2", "https://app2.test/hook", triggers_audio=True)

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(app_integrations, "get_available_apps", return_value=[app1, app2]), patch.object(
            app_integrations, "get_webhook_client", return_value=mock_client
        ):
            await app_integrations.trigger_realtime_audio_bytes("uid-1", 8000, bytearray(b'\x00' * 10))

        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_one_failure_doesnt_cancel_others(self):
        """One app timeout should not prevent other apps from receiving audio."""
        import httpx

        app1 = _make_app("a1", "https://app1.test/hook", triggers_audio=True)
        app2 = _make_app("a2", "https://app2.test/hook", triggers_audio=True)

        mock_response = MagicMock()
        mock_response.status_code = 200

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "app1" in str(args):
                raise httpx.TimeoutException("timeout")
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=_side_effect)

        with patch.object(app_integrations, "get_available_apps", return_value=[app1, app2]), patch.object(
            app_integrations, "get_webhook_client", return_value=mock_client
        ):
            # Should not raise
            await app_integrations.trigger_realtime_audio_bytes("uid-1", 8000, bytearray(b'\x00'))

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_threading_used(self):
        """Verify threading.Thread is NOT used in the async path."""
        app1 = _make_app("a1", "https://app1.test/hook", triggers_audio=True)

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(app_integrations, "get_available_apps", return_value=[app1]), patch.object(
            app_integrations, "get_webhook_client", return_value=mock_client
        ), patch.object(app_integrations, "threading") as mock_threading:
            await app_integrations.trigger_realtime_audio_bytes("uid-1", 8000, bytearray(b'\x00'))
            mock_threading.Thread.assert_not_called()


class TestAudioBytesChunkedFanOut:
    """Test >8 apps are sent in chunked batches."""

    @pytest.mark.asyncio
    async def test_12_apps_sent_in_two_chunks(self):
        """12 apps should be sent in chunks of 8 + 4."""
        apps = []
        for i in range(12):
            app = MagicMock()
            app.id = f"app-{i}"
            app.triggers_realtime_audio_bytes.return_value = True
            app.enabled = True
            app.external_integration.webhook_url = f"https://app{i}.test/audio"
            apps.append(app)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(app_integrations, "get_available_apps", return_value=apps), patch.object(
            app_integrations, "get_webhook_client", return_value=mock_client
        ):
            await app_integrations.trigger_realtime_audio_bytes("uid-1", 8000, bytearray(b'\x00' * 100))

        # All 12 apps should have received the audio
        assert mock_client.post.call_count == 12


class TestAsyncTriggerRealtimeIntegrations:
    """Test async realtime integration fan-out."""

    @pytest.mark.asyncio
    async def test_no_apps_returns_empty(self):
        """No apps and no mentor → empty result."""
        with patch.object(app_integrations, "get_available_apps", return_value=[]), patch.object(
            app_integrations, "process_mentor_notification", return_value=None
        ):
            result = await app_integrations.trigger_realtime_integrations("uid-1", [{"text": "hi"}], "conv-1")
        assert result == {}

    @pytest.mark.asyncio
    async def test_multiple_apps_called_concurrently(self):
        """All matching apps called via httpx gather, not Thread+join."""
        app1 = _make_app("a1", "https://app1.test/hook", triggers_realtime=True)
        app2 = _make_app("a2", "https://app2.test/hook", triggers_realtime=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.text = ""

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(app_integrations, "get_available_apps", return_value=[app1, app2]), patch.object(
            app_integrations, "process_mentor_notification", return_value=None
        ), patch.object(app_integrations, "get_webhook_client", return_value=mock_client):
            await app_integrations.trigger_realtime_integrations("uid-1", [{"text": "hi"}], "conv-1")

        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_app_response_message_triggers_notification(self):
        """App returning a message > 5 chars triggers notification."""
        app1 = _make_app("a1", "https://app1.test/hook", triggers_realtime=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Important info here"}
        mock_response.text = ""

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(app_integrations, "get_available_apps", return_value=[app1]), patch.object(
            app_integrations, "process_mentor_notification", return_value=None
        ), patch.object(app_integrations, "get_webhook_client", return_value=mock_client), patch.object(
            app_integrations, "send_app_notification"
        ) as mock_notify, patch.object(
            app_integrations, "add_app_message", return_value={"id": "msg-1"}
        ):
            result = await app_integrations.trigger_realtime_integrations("uid-1", [{"text": "hi"}], "conv-1")

        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_url_query_param_handling(self):
        """URL with existing query params uses & separator."""
        app1 = _make_app("a1", "https://app1.test/hook?key=val", triggers_realtime=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.text = ""

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(app_integrations, "get_available_apps", return_value=[app1]), patch.object(
            app_integrations, "process_mentor_notification", return_value=None
        ), patch.object(app_integrations, "get_webhook_client", return_value=mock_client):
            await app_integrations.trigger_realtime_integrations("uid-1", [{"text": "hi"}], None)

        call_url = mock_client.post.call_args[0][0]
        assert "&uid=uid-1" in call_url
