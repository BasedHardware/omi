"""Mock utils.webhooks — slow stubs for backpressure."""

import asyncio


async def send_audio_bytes_developer_webhook(uid, sample_rate, data):
    await asyncio.sleep(0.5)


async def realtime_transcript_webhook(uid, segments):
    await asyncio.sleep(0.3)


def get_audio_bytes_webhook_seconds(uid):
    """Return a short delay so audio bytes webhook path is exercised."""
    return 2
