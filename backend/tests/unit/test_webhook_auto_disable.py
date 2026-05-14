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


def _load_app_tools_module():
    """Load app_tools module directly, bypassing __init__.py which pulls in heavy deps."""
    _db_redis_mod = sys.modules.get("database.redis_db")
    if _db_redis_mod and not hasattr(_db_redis_mod, 'get_cached_user_geolocation'):
        _db_redis_mod.get_cached_user_geolocation = MagicMock(return_value=None)
    for mod_name in ["utils.mcp_client", "utils.log_sanitizer", "utils.retrieval", "utils.retrieval.agentic"]:
        sys.modules.setdefault(mod_name, MagicMock())
    if "utils.retrieval" in sys.modules:
        sys.modules["utils.retrieval"].__path__ = []
    if "utils.retrieval.tools.app_tools" in sys.modules:
        return sys.modules["utils.retrieval.tools.app_tools"]
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
        """After 72h of failures, should return 3 (auto-disable)."""
        from database.webhook_health import record_app_webhook_failure

        mock_script = MagicMock(return_value=3)
        with patch("database.webhook_health._get_failure_script", return_value=mock_script):
            result = record_app_webhook_failure("app-1", 500, "Internal Server Error")
        assert result == 3

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
    """Test that success resets all failure state."""

    def test_success_resets_state(self):
        """record_app_webhook_success should call hset with zeroed failure fields."""
        from database.webhook_health import record_app_webhook_success

        mock_r = MagicMock()
        with patch("database.webhook_health.r", mock_r):
            record_app_webhook_success("app-1")

        mock_r.hset.assert_called_once()
        call_kwargs = mock_r.hset.call_args
        mapping = call_kwargs.kwargs.get('mapping') or call_kwargs[1].get('mapping')
        assert mapping['failure_count'] == '0'
        assert mapping['disabled'] == '0'
        assert mapping['notified_day1'] == '0'
        assert mapping['notified_day2'] == '0'

    def test_success_redis_error_does_not_raise(self):
        """Redis errors during success recording should be swallowed."""
        from database.webhook_health import record_app_webhook_success

        mock_r = MagicMock()
        mock_r.hset.side_effect = Exception("Redis down")
        with patch("database.webhook_health.r", mock_r):
            record_app_webhook_success("app-1")


class TestIsAppWebhookDisabled:
    """Test the disabled check function."""

    def test_disabled_returns_true(self):
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.hget.return_value = b'1'
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is True

    def test_not_disabled_returns_false(self):
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.hget.return_value = b'0'
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is False

    def test_no_data_returns_false(self):
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.hget.return_value = None
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is False

    def test_redis_error_returns_false(self):
        """Redis errors should fail open (not disabled)."""
        from database.webhook_health import is_app_webhook_disabled

        mock_r = MagicMock()
        mock_r.hget.side_effect = Exception("Redis timeout")
        with patch("database.webhook_health.r", mock_r):
            assert is_app_webhook_disabled("app-1") is False


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

    def test_success_resets_failure_count(self):
        from database.webhook_health import record_dev_webhook_success

        mock_r = MagicMock()
        with patch("database.webhook_health.r", mock_r):
            record_dev_webhook_success("uid-1", "memory_created")

        mock_r.hset.assert_called_once()
        call_kwargs = mock_r.hset.call_args
        mapping = call_kwargs.kwargs.get('mapping') or call_kwargs[1].get('mapping')
        assert mapping['failure_count'] == '0'


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
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_fail.assert_called_once()
            mock_disable.assert_called_once()

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
        mock_r.hgetall.return_value = {
            b'failure_count': b'5',
            b'last_status': b'500',
            b'disabled': b'0',
        }
        with patch("database.webhook_health.r", mock_r):
            result = get_app_webhook_health("app-1")
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
        mock_success.assert_called_once_with("app-1")

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
        mock_fail.assert_called_once_with("app-1", 500, "HTTP 500")

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
        mock_fail.assert_called_once_with("app-1", 0, "TimeoutException")
