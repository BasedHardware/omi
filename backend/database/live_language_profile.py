"""Small rolling projection of confidently classified live STT languages."""

from __future__ import annotations

import re
from typing import Any

from google.cloud.firestore_v1 import transactional

from database._client import get_data_plane_firestore_client
from database.firestore_cache import CachePolicy, get_or_fetch, invalidate

FIELD = 'live_stt_language_sessions'
MAX_SESSIONS = 20
MAX_CODES = 16
MAX_COUNT = 10000
_CACHE = CachePolicy(namespace='live_stt_language_sessions', version=1, ttl_seconds=120)


def _clean_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts = {
        code: min(count, MAX_COUNT)
        for code, count in value.items()
        if isinstance(code, str) and re.fullmatch(r'[a-z]{2,3}', code) and type(count) is int and count > 0
    }
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:MAX_CODES])


def _clean_sessions(value: Any) -> list[dict[str, int]]:
    if not isinstance(value, list):
        return []
    return [counts for item in value[-MAX_SESSIONS:] if (counts := _clean_counts(item))]


def get_live_language_sessions(uid: str, *, firestore_client: Any = None) -> list[dict[str, int]]:
    def fetch() -> list[dict[str, int]]:
        client = firestore_client or get_data_plane_firestore_client()
        snapshot = client.collection('users').document(uid).get([FIELD])
        return _clean_sessions((snapshot.to_dict() or {}).get(FIELD))

    if firestore_client is not None:
        return fetch()
    return get_or_fetch(_CACHE, uid, fetch)


@transactional
def _append_transaction(transaction: Any, user_ref: Any, counts: dict[str, int]) -> bool:
    snapshot = user_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    sessions = _clean_sessions((snapshot.to_dict() or {}).get(FIELD))
    transaction.update(user_ref, {FIELD: (sessions + [counts])[-MAX_SESSIONS:]})
    return True


def append_live_language_session(uid: str, counts: dict[str, int], *, firestore_client: Any = None) -> bool:
    clean = _clean_counts(counts)
    if not clean:
        return False
    client = firestore_client or get_data_plane_firestore_client()
    updated = _append_transaction(client.transaction(), client.collection('users').document(uid), clean)
    if updated and firestore_client is None:
        invalidate(_CACHE, uid)
    return updated
