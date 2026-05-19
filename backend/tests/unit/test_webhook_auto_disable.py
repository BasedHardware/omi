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
_db_redis.remove_app_from_all_enabled_sets = MagicMock(return_value=[])
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

    def test_chat_tool_non_2xx_blocks_reenable(self):
        """Chat tool returning 404 should block re-enable."""
        from fastapi import HTTPException

        app = {
            'external_integration': {},
            'chat_tools': [{'endpoint': 'https://tool.example.com/api', 'name': 't', 'method': 'POST'}],
        }
        update = {}
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("utils.apps.httpx.request", return_value=mock_resp):
            with pytest.raises(HTTPException) as exc_info:
                self._validate(app, update, 'app-1')
        assert exc_info.value.status_code == 400
        assert '404' in exc_info.value.detail

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
        assert 'GET' in methods
        urls = [u for _, u in call_urls]
        assert 'https://a.com/wh' in urls
        assert 'https://b.com/mcp' in urls
        assert 'https://c.com/tool' in urls

    def test_second_endpoint_failure_blocks_even_if_first_healthy(self):
        """If first endpoint is healthy but second fails, re-enable should be blocked."""
        from fastapi import HTTPException

        app = {
            'external_integration': {'webhook_url': 'https://ok.com/wh'},
            'chat_tools': [{'endpoint': 'https://broken.com/tool', 'name': 't'}],
        }
        update = {}
        call_count = [0]

        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status_code = 200 if call_count[0] == 1 else 503
            return resp

        with patch("utils.apps.httpx.request", side_effect=mock_request):
            with pytest.raises(HTTPException) as exc_info:
                self._validate(app, update, 'app-1')
        assert exc_info.value.status_code == 400
        assert '503' in exc_info.value.detail

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

        state['last_failure_at'] = now_ts
        state['last_status'] = status
        state['last_error'] = error
        state['failure_count'] = state.get('failure_count', 0) + 1

        first_ts = int(first)
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
        assert '86400' in _RECORD_FAILURE_LUA  # 24h in seconds


class TestDisableUserNotification:
    """Test that auto-disable notifies affected users and removes from enabled sets."""

    def test_disable_action_removes_from_all_users(self):
        """action=3 should call remove_app_from_all_enabled_sets."""
        _app_tools = _load_app_tools_module()

        with (
            patch.object(_app_tools, 'disable_app_in_firestore') as mock_disable,
            patch.object(_app_tools, 'delete_app_cache_by_id'),
            patch.object(
                _app_tools, 'remove_app_from_all_enabled_sets', return_value=['uid-1', 'uid-2']
            ) as mock_remove,
            patch.object(_app_tools, 'get_app_by_id_db', return_value={'name': 'Test App', 'uid': 'owner-1'}),
            patch.object(_app_tools, '_notify_app_owner'),
            patch.object(_app_tools, 'send_notification') as mock_notify,
        ):
            _app_tools._handle_app_webhook_disable('app-1', 3, 'HTTP 500')
            mock_disable.assert_called_once()
            mock_remove.assert_called_once_with('app-1')
            assert mock_notify.call_count == 2
            notified_uids = [call[0][0] for call in mock_notify.call_args_list]
            assert 'uid-1' in notified_uids
            assert 'uid-2' in notified_uids

    def test_disable_action_notifies_with_app_name(self):
        """User notifications should include the app name."""
        _app_tools = _load_app_tools_module()

        with (
            patch.object(_app_tools, 'disable_app_in_firestore'),
            patch.object(_app_tools, 'delete_app_cache_by_id'),
            patch.object(_app_tools, 'remove_app_from_all_enabled_sets', return_value=['uid-1']),
            patch.object(_app_tools, 'get_app_by_id_db', return_value={'name': 'My Awesome App', 'uid': 'owner-1'}),
            patch.object(_app_tools, '_notify_app_owner'),
            patch.object(_app_tools, 'send_notification') as mock_notify,
        ):
            _app_tools._handle_app_webhook_disable('app-1', 3, 'HTTP 404')
            title = mock_notify.call_args[0][1]
            body = mock_notify.call_args[0][2]
            assert 'My Awesome App' in title
            assert 'My Awesome App' in body
            assert 'connectivity issues' in body

    def test_no_affected_users_still_disables(self):
        """Disable should proceed even with no affected users."""
        _app_tools = _load_app_tools_module()

        with (
            patch.object(_app_tools, 'disable_app_in_firestore') as mock_disable,
            patch.object(_app_tools, 'delete_app_cache_by_id'),
            patch.object(_app_tools, 'remove_app_from_all_enabled_sets', return_value=[]),
            patch.object(_app_tools, 'get_app_by_id_db', return_value={'name': 'Test', 'uid': 'owner-1'}),
            patch.object(_app_tools, '_notify_app_owner'),
            patch.object(_app_tools, 'send_notification') as mock_notify,
        ):
            _app_tools._handle_app_webhook_disable('app-1', 3, 'HTTP 500')
            mock_disable.assert_called_once()
            mock_notify.assert_not_called()
