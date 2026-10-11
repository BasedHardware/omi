"""Bounded owner-encrypted excerpt evidence, purged with conversation audio.

One object per conversation, at most 16 PCM-digest entries, each usable for
12 hours. Stored vectors never enter generic Redis JSON. Storage shares the
private evidence cache's encryption and account-deletion write fence.
"""

import json
import math
import time

import numpy as np

from database import conversation_tombstones
from database import conversations as conversations_db
from utils.other import storage
from utils.speaker_tag_prompts.owner_confirmation import MAX_CONSTITUENTS

TTL_SECONDS = 12 * 60 * 60
MAX_DIMENSIONS = 4096
MAX_BYTES = 2 * 1024 * 1024


def _bounded(entries: dict, now: float) -> dict:
    result = {}
    for digest, entry in list(entries.items())[-MAX_CONSTITUENTS:]:
        try:
            expiry = float(entry['expires_at'])
            vector = np.asarray(entry['vector'], dtype=np.float32)
            if (
                isinstance(digest, str)
                and len(digest) == 64
                and math.isfinite(expiry)
                and now < expiry <= now + TTL_SECONDS
                and vector.ndim == 1
                and 0 < vector.size <= MAX_DIMENSIONS
                and np.isfinite(vector).all()
                and np.linalg.norm(vector) > 0
            ):
                result[digest] = {'expires_at': expiry, 'vector': vector.tolist()}
        except (KeyError, TypeError, ValueError):
            continue
    return result


def load(uid: str, conversation_id: str) -> dict:
    data = storage.download_owner_prompt_embedding_cache(uid, conversation_id)
    if data is None:
        return {}
    try:
        if len(data) > MAX_BYTES:
            return {}
        payload = json.loads(data)
        return _bounded(payload['entries'], time.time()) if payload.get('v') == 1 else {}
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}


def _source_live(uid: str, conversation_id: str) -> bool:
    if conversation_tombstones.is_deleted(uid, conversation_id):
        return False
    source = conversations_db.get_conversation(uid, conversation_id)
    return bool(source and not source.get('deleted') and not source.get('discarded'))


def save(uid: str, conversation_id: str, entries: dict) -> None:
    data = json.dumps({'v': 1, 'entries': _bounded(entries, time.time())}, allow_nan=False).encode()
    if len(data) > MAX_BYTES:
        raise ValueError('Owner prompt evidence exceeds cache budget')
    if not _source_live(uid, conversation_id):
        return
    storage.upload_owner_prompt_embedding_cache(uid, conversation_id, data)
    try:
        live = _source_live(uid, conversation_id)
    except Exception:
        # An unconfirmed post-write fence cannot retain derived biometric data.
        storage.delete_owner_prompt_embedding_cache(uid, conversation_id)
        raise
    if not live:
        storage.delete_owner_prompt_embedding_cache(uid, conversation_id)
