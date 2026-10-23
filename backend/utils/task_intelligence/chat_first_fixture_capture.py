"""Conversation payload for the fixed local/offline Chat-first fixture accounts."""

from datetime import datetime, timedelta
from typing import Any

from utils.conversations.terminal_relevance import stamp_terminal_decision


def capture_payload(*, capture_id: str, now: datetime) -> dict[str, Any]:
    """The smallest persisted Omi capture shape accepted by the existing archive."""

    payload = {
        'id': capture_id,
        'source': 'omi',
        'status': 'completed',
        'discarded': False,
        'created_at': now,
        'started_at': now - timedelta(minutes=20),
        'finished_at': now - timedelta(minutes=5),
        'structured': {'title': 'E2E fixture capture'},
        'transcript_segments': [],
        'data_protection_level': 'standard',
    }
    stamp_terminal_decision(payload, path='fixture_seed')
    return payload
