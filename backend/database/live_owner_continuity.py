"""Short-lived owner-encrypted acoustic handoff, never a speaker-id handoff.

Redis supplies TTL and atomic per-device generation fencing. Payloads use the
same authenticated per-user framing as the private speaker-embedding cache.
"""

import hashlib
import json
import logging
from functools import lru_cache
from typing import Any, Optional

from google.cloud import firestore

from database._client import get_firestore_client
from database.conversations import conversations_collection, decode_manual_speaker_assignments
from database.redis_db import create_bounded_redis_client
from utils.encryption import decrypt_audio_file, encrypt_audio_chunk

logger = logging.getLogger(__name__)
GAP_SECONDS = 120
MAX_PAYLOAD_BYTES = 16_384
_MAX_IDENTIFIER_LENGTH = 128
_MAX_TOKEN_LENGTH = 256
_ELIGIBLE_FIELDS = ('deleted', 'discarded', 'is_locked')
_PROJECTION = [
    *_ELIGIBLE_FIELDS,
    'manual_speaker_assignments',
    'manual_speaker_assignments_compressed',
]


def _clean_identifier(value: Any, code: str) -> str:
    """A Firestore path segment; anything that cannot address a document fails."""
    if not isinstance(value, str) or isinstance(value, bool):
        raise ValueError(code)
    token = value.strip()
    if not token or token in ('.', '..', '__reserved__') or len(token) > _MAX_IDENTIFIER_LENGTH:
        raise ValueError(code)
    if '/' in token or '\\' in token or '..' in token:
        raise ValueError(code)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        raise ValueError(code)
    return token


def _clean_token(value: Any) -> str:
    if not isinstance(value, str) or isinstance(value, bool):
        raise ValueError('owner_reconnect_token')
    token = value.strip()
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        raise ValueError('owner_reconnect_token')
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        raise ValueError('owner_reconnect_token')
    return token


def _clean_revision(value: Any) -> int:
    """A monotonic counter: booleans, non-integers and negatives cannot fence."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('owner_reconnect_revision')
    return value


def _payload(snapshot: Any) -> Optional[dict[str, Any]]:
    """Projected snapshot to a dict payload; unusable shapes become absent."""
    try:
        if not getattr(snapshot, 'exists', False):
            return None
        data = snapshot.to_dict()
    except (AttributeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _eligible(data: Optional[dict[str, Any]]) -> bool:
    return data is not None and not any(data.get(key) for key in _ELIGIBLE_FIELDS)


@lru_cache(maxsize=1)
def _client() -> Any:
    return create_bounded_redis_client(0.25)


def _keys(uid: str, device: str) -> tuple[str, str]:
    digest = hashlib.sha256(json.dumps([uid, device]).encode()).hexdigest()
    # Hash tag keeps both keys in the same slot on clustered Redis.
    root = f'owner-reconnect:{{{digest}}}:v1'
    return root + ':generation', root + ':evidence'


def begin(uid: str, device: str, token: str) -> tuple[Optional[dict[str, Any]], str]:
    """Consume at most one donor; a newer socket fences every older writer."""
    uid = _clean_identifier(uid, 'owner_reconnect_uid')
    device = _clean_identifier(device, 'owner_reconnect_device')
    token = _clean_token(token)
    generation, evidence = _keys(uid, device)
    try:
        raw = _client().eval(
            "local v=redis.call('GET',KEYS[2]); redis.call('DEL',KEYS[2]); "
            "redis.call('SET',KEYS[1],ARGV[1],'EX',86400); "
            "redis.call('SET',KEYS[3],0,'EX',86400); return v",
            3,
            generation,
            evidence,
            generation.rsplit(':', 1)[0] + ':revision',
            token,
        )
    except Exception as error:
        logger.warning('owner_reconnect_cache_read_failed type=%s', type(error).__name__)
        return None, 'unavailable'
    if not raw:
        return None, 'absent'
    try:
        if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_PAYLOAD_BYTES:
            return None, 'corrupt'
        payload = json.loads(decrypt_audio_file(raw, uid))
        if not isinstance(payload, dict) or payload.get('device') != device or payload.get('v') != 1:
            return None, 'corrupt'
        return payload, 'loaded'
    except Exception:
        return None, 'corrupt'


def _decode(uid: str, data: dict[str, Any]) -> Optional[dict]:
    try:
        return decode_manual_speaker_assignments(
            uid,
            data.get('manual_speaker_assignments'),
            bool(data.get('manual_speaker_assignments_compressed')),
        )
    except Exception as error:
        logger.warning('owner_reconnect_decode_failed type=%s', type(error).__name__)
        return None


def donor_authority(uid: str, conversation: str, *, firestore_client: Any = None) -> Optional[dict]:
    """Read durable receipt authority, failing closed on missing/ineligible donors."""
    uid = _clean_identifier(uid, 'owner_reconnect_uid')
    conversation = _clean_identifier(conversation, 'owner_reconnect_conversation')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        snapshot = (
            client.collection('users')
            .document(uid)
            .collection(conversations_collection)
            .document(conversation)
            .get(field_paths=list(_PROJECTION))
        )
    except Exception as error:
        logger.warning('owner_reconnect_authority_read_failed type=%s', type(error).__name__)
        return None
    data = _payload(snapshot)
    if not _eligible(data):
        return None
    return _decode(uid, data)


def authority_snapshot(
    uid: str, conversations: tuple[str, ...], *, firestore_client: Any = None
) -> dict[str, Optional[dict]]:
    """Read receiving, acoustic donor and rollover donor at one transaction read time.

    Separate awaited reads can each be current while their combination has
    never been authoritative. Only projected receipt/privacy fields are read;
    no transcript or user evidence is written by this transaction.
    """
    uid = _clean_identifier(uid, 'owner_reconnect_uid')
    if isinstance(conversations, (str, bytes)) or not hasattr(conversations, '__iter__'):
        raise ValueError('owner authority requires one to three conversations')
    cleaned = tuple(_clean_identifier(item, 'owner_reconnect_conversation') for item in conversations)
    if not 1 <= len(cleaned) <= 3:
        raise ValueError('owner authority requires one to three conversations')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)

    @firestore.transactional
    def read(transaction: Any) -> dict[str, Optional[dict]]:
        result = {}
        for conversation in dict.fromkeys(cleaned):
            snapshot = collection.document(conversation).get(
                transaction=transaction,
                field_paths=list(_PROJECTION),
            )
            data = _payload(snapshot)
            result[conversation] = _decode(uid, data) if _eligible(data) else None
        return result

    return read(client.transaction())


def publish(uid: str, device: str, token: str, payload: Optional[dict[str, Any]], revision: int) -> None:
    """CAS publication/withdrawal; late completion from an old socket loses."""
    uid = _clean_identifier(uid, 'owner_reconnect_uid')
    device = _clean_identifier(device, 'owner_reconnect_device')
    token = _clean_token(token)
    revision = _clean_revision(revision)
    if payload is not None and not isinstance(payload, dict):
        raise ValueError('owner_reconnect_payload')
    generation, evidence = _keys(uid, device)
    try:
        encrypted = (
            encrypt_audio_chunk(json.dumps(payload).encode(), uid) if payload is not None else b''
        )
        if len(encrypted) > MAX_PAYLOAD_BYTES:
            return
        _client().eval(
            "if redis.call('GET',KEYS[1])~=ARGV[1] then return 0 end; "
            "if tonumber(redis.call('GET',KEYS[3]) or '0')>=tonumber(ARGV[4]) then return 0 end; "
            "redis.call('SET',KEYS[3],ARGV[4],'EX',86400); "
            "if ARGV[2]=='' then redis.call('DEL',KEYS[2]) else "
            "redis.call('SET',KEYS[2],ARGV[2],'EX',ARGV[3]) end; return 1",
            3,
            generation,
            evidence,
            generation.rsplit(':', 1)[0] + ':revision',
            token,
            encrypted,
            GAP_SECONDS,
            revision,
        )
    except Exception as error:
        logger.warning('owner_reconnect_cache_write_failed type=%s', type(error).__name__)
