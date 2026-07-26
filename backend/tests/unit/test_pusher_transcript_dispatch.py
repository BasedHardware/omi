from unittest.mock import AsyncMock, patch

import pytest

from routers.pusher import _dispatch_transcript_item


@pytest.mark.asyncio
async def test_webhook_runs_when_realtime_integration_fails():
    segments = [{"id": "segment-1", "text": "hello"}]
    with patch(
        "routers.pusher.trigger_realtime_integrations",
        AsyncMock(side_effect=RuntimeError("integration failed")),
    ) as integration, patch("routers.pusher.realtime_transcript_webhook", AsyncMock()) as webhook:
        await _dispatch_transcript_item("uid-1", segments, "conversation-1")

    integration.assert_awaited_once_with("uid-1", segments, "conversation-1")
    webhook.assert_awaited_once_with("uid-1", segments)
