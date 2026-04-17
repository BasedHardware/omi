"""Tests for async webhook delivery (issue #6369 Phase 1).

Verifies that realtime_transcript_webhook and send_audio_bytes_developer_webhook
use httpx.AsyncClient instead of blocking requests.post.
"""

import ast
import os
import re
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
_db_redis = types.ModuleType("database.redis_db")
sys.modules["database.redis_db"] = _db_redis
_db_redis.get_user_webhook_db = MagicMock(return_value="https://example.com/webhook")
_db_redis.user_webhook_status_db = MagicMock(return_value=True)
_db_redis.disable_user_webhook_db = MagicMock()
_db_redis.enable_user_webhook_db = MagicMock()
_db_redis.set_user_webhook_db = MagicMock()

for mod_name in ["database", "database.notifications", "database.users"]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)
        if mod_name == "database":
            sys.modules[mod_name].__path__ = []

sys.modules["database.notifications"].get_token_only = MagicMock(return_value=None)
sys.modules["database.users"].get_user_profile = MagicMock(return_value={"name": "Test"})
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])

if "utils.notifications" not in sys.modules:
    sys.modules["utils.notifications"] = types.ModuleType("utils.notifications")
sys.modules["utils.notifications"].send_notification = MagicMock()

from utils.webhooks import realtime_transcript_webhook, send_audio_bytes_developer_webhook


class TestRealtimeTranscriptWebhook:
    """Test realtime_transcript_webhook uses httpx async."""

    @pytest.mark.asyncio
    async def test_success_sends_via_httpx(self):
        """Verify webhook uses httpx.AsyncClient.post, not requests.post."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "segments" in call_args.kwargs.get("json", {})

    @pytest.mark.asyncio
    async def test_notification_on_200_with_message(self):
        """Verify webhook notification sent when response has message > 5 chars."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Important alert here"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client), patch(
            "utils.webhooks.send_webhook_notification"
        ) as mock_notify:
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_notify.assert_called_once_with("uid-1", "Important alert here")

    @pytest.mark.asyncio
    async def test_no_notification_on_short_message(self):
        """Verify no notification for messages <= 5 chars."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "hi"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client), patch(
            "utils.webhooks.send_webhook_notification"
        ) as mock_notify:
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_webhook_skips(self):
        """Verify disabled webhook returns early without HTTP call."""
        mock_client = AsyncMock()

        with patch("utils.webhooks.user_webhook_status_db", return_value=False), patch(
            "utils.webhooks.get_webhook_client", return_value=mock_client
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_error_handled(self):
        """Verify httpx timeout is caught and logged."""
        import httpx

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("connect timeout"))

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client):
            # Should not raise
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])


class TestSendAudioBytesDeveloperWebhook:
    """Test send_audio_bytes_developer_webhook uses httpx async."""

    @pytest.mark.asyncio
    async def test_success_sends_via_httpx(self):
        """Verify audio bytes webhook uses httpx.AsyncClient.post."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00' * 100))

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args.kwargs.get("headers", {}).get("Content-Type") == "application/octet-stream"

    @pytest.mark.asyncio
    async def test_bytearray_converted_to_bytes(self):
        """Verify bytearray is converted to immutable bytes before sending."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\xab\xcd'))

        call_args = mock_client.post.call_args
        sent_content = call_args.kwargs.get("content")
        assert isinstance(sent_content, bytes)

    @pytest.mark.asyncio
    async def test_url_comma_parsing(self):
        """Verify url,seconds format is parsed correctly — seconds stripped, only URL used."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_user_webhook_db", return_value="https://example.com/audio,10"), patch(
            "utils.webhooks.get_webhook_client", return_value=mock_client
        ):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00'))

        call_url = mock_client.post.call_args[0][0]
        assert "https://example.com/audio" in call_url
        assert ",10" not in call_url

    @pytest.mark.asyncio
    async def test_disabled_webhook_skips(self):
        """Verify disabled webhook returns early."""
        mock_client = AsyncMock()

        with patch("utils.webhooks.user_webhook_status_db", return_value=False), patch(
            "utils.webhooks.get_webhook_client", return_value=mock_client
        ):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00'))
            mock_client.post.assert_not_called()


class TestConversationAndSummaryWebhooksStructural:
    """AST-based structural tests for conversation_created_webhook and day_summary_webhook.

    These were migrated from blocking requests to async httpx. Verify the migration
    is in place and uses httpx (not requests) without importing the module at the
    class level (to avoid heavy transitive deps).
    """

    @staticmethod
    def _read_webhooks_source() -> str:
        webhooks_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'webhooks.py')
        with open(webhooks_path) as f:
            return f.read()

    @staticmethod
    def _parse_webhooks_ast():
        webhooks_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'webhooks.py')
        with open(webhooks_path) as f:
            return ast.parse(f.read())

    def test_conversation_created_webhook_is_async(self):
        """conversation_created_webhook must be defined as an async function."""
        tree = self._parse_webhooks_ast()
        async_funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
        assert (
            'conversation_created_webhook' in async_funcs
        ), "conversation_created_webhook must be async — it was migrated from blocking requests to httpx"

    def test_day_summary_webhook_is_async(self):
        """day_summary_webhook must be defined as an async function."""
        tree = self._parse_webhooks_ast()
        async_funcs = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
        assert (
            'day_summary_webhook' in async_funcs
        ), "day_summary_webhook must be async — it was migrated from blocking requests to httpx"

    def test_webhooks_does_not_import_requests(self):
        """utils/webhooks.py must not import the blocking requests library."""
        source = self._read_webhooks_source()
        # Allow 'requests' only as part of another name (e.g. 'allow_request')
        bare_import = re.search(r'^import requests\b', source, re.MULTILINE)
        from_import = re.search(r'^from requests\b', source, re.MULTILINE)
        assert (
            bare_import is None and from_import is None
        ), "utils/webhooks.py must not import the blocking 'requests' library — use httpx.AsyncClient"

    def test_webhooks_uses_httpx_client(self):
        """utils/webhooks.py must use the shared httpx client (get_webhook_client)."""
        source = self._read_webhooks_source()
        assert (
            'get_webhook_client' in source
        ), "webhooks.py must use get_webhook_client() (shared httpx.AsyncClient) for HTTP calls"

    def test_conversation_created_webhook_uses_await_post(self):
        """conversation_created_webhook must await an async HTTP post, not call requests.post."""
        source = self._read_webhooks_source()
        start = source.index('async def conversation_created_webhook')
        # End at next top-level async def
        next_def = source.find('\nasync def ', start + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[start:next_def]

        assert 'await' in func_body, "conversation_created_webhook must use await for async HTTP call"
        assert '.post(' in func_body, "conversation_created_webhook must call .post() to send the payload"
        assert (
            'requests.post' not in func_body
        ), "conversation_created_webhook must not use blocking requests.post — use httpx.AsyncClient"

    def test_day_summary_webhook_uses_await_post(self):
        """day_summary_webhook must await an async HTTP post, not call requests.post."""
        source = self._read_webhooks_source()
        start = source.index('async def day_summary_webhook')
        next_def = source.find('\nasync def ', start + 1)
        if next_def == -1:
            next_def = len(source)
        func_body = source[start:next_def]

        assert 'await' in func_body, "day_summary_webhook must use await for async HTTP call"
        assert '.post(' in func_body, "day_summary_webhook must call .post() to send the payload"
        assert (
            'requests.post' not in func_body
        ), "day_summary_webhook must not use blocking requests.post — use httpx.AsyncClient"


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration in webhook functions."""

    @pytest.mark.asyncio
    async def test_transcript_webhook_skips_when_circuit_open(self):
        """realtime_transcript_webhook must skip HTTP call when circuit breaker is open."""
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = False

        mock_client = AsyncMock()

        with patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb), patch(
            "utils.webhooks.get_webhook_client", return_value=mock_client
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcript_webhook_records_success_on_200(self):
        """realtime_transcript_webhook must call record_success on successful HTTP call."""
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb), patch(
            "utils.webhooks.get_webhook_client", return_value=mock_client
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_cb.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_transcript_webhook_records_failure_on_exception(self):
        """realtime_transcript_webhook must call record_failure on HTTP exception."""
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        with patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb), patch(
            "utils.webhooks.get_webhook_client", return_value=mock_client
        ):
            await realtime_transcript_webhook("uid-1", [{"text": "hello"}])
            mock_cb.record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_audio_bytes_webhook_skips_when_circuit_open(self):
        """send_audio_bytes_developer_webhook must skip HTTP call when circuit breaker is open."""
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = False

        mock_client = AsyncMock()

        with patch("utils.webhooks.get_webhook_circuit_breaker", return_value=mock_cb), patch(
            "utils.webhooks.get_webhook_client", return_value=mock_client
        ):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00' * 100))
            mock_client.post.assert_not_called()
