from __future__ import annotations

from typing import Any

from config.assistant_voices import normalize_assistant_voice
from database._client import get_data_plane_firestore_client

_ASSISTANT_VOICE_FIELD = 'assistant_voice_id'


def get_assistant_voice(uid: str, *, firestore_client: Any = None) -> str:
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    snapshot = client.collection('users').document(uid).get()
    data = snapshot.to_dict() if snapshot.exists else None
    stored = data.get(_ASSISTANT_VOICE_FIELD) if isinstance(data, dict) else None
    return normalize_assistant_voice(stored)


def set_assistant_voice(uid: str, voice_id: str, *, firestore_client: Any = None) -> str:
    normalized = normalize_assistant_voice(voice_id)
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    client.collection('users').document(uid).set({_ASSISTANT_VOICE_FIELD: normalized}, merge=True)
    return normalized
