"""Tests for webhook auto-disable (issue #6885).

Verifies:
- Redis Lua scripts for graduated failure tracking (app webhooks)
- Redis Lua scripts for consecutive failure threshold (dev webhooks)
- Health state reset on success
- Integration with developer webhook functions
- Circuit breaker + health tracking in chat tool endpoints
"""

import importlib
import os
import sys
import types
from unittest.mock import MagicMock, AsyncMock, patch

import httpx
import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Stub database modules before import
sys.modules.setdefault("database._client", MagicMock())
_db_redis = sys.modules.get("database.redis_db")
if _db_redis is None:
    _db_redis = types.ModuleType("database.redis_db")
    sys.modules["database.redis_db"] = _db_redis
_db_redis.get_user_webhook_db = MagicMock(return_value="https://example.com/webhook")
_db_redis.user_webhook_status_db = MagicMock(return_value=True)
_db_redis.disable_user_webhook_db = MagicMock()
_db_redis.enable_user_webhook_db = MagicMock()
_db_redis.set_user_webhook_db = MagicMock()
_db_redis.get_cached_user_geolocation = MagicMock(return_value=None)
_db_redis.get_enabled_apps = MagicMock(return_value=[])
_db_redis.r = MagicMock()

_backend_dir = os.path.join(os.path.dirname(__file__), '..', '..')
_db_dir = os.path.join(_backend_dir, 'database')

for mod_name in ["database", "database.notifications", "database.users", "database.folders", "database.conversations"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)
        if mod_name == "database":
            sys.modules[mod_name].__path__ = [os.path.abspath(_db_dir)]

sys.modules["database.notifications"].get_token_only = MagicMock(return_value=None)
sys.modules["database.users"].get_user_profile = MagicMock(return_value={"name": "Test"})
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])
sys.modules["database.folders"].get_folders = MagicMock(return_value=[])
sys.modules["database.conversations"].get_conversations = MagicMock(return_value=[])

if "utils.notifications" not in sys.modules:
    sys.modules["utils.notifications"] = types.ModuleType("utils.notifications")
sys.modules["utils.notifications"].send_notification = MagicMock()

if "database.apps" not in sys.modules:
    sys.modules["database.apps"] = types.ModuleType("database.apps")
sys.modules["database.apps"].delete_app_cache_by_id = MagicMock()
sys.modules["database.apps"].get_app_by_id_db = MagicMock(return_value=None)

if "utils.executors" not in sys.modules:
    _executors_mod = types.ModuleType("utils.executors")
    sys.modules["utils.executors"] = _executors_mod
_executors_mod = sys.modules["utils.executors"]
_executors_mod.db_executor = MagicMock()
_executors_mod.llm_executor = MagicMock()
_executors_mod.storage_executor = MagicMock()
_executors_mod.critical_executor = MagicMock()
_executors_mod.postprocess_executor = MagicMock()
_executors_mod.sync_executor = MagicMock()
_executors_mod.stripe_executor = MagicMock()


async def _mock_run_blocking(executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


_executors_mod.run_blocking = _mock_run_blocking


def _load_app_tools_module():
    """Load app_tools module directly, bypassing __init__.py which pulls in heavy deps."""
    _db_redis_mod = sys.modules.get("database.redis_db")
    if _db_redis_mod:
        for attr in ['get_cached_user_geolocation', 'delete_app_cache_by_id', 'get_enabled_apps']:
            if not hasattr(_db_redis_mod, attr):
                setattr(_db_redis_mod, attr, MagicMock())
    for mod_name in [
        "utils.mcp_client",
        "utils.log_sanitizer",
        "utils.retrieval",
        "utils.retrieval.agentic",
        "utils.notifications",
    ]:
        sys.modules.setdefault(mod_name, MagicMock())
    _notif_mod = sys.modules.get("utils.notifications")
    if _notif_mod and not hasattr(_notif_mod, 'send_notification'):
        _notif_mod.send_notification = MagicMock()
    _apps_db_mod = sys.modules.get("database.apps")
    if _apps_db_mod and not hasattr(_apps_db_mod, 'get_app_by_id_db'):
        _apps_db_mod.get_app_by_id_db = MagicMock(return_value=None)
    if "utils.retrieval" in sys.modules:
        sys.modules["utils.retrieval"].__path__ = []
    if "utils.retrieval.tools.app_tools" in sys.modules:
        existing = sys.modules["utils.retrieval.tools.app_tools"]
        if hasattr(existing, 'is_app_webhook_disabled'):
            return existing
        del sys.modules["utils.retrieval.tools.app_tools"]
    spec = importlib.util.spec_from_file_location(
        "utils.retrieval.tools.app_tools",
        os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'retrieval', 'tools', 'app_tools.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["utils.retrieval.tools.app_tools"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestAppWebhookHealthLuaScript:
    """Test the graduated failure Lua script logic for marketplace app webhooks."""

    def test_first_failure_returns_no_action(self):
        """First failure should initialize state and return 0 (no action)."""
        from database.webhook_health import record_app_webhook_failure

        mock_script = MagicMock(return_value=0)
        with patch("database.webhook_health._get_failure_script", return_value=mock_script):
            result = record_app_webhook_failure("app-1", 500, "Internal Server Error")
        assert result == 0

    def test_day1_warning_returns_1(self):
        """After 24h of failures, should return 1 (day1 warn)."""
        from database.webhook_health import record_app_webhook_failure

        mock_script = MagicMock(return_value=1)
        with patch("database.webhook_health._get_failure_script", return_value=mock_script):
            result = record_app_webhook_failure("app-1", 500, "Internal Server Error")
        assert result == 1

    def test_day2_warning_returns_2(self):
        """After 48h of failures, should return 2 (day2 warn)."""
        from database.webhook_health import record_app_webhook_failure

        mock_script = MagicMock(return_value=2)
        with patch("database.webhook_health._get_failure_script", return_value=mock_script):
            result = record_app_webhook_failure("app-1", 500, "Internal Server Error")
        assert result == 2

    def test_disable_returns_3(self):
        """After 72h of failures, should return 3 (auto-disable) and set app-level disabled key."""
        from database.webhook_health import record_app_webhook_failure

        mock_script = MagicMock(return_value=3)
        mock_r = MagicMock()
        with (
            patch("database.webhook_health._get_failure_script", return_value=mock_script),
            patch("database.webhook_health.r", mock_r),
        ):
            result = record_app_webhook_failure("app-1", 500, "Internal Server Error")
        assert result == 3
        mock_r.setex.assert_called_once_with('app_webhook_disabled:app-1', 7 * 86400, '1')

    def test_redis_error_returns_no_action(self):
        """Redis errors should fail open (return 0, never auto-disable)."""
        from database.webhook_health import record_app_webhook_failure

        mock_script = MagicMock(side_effect=Exception("Redis connection lost"))
        with patch("database.webhook_health._get_failure_script", return_value=mock_script):
            result = record_app_webhook_failure("app-1", 500, "error")
        assert result == 0

    def test_error_message_truncated(self):
        """Error messages should be truncated to 200 chars."""
        from database.webhook_health import record_app_webhook_failure

        long_error = "x" * 500
        mock_script = MagicMock(return_value=0)
        with patch("database.webhook_health._get_failure_script", return_value=mock_script):
            record_app_webhook_failure("app-1", 500, long_error)
        call_args = mock_script.call_args
        error_arg = call_args.kwargs['args'][2]
        assert len(error_arg) == 200


class TestAppWebhookSuccessReset:
    """Test that success records via Lua script without resetting failure state."""

    def test_success_calls_lua_script(self):
        """record_app_webhook_success should invoke the success Lua script with endpoint key."""
        from database.webhook_health import record_app_webhook_success

        mock_script = MagicMock(return_value=1)
        with patch("database.webhook_health._get_success_script", return_value=mock_script):
            record_app_webhook_success("app-1")
        mock_script.assert_called_once()
        args = mock_script.call_args
        assert args.kwargs['keys'] == ['app_webhook_health:app-1:realtime']

    def test_success_redis_error_does_not_raise(self):
        """Redis errors during success recording should be swallowed."""
        from database.webhook_health import record_app_webhook_success

        mock_script = MagicMock(side_effect=Exception("Redis down"))
        with patch("database.webhook_health._get_success_script", return_value=mock_script):
            record_app_webhook_success("app-1")


class TestIsAppWebhookDisabled:
    """Test the disabled check function."""

    def setup_method(self):
        from database import webhook_health

        with webhook_health._cache_lock:
            webhook_health._disabled_cache.clear()

    def test_disabled_returns_true(self):
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.get.return_value = b'1'
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is True

    def test_not_disabled_returns_false(self):
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.get.return_value = b'0'
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is False

    def test_no_data_returns_false(self):
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.get.return_value = None
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is False

    def test_redis_error_returns_false(self):
        """Redis errors should fail open (not disabled)."""
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.get.side_effect = Exception("Redis timeout")
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is False


class TestClearAppWebhookHealth:
    """Test clear_app_webhook_health used on re-enable."""

    def test_clear_deletes_key(self):
        from database.webhook_health import clear_app_webhook_health

        mock_r = MagicMock()
        with patch("database.webhook_health.r", mock_r):
            clear_app_webhook_health("app-1")
        mock_r.delete.assert_called_once()
        deleted_keys = mock_r.delete.call_args[0]
        assert 'app_webhook_disabled:app-1' in deleted_keys
        assert 'app_webhook_health:app-1:realtime' in deleted_keys
        assert 'app_webhook_health:app-1:chat_tool' in deleted_keys
        assert 'app_webhook_health:app-1:mcp_tool' in deleted_keys

    def test_clear_redis_error_does_not_raise(self):
        from database.webhook_health import clear_app_webhook_health

        mock_r = MagicMock()
        mock_r.delete.side_effect = Exception("Redis down")
        with patch("database.webhook_health.r", mock_r):
            clear_app_webhook_health("app-1")


class TestDevWebhookHealthTracking:
    """Test developer webhook consecutive failure tracking."""

    def test_below_threshold_returns_false(self):
        from database.webhook_health import record_dev_webhook_failure

        mock_script = MagicMock(return_value=0)
        with patch("database.webhook_health._get_dev_failure_script", return_value=mock_script):
            result = record_dev_webhook_failure("uid-1", "memory_created", 500, "error")
        assert result is False

    def test_threshold_exceeded_returns_true(self):
        from database.webhook_health import record_dev_webhook_failure

        mock_script = MagicMock(return_value=1)
        with patch("database.webhook_health._get_dev_failure_script", return_value=mock_script):
            result = record_dev_webhook_failure("uid-1", "memory_created", 500, "error")
        assert result is True

    def test_redis_error_returns_false(self):
        from database.webhook_health import record_dev_webhook_failure

        mock_script = MagicMock(side_effect=Exception("Redis error"))
        with patch("database.webhook_health._get_dev_failure_script", return_value=mock_script):
            result = record_dev_webhook_failure("uid-1", "memory_created", 500, "error")
        assert result is False

    def test_success_resets_failure_count_and_disabled(self):
        from database.webhook_health import record_dev_webhook_success

        mock_r = MagicMock()
        with patch("database.webhook_health.r", mock_r):
            record_dev_webhook_success("uid-1", "memory_created")

        mock_r.hset.assert_called_once()
        call_kwargs = mock_r.hset.call_args
        mapping = call_kwargs.kwargs.get('mapping') or call_kwargs[1].get('mapping')
        assert mapping['failure_count'] == '0'
        assert mapping['disabled'] == '0'


class TestDevWebhookAutoDisable:
    """Test developer webhook auto-disable integration in webhooks.py."""

    @pytest.mark.asyncio
    async def test_dev_webhook_disabled_on_threshold(self):
        """When failure threshold exceeded, disable_user_webhook_db should be called."""
        from utils.webhooks import realtime_transcript_webhook

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        with (
            patch("utils.webhooks.get_webhook_client", return_value=mock_client),
            patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb),
            patch("utils.webhooks.record_dev_webhook_failure", return_value=True) as mock_fail,
            patch("utils.webhooks.disable_user_webhook_db") as mock_disable,
            patch("utils.webhooks.send_notification") as mock_notify,
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_fail.assert_called_once()
            mock_disable.assert_called_once()
            mock_notify.assert_called_once()
            notify_args = mock_notify.call_args[0]
            assert notify_args[0] == "uid-1"
            assert "Auto-Disabled" in notify_args[1]
            assert "consecutive failures" in notify_args[2]

    @pytest.mark.asyncio
    async def test_dev_webhook_success_records_health(self):
        """Successful dev webhook should call record_dev_webhook_success."""
        from utils.webhooks import realtime_transcript_webhook

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        with (
            patch("utils.webhooks.get_webhook_client", return_value=mock_client),
            patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb),
            patch("utils.webhooks.record_dev_webhook_success") as mock_success,
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_dev_webhook_exception_records_failure(self):
        """Exception during dev webhook should record failure with exception type."""
        from utils.webhooks import realtime_transcript_webhook

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        with (
            patch("utils.webhooks.get_webhook_client", return_value=mock_client),
            patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb),
            patch("utils.webhooks.record_dev_webhook_failure", return_value=False) as mock_fail,
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_fail.assert_called_once()
            args = mock_fail.call_args[0]
            assert args[2] == 0
            assert args[3] == 'ConnectionError'


class TestDisableAppInFirestore:
    """Test Firestore disable function."""

    def test_disable_updates_firestore(self):
        from database.webhook_health import disable_app_in_firestore

        mock_db = MagicMock()
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref

        with patch("database.webhook_health.db", mock_db):
            disable_app_in_firestore("app-1", "HTTP 500", 72)

        mock_ref.update.assert_called_once()
        update_data = mock_ref.update.call_args[0][0]
        assert update_data['disabled'] is True
        assert update_data['disabled_reason'] == 'webhook_failures'
        assert update_data['disabled_error'] == 'HTTP 500'
        assert update_data['disabled_failure_duration_hours'] == 72

    def test_disable_firestore_error_does_not_raise(self):
        from database.webhook_health import disable_app_in_firestore

        mock_db = MagicMock()
        mock_db.collection.side_effect = Exception("Firestore unavailable")

        with patch("database.webhook_health.db", mock_db):
            disable_app_in_firestore("app-1", "error", 72)


class TestGetAppWebhookHealth:
    """Test the full health state retrieval."""

    def test_returns_decoded_data(self):
        from database.webhook_health import get_app_webhook_health

        mock_r = MagicMock()
        ep_data = {
            b'failure_count': b'5',
            b'last_status': b'500',
            b'disabled': b'0',
        }
        mock_r.hgetall.side_effect = [ep_data, {}, {}]
        with patch("database.webhook_health.r", mock_r):
            result = get_app_webhook_health("app-1")
        assert 'realtime' in result
        assert result['realtime'] == {'failure_count': '5', 'last_status': '500', 'disabled': '0'}

    def test_returns_single_endpoint_data(self):
        from database.webhook_health import get_app_webhook_health

        mock_r = MagicMock()
        mock_r.hgetall.return_value = {
            b'failure_count': b'5',
            b'last_status': b'500',
            b'disabled': b'0',
        }
        with patch("database.webhook_health.r", mock_r):
            result = get_app_webhook_health("app-1", endpoint="chat_tool")
        assert result == {'failure_count': '5', 'last_status': '500', 'disabled': '0'}

    def test_returns_none_when_no_data(self):
        from database.webhook_health import get_app_webhook_health

        mock_r = MagicMock()
        mock_r.hgetall.return_value = {}
        with patch("database.webhook_health.r", mock_r):
            result = get_app_webhook_health("app-1")
        assert result is None

    def test_returns_none_on_redis_error(self):
        from database.webhook_health import get_app_webhook_health

        mock_r = MagicMock()
        mock_r.hgetall.side_effect = Exception("Redis error")
        with patch("database.webhook_health.r", mock_r):
            result = get_app_webhook_health("app-1")
        assert result is None

    def test_returns_none_for_single_endpoint_no_data(self):
        from database.webhook_health import get_app_webhook_health

        mock_r = MagicMock()
        mock_r.hgetall.return_value = {}
        with patch("database.webhook_health.r", mock_r):
            result = get_app_webhook_health("app-1", endpoint="chat_tool")
        assert result is None


class TestChatToolCircuitBreaker:
    """Test circuit breaker and health tracking in app_tools._call_tool_endpoint."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self._app_tools = _load_app_tools_module()

    @pytest.mark.asyncio
    async def test_disabled_app_returns_early(self):
        """Chat tool calls should return early if app is auto-disabled."""
        from models.app import ChatTool

        tool = ChatTool(
            name="test_tool",
            description="test",
            endpoint="https://example.com/tool",
            method="POST",
        )
        config = {'configurable': {'user_id': 'uid-1'}}
        mod = self._app_tools

        with patch.object(mod, "is_app_webhook_disabled", return_value=True):
            result = await mod._call_tool_endpoint({}, config, tool, "app-1")
        assert "temporarily disabled" in result

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_returns_early(self):
        """Chat tool calls should return early if circuit breaker is open."""
        from models.app import ChatTool

        tool = ChatTool(
            name="test_tool",
            description="test",
            endpoint="https://example.com/tool",
            method="POST",
        )
        config = {'configurable': {'user_id': 'uid-1'}}
        mod = self._app_tools

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = False

        with (
            patch.object(mod, "is_app_webhook_disabled", return_value=False),
            patch.object(mod, "get_webhook_circuit_breaker", return_value=mock_cb),
        ):
            result = await mod._call_tool_endpoint({}, config, tool, "app-1")
        assert "temporarily unavailable" in result

    @pytest.mark.asyncio
    async def test_success_records_health(self):
        """Successful chat tool call should record success in health tracking."""
        from models.app import ChatTool

        tool = ChatTool(
            name="test_tool",
            description="test",
            endpoint="https://example.com/tool",
            method="POST",
        )
        config = {'configurable': {'user_id': 'uid-1'}}
        mod = self._app_tools

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}

        with (
            patch.object(mod, "is_app_webhook_disabled", return_value=False),
            patch.object(mod, "get_webhook_circuit_breaker", return_value=mock_cb),
            patch.object(mod, "record_app_webhook_success") as mock_success,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await mod._call_tool_endpoint({}, config, tool, "app-1")

        assert result == "ok"
        mock_cb.record_success.assert_called_once()
        mock_success.assert_called_once_with("app-1", "chat_tool")

    @pytest.mark.asyncio
    async def test_failure_records_health(self):
        """Failed chat tool call should record failure in health tracking."""
        from models.app import ChatTool

        tool = ChatTool(
            name="test_tool",
            description="test",
            endpoint="https://example.com/tool",
            method="POST",
        )
        config = {'configurable': {'user_id': 'uid-1'}}
        mod = self._app_tools

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "internal error"}

        with (
            patch.object(mod, "is_app_webhook_disabled", return_value=False),
            patch.object(mod, "get_webhook_circuit_breaker", return_value=mock_cb),
            patch.object(mod, "record_app_webhook_failure", return_value=0) as mock_fail,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await mod._call_tool_endpoint({}, config, tool, "app-1")

        mock_cb.record_failure.assert_called_once()
        mock_fail.assert_called_once_with("app-1", 500, "HTTP 500", "chat_tool")

    @pytest.mark.asyncio
    async def test_timeout_records_failure(self):
        """Timeout in chat tool call should record failure."""
        import httpx
        from models.app import ChatTool

        tool = ChatTool(
            name="test_tool",
            description="test",
            endpoint="https://example.com/tool",
            method="POST",
        )
        config = {'configurable': {'user_id': 'uid-1'}}
        mod = self._app_tools

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        with (
            patch.object(mod, "is_app_webhook_disabled", return_value=False),
            patch.object(mod, "get_webhook_circuit_breaker", return_value=mock_cb),
            patch.object(mod, "record_app_webhook_failure", return_value=0) as mock_fail,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await mod._call_tool_endpoint({}, config, tool, "app-1")

        assert "Timeout" in result
        mock_cb.record_failure.assert_called_once()
        mock_fail.assert_called_once_with("app-1", 0, "TimeoutException", "chat_tool")


def _load_validate_helper():
    """Load validate_app_endpoints_for_reenable directly from source, bypassing heavy deps."""
    _utils_apps_key = "utils.apps"
    if _utils_apps_key in sys.modules and hasattr(sys.modules[_utils_apps_key], 'validate_app_endpoints_for_reenable'):
        return sys.modules[_utils_apps_key].validate_app_endpoints_for_reenable
    _saved = {}
    _mock_modules = [
        "database.redis_db",
        "database.apps",
        "database.auth",
        "database.cache",
        "database.conversations",
        "database.memories",
        "database.users",
        "utils.stripe",
        "utils.llm",
        "utils.llm.persona",
        "utils.llm.usage_tracker",
        "utils.social",
        "utils.conversations",
        "utils.conversations.factory",
        "utils.conversations.render",
        "models.app",
    ]
    for mod_name in _mock_modules:
        _saved[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = MagicMock()
    spec = importlib.util.spec_from_file_location(
        _utils_apps_key,
        os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'apps.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_utils_apps_key] = mod
    spec.loader.exec_module(mod)
    for mod_name, orig in _saved.items():
        if orig is not None:
            sys.modules[mod_name] = orig
    return mod.validate_app_endpoints_for_reenable


class TestReEnableRouterBehavior:
    """Tests for the production validate_app_endpoints_for_reenable helper from utils.apps."""

    @pytest.fixture(autouse=True)
    def _load_helper(self):
        self._validate = _load_validate_helper()

    def test_no_endpoints_returns_400(self):
        """Re-enable with no configured endpoints should return 400."""
        from fastapi import HTTPException

        app = {'external_integration': {}, 'chat_tools': []}
        update = {}
        with pytest.raises(HTTPException) as exc_info:
            self._validate(app, update, 'app-1')
        assert exc_info.value.status_code == 400
        assert 'No configured endpoints' in exc_info.value.detail

    def test_webhook_unhealthy_blocks_reenable(self):
        """Webhook returning 500 should block re-enable."""
        from fastapi import HTTPException

        app = {'external_integration': {'webhook_url': 'https://example.com/wh'}, 'chat_tools': []}
        update = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("utils.apps.httpx.request", return_value=mock_resp):
            with pytest.raises(HTTPException) as exc_info:
                self._validate(app, update, 'app-1')
        assert exc_info.value.status_code == 400
        assert '500' in exc_info.value.detail

    def test_webhook_healthy_allows_reenable(self):
        """Webhook returning 200 should allow re-enable."""
        app = {'external_integration': {'webhook_url': 'https://example.com/wh'}, 'chat_tools': []}
        update = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("utils.apps.httpx.request", return_value=mock_resp):
            self._validate(app, update, 'app-1')

    def test_mcp_non_2xx_allowed(self):
        """MCP returning 401 (auth required) should still allow re-enable."""
        app = {'external_integration': {'mcp_server_url': 'https://mcp.example.com'}, 'chat_tools': []}
        update = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("utils.apps.httpx.request", return_value=mock_resp):
            self._validate(app, update, 'app-1')

    def test_chat_tool_reachability_check_allows_non_2xx(self):
        """Chat tool health check uses HEAD for reachability only — non-2xx is acceptable."""
        app = {
            'external_integration': {},
            'chat_tools': [{'endpoint': 'https://tool.example.com/api', 'name': 't', 'method': 'POST'}],
        }
        update = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("utils.apps.httpx.request", return_value=mock_resp):
            self._validate(app, update, 'app-1')

    def test_timeout_blocks_reenable(self):
        """Timeout on any endpoint should block re-enable."""
        from fastapi import HTTPException

        app = {'external_integration': {'webhook_url': 'https://slow.example.com'}, 'chat_tools': []}
        update = {}
        with patch("utils.apps.httpx.request", side_effect=httpx.TimeoutException("timeout")):
            with pytest.raises(HTTPException) as exc_info:
                self._validate(app, update, 'app-1')
        assert exc_info.value.status_code == 400
        assert 'timed out' in exc_info.value.detail

    def test_connect_error_blocks_reenable(self):
        """Connection error on any endpoint should block re-enable."""
        from fastapi import HTTPException

        app = {'external_integration': {'webhook_url': 'https://down.example.com'}, 'chat_tools': []}
        update = {}
        with patch("utils.apps.httpx.request", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(HTTPException) as exc_info:
                self._validate(app, update, 'app-1')
        assert exc_info.value.status_code == 400
        assert 'Cannot connect' in exc_info.value.detail

    def test_all_endpoints_checked(self):
        """All configured endpoints must be probed before allowing re-enable."""
        app = {
            'external_integration': {'webhook_url': 'https://a.com/wh', 'mcp_server_url': 'https://b.com/mcp'},
            'chat_tools': [{'endpoint': 'https://c.com/tool', 'name': 't', 'method': 'GET'}],
        }
        update = {}
        call_urls = []

        def mock_request(method, url, **kwargs):
            call_urls.append((method, url))
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("utils.apps.httpx.request", side_effect=mock_request):
            self._validate(app, update, 'app-1')

        assert len(call_urls) == 3
        methods = [m for m, _ in call_urls]
        assert 'POST' in methods
        assert 'HEAD' in methods
        urls = [u for _, u in call_urls]
        assert 'https://a.com/wh' in urls
        assert 'https://b.com/mcp' in urls
        assert 'https://c.com/tool' in urls

    def test_second_webhook_failure_blocks_even_if_first_healthy(self):
        """If webhook is healthy but MCP fails with connect error, re-enable should be blocked."""
        from fastapi import HTTPException

        app = {
            'external_integration': {'webhook_url': 'https://ok.com/wh', 'mcp_server_url': 'https://broken.com/mcp'},
            'chat_tools': [],
        }
        update = {}
        call_count = [0]

        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                resp = MagicMock()
                resp.status_code = 200
                return resp
            raise httpx.ConnectError("refused")

        with patch("utils.apps.httpx.request", side_effect=mock_request):
            with pytest.raises(HTTPException) as exc_info:
                self._validate(app, update, 'app-1')
        assert exc_info.value.status_code == 400
        assert 'Cannot connect' in exc_info.value.detail

    def test_updated_chat_tools_preferred_over_stale_db(self):
        """update_dict chat_tools should override stale app chat_tools."""
        app = {
            'external_integration': {},
            'chat_tools': [{'endpoint': 'https://old-broken.example.com/api', 'name': 'old'}],
        }
        update = {'chat_tools': [{'endpoint': 'https://new-fixed.example.com/api', 'name': 'new'}]}
        probed_urls = []

        def mock_request(method, url, **kwargs):
            probed_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("utils.apps.httpx.request", side_effect=mock_request):
            self._validate(app, update, 'app-1')
        assert probed_urls == ['https://new-fixed.example.com/api']

    def test_exact_duplicate_url_deduped(self):
        """Same URL in webhook_url and chat_tools should be probed only once."""
        app = {
            'external_integration': {'webhook_url': 'https://example.com/hook'},
            'chat_tools': [{'endpoint': 'https://example.com/hook', 'name': 't'}],
        }
        update = {}
        probed_urls = []

        def mock_request(method, url, **kwargs):
            probed_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("utils.apps.httpx.request", side_effect=mock_request):
            self._validate(app, update, 'app-1')
        assert probed_urls == ['https://example.com/hook']

    def test_same_host_different_path_both_checked(self):
        """Same host but different URL paths must both be probed."""
        app = {
            'external_integration': {'webhook_url': 'https://example.com/webhook'},
            'chat_tools': [{'endpoint': 'https://example.com/tool', 'name': 't'}],
        }
        update = {}
        probed_urls = []

        def mock_request(method, url, **kwargs):
            probed_urls.append(url)
            resp = MagicMock()
            resp.status_code = 200
            return resp

        with patch("utils.apps.httpx.request", side_effect=mock_request):
            self._validate(app, update, 'app-1')
        assert len(probed_urls) == 2
        assert 'https://example.com/webhook' in probed_urls
        assert 'https://example.com/tool' in probed_urls


class TestLuaTimeProgression:
    """Verify the Lua script's graduated response thresholds via a Python state machine
    that mirrors the Lua logic. This catches off-by-one errors in the 24h/48h/72h
    elapsed checks and ensures the notification/disable flags are idempotent."""

    @staticmethod
    def _lua_sim(state: dict, now_ts: int, status: str, error: str) -> int:
        """Python equivalent of _RECORD_FAILURE_LUA."""
        first = state.get('first_failure_at')
        if not first:
            state.update(
                {
                    'first_failure_at': now_ts,
                    'last_failure_at': now_ts,
                    'last_success_at': '',
                    'failure_count': 1,
                    'last_status': status,
                    'last_error': error,
                    'notified_day1': '0',
                    'notified_day2': '0',
                    'disabled': '0',
                }
            )
            return 0

        first_ts = int(first)
        last_success = state.get('last_success_at', '')
        if last_success and last_success != '':
            last_success_ts = int(last_success)
            if last_success_ts >= first_ts:
                state.update(
                    {
                        'first_failure_at': now_ts,
                        'last_failure_at': now_ts,
                        'last_success_at': '',
                        'failure_count': 1,
                        'last_status': status,
                        'last_error': error,
                        'notified_day1': '0',
                        'notified_day2': '0',
                        'disabled': '0',
                    }
                )
                return 0

        state['last_failure_at'] = now_ts
        state['last_status'] = status
        state['last_error'] = error
        state['failure_count'] = state.get('failure_count', 0) + 1

        elapsed = now_ts - first_ts

        if elapsed >= 259200:  # 72h
            if state.get('disabled') != '1':
                state['disabled'] = '1'
                return 3
            return 0
        if elapsed >= 172800:  # 48h
            if state.get('notified_day2') != '1':
                state['notified_day2'] = '1'
                return 2
            return 0
        if elapsed >= 86400:  # 24h
            if state.get('notified_day1') != '1':
                state['notified_day1'] = '1'
                return 1
        return 0

    def test_full_graduated_timeline(self):
        """Walk through 0h → 12h → 24h → 36h → 48h → 60h → 72h → 84h."""
        state = {}
        t0 = 1_700_000_000

        assert self._lua_sim(state, t0, '500', 'error') == 0
        assert state['first_failure_at'] == t0

        assert self._lua_sim(state, t0 + 43200, '500', 'error') == 0

        assert self._lua_sim(state, t0 + 86400, '500', 'error') == 1
        assert state['notified_day1'] == '1'

        assert self._lua_sim(state, t0 + 129600, '500', 'error') == 0

        assert self._lua_sim(state, t0 + 172800, '500', 'error') == 2
        assert state['notified_day2'] == '1'

        assert self._lua_sim(state, t0 + 216000, '500', 'error') == 0

        assert self._lua_sim(state, t0 + 259200, '500', 'error') == 3
        assert state['disabled'] == '1'

        assert self._lua_sim(state, t0 + 302400, '500', 'error') == 0

    def test_notifications_are_idempotent(self):
        """Each notification fires exactly once, even with repeated calls at same threshold."""
        state = {}
        t0 = 1_700_000_000

        self._lua_sim(state, t0, '500', 'error')
        assert self._lua_sim(state, t0 + 86400, '500', 'error') == 1
        assert self._lua_sim(state, t0 + 86401, '500', 'error') == 0
        assert self._lua_sim(state, t0 + 86402, '500', 'error') == 0

        assert self._lua_sim(state, t0 + 172800, '500', 'error') == 2
        assert self._lua_sim(state, t0 + 172801, '500', 'error') == 0

        assert self._lua_sim(state, t0 + 259200, '500', 'error') == 3
        assert self._lua_sim(state, t0 + 259201, '500', 'error') == 0

    def test_just_under_thresholds_no_action(self):
        """Failures 1 second before each threshold don't trigger that threshold."""
        state = {}
        t0 = 1_700_000_000

        self._lua_sim(state, t0, '500', 'error')
        assert self._lua_sim(state, t0 + 86399, '500', 'error') == 0
        assert state['notified_day1'] == '0'

        state2 = {}
        self._lua_sim(state2, t0, '500', 'error')
        self._lua_sim(state2, t0 + 86400, '500', 'error')  # trigger day1
        assert state2['notified_day1'] == '1'
        assert self._lua_sim(state2, t0 + 172799, '500', 'error') == 0
        assert state2['notified_day2'] == '0'

        state3 = {}
        self._lua_sim(state3, t0, '500', 'error')
        self._lua_sim(state3, t0 + 86400, '500', 'error')  # trigger day1
        self._lua_sim(state3, t0 + 172800, '500', 'error')  # trigger day2
        assert state3['notified_day2'] == '1'
        assert self._lua_sim(state3, t0 + 259199, '500', 'error') == 0
        assert state3['disabled'] == '0'

    def test_python_sim_matches_lua_source_thresholds(self):
        """Verify the Python simulator uses the same constants as the Lua source."""
        from database.webhook_health import _RECORD_FAILURE_LUA

        assert '259200' in _RECORD_FAILURE_LUA  # 72h in seconds
        assert '172800' in _RECORD_FAILURE_LUA  # 48h in seconds

    def test_success_between_failures_resets_window(self):
        """Regression: failure → success → 72h → failure should NOT disable.

        A transient failure followed by recovery should reset the failure window.
        The second failure after 72h starts a fresh window, not auto-disable.
        """
        state = {}
        t0 = 1_700_000_000

        assert self._lua_sim(state, t0, '500', 'error') == 0
        assert state['first_failure_at'] == t0

        state['last_success_at'] = str(t0 + 3600)

        result = self._lua_sim(state, t0 + 259200, '500', 'error')
        assert result == 0
        assert state['disabled'] == '0'
        assert state['first_failure_at'] == t0 + 259200
        assert state['failure_count'] == 1

    def test_no_success_between_failures_still_disables(self):
        """Without any success, the 72h window proceeds to disable as designed."""
        state = {}
        t0 = 1_700_000_000

        self._lua_sim(state, t0, '500', 'error')
        self._lua_sim(state, t0 + 86400, '500', 'error')  # day1 warn
        self._lua_sim(state, t0 + 172800, '500', 'error')  # day2 warn
        result = self._lua_sim(state, t0 + 259200, '500', 'error')
        assert result == 3
        assert state['disabled'] == '1'

    def test_same_second_success_failure_does_not_prevent_disable(self):
        """Regression: failure@100 -> success@200 -> failure@200 -> 72h failure must disable.

        If reset branch doesn't clear last_success_at, the stale success timestamp
        keeps resetting the failure window on every subsequent failure.
        """
        state = {}
        t0 = 1_700_000_000

        self._lua_sim(state, t0, '500', 'error')
        state['last_success_at'] = str(t0 + 100)
        assert self._lua_sim(state, t0 + 100, '500', 'error') == 0
        assert state['first_failure_at'] == t0 + 100
        assert state['last_success_at'] == ''

        self._lua_sim(state, t0 + 100 + 86400, '500', 'error')  # day1 warn
        self._lua_sim(state, t0 + 100 + 172800, '500', 'error')  # day2 warn
        result = self._lua_sim(state, t0 + 100 + 259200, '500', 'error')
        assert result == 3
        assert state['disabled'] == '1'


class TestDisableAction:
    """Test that auto-disable calls Firestore disable and notifies app owner."""

    def test_disable_action_disables_and_notifies_owner(self):
        """action=3 should disable in Firestore, clear cache, notify owner."""
        _app_tools = _load_app_tools_module()

        with (
            patch.object(_app_tools, 'disable_app_in_firestore') as mock_disable,
            patch.object(_app_tools, 'delete_app_cache_by_id') as mock_cache,
            patch.object(_app_tools, '_notify_app_owner') as mock_notify,
        ):
            _app_tools._handle_app_webhook_disable('app-1', 3, 'HTTP 500')
            mock_disable.assert_called_once_with('app-1', 'HTTP 500', 72)
            mock_cache.assert_called_once_with('app-1')
            mock_notify.assert_called_once()
            assert 'Auto-Disabled' in mock_notify.call_args[0][1]

    def test_disable_preserves_user_enabled_sets(self):
        """action=3 should NOT remove app from users' enabled_plugins."""
        _app_tools = _load_app_tools_module()

        with (
            patch.object(_app_tools, 'disable_app_in_firestore'),
            patch.object(_app_tools, 'delete_app_cache_by_id'),
            patch.object(_app_tools, '_notify_app_owner'),
        ):
            _app_tools._handle_app_webhook_disable('app-1', 3, 'HTTP 500')
            assert (
                not hasattr(_app_tools, 'remove_app_from_all_enabled_sets')
                or not getattr(_app_tools, 'remove_app_from_all_enabled_sets', MagicMock()).called
            )


class TestLuaSourceVerification:
    """Verify the Lua script structure matches expected behavior contracts."""

    def test_lua_checks_thresholds_in_descending_order(self):
        """72h must be checked before 48h before 24h to avoid wrong action."""
        from database.webhook_health import _RECORD_FAILURE_LUA

        pos_72 = _RECORD_FAILURE_LUA.index('259200')
        pos_48 = _RECORD_FAILURE_LUA.index('172800')
        pos_24 = _RECORD_FAILURE_LUA.index('86400')
        assert pos_72 < pos_48 < pos_24

    def test_lua_sets_disabled_flag(self):
        """Lua script must set disabled='1' when returning action 3."""
        from database.webhook_health import _RECORD_FAILURE_LUA

        disabled_set = _RECORD_FAILURE_LUA.index("'disabled', '1'")
        return_3 = _RECORD_FAILURE_LUA.index('return 3')
        assert disabled_set < return_3

    def test_lua_checks_idempotent_flags(self):
        """Each notification checks its flag before setting, preventing duplicates."""
        from database.webhook_health import _RECORD_FAILURE_LUA

        assert "notified_day1" in _RECORD_FAILURE_LUA
        assert "notified_day2" in _RECORD_FAILURE_LUA
        assert _RECORD_FAILURE_LUA.count("HGET") >= 3  # disabled, notified_day1, notified_day2

    def test_lua_first_failure_initializes_all_fields(self):
        """First failure branch must initialize all required fields."""
        from database.webhook_health import _RECORD_FAILURE_LUA

        required_fields = [
            'first_failure_at',
            'last_failure_at',
            'failure_count',
            'disabled',
            'notified_day1',
            'notified_day2',
        ]
        first_branch_end = _RECORD_FAILURE_LUA.index('return 0')
        first_branch = _RECORD_FAILURE_LUA[:first_branch_end]
        for field in required_fields:
            assert field in first_branch, f"Missing {field} in first-failure initialization"

    def test_lua_checks_last_success_before_elapsed(self):
        """Lua script must check last_success_at > first_failure_at to reset window."""
        from database.webhook_health import _RECORD_FAILURE_LUA

        assert 'last_success_at' in _RECORD_FAILURE_LUA
        pos_success_check = _RECORD_FAILURE_LUA.index('last_success_ts')
        pos_elapsed_check = _RECORD_FAILURE_LUA.index('elapsed')
        assert pos_success_check < pos_elapsed_check


class TestMarketplaceIntegrationHealthPaths:
    """Test health action handling in marketplace integration triggers."""

    def test_action_1_warns_owner(self):
        """Day 1 warning should notify app owner with correct message."""
        _app_tools = _load_app_tools_module()

        with patch.object(_app_tools, '_notify_app_owner') as mock_notify:
            _app_tools._handle_app_webhook_disable('app-1', 1, 'HTTP 500')
        mock_notify.assert_called_once()
        args = mock_notify.call_args[0]
        assert args[0] == 'app-1'
        assert 'Failing' in args[1]
        assert '24' in args[2]

    def test_action_2_final_warning(self):
        """Day 2 final warning should notify with urgency."""
        _app_tools = _load_app_tools_module()

        with patch.object(_app_tools, '_notify_app_owner') as mock_notify:
            _app_tools._handle_app_webhook_disable('app-1', 2, 'HTTP 404')
        mock_notify.assert_called_once()
        args = mock_notify.call_args[0]
        assert 'Final Warning' in args[1]
        assert '48' in args[2]

    def test_action_0_does_nothing(self):
        """No action should not notify."""
        _app_tools = _load_app_tools_module()

        with patch.object(_app_tools, '_notify_app_owner') as mock_notify:
            _app_tools._handle_app_webhook_disable('app-1', 0, 'error')
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_connect_error_records_failure(self):
        """HTTP connection error on chat tool should record failure."""
        _app_tools = _load_app_tools_module()

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        with (
            patch.object(_app_tools, 'is_app_webhook_disabled', return_value=False),
            patch.object(_app_tools, 'get_webhook_circuit_breaker', return_value=mock_cb),
            patch.object(_app_tools, 'record_app_webhook_failure', return_value=0) as mock_fail,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            config = {'configurable': {'user_id': 'uid-1'}}
            from models.app import ChatTool

            tool = ChatTool(name="test", description="test", endpoint="https://dead.example.com/tool")
            result = await _app_tools._call_tool_endpoint({}, config, tool, "app-1")
        mock_fail.assert_called_once()
        assert mock_fail.call_args[0][0] == 'app-1'
        assert mock_fail.call_args[0][2] == 'ConnectError'
        assert mock_fail.call_args[0][3] == 'chat_tool'


class TestDevWebhookEdgeCases:
    """Test dev webhook Lua script edge behavior via mock return values."""

    def test_below_threshold_99_no_disable(self):
        """99 failures should not trigger disable (returns 0)."""
        from database.webhook_health import record_dev_webhook_failure

        mock_script = MagicMock(return_value=0)
        with patch("database.webhook_health._get_dev_failure_script", return_value=mock_script):
            result = record_dev_webhook_failure("uid-1", "memory_created", 500, "error")
        assert result is False

    def test_at_threshold_100_triggers_disable(self):
        """100th failure should trigger disable (returns 1)."""
        from database.webhook_health import record_dev_webhook_failure

        mock_script = MagicMock(return_value=1)
        with patch("database.webhook_health._get_dev_failure_script", return_value=mock_script):
            result = record_dev_webhook_failure("uid-1", "memory_created", 500, "error")
        assert result is True

    def test_already_disabled_returns_no_action(self):
        """When disabled=1 is already set, Lua returns 0 (no duplicate action)."""
        from database.webhook_health import record_dev_webhook_failure

        mock_script = MagicMock(return_value=0)
        with patch("database.webhook_health._get_dev_failure_script", return_value=mock_script):
            result = record_dev_webhook_failure("uid-1", "memory_created", 500, "error")
        assert result is False

    def test_dev_success_clears_disabled_flag(self):
        """record_dev_webhook_success must set disabled='0' to allow re-triggering."""
        from database.webhook_health import record_dev_webhook_success

        mock_r = MagicMock()
        with patch("database.webhook_health.r", mock_r):
            record_dev_webhook_success("uid-1", "audio_bytes")

        mapping = mock_r.hset.call_args.kwargs.get('mapping') or mock_r.hset.call_args[1].get('mapping')
        assert mapping['disabled'] == '0'
        assert mapping['failure_count'] == '0'


class TestMCPToolHealthTracking:
    """Test MCP tool disabled gate and health tracking in create_app_tool."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self._app_tools = _load_app_tools_module()

    @pytest.mark.asyncio
    async def test_mcp_disabled_app_returns_early(self):
        """MCP tool call should return early if app is auto-disabled."""
        from models.app import ChatTool

        tool = ChatTool(name="mcp_test", description="test MCP", endpoint="", is_mcp=True, transport="sse")
        mod = self._app_tools
        structured_tool = mod.create_app_tool(tool, "app-mcp-1", "TestMCPApp", mcp_server_url="https://mcp.example.com")
        with patch.object(mod, "is_app_webhook_disabled", return_value=True):
            result = await structured_tool.coroutine()
        assert "temporarily disabled" in result

    @pytest.mark.asyncio
    async def test_mcp_circuit_breaker_open_returns_early(self):
        """MCP tool call should return early if circuit breaker is open."""
        from models.app import ChatTool

        tool = ChatTool(name="mcp_test", description="test MCP", endpoint="", is_mcp=True, transport="sse")
        mod = self._app_tools
        structured_tool = mod.create_app_tool(tool, "app-mcp-1", "TestMCPApp", mcp_server_url="https://mcp.example.com")
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = False
        with (
            patch.object(mod, "is_app_webhook_disabled", return_value=False),
            patch.object(mod, "get_webhook_circuit_breaker", return_value=mock_cb),
        ):
            result = await structured_tool.coroutine()
        assert "temporarily unavailable" in result

    @pytest.mark.asyncio
    async def test_mcp_success_records_health(self):
        """Successful MCP tool call should record success."""
        from models.app import ChatTool

        tool = ChatTool(name="mcp_test", description="test MCP", endpoint="", is_mcp=True, transport="sse")
        mod = self._app_tools
        structured_tool = mod.create_app_tool(tool, "app-mcp-1", "TestMCPApp", mcp_server_url="https://mcp.example.com")
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True
        with (
            patch.object(mod, "is_app_webhook_disabled", return_value=False),
            patch.object(mod, "get_webhook_circuit_breaker", return_value=mock_cb),
            patch.object(mod, "call_mcp_tool", new_callable=AsyncMock, return_value="result ok"),
            patch.object(mod, "record_app_webhook_success") as mock_success,
        ):
            result = await structured_tool.coroutine()
        assert result == "result ok"
        mock_success.assert_called_once_with("app-mcp-1", "mcp_tool")

    @pytest.mark.asyncio
    async def test_mcp_failure_records_health(self):
        """Failed MCP tool call should record failure."""
        from models.app import ChatTool

        tool = ChatTool(name="mcp_test", description="test MCP", endpoint="", is_mcp=True, transport="sse")
        mod = self._app_tools
        structured_tool = mod.create_app_tool(tool, "app-mcp-1", "TestMCPApp", mcp_server_url="https://mcp.example.com")
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True
        with (
            patch.object(mod, "is_app_webhook_disabled", return_value=False),
            patch.object(mod, "get_webhook_circuit_breaker", return_value=mock_cb),
            patch.object(mod, "call_mcp_tool", new_callable=AsyncMock, return_value="Error: connection refused"),
            patch.object(mod, "record_app_webhook_failure", return_value=0) as mock_fail,
        ):
            result = await structured_tool.coroutine()
        mock_fail.assert_called_once()
        assert mock_fail.call_args[0][0] == "app-mcp-1"


class TestLoadAppToolsSkipsDisabled:
    """Test that load_app_tools skips disabled apps."""

    def test_disabled_app_skipped(self):
        """load_app_tools should skip apps with disabled=True."""
        _app_tools = _load_app_tools_module()

        with (
            patch.object(_app_tools, "get_enabled_apps", return_value=["app-disabled"]),
            patch.object(_app_tools, "get_app_by_id_db", return_value={"id": "app-disabled", "disabled": True}),
        ):
            tools = _app_tools.load_app_tools("uid-1")
        assert len(tools) == 0

    def test_non_disabled_app_loaded(self):
        """load_app_tools should load tools from non-disabled apps."""
        _app_tools = _load_app_tools_module()

        app_data = {
            "id": "app-1",
            "name": "Test App",
            "author": "test-author",
            "description": "A test app",
            "image": "https://example.com/icon.png",
            "capabilities": ["chat"],
            "disabled": False,
            "uid": "owner-1",
            "category": "other",
            "chat_tools": [
                {"name": "test_tool", "description": "test", "endpoint": "https://example.com/tool", "method": "POST"}
            ],
            "external_integration": None,
        }
        with (
            patch.object(_app_tools, "get_enabled_apps", return_value=["app-1"]),
            patch.object(_app_tools, "get_app_by_id_db", return_value=app_data),
        ):
            tools = _app_tools.load_app_tools("uid-1")
        assert len(tools) == 1


class TestDevWebhookManualReEnable:
    """Test that manual dev webhook re-enable clears health state."""

    def test_success_on_enable_clears_state(self):
        """record_dev_webhook_success called on manual enable should reset all fields."""
        from database.webhook_health import record_dev_webhook_success

        mock_r = MagicMock()
        with patch("database.webhook_health.r", mock_r):
            record_dev_webhook_success("uid-1", "realtime_transcript")

        mapping = mock_r.hset.call_args.kwargs.get('mapping') or mock_r.hset.call_args[1].get('mapping')
        assert mapping['failure_count'] == '0'
        assert mapping['disabled'] == '0'
        assert mapping['last_error'] == ''
        mock_r.expire.assert_called_once()


class TestDisabledCacheInMemory:
    """Test in-memory cache for is_app_webhook_disabled."""

    def setup_method(self):
        from database import webhook_health

        self.wh = webhook_health
        with self.wh._cache_lock:
            self.wh._disabled_cache.clear()

    def test_caches_false_avoids_repeated_get(self):
        mock_r = MagicMock()
        mock_r.get.return_value = b'0'
        with patch.object(self.wh, 'r', mock_r):
            r1 = self.wh.is_app_webhook_disabled("app-cache-1")
            r2 = self.wh.is_app_webhook_disabled("app-cache-1")
        assert r1 is False
        assert r2 is False
        assert mock_r.get.call_count == 1

    def test_caches_true_avoids_repeated_get(self):
        mock_r = MagicMock()
        mock_r.get.return_value = b'1'
        with patch.object(self.wh, 'r', mock_r):
            r1 = self.wh.is_app_webhook_disabled("app-cache-2")
            r2 = self.wh.is_app_webhook_disabled("app-cache-2")
        assert r1 is True
        assert r2 is True
        assert mock_r.get.call_count == 1

    def test_cache_expires_after_ttl(self):
        mock_r = MagicMock()
        mock_r.get.return_value = b'0'
        with patch.object(self.wh, 'r', mock_r):
            self.wh.is_app_webhook_disabled("app-cache-3")
            with self.wh._cache_lock:
                entry = self.wh._disabled_cache["app-cache-3"]
                self.wh._disabled_cache["app-cache-3"] = (entry[0], entry[1] - 61, entry[2])
            mock_r.get.return_value = b'1'
            result = self.wh.is_app_webhook_disabled("app-cache-3")
        assert result is True
        assert mock_r.get.call_count == 2

    def test_redis_error_returns_false_not_cached(self):
        mock_r = MagicMock()
        mock_r.get.side_effect = Exception("Redis down")
        with patch.object(self.wh, 'r', mock_r):
            r1 = self.wh.is_app_webhook_disabled("app-cache-4")
        assert r1 is False
        assert "app-cache-4" not in self.wh._disabled_cache

    def test_clear_invalidates_disabled_cache(self):
        mock_r = MagicMock()
        mock_r.get.return_value = b'1'
        with patch.object(self.wh, 'r', mock_r):
            self.wh.is_app_webhook_disabled("app-cache-5")
            assert self.wh._disabled_cache["app-cache-5"][0] is True
        mock_r2 = MagicMock()
        with patch.object(self.wh, 'r', mock_r2):
            self.wh.clear_app_webhook_health("app-cache-5")
        assert self.wh._disabled_cache["app-cache-5"][0] is False

    def test_disable_in_firestore_sets_cache_true(self):
        mock_r = MagicMock()
        mock_r.get.return_value = b'0'
        mock_db = MagicMock()
        with patch.object(self.wh, 'r', mock_r), patch.object(self.wh, 'db', mock_db):
            self.wh.is_app_webhook_disabled("app-cache-6")
            assert self.wh._disabled_cache["app-cache-6"][0] is False
            self.wh.disable_app_in_firestore("app-cache-6", "test error", 72)
            assert self.wh._disabled_cache["app-cache-6"][0] is True
            result = self.wh.is_app_webhook_disabled("app-cache-6")
        assert result is True
        assert mock_r.get.call_count == 1


class TestCacheRaceSafety:
    """Regression: authoritative cache writes must not be overwritten by stale Redis reads."""

    def setup_method(self):
        from database import webhook_health

        self.wh = webhook_health
        with self.wh._cache_lock:
            self.wh._disabled_cache.clear()

    def test_stale_read_does_not_overwrite_disable(self):
        """Simulate: is_app_webhook_disabled reads Redis (False), then disable bumps gen.
        The stale read must not overwrite the authoritative True."""
        mock_r = MagicMock()
        mock_r.get.return_value = b'0'
        with patch.object(self.wh, 'r', mock_r):
            self.wh.is_app_webhook_disabled("app-race-1")
        assert self.wh._disabled_cache["app-race-1"][0] is False
        pre_gen = self.wh._disabled_cache["app-race-1"][2]

        mock_r2 = MagicMock()
        with patch.object(self.wh, 'r', mock_r2):
            with self.wh._cache_lock:
                gen = self.wh._disabled_cache.get("app-race-1", (False, 0, 0))[2] + 1
                self.wh._disabled_cache["app-race-1"] = (True, self.wh.time.monotonic(), gen)

        mock_r3 = MagicMock()
        mock_r3.get.return_value = b'0'
        now = self.wh.time.monotonic()
        with self.wh._cache_lock:
            entry = self.wh._disabled_cache["app-race-1"]
            self.wh._disabled_cache["app-race-1"] = (entry[0], entry[1] - 61, entry[2])

        with patch.object(self.wh, 'r', mock_r3):
            result = self.wh.is_app_webhook_disabled("app-race-1")
        assert result is False
        assert self.wh._disabled_cache["app-race-1"][0] is False

    def test_stale_read_does_not_overwrite_clear(self):
        """Simulate: is_app_webhook_disabled starts Redis read, clear bumps gen.
        The stale read must not repopulate True after clear."""
        mock_r = MagicMock()
        mock_r.get.return_value = b'1'
        with patch.object(self.wh, 'r', mock_r):
            self.wh.is_app_webhook_disabled("app-race-2")
        assert self.wh._disabled_cache["app-race-2"][0] is True

        mock_r2 = MagicMock()
        with patch.object(self.wh, 'r', mock_r2):
            self.wh.clear_app_webhook_health("app-race-2")
        assert self.wh._disabled_cache["app-race-2"][0] is False
        clear_gen = self.wh._disabled_cache["app-race-2"][2]

        with self.wh._cache_lock:
            entry = self.wh._disabled_cache["app-race-2"]
            self.wh._disabled_cache["app-race-2"] = (entry[0], entry[1] - 61, entry[2])

        mock_r3 = MagicMock()
        mock_r3.get.return_value = b'1'
        with patch.object(self.wh, 'r', mock_r3):
            result = self.wh.is_app_webhook_disabled("app-race-2")
        assert result is True
        assert self.wh._disabled_cache["app-race-2"][2] == clear_gen

    def test_generation_increments_on_disable(self):
        """record_app_webhook_failure action=3 bumps generation."""
        mock_script = MagicMock(return_value=3)
        mock_r = MagicMock()
        with (
            patch("database.webhook_health._get_failure_script", return_value=mock_script),
            patch("database.webhook_health.r", mock_r),
        ):
            self.wh.record_app_webhook_failure("app-race-3", 500, "error")
        entry = self.wh._disabled_cache.get("app-race-3")
        assert entry is not None
        assert entry[0] is True
        assert entry[2] == 1


class TestSuccessDebounce:
    """Test success Lua script debounce and recovery bypass logic."""

    def setup_method(self):
        from database import webhook_health

        self.wh = webhook_health

    def test_success_calls_lua_script(self):
        mock_script = MagicMock(return_value=1)
        with patch("database.webhook_health._get_success_script", return_value=mock_script):
            self.wh.record_app_webhook_success("app-deb-1")
        assert mock_script.call_count == 1

    def test_failure_not_debounced(self):
        mock_script = MagicMock(return_value=0)
        with patch("database.webhook_health._get_failure_script", return_value=mock_script):
            self.wh.record_app_webhook_failure("app-deb-6", 500, "error")
            self.wh.record_app_webhook_failure("app-deb-6", 500, "error")
        assert mock_script.call_count == 2

    def test_dev_webhook_success_not_debounced(self):
        """Dev webhook success resets failure_count — must NOT be debounced."""
        mock_r = MagicMock()
        with patch.object(self.wh, 'r', mock_r):
            self.wh.record_dev_webhook_success("uid-1", "realtime_transcript")
            self.wh.record_dev_webhook_success("uid-1", "realtime_transcript")
        assert mock_r.hset.call_count == 2


class TestSuccessLuaScript:
    """Test the success Lua script logic via Python state machine."""

    @staticmethod
    def _lua_success_sim(state: dict, now_ts: int, debounce: int) -> int:
        """Python equivalent of _RECORD_SUCCESS_LUA."""
        first_failure = state.get('first_failure_at', '')
        last_success = state.get('last_success_at', '')

        if first_failure and first_failure != '':
            ff = int(first_failure)
            ls = int(last_success) if (last_success and last_success != '') else 0
            if ff >= ls:
                state['last_success_at'] = str(now_ts)
                return 1

        if last_success and last_success != '':
            ls = int(last_success)
            if (now_ts - ls) < debounce:
                return 0

        state['last_success_at'] = str(now_ts)
        return 1

    def test_first_success_writes(self):
        state = {}
        assert self._lua_success_sim(state, 1000, 60) == 1
        assert state['last_success_at'] == '1000'

    def test_second_success_within_window_debounced(self):
        state = {'last_success_at': '1000'}
        assert self._lua_success_sim(state, 1030, 60) == 0
        assert state['last_success_at'] == '1000'

    def test_success_after_window_writes(self):
        state = {'last_success_at': '1000'}
        assert self._lua_success_sim(state, 1061, 60) == 1
        assert state['last_success_at'] == '1061'

    def test_recovery_success_bypasses_debounce(self):
        """Success at t=0, failure at t=30, success at t=40 must write (recovery)."""
        state = {'last_success_at': '1000', 'first_failure_at': '1030'}
        assert self._lua_success_sim(state, 1040, 60) == 1
        assert state['last_success_at'] == '1040'

    def test_same_second_recovery_writes(self):
        """Failure and success in the same second — >= ensures recovery writes."""
        state = {'last_success_at': '999', 'first_failure_at': '1000'}
        assert self._lua_success_sim(state, 1000, 60) == 1
        assert state['last_success_at'] == '1000'

    def test_after_recovery_debounce_resumes(self):
        """Once recovery success is written, subsequent successes debounce normally."""
        state = {'last_success_at': '1040', 'first_failure_at': '1030'}
        assert self._lua_success_sim(state, 1050, 60) == 0

    def test_different_apps_independent(self):
        state_a = {}
        state_b = {}
        assert self._lua_success_sim(state_a, 1000, 60) == 1
        assert self._lua_success_sim(state_b, 1000, 60) == 1

    def test_multi_pod_recovery_sequence(self):
        """Regression: success(pod A) → failure(pod B) → success(pod A) must write.

        Even though pod A doesn't know about pod B's failure, the Lua script
        checks Redis state atomically.
        """
        state = {}
        self._lua_success_sim(state, 1000, 60)
        state['first_failure_at'] = '1030'
        state['failure_count'] = '1'
        assert self._lua_success_sim(state, 1040, 60) == 1
        assert state['last_success_at'] == '1040'


class TestCacheEviction:
    """Test cache size cap and eviction."""

    def setup_method(self):
        from database import webhook_health

        self.wh = webhook_health
        with self.wh._cache_lock:
            self.wh._disabled_cache.clear()

    def test_disabled_cache_evicts_when_over_max(self):
        mock_r = MagicMock()
        mock_r.get.return_value = b'0'
        original_max = self.wh._CACHE_MAX_SIZE
        try:
            self.wh._CACHE_MAX_SIZE = 5
            with patch.object(self.wh, 'r', mock_r):
                for i in range(7):
                    self.wh.is_app_webhook_disabled(f"evict-app-{i}")
            assert len(self.wh._disabled_cache) <= 6
        finally:
            self.wh._CACHE_MAX_SIZE = original_max


class TestPerEndpointHealthIsolation:
    """Regression: healthy endpoint A must NOT reset failure window for broken endpoint B."""

    def test_endpoint_a_success_does_not_mask_endpoint_b_failure(self):
        """Chat tool fails for 72h while realtime webhook succeeds — should still disable."""
        from database.webhook_health import (
            record_app_webhook_failure,
            record_app_webhook_success,
            ENDPOINT_REALTIME,
            ENDPOINT_CHAT_TOOL,
        )

        mock_fail_script = MagicMock(side_effect=[0, 1, 2, 3])
        mock_success_script = MagicMock(return_value=1)
        mock_r = MagicMock()
        with (
            patch("database.webhook_health._get_failure_script", return_value=mock_fail_script),
            patch("database.webhook_health._get_success_script", return_value=mock_success_script),
            patch("database.webhook_health.r", mock_r),
        ):
            record_app_webhook_failure("app-1", 500, "error", ENDPOINT_CHAT_TOOL)
            record_app_webhook_success("app-1", ENDPOINT_REALTIME)
            record_app_webhook_failure("app-1", 500, "error", ENDPOINT_CHAT_TOOL)
            record_app_webhook_success("app-1", ENDPOINT_REALTIME)
            record_app_webhook_failure("app-1", 500, "error", ENDPOINT_CHAT_TOOL)
            record_app_webhook_success("app-1", ENDPOINT_REALTIME)
            result = record_app_webhook_failure("app-1", 500, "error", ENDPOINT_CHAT_TOOL)

        assert result == 3

        fail_keys = [c.kwargs['keys'][0] for c in mock_fail_script.call_args_list]
        success_keys = [c.kwargs['keys'][0] for c in mock_success_script.call_args_list]
        assert all(k == 'app_webhook_health:app-1:chat_tool' for k in fail_keys)
        assert all(k == 'app_webhook_health:app-1:realtime' for k in success_keys)

        mock_r.setex.assert_called_once_with('app_webhook_disabled:app-1', 7 * 86400, '1')

    def test_different_endpoints_use_different_redis_keys(self):
        """Each endpoint surface gets its own Redis key."""
        from database.webhook_health import (
            record_app_webhook_failure,
            record_app_webhook_success,
            ENDPOINT_REALTIME,
            ENDPOINT_CHAT_TOOL,
            ENDPOINT_MCP_TOOL,
        )

        mock_fail_script = MagicMock(return_value=0)
        mock_success_script = MagicMock(return_value=1)
        with (
            patch("database.webhook_health._get_failure_script", return_value=mock_fail_script),
            patch("database.webhook_health._get_success_script", return_value=mock_success_script),
        ):
            record_app_webhook_failure("app-1", 500, "err", ENDPOINT_REALTIME)
            record_app_webhook_failure("app-1", 500, "err", ENDPOINT_CHAT_TOOL)
            record_app_webhook_failure("app-1", 500, "err", ENDPOINT_MCP_TOOL)
            record_app_webhook_success("app-1", ENDPOINT_REALTIME)
            record_app_webhook_success("app-1", ENDPOINT_CHAT_TOOL)

        fail_keys = [c.kwargs['keys'][0] for c in mock_fail_script.call_args_list]
        success_keys = [c.kwargs['keys'][0] for c in mock_success_script.call_args_list]
        assert fail_keys == [
            'app_webhook_health:app-1:realtime',
            'app_webhook_health:app-1:chat_tool',
            'app_webhook_health:app-1:mcp_tool',
        ]
        assert success_keys == [
            'app_webhook_health:app-1:realtime',
            'app_webhook_health:app-1:chat_tool',
        ]

    def test_disable_on_any_endpoint_sets_app_level_flag(self):
        """When any endpoint triggers disable (action=3), app-level disabled key is set."""
        from database.webhook_health import record_app_webhook_failure, ENDPOINT_MCP_TOOL, _disabled_cache, _cache_lock

        mock_fail_script = MagicMock(return_value=3)
        mock_r = MagicMock()
        with _cache_lock:
            _disabled_cache.clear()
        with (
            patch("database.webhook_health._get_failure_script", return_value=mock_fail_script),
            patch("database.webhook_health.r", mock_r),
        ):
            result = record_app_webhook_failure("app-mcp-1", 500, "error", ENDPOINT_MCP_TOOL)
        assert result == 3
        mock_r.setex.assert_called_once_with('app_webhook_disabled:app-mcp-1', 7 * 86400, '1')
        with _cache_lock:
            assert _disabled_cache.get("app-mcp-1", (None,))[0] is True


class TestFakeRedisFailureLua:
    """Execute the real failure Lua script against fakeredis to verify atomic behavior."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        import fakeredis

        self.fr = fakeredis.FakeRedis()
        from database.webhook_health import _RECORD_FAILURE_LUA, _HEALTH_TTL

        self.script = self.fr.register_script(_RECORD_FAILURE_LUA)
        self.ttl = _HEALTH_TTL

    def _run(self, app_id, now_ts, status, error):
        key = f'app_webhook_health:{app_id}:realtime'
        return int(self.script(keys=[key], args=[now_ts, str(status), error[:200], self.ttl]))

    def _hgetall(self, app_id):
        key = f'app_webhook_health:{app_id}:realtime'
        data = self.fr.hgetall(key)
        return {k.decode(): v.decode() for k, v in data.items()}

    def test_graduated_timeline(self):
        t0 = 1_700_000_000
        assert self._run("app-lua", t0, 500, "err") == 0
        assert self._run("app-lua", t0 + 86400, 500, "err") == 1
        assert self._run("app-lua", t0 + 86401, 500, "err") == 0
        assert self._run("app-lua", t0 + 172800, 500, "err") == 2
        assert self._run("app-lua", t0 + 172801, 500, "err") == 0
        assert self._run("app-lua", t0 + 259200, 500, "err") == 3
        assert self._run("app-lua", t0 + 259201, 500, "err") == 0
        state = self._hgetall("app-lua")
        assert state['disabled'] == '1'
        assert int(state['failure_count']) >= 7

    def test_success_resets_window(self):
        t0 = 1_700_000_000
        self._run("app-reset", t0, 500, "err")
        key = 'app_webhook_health:app-reset:realtime'
        self.fr.hset(key, 'last_success_at', str(t0 + 3600))
        assert self._run("app-reset", t0 + 259200, 500, "err") == 0
        state = self._hgetall("app-reset")
        assert state['disabled'] == '0'
        assert int(state['first_failure_at']) == t0 + 259200

    def test_same_second_success_failure_clears_last_success(self):
        t0 = 1_700_000_000
        self._run("app-ss", t0, 500, "err")
        key = 'app_webhook_health:app-ss:realtime'
        self.fr.hset(key, 'last_success_at', str(t0 + 100))
        self._run("app-ss", t0 + 100, 500, "err")
        state = self._hgetall("app-ss")
        assert state['last_success_at'] == ''
        assert int(state['first_failure_at']) == t0 + 100

    def test_ttl_set_on_key(self):
        self._run("app-ttl", 1_700_000_000, 500, "err")
        key = 'app_webhook_health:app-ttl:realtime'
        ttl = self.fr.ttl(key)
        assert ttl > 0
        assert ttl <= self.ttl

    def test_error_truncated_to_200(self):
        self._run("app-trunc", 1_700_000_000, 500, "x" * 500)
        state = self._hgetall("app-trunc")
        assert len(state['last_error']) <= 200


class TestFakeRedisSuccessLua:
    """Execute the real success Lua script against fakeredis."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        import fakeredis

        self.fr = fakeredis.FakeRedis()
        from database.webhook_health import _RECORD_SUCCESS_LUA, _HEALTH_TTL, _SUCCESS_DEBOUNCE

        self.script = self.fr.register_script(_RECORD_SUCCESS_LUA)
        self.ttl = _HEALTH_TTL
        self.debounce = _SUCCESS_DEBOUNCE

    def _run(self, app_id, now_ts):
        key = f'app_webhook_health:{app_id}:realtime'
        return int(self.script(keys=[key], args=[now_ts, self.debounce, self.ttl]))

    def test_first_success_writes(self):
        assert self._run("app-s1", 1000) == 1
        val = self.fr.hget('app_webhook_health:app-s1:realtime', 'last_success_at')
        assert val == b'1000'

    def test_debounce_within_window(self):
        self._run("app-s2", 1000)
        assert self._run("app-s2", 1030) == 0

    def test_debounce_after_window(self):
        self._run("app-s3", 1000)
        assert self._run("app-s3", 1061) == 1

    def test_recovery_bypasses_debounce(self):
        key = 'app_webhook_health:app-s4:realtime'
        self.fr.hset(key, mapping={'last_success_at': '1000', 'first_failure_at': '1030'})
        assert self._run("app-s4", 1040) == 1
        val = self.fr.hget(key, 'last_success_at')
        assert val == b'1040'

    def test_ttl_set_on_key(self):
        self._run("app-sttl", 1000)
        ttl = self.fr.ttl('app_webhook_health:app-sttl:realtime')
        assert ttl > 0


class TestFakeRedisDevFailureLua:
    """Execute the real dev failure Lua script against fakeredis."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        import fakeredis

        self.fr = fakeredis.FakeRedis()
        from database.webhook_health import _DEV_RECORD_FAILURE_LUA, _HEALTH_TTL, _DEV_FAILURE_THRESHOLD

        self.script = self.fr.register_script(_DEV_RECORD_FAILURE_LUA)
        self.ttl = _HEALTH_TTL
        self.threshold = _DEV_FAILURE_THRESHOLD

    def _run(self, uid, wtype, now_ts, status, error):
        key = f'dev_webhook_health:{uid}:{wtype}'
        return int(self.script(keys=[key], args=[now_ts, str(status), error[:200], self.ttl, self.threshold]))

    def test_below_threshold_no_disable(self):
        for i in range(99):
            assert self._run("uid-1", "memory_created", 1000 + i, 500, "err") == 0

    def test_at_threshold_disables(self):
        for i in range(99):
            self._run("uid-2", "memory_created", 1000 + i, 500, "err")
        assert self._run("uid-2", "memory_created", 2000, 500, "err") == 1
        val = self.fr.hget('dev_webhook_health:uid-2:memory_created', 'disabled')
        assert val == b'1'

    def test_already_disabled_returns_0(self):
        for i in range(100):
            self._run("uid-3", "memory_created", 1000 + i, 500, "err")
        assert self._run("uid-3", "memory_created", 2000, 500, "err") == 0

    def test_success_reset_then_fail_again(self):
        for i in range(50):
            self._run("uid-4", "realtime_transcript", 1000 + i, 500, "err")
        key = 'dev_webhook_health:uid-4:realtime_transcript'
        self.fr.hset(key, mapping={'failure_count': '0', 'disabled': '0'})
        for i in range(99):
            self._run("uid-4", "realtime_transcript", 2000 + i, 500, "err")
        assert self._run("uid-4", "realtime_transcript", 3000, 500, "err") == 1


class TestDevWebhookIntegrationPaths:
    """Test developer webhook health tracking integration in utils/webhooks.py."""

    @pytest.mark.asyncio
    async def test_conversation_created_records_success(self):
        from utils.webhooks import conversation_created_webhook

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        from database.webhook_health import record_dev_webhook_success

        with (
            patch("utils.webhooks.record_dev_webhook_success") as mock_success,
            patch("utils.webhooks.get_webhook_client", return_value=mock_client),
            patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb),
            patch("utils.webhooks.get_webhook_semaphore", return_value=AsyncMock()),
        ):
            mock_sem = AsyncMock()
            mock_sem.__aenter__ = AsyncMock()
            mock_sem.__aexit__ = AsyncMock()
            with patch("utils.webhooks.get_webhook_semaphore", return_value=mock_sem):
                mock_memory = MagicMock()
                mock_memory.is_locked = False
                with (
                    patch("utils.webhooks.conversation_to_dict", return_value={}),
                    patch("utils.webhooks.populate_speaker_names"),
                    patch("utils.webhooks.populate_folder_names"),
                ):
                    await conversation_created_webhook("uid-1", mock_memory)
        mock_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversation_created_records_failure(self):
        from utils.webhooks import conversation_created_webhook

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        mock_sem = AsyncMock()
        mock_sem.__aenter__ = AsyncMock()
        mock_sem.__aexit__ = AsyncMock()

        with (
            patch("utils.webhooks.record_dev_webhook_failure", return_value=False) as mock_fail,
            patch("utils.webhooks.get_webhook_client", return_value=mock_client),
            patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb),
            patch("utils.webhooks.get_webhook_semaphore", return_value=mock_sem),
        ):
            mock_memory = MagicMock()
            mock_memory.is_locked = False
            with (
                patch("utils.webhooks.conversation_to_dict", return_value={}),
                patch("utils.webhooks.populate_speaker_names"),
                patch("utils.webhooks.populate_folder_names"),
            ):
                await conversation_created_webhook("uid-1", mock_memory)
        mock_fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_conversation_created_auto_disables(self):
        """Auto-disable should trigger when failure threshold exceeded."""
        from utils.webhooks import conversation_created_webhook

        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        mock_sem = AsyncMock()
        mock_sem.__aenter__ = AsyncMock()
        mock_sem.__aexit__ = AsyncMock()

        with (
            patch("utils.webhooks.record_dev_webhook_failure", return_value=True) as mock_fail,
            patch("utils.webhooks.disable_user_webhook_db") as mock_disable,
            patch("utils.webhooks.send_notification") as mock_notify,
            patch("utils.webhooks.get_webhook_client", return_value=mock_client),
            patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb),
            patch("utils.webhooks.get_webhook_semaphore", return_value=mock_sem),
        ):
            mock_memory = MagicMock()
            mock_memory.is_locked = False
            with (
                patch("utils.webhooks.conversation_to_dict", return_value={}),
                patch("utils.webhooks.populate_speaker_names"),
                patch("utils.webhooks.populate_folder_names"),
            ):
                await conversation_created_webhook("uid-1", mock_memory)
        mock_disable.assert_called_once()
        mock_notify.assert_called_once()
