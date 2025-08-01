from datetime import datetime
from database import user_usage as user_usage_db


def record_usage(
    uid: str,
    transcription_seconds: int = 0,
    words_transcribed: int = 0,
    words_summarized: int = 0,
    memories_created: int = 0,
):
    """Records hourly usage stats for a user."""
    now = datetime.utcnow()
    updates = {
        'transcription_seconds': transcription_seconds,
        'words_transcribed': words_transcribed,
        'words_summarized': words_summarized,
        'memories_created': memories_created,
    }
    user_usage_db.update_hourly_usage(uid, now, updates)
