"""Mock utils.app_integrations — slow stubs to create backpressure."""

import asyncio


async def trigger_realtime_integrations(uid, segments, memory_id):
    """Slow consumer — creates transcript queue backpressure."""
    await asyncio.sleep(0.5)


async def trigger_realtime_audio_bytes(uid, sample_rate, data):
    """Slow consumer — creates audio bytes queue backpressure."""
    await asyncio.sleep(1.0)


async def trigger_external_integrations(uid, conversation):
    """Slow — keeps _process_conversation_task alive longer."""
    await asyncio.sleep(2.0)
    return []
