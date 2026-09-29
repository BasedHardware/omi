"""Small rolling projection of confidently classified live STT languages."""

from __future__ import annotations

import re
from typing import Any

from google.cloud.firestore_v1 import transactional

from database._client import db, get_data_plane_firestore_client
from database.firestore_cache import CachePolicy, get_or_fetch, invalidate

FIELD = 'live_stt_language_sessions'
MAX_SESSIONS = 20
MAX_CODES = 16
MAX_COUNT = 10000
MAX_ID_LENGTH = 128
_CACHE = CachePolicy(namespace='live_stt_language_sessions', version=1, ttl_seconds=120)


def _clean_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_ID_LENGTH:
        return None
    if any(char in cleaned for char in ('/', '\\', '\0')) or '..' in cleaned:
        return None
    return cleaned


def _clean_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for code, count in value.items():
        if isinstance(code, str) and type(count) is int and count > 0:
            clean_code = code.strip().lower()
            if re.fullmatch(r'[a-z]{2,3}', clean_code):
                counts[clean_code] = min(count, MAX_COUNT)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:MAX_CODES])


def _clean_sessions(value: Any) -> list[dict[str, int]]:
    if not isinstance(value, list):
        return []
    cleaned_sessions: list[dict[str, int]] = []
    for item in value[-MAX_SESSIONS:]:
        if isinstance(item, dict):
            counts = _clean_counts(item)
            if counts:
                cleaned_sessions.append(counts)
    return cleaned_sessions


def _resolve_client(firestore_client: Any = None) -> Any:
    if firestore_client is not None:
        return firestore_client
    try:
        client = get_data_plane_firestore_client()
        if client is not None:
            return client
    except Exception:
        pass
    try:
        return db
    except Exception:
        return None


def invalidate_live_language_sessions_cache(uid: str) -> None:
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return
    try:
        invalidate(_CACHE, clean_uid)
    except Exception:
        pass


def get_live_language_sessions(uid: str, *, firestore_client: Any = None) -> list[dict[str, int]]:
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return []

    def fetch() -> list[dict[str, int]]:
        client = _resolve_client(firestore_client)
        if client is None:
            return []
        try:
            snapshot = client.collection('users').document(clean_uid).get([FIELD])
            if not snapshot or not getattr(snapshot, 'exists', True):
                return []
            data = snapshot.to_dict()
            return _clean_sessions((data or {}).get(FIELD))
        except Exception:
            return []

    if firestore_client is not None:
        return fetch()
    try:
        return get_or_fetch(_CACHE, clean_uid, fetch)
    except Exception:
        return fetch()


@transactional
def _append_transaction(transaction: Any, user_ref: Any, counts: dict[str, int]) -> bool:
    try:
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot or not getattr(snapshot, 'exists', False):
            return False
        data = snapshot.to_dict()
        sessions = _clean_sessions((data or {}).get(FIELD))
        transaction.update(user_ref, {FIELD: (sessions + [counts])[-MAX_SESSIONS:]})
        return True
    except Exception:
        return False


def append_live_language_session(uid: str, counts: dict[str, int], *, firestore_client: Any = None) -> bool:
    clean_uid = _clean_id(uid)
    if not clean_uid:
        return False
    clean = _clean_counts(counts)
    if not clean:
        return False
    client = _resolve_client(firestore_client)
    if client is None:
        return False
    try:
        user_ref = client.collection('users').document(clean_uid)
        txn = client.transaction() if callable(getattr(client, 'transaction', None)) else None
        if txn is not None:
            updated = _append_transaction(txn, user_ref, clean)
        else:
            snapshot = user_ref.get()
            if not snapshot or not getattr(snapshot, 'exists', False):
                return False
            data = snapshot.to_dict()
            sessions = _clean_sessions((data or {}).get(FIELD))
            user_ref.update({FIELD: (sessions + [clean])[-MAX_SESSIONS:]})
            updated = True
        if updated and firestore_client is None:
            invalidate_live_language_sessions_cache(clean_uid)
        return bool(updated)
    except Exception:
        return False
