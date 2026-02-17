"""Mock utils.other.storage — slow upload stub for private cloud queue backpressure."""

import time


def upload_audio_chunk(chunk_data, uid, conversation_id, timestamp):
    """Slow — blocks private_cloud_queue consumer so queue grows."""
    time.sleep(2.0)
