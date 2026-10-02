"""Revocation fences for long-lived Developer and MCP bearer keys.

Revoke confirms a permanent deny marker before purging positive caches, then
the caller deletes the authoritative key and its grant. Marker failure leaves
Firestore untouched; purge failure leaves the marker in place and reports 503.
Neither failure is rolled back: retries can safely complete the deletion.

Markers have no TTL because these credentials and a paused pre-delete reader
have no bounded lifetime. Every authentication checks before and after reading
or filling. An unreadable marker disables positive-cache reads and fills for
that authentication; only a fresh authoritative Firestore lookup can credit it.
The Lua fill shares Redis's ordering with marker SET, so no fill can resurrect
a positive entry after the fence.
"""

import json
import logging
from typing import Any, Optional, Sequence

from database.api_key_metadata import ApiKeyCacheReadMode, ApiKeyCacheReadResult, ApiKeyRevocationUnavailableError

logger = logging.getLogger(__name__)

_FILL_IF_ACTIVE = """
if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
for i = 2, #KEYS do
    redis.call('SET', KEYS[i], ARGV[i], 'EX', ARGV[1])
end
return 1
"""


def _redis() -> Any:
    from database import redis_db

    return redis_db.r


def _marker_key(kind: str, hashed_key: str) -> str:
    if kind not in ("dev", "mcp"):
        raise ValueError("Unknown API key family")
    return f"api_key:revoked:{kind}:{hashed_key}"


def _read_marker(client: Any, kind: str, hashed_key: str) -> Optional[bool]:
    raw = client.get(_marker_key(kind, hashed_key))
    if raw is None:
        return False  # Redis GET nil confirms that the marker is absent.
    if isinstance(raw, (str, bytes)) and raw:
        return True
    return None  # An unexpected response does not confirm absence.


def is_revoked(kind: str, hashed_key: str) -> Optional[bool]:
    """Return revoked/active, or None when auth must bypass the positive cache."""
    try:
        return _read_marker(_redis(), kind, hashed_key)
    except Exception as exc:
        logger.warning("Error reading %s API key revocation marker: %s", kind, exc)
        return None


def mark_revoked(client: Any, kind: str, hashed_key: str) -> None:
    """Require an acknowledged permanent marker before any destructive step."""
    try:
        if not client.set(_marker_key(kind, hashed_key), "1"):
            raise ApiKeyRevocationUnavailableError("API key revocation fence write was not confirmed")
    except ApiKeyRevocationUnavailableError:
        raise
    except Exception as exc:
        raise ApiKeyRevocationUnavailableError("API key revocation fence write failed") from exc


def fill_if_active(client: Any, kind: str, hashed_key: str, entries: Sequence[tuple[str, str]], ttl: int) -> bool:
    """Atomically check the marker and write all positive cache entries."""
    keys = [_marker_key(kind, hashed_key), *(key for key, _value in entries)]
    values = [value for _key, value in entries]
    return client.eval(_FILL_IF_ACTIVE, len(keys), *keys, ttl, *values) == 1


def read_context(client: Any, kind: str, hashed_key: str) -> ApiKeyCacheReadResult:
    """Read current/legacy positive entries, checking the fence after the read."""
    try:
        cache_key = f"mcp_api_key_auth:{hashed_key}" if kind == "mcp" else f"dev_api_key:{hashed_key}"
        raw = client.get(cache_key)
        data = None
        if raw:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            if not isinstance(data, dict):
                return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.ERROR)
        elif kind == "mcp":
            legacy = client.get(f"mcp_api_key:{hashed_key}")
            if legacy:
                uid = legacy.decode() if isinstance(legacy, bytes) else legacy
                if not isinstance(uid, str):
                    return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.ERROR)
                data = {"user_id": uid, "scopes": None, "key_id": None, "app_id": None}
        revoked = _read_marker(client, kind, hashed_key)
        if revoked is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.ERROR)
        if revoked or data is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.HIT, data=data)
    except Exception as exc:
        logger.error("Error reading %s API key auth cache: %s", kind, exc)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.ERROR)
