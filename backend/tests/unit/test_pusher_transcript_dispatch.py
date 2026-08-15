import asyncio
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


@pytest.mark.asyncio
async def test_webhook_starts_while_realtime_integration_is_blocked():
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked_integration(*args):
        started.set()
        await release.wait()

    webhook = AsyncMock()
    segments = [{"id": "segment-1", "text": "hello"}]
    with patch("routers.pusher.trigger_realtime_integrations", blocked_integration), patch(
        "routers.pusher.realtime_transcript_webhook", webhook
    ):
        task = asyncio.create_task(_dispatch_transcript_item("uid-1", segments, "conversation-1"))
        await started.wait()
        await asyncio.sleep(0)
        webhook.assert_awaited_once_with("uid-1", segments)
        release.set()
        await task
