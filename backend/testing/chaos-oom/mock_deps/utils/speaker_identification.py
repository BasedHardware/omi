"""Mock utils.speaker_identification — slow stub."""

import asyncio


async def extract_speaker_samples(uid, person_id, conversation_id, segment_ids, sample_rate):
    """Slow — keeps speaker sample tasks alive."""
    await asyncio.sleep(3.0)
