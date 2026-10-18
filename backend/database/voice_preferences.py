from __future__ import annotations

import logging
from typing import Any

from google.api_core.exceptions import GoogleAPICallError

from config.assistant_voices import DEFAULT_ASSISTANT_VOICE, normalize_assistant_voice
from database._client import get_data_plane_firestore_client

logger = logging.getLogger(__name__)

_ASSISTANT_VOICE_FIELD = 'assistant_voice_id'


def _sanitize_uid(uid: Any) -> str:
    """UIDs from headers/tokens can carry whitespace; an unsanitized uid
    skews the document path and reads/writes the wrong user root."""
    return uid.strip() if isinstance(uid, str) else ''


def get_assistant_voice(uid: str, *, firestore_client: Any = None) -> str:
    uid = _sanitize_uid(uid)
    if not uid:
        return DEFAULT_ASSISTANT_VOICE
    try:
        client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
        snapshot = client.collection('users').document(uid).get()
        data = snapshot.to_dict() if snapshot.exists else None
    except (GoogleAPICallError, OSError, TimeoutError):
        # A data-plane outage must not break the caller's voice lookup —
        # fall back to the catalog default rather than raise. Programming
        # errors (AttributeError etc.) still propagate.
        logger.warning('assistant voice read failed', exc_info=True)
        return DEFAULT_ASSISTANT_VOICE
    stored = data.get(_ASSISTANT_VOICE_FIELD) if isinstance(data, dict) else None
    return normalize_assistant_voice(stored)


def set_assistant_voice(uid: str, voice_id: str, *, firestore_client: Any = None) -> str:
    uid = _sanitize_uid(uid)
    if not uid:
        raise ValueError('invalid_uid')
    normalized = normalize_assistant_voice(voice_id)
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    if client is None:
        raise RuntimeError('data plane unavailable')
    client.collection('users').document(uid).set({_ASSISTANT_VOICE_FIELD: normalized}, merge=True)
    return normalized
