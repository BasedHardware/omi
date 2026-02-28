"""Mock utils.webhooks — slow stubs for backpressure."""

import asyncio


async def send_audio_bytes_developer_webhook(uid, sample_rate, data):
    await asyncio.sleep(0.5)


async def realtime_transcript_webhook(uid, segments):
    await asyncio.sleep(0.3)


def get_audio_bytes_webhook_seconds(uid):
    """Disable audio bytes webhook path for audiobuffer leak repro."""
    return 0
