"""Pure fields for a published person voice sample, independent of transaction machinery."""

from datetime import datetime, timezone
from typing import Optional

__all__ = ['project_person_learning', 'speech_sample_source', 'voice_learning_fields']


def project_person_learning(*args, **kwargs):
    # Deferred: database.users imports this module, and unit harnesses that stub the
    # models/database tree import database.users without the job ledger's dependencies.
    from database.speaker_learning_jobs import project_person_learning as project

    return project(*args, **kwargs)


def speech_sample_source(conversation_id: str, segment_ids: list, generation: Optional[int]) -> dict:
    return {
        'conversation_id': conversation_id,
        'segment_ids': segment_ids,
        'generation': generation,
        'stored_at': datetime.now(timezone.utc),
    }


def voice_learning_fields(state: str, outcome: str, speech_seconds: Optional[float]) -> dict:
    return {
        'voice_learning_state': state,
        'voice_learning_outcome': outcome,
        'voice_speech_seconds': speech_seconds,
        'voice_needed_seconds': None,
    }
