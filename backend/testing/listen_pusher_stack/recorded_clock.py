"""Fixture operations on the recording clock of the isolated emulator stack."""

from datetime import datetime, timedelta, timezone

from utils.conversations.recorded_time import conversation_span


def age_conversation(client, uid: str, conversation_id: str) -> None:
    """Move the whole recording window into the past, preserving arrival metadata."""
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    row = ref.get().to_dict()
    span = conversation_span(row)
    if span is None:
        raise ValueError('cannot age a conversation without recorded evidence')
    end = datetime.now(timezone.utc) - timedelta(seconds=121)
    shift = end - span.recorded_end
    ref.update(
        {
            'started_at': row['started_at'] + shift,
            'recorded_start': span.recorded_start + shift,
            'recorded_end': end,
            'last_speech_at': end,
            'finished_at': end,
        }
    )
