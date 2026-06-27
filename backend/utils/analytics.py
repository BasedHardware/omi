from datetime import datetime
from typing import Optional

from database import user_usage as user_usage_db


def billable_transcription_seconds(
    last_usage_record_timestamp: Optional[float],
    last_audio_received_time: Optional[float],
    current_time: float,
) -> int:
    """Listening seconds to bill since the last usage record, clamped to the last
    audio byte actually received (#4700).

    Client keepalive pings hold the /v4/listen socket open long after the device
    stops sending audio; counting raw wall-clock time then accrues phantom
    listening minutes for hours. No audio streamed also means no STT vendor cost,
    so idle socket time must not be billed.
    """
    if not last_usage_record_timestamp:
        return 0
    billable_until = min(current_time, last_audio_received_time or current_time)
    return max(0, int(billable_until - last_usage_record_timestamp))


def record_usage(
    uid: str,
    transcription_seconds: int = 0,
    words_transcribed: int = 0,
    insights_gained: int = 0,
    memories_created: int = 0,
    speech_seconds: int = 0,
):
    """Records hourly usage stats for a user."""
    now = datetime.utcnow()
    updates = {
        'transcription_seconds': transcription_seconds,
        'words_transcribed': words_transcribed,
        'insights_gained': insights_gained,
        'memories_created': memories_created,
        'speech_seconds': speech_seconds,
    }
    user_usage_db.update_hourly_usage(uid, now, updates)
