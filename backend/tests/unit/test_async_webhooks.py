"""Tests for async webhook delivery (issue #6369 Phase 1).

Verifies that realtime_transcript_webhook and send_audio_bytes_developer_webhook
use httpx.AsyncClient instead of blocking requests.post.
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
