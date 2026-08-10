"""Tests for async webhook delivery (issue #6369 Phase 1).

Verifies that realtime_transcript_webhook and send_audio_bytes_developer_webhook
use httpx.AsyncClient instead of blocking requests.post.
"""

import ast
import asyncio
import os
import re
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

import database.redis_db as redis_db_module
import utils.webhooks as webhooks_module
from models.users import WebhookType
from utils.webhooks import realtime_transcript_webhook, send_audio_bytes_developer_webhook, day_summary_webhook


@pytest.fixture(autouse=True)
def _stub_webhook_db_helpers(monkeypatch):
    """Hermetic defaults for the DB-interfacing names ``utils.webhooks`` binds.

    Replaces the former module-scope ``sys.modules`` stubs of ``database.redis_db``
    etc. Individual tests override specific names via ``with patch(...)`` as needed.
    """
    monkeypatch.setattr(webhooks_module, "user_webhook_status_db", MagicMock(return_value=True))
    redis_helpers = MagicMock()
    redis_helpers.try_acquire_audio_bytes_webhook_lock = MagicMock(return_value="lock-token")
    redis_helpers.release_audio_bytes_webhook_lock = MagicMock()
    monkeypatch.setattr(webhooks_module, "redis_db", redis_helpers)
    monkeypatch.setattr(webhooks_module, "get_user_webhook_db", MagicMock(return_value="https://example.com/webhook"))
    monkeypatch.setattr(webhooks_module, "disable_user_webhook_db", MagicMock())
    monkeypatch.setattr(webhooks_module, "enable_user_webhook_db", MagicMock())
    monkeypatch.setattr(webhooks_module, "set_user_webhook_db", MagicMock())
    monkeypatch.setattr(webhooks_module, "record_dev_webhook_success", MagicMock())
    monkeypatch.setattr(webhooks_module, "record_dev_webhook_failure", MagicMock(return_value=False))


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

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client), patch(
            "utils.webhooks._get_dev_webhook_retry_delays", return_value=()
        ):
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
    async def test_bytearray_converted_to_bytes_at_call_site(self):
        """Verify bytearray is converted to bytes inline at httpx call (required by httpx 0.28)."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\xab\xcd'))

        call_args = mock_client.post.call_args
        sent_content = call_args.kwargs.get("content")
        assert isinstance(sent_content, bytes)
        assert sent_content == b'\xab\xcd'

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

    @pytest.mark.asyncio
    async def test_contention_skips_delivery_while_first_request_is_in_flight(self):
        first_post_started = asyncio.Event()
        allow_first_post_to_finish = asyncio.Event()
        mock_response = MagicMock(status_code=200)

        async def post(*_args, **_kwargs):
            first_post_started.set()
            await allow_first_post_to_finish.wait()
            return mock_response

        mock_client = AsyncMock()
        mock_client.post.side_effect = post
        lock = MagicMock(side_effect=["first-token", None])

        with patch.object(webhooks_module.redis_db, "try_acquire_audio_bytes_webhook_lock", lock), patch.object(
            webhooks_module,
            "get_webhook_circuit_breaker",
            return_value=MagicMock(allow_request=MagicMock(return_value=True)),
        ), patch.object(webhooks_module, "get_webhook_client", return_value=mock_client):
            first_delivery = asyncio.create_task(
                send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00' * 100))
            )
            await first_post_started.wait()
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00' * 100))
            allow_first_post_to_finish.set()
            await first_delivery

        assert mock_client.post.call_count == 1
        webhooks_module.redis_db.release_audio_bytes_webhook_lock.assert_called_once_with("uid-1", "first-token")

    @pytest.mark.asyncio
    async def test_invalid_url_releases_lock_without_delivery(self):
        mock_client = AsyncMock()

        with patch.object(
            webhooks_module, "get_user_webhook_db", return_value="ftp://example.com/audio,10"
        ), patch.object(webhooks_module, "get_webhook_client", return_value=mock_client):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00'))

        mock_client.post.assert_not_called()
        webhooks_module.redis_db.release_audio_bytes_webhook_lock.assert_called_once_with("uid-1", "lock-token")

    @pytest.mark.asyncio
    async def test_configured_duration_controls_payload_truncation(self):
        mock_response = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            webhooks_module, "get_user_webhook_db", return_value="https://example.com/audio,10"
        ), patch.object(
            webhooks_module,
            "get_webhook_circuit_breaker",
            return_value=MagicMock(allow_request=MagicMock(return_value=True)),
        ), patch.object(
            webhooks_module, "get_webhook_client", return_value=mock_client
        ):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00' * (8000 * 2 * 15)))

        sent_content = mock_client.post.call_args.kwargs["content"]
        assert len(sent_content) == 8000 * 2 * 10

    @pytest.mark.asyncio
    async def test_delivery_failure_records_failure_and_releases_lock(self):
        mock_cb = MagicMock()
        mock_cb.allow_request.return_value = True
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=RuntimeError("delivery failed"))

        with patch.object(webhooks_module, "get_webhook_circuit_breaker", return_value=mock_cb), patch.object(
            webhooks_module, "get_webhook_client", return_value=mock_client
        ), patch.object(webhooks_module, "_get_dev_webhook_retry_delays", return_value=()):
            await send_audio_bytes_developer_webhook("uid-1", 8000, bytearray(b'\x00'))

        mock_cb.record_failure.assert_called_once()
        webhooks_module.record_dev_webhook_failure.assert_called_once_with(
            "uid-1", webhooks_module.WebhookType.audio_bytes, 0, "RuntimeError"
        )
        webhooks_module.redis_db.release_audio_bytes_webhook_lock.assert_called_once_with("uid-1", "lock-token")


class TestAudioBytesWebhookRedisLock:
    def test_redis_outage_preserves_fail_open_delivery_decision(self, monkeypatch):
        mock_redis = MagicMock()
        mock_redis.set.side_effect = ConnectionError("redis unavailable")
        monkeypatch.setattr(redis_db_module, "r", mock_redis)

        token = redis_db_module.try_acquire_audio_bytes_webhook_lock("uid-1", ttl=181)

        assert token
        mock_redis.set.assert_called_once_with("users:uid-1:audio_bytes_webhook_lock", token, ex=181, nx=True)

    def test_release_only_deletes_matching_lock_token(self, monkeypatch):
        mock_redis = MagicMock()
        monkeypatch.setattr(redis_db_module, "r", mock_redis)

        redis_db_module.release_audio_bytes_webhook_lock("uid-1", "lock-token")

        script, key_count, key, token = mock_redis.eval.call_args.args
        assert key_count == 1
        assert key == "users:uid-1:audio_bytes_webhook_lock"
        assert token == "lock-token"
        assert "redis.call('get', KEYS[1]) == ARGV[1]" in script

    def test_release_redis_failure_is_best_effort(self, monkeypatch):
        mock_redis = MagicMock()
        mock_redis.eval.side_effect = [ConnectionError("redis unavailable"), 1]
        monkeypatch.setattr(redis_db_module, "r", mock_redis)

        redis_db_module.release_audio_bytes_webhook_lock("uid-1", "lock-token")
        assert mock_redis.eval.call_count == 2


class TestConversationAndSummaryWebhooksStructural:
    """AST-based structural tests for conversation_created_webhook and day_summary_webhook.

    These were migrated from blocking requests to async httpx. Verify the migration
    is in place and uses httpx (not requests) without importing the module at the
    class level (to avoid heavy transitive deps).
    """

    @staticmethod
    def _read_webhooks_source() -> str:
        webhooks_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'webhooks.py')
        with open(webhooks_path, encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def _parse_webhooks_ast():
        webhooks_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'webhooks.py')
        with open(webhooks_path, encoding='utf-8') as f:
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
        assert '_post_dev_webhook(' in func_body, "conversation_created_webhook must use the async webhook helper"
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
        assert '_post_dev_webhook(' in func_body, "day_summary_webhook must use the async webhook helper"
        assert (
            'requests.post' not in func_body
        ), "day_summary_webhook must not use blocking requests.post — use httpx.AsyncClient"


class TestDaySummaryWebhookJsonField:
    """Verify the new ``summary_json`` field is sent alongside the legacy ``summary`` string.

    The wire format keeps ``summary`` as a Python ``repr`` string for backward
    compatibility (existing receivers depend on it). The new ``summary_json``
    field carries the exact same payload as a real JSON object so receivers can
    migrate off ``ast.literal_eval``-style parsing. These tests pin both
    behaviours to prevent silent regressions in either direction.
    """

    _SAMPLE_SUMMARY_JSON = {
        "id": "summary-abc",
        "date": "2024-01-15",
        "headline": "Productive day with three meetings",
        "overview": "You had a productive day focused on project planning.",
        "day_emoji": "💼",
        "stats": {"total_conversations": 3, "total_duration_minutes": 120, "action_items_count": 1},
        "highlights": [],
        "action_items": [],
        "unresolved_questions": [],
        "decisions_made": [],
        "knowledge_nuggets": [],
        "locations": [],
    }

    @pytest.mark.asyncio
    async def test_payload_includes_summary_json_as_dict_and_keeps_legacy_summary(self):
        """Both legacy ``summary`` (str) and new ``summary_json`` (dict) must travel together."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        legacy_summary_str = str(self._SAMPLE_SUMMARY_JSON)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client):
            await day_summary_webhook("uid-1", legacy_summary_str, self._SAMPLE_SUMMARY_JSON)

        mock_client.post.assert_called_once()
        payload = mock_client.post.call_args.kwargs["json"]

        assert isinstance(
            payload["summary_json"], dict
        ), f"summary_json must be a JSON object, got {type(payload['summary_json'])}: {payload['summary_json']!r}"
        assert payload["summary_json"]["headline"] == "Productive day with three meetings"

        assert isinstance(payload["summary"], str), "legacy summary must remain a string for backward compatibility"
        assert payload["summary"] == legacy_summary_str

        assert payload["uid"] == "uid-1"
        assert payload["created_at"].endswith("+00:00")

    @pytest.mark.asyncio
    async def test_summary_json_defaults_to_none_when_not_supplied(self):
        """Callers that haven't migrated yet still get a well-formed payload (summary_json: null)."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("utils.webhooks.get_webhook_client", return_value=mock_client):
            await day_summary_webhook("uid-1", "{'legacy': 'repr'}")

        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["summary_json"] is None
        assert payload["summary"] == "{'legacy': 'repr'}"


class TestSendSummaryNotificationWiresSummaryJson:
    """Static guard that ``_send_summary_notification`` passes the dict as ``summary_json``.

    Avoids importing notifications.py (which pulls in Firestore / LLM / pytz) by
    grepping the source. Mirrors the existing static-wiring tests in
    test_async_http_infrastructure.py.
    """

    def test_notifications_passes_summary_data_as_summary_json(self):
        path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'other', 'notifications.py')
        with open(path, encoding='utf-8') as f:
            src = f.read()

        assert 'day_summary_webhook(uid, str(summary_data), summary_data)' in src, (
            "_send_summary_notification must pass summary_data (dict) as the summary_json arg of day_summary_webhook "
            "so receivers get a real JSON object alongside the legacy repr string."
        )


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
        ), patch("utils.webhooks._get_dev_webhook_retry_delays", return_value=()):
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


class TestWebhookFirstTimeSetup:
    """#11365: a stored setting with no endpoint must not toggle the webhook on."""

    def test_audio_bytes_delay_only_setting_stays_disabled(self):
        """'<url>,<seconds>' with the URL cleared has nowhere to deliver to."""
        with patch.object(webhooks_module, "get_user_webhook_db", return_value=",5"):
            assert webhooks_module.webhook_first_time_setup("uid-1", WebhookType.audio_bytes) is False
            webhooks_module.disable_user_webhook_db.assert_called_once_with("uid-1", WebhookType.audio_bytes)
            webhooks_module.enable_user_webhook_db.assert_not_called()

    def test_configured_audio_bytes_setting_enables(self):
        with patch.object(webhooks_module, "get_user_webhook_db", return_value="https://example.com/audio,5"):
            assert webhooks_module.webhook_first_time_setup("uid-1", WebhookType.audio_bytes) is True
            webhooks_module.enable_user_webhook_db.assert_called_once_with("uid-1", WebhookType.audio_bytes)

    def test_blank_url_stays_disabled(self):
        with patch.object(webhooks_module, "get_user_webhook_db", return_value="   "):
            assert webhooks_module.webhook_first_time_setup("uid-1", WebhookType.memory_created) is False
            webhooks_module.disable_user_webhook_db.assert_called_once_with("uid-1", WebhookType.memory_created)
