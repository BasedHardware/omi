"""Short-lived owner-encrypted acoustic handoff, never a speaker-id handoff.

Redis supplies TTL and atomic per-device generation fencing. Payloads use the
same authenticated per-user framing as the private speaker-embedding cache.
"""

import hashlib
import json
import logging
from functools import lru_cache
from typing import Any, Optional

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
            "redis.call('SET',KEYS[1],ARGV[1],'EX',86400); return v",
            2,
            *_keys(uid, device),
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


def publish(uid: str, device: str, token: str, payload: Optional[dict[str, Any]]) -> None:
    """CAS publication/withdrawal; late completion from an old socket loses."""
    try:
        encrypted = encrypt_audio_chunk(json.dumps(payload).encode(), uid) if payload is not None else b''
        if len(encrypted) > MAX_PAYLOAD_BYTES:
            return
        _client().eval(
            "if redis.call('GET',KEYS[1])~=ARGV[1] then return 0 end; "
            "if ARGV[2]=='' then redis.call('DEL',KEYS[2]) else "
            "redis.call('SET',KEYS[2],ARGV[2],'EX',ARGV[3]) end; return 1",
            2,
            *_keys(uid, device),
            token,
            encrypted,
            GAP_SECONDS,
        )
    except Exception as error:
        logger.warning('owner_reconnect_cache_write_failed type=%s', type(error).__name__)
