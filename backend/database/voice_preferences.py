from __future__ import annotations

import logging
from typing import Any, Optional

from config.assistant_voices import DEFAULT_ASSISTANT_VOICE, normalize_assistant_voice
from database._client import get_data_plane_firestore_client

_ASSISTANT_VOICE_FIELD = 'assistant_voice_id'
_LOGGER = logging.getLogger(__name__)


def get_assistant_voice(uid: str, *, firestore_client: Optional[Any] = None) -> str:
    cleaned_uid = uid.strip() if uid else ''
    if not cleaned_uid:
        return DEFAULT_ASSISTANT_VOICE
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    if client is None:
        return DEFAULT_ASSISTANT_VOICE
    try:
        snapshot = client.collection('users').document(cleaned_uid).get()
        if not getattr(snapshot, 'exists', False):
            return DEFAULT_ASSISTANT_VOICE
        data = snapshot.to_dict()
        stored = data.get(_ASSISTANT_VOICE_FIELD) if isinstance(data, dict) else None
        return normalize_assistant_voice(stored)
    except Exception as e:
        _LOGGER.warning('Failed to fetch assistant voice for uid %s: %s', cleaned_uid, e)
        return DEFAULT_ASSISTANT_VOICE


def set_assistant_voice(uid: str, voice_id: str, *, firestore_client: Optional[Any] = None) -> str:
    cleaned_uid = uid.strip() if uid else ''
    if not cleaned_uid:
        raise ValueError('uid must be a non-empty string')
    normalized = normalize_assistant_voice(voice_id)
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    if client is None:
        raise RuntimeError('Firestore data plane client is unavailable')
    try:
        client.collection('users').document(cleaned_uid).set({_ASSISTANT_VOICE_FIELD: normalized}, merge=True)
    except Exception as e:
        _LOGGER.error('Failed to set assistant voice for uid %s: %s', cleaned_uid, e)
        raise
    return normalized
