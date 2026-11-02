"""Pure fields for a published person voice sample, independent of transaction machinery."""

from datetime import datetime, timezone
from typing import Optional
from database import speaker_auto_enroll
from utils.speakers import auto_enroll

__all__ = ['project_person_learning', 'speech_sample_source', 'voice_learning_fields']


def project_person_learning(*args, **kwargs):
    # Deferred: database.users imports this module, and unit harnesses that stub the
    # models/database tree import database.users without the job ledger's dependencies.
    from database.speaker_learning_jobs import project_person_learning as project

    data = project(*args, **kwargs)
    if data and data.get('speaker_auto_enroll_pool'):
        uid = args[0] if args else kwargs['uid']
        cache = kwargs.get('projection_cache')
        key = ('auto_enroll_context', uid)
        can_use = cache.get(key) if cache is not None else None
        if can_use is None:
            can_use = speaker_auto_enroll.context(uid, firestore_client=kwargs.get('firestore_client'))
            if cache is not None:
                cache[key] = can_use
        if auto_enroll.usable(uid, data, can_use) is not None:
            # Public Person accepts explicit readiness when no raw embedding is
            # present. Keep the encrypted pool for internal voiceprint consumers.
            data = {k: v for k, v in data.items() if k != 'speaker_embedding'}
            data.update(voice_readiness='ready', voice_learning_state='learned')
    return data


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
