"""Firestore open-loop store: per-user loops and daily surfaced cards.

Storage layout:

- ``users/{uid}/open_loops/{loop_id}`` — one document per loop. The whole loop
  dict (quotes from the owner's conversations) is stored as one derived JSON
  blob: zlib-compressed and AES-encrypted for **every** user, the enhanced
  protection shape from ``database/conversations.py`` applied unconditionally
  because the content is conversation-derived regardless of tier. The raw
  document is ``{id, data: <encrypted blob>, data_compressed: True}`` plus a
  plain ``status``/``last_activity_at`` mirror used only for bounded-read
  triage; nothing readable leaves the blob.
- ``users/{uid}/open_loop_cards/{date}`` — the per-local-day surfaced cards
  (state pending|done|remind|dropped). Its existence is also the daily pass's
  once-per-day marker; an empty cards list still marks the pass as run.

The collection is read by streaming the subcollection and filtering in code
(no queries, no new indexes); expiry plus the store cap keep it small.
"""

from __future__ import annotations

import json
import logging
import zlib
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from ._client import get_firestore_client
from utils import encryption

logger = logging.getLogger(__name__)

OPEN_LOOPS_COLLECTION = 'open_loops'
OPEN_LOOP_CARDS_COLLECTION = 'open_loop_cards'

DATA_FIELD = 'data'
DATA_COMPRESSED_FIELD = 'data_compressed'


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _protect(value: Any, uid: str) -> str:
    payload = zlib.compress(json.dumps(value, default=_json_default).encode('utf-8'))
    return encryption.encrypt(payload.hex(), uid)


def _reveal(raw: Any, uid: str) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        payload = encryption.decrypt(raw, uid)
        return json.loads(zlib.decompress(bytes.fromhex(payload)).decode('utf-8'))
    raise ValueError(f'undecodable open-loop blob: {type(raw).__name__}')


def _collection(uid: str, name: str, firestore_client: Any):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return client.collection('users').document(uid).collection(name)


def _loop_ref(uid: str, loop_id: str, *, firestore_client: Any = None):
    return _collection(uid, OPEN_LOOPS_COLLECTION, firestore_client).document(loop_id)


def upsert_loop(uid: str, loop: Dict[str, Any], *, firestore_client: Any = None) -> None:
    """Write one loop document (full overwrite; loops are small and self-contained)."""
    loop_id = str(loop['id'])
    _loop_ref(uid, loop_id, firestore_client=firestore_client).set(
        {
            'id': loop_id,
            # Plain triage mirrors: never conversation content, only status.
            'status': loop.get('status'),
            'last_activity_at': loop.get('last_activity_at'),
            DATA_FIELD: _protect(loop, uid),
            DATA_COMPRESSED_FIELD: True,
        }
    )


def delete_loops(uid: str, loop_ids: List[str], *, firestore_client: Any = None) -> None:
    for loop_id in loop_ids:
        _loop_ref(uid, str(loop_id), firestore_client=firestore_client).delete()


def get_loops(uid: str, *, firestore_client: Any = None) -> List[Dict[str, Any]]:
    """All stored loops, decoded. Undecodable documents are skipped, not fatal."""
    loops: List[Dict[str, Any]] = []
    for doc in _collection(uid, OPEN_LOOPS_COLLECTION, firestore_client).stream():
        raw = doc.to_dict() or {}
        if not raw.get(DATA_COMPRESSED_FIELD):
            continue
        try:
            value = _reveal(raw.get(DATA_FIELD), uid)
        except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
            logger.error('open_loop_store_undecodable uid=%s loop_id=%s', uid, doc.id)
            continue
        if isinstance(value, dict) and value.get('id'):
            loops.append(value)
    return loops


def get_cards_doc(uid: str, date_str: str, *, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    """The raw cards document for one local day, or None when the pass has not run."""
    raw = _collection(uid, OPEN_LOOP_CARDS_COLLECTION, firestore_client).document(date_str).get().to_dict()
    return raw if raw else None


def get_cards(uid: str, date_str: str, *, firestore_client: Any = None) -> Optional[List[Dict[str, Any]]]:
    """The decoded cards for one local day; None when the pass has not run."""
    raw = get_cards_doc(uid, date_str, firestore_client=firestore_client)
    if raw is None:
        return None
    try:
        value = _reveal(raw.get(DATA_FIELD), uid)
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
        logger.error('open_loop_cards_undecodable uid=%s date=%s', uid, date_str)
        return []
    return value if isinstance(value, list) else []


def set_cards(uid: str, date_str: str, cards: List[Dict[str, Any]], *, firestore_client: Any = None) -> None:
    """Store the day's surfaced cards (possibly empty) — also the pass-ran marker."""
    _collection(uid, OPEN_LOOP_CARDS_COLLECTION, firestore_client).document(date_str).set(
        {
            'date': date_str,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            DATA_FIELD: _protect(cards, uid),
            DATA_COMPRESSED_FIELD: True,
        }
    )
