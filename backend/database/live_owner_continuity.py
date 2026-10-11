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
    try:
        raw = _client().eval(
            "local v=redis.call('GET',KEYS[2]); redis.call('DEL',KEYS[2]); "
            "redis.call('SET',KEYS[1],ARGV[1],'EX',86400); "
            "redis.call('SET',KEYS[3],0,'EX',86400); return v",
            3,
            *_keys(uid, device),
            _keys(uid, device)[0] + ':revision',
            token,
        )
    except Exception as error:
        logger.warning('owner_reconnect_cache_read_failed type=%s', type(error).__name__)
        return None, 'unavailable'
    if not raw:
        return None, 'absent'
    try:
        if len(raw) > MAX_PAYLOAD_BYTES:
            return None, 'corrupt'
        payload = json.loads(decrypt_audio_file(raw, uid))
        if not isinstance(payload, dict) or payload.get('device') != device or payload.get('v') != 1:
            return None, 'corrupt'
        return payload, 'loaded'
    except Exception:
        return None, 'corrupt'


def donor_authority(uid: str, conversation: str) -> Optional[dict]:
    """Read durable receipt authority, failing closed on missing/ineligible donors."""
    snapshot = (
        get_firestore_client()
        .collection('users')
        .document(uid)
        .collection(conversations_collection)
        .document(conversation)
        .get(
            field_paths=[
                'deleted',
                'discarded',
                'is_locked',
                'manual_speaker_assignments',
                'manual_speaker_assignments_compressed',
            ]
        )
    )
    data = snapshot.to_dict() if snapshot.exists else None
    if data is None or any(data.get(key) for key in ('deleted', 'discarded', 'is_locked')):
        return None
    return decode_manual_speaker_assignments(
        uid, data.get('manual_speaker_assignments'), bool(data.get('manual_speaker_assignments_compressed'))
    )


def authority_snapshot(
    uid: str, conversations: tuple[str, ...], *, firestore_client: Any = None
) -> dict[str, Optional[dict]]:
    """Read receiving, acoustic donor and rollover donor at one transaction read time.

    Separate awaited reads can each be current while their combination has
    never been authoritative. Only projected receipt/privacy fields are read;
    no transcript or user evidence is written by this transaction.
    """
    if not 1 <= len(conversations) <= 3:
        raise ValueError('owner authority requires one to three conversations')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)

    @firestore.transactional
    def read(transaction: Any) -> dict[str, Optional[dict]]:
        result = {}
        for conversation in dict.fromkeys(conversations):
            snapshot = collection.document(conversation).get(
                transaction=transaction,
                field_paths=[
                    'deleted',
                    'discarded',
                    'is_locked',
                    'manual_speaker_assignments',
                    'manual_speaker_assignments_compressed',
                ],
            )
            data = snapshot.to_dict() if snapshot.exists else None
            result[conversation] = (
                decode_manual_speaker_assignments(
                    uid, data.get('manual_speaker_assignments'), bool(data.get('manual_speaker_assignments_compressed'))
                )
                if data is not None and not any(data.get(key) for key in ('deleted', 'discarded', 'is_locked'))
                else None
            )
        return result

    return read(client.transaction())


def publish(uid: str, device: str, token: str, payload: Optional[dict[str, Any]], revision: int) -> None:
    """CAS publication/withdrawal; late completion from an old socket loses."""
    try:
        encrypted = encrypt_audio_chunk(json.dumps(payload).encode(), uid) if payload is not None else b''
        if len(encrypted) > MAX_PAYLOAD_BYTES:
            return
        _client().eval(
            "if redis.call('GET',KEYS[1])~=ARGV[1] then return 0 end; "
            "if tonumber(redis.call('GET',KEYS[3]) or '0')>=tonumber(ARGV[4]) then return 0 end; "
            "redis.call('SET',KEYS[3],ARGV[4],'EX',86400); "
            "if ARGV[2]=='' then redis.call('DEL',KEYS[2]) else "
            "redis.call('SET',KEYS[2],ARGV[2],'EX',ARGV[3]) end; return 1",
            3,
            *_keys(uid, device),
            _keys(uid, device)[0] + ':revision',
            token,
            encrypted,
            GAP_SECONDS,
            revision,
        )
    except Exception as error:
        logger.warning('owner_reconnect_cache_write_failed type=%s', type(error).__name__)
