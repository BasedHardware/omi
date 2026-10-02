"""Redis positive-only cache for MCP OAuth access-token validation.

``validate_access_token`` runs on every hosted MCP request. A validated token
identity is cached for at most ``CACHE_TTL_CAP_SECONDS`` so steady traffic does
not re-read the token and grant documents per request; every hit still
revalidates shape, expiry, scopes, audience equivalence, and the per-grant
revocation marker, so a hit is only ever as fresh as the marker.

Revocation writes a ``mcp:oauth:revoked:{sha256(grant_id)}`` marker BEFORE the
Firestore revoke so a validation that slipped between the marker and the
Firestore write still fails, then deletes every cached token the grant index
knows about. All Redis failures raise ``McpTokenStoreUnavailable`` — revocation
callers keep it fail-closed (a revoke that cannot write its marker reports no
success), while ``validate_access_token`` degrades to the authoritative
Firestore path when the cache, marker, or throttle store is down.

Plaintext tokens are never placed in keys, values, or logs: keys are sha256
digests of the token and grant ids. Cached identities are HMAC-signed via
``database.mcp_cache_integrity`` so a forged Redis write can never mint an
identity; when the signing secret is absent the OAuth path fails closed.
"""

import hashlib
import time
from typing import Any, Dict, List, Optional

import database.mcp_cache_integrity as mcp_cache_integrity
import database.redis_db as redis_db
from config.mcp_resource_urls import mcp_resource_urls_match
from config.mcp_scopes import MCP_FULL_ACCESS_SCOPES

ACCESS_TOKEN_CACHE_TTL_CAP_SECONDS = 60
LAST_USED_THROTTLE_SECONDS = 600

_ACCESS_TOKEN_KEY_PREFIX = "mcp:oauth:at:"
_REVOKED_GRANT_KEY_PREFIX = "mcp:oauth:revoked:"
_GRANT_TOKENS_KEY_PREFIX = "mcp:oauth:grant_tokens:"
_LAST_USED_KEY_PREFIX = "mcp:oauth:last_used:"
_INTEGRITY_TAG = "at"


class McpTokenStoreUnavailable(RuntimeError):
    """A Redis cache/marker/throttle operation failed — the caller decides
    whether its operation can safely fall back to Firestore."""


def _redis() -> Any:
    return redis_db.r


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _access_token_key(access_token: str) -> str:
    return f"{_ACCESS_TOKEN_KEY_PREFIX}{_sha256(access_token)}"


def _revoked_grant_key(grant_id: str) -> str:
    return f"{_REVOKED_GRANT_KEY_PREFIX}{_sha256(grant_id)}"


def _grant_tokens_key(grant_id: str) -> str:
    return f"{_GRANT_TOKENS_KEY_PREFIX}{_sha256(grant_id)}"


def _last_used_key(access_token: str) -> str:
    return f"{_LAST_USED_KEY_PREFIX}{_sha256(access_token)}"


def _decode(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


def _entry_is_valid(entry: object, resource: str, now: float) -> bool:
    """Revalidate a cached identity on every hit: shape, scopes, expiry, and
    canonical/legacy audience equivalence (cross-host audiences never match)."""
    if not isinstance(entry, dict):
        return False
    scopes = entry.get("scopes")
    if (
        not isinstance(entry.get("uid"), str)
        or not entry["uid"]
        or not isinstance(entry.get("client_id"), str)
        or not entry["client_id"]
        or not isinstance(entry.get("grant_id"), str)
        or not entry["grant_id"]
        or not isinstance(entry.get("resource"), str)
        or not entry["resource"]
        or not isinstance(scopes, list)
        or not scopes
        or any(not isinstance(scope, str) or scope not in MCP_FULL_ACCESS_SCOPES for scope in scopes)
        or not isinstance(entry.get("expires_at"), (int, float))
        or entry["expires_at"] <= now
        or not isinstance(entry.get("token_hash"), str)
    ):
        return False
    return mcp_resource_urls_match(entry["resource"], resource)


def grant_revocation_marker_exists(grant_id: str) -> bool:
    """Fail-closed marker read: a Redis error raises, never silently passes."""
    try:
        return bool(_redis().exists(_revoked_grant_key(grant_id)))
    except McpTokenStoreUnavailable:
        raise
    except Exception as exc:
        raise McpTokenStoreUnavailable("MCP OAuth revocation marker unavailable") from exc


def read_access_token(access_token: str, resource: str) -> Optional[Dict[str, Any]]:
    """Return a validated cached identity for ``access_token``, or ``None``.

    ``None`` covers cache miss, malformed or forged (MAC-invalid) entries,
    expired entries, audience mismatch, and revoked grants — the caller then
    runs the Firestore path. A missing signing secret fails closed: unsigned
    cache data can never be trusted.
    """
    if not mcp_cache_integrity.integrity_available():
        raise McpTokenStoreUnavailable("MCP OAuth token cache signing secret unavailable")
    client = _redis()
    key = _access_token_key(access_token)
    try:
        raw = client.get(key)
    except Exception as exc:
        raise McpTokenStoreUnavailable("MCP OAuth token cache unavailable") from exc
    if raw is None:
        return None
    entry = mcp_cache_integrity.loads_verified(raw, _INTEGRITY_TAG)
    if not _entry_is_valid(entry, resource, now=time.time()):
        return None
    # The signed payload binds its own token hash, so a valid blob copied to
    # a different token key is dropped — copying cannot transfer an identity.
    if entry["token_hash"] != _sha256(access_token):  # type: ignore[index]
        return None
    grant_id = str(entry["grant_id"])  # type: ignore[index]
    if grant_revocation_marker_exists(grant_id):
        try:
            client.delete(key)
        except Exception as exc:
            raise McpTokenStoreUnavailable("MCP OAuth token cache unavailable") from exc
        return None
    return {
        "uid": entry["uid"],  # type: ignore[index]
        "auth_type": "oauth",
        "client_id": entry["client_id"],  # type: ignore[index]
        "resource": entry["resource"],  # type: ignore[index]
        "scopes": list(entry["scopes"]),  # type: ignore[index]
        "grant_id": grant_id,
    }


def fill_access_token(
    access_token: str, identity: Dict[str, Any], expires_at_epoch: float, *, index_ttl_seconds: int
) -> None:
    """Cache a fully validated identity with TTL min(60s, token time-to-live),
    and index the token hash under its grant for targeted revocation.
    ``index_ttl_seconds`` is the access-token TTL the caller guarantees."""
    remaining = expires_at_epoch - time.time()
    ttl = min(ACCESS_TOKEN_CACHE_TTL_CAP_SECONDS, int(remaining))
    if ttl <= 0:
        return
    grant_id = str(identity.get("grant_id") or "")
    if not grant_id:
        return
    token_hash = _sha256(access_token)
    entry = {
        "uid": identity["uid"],
        "client_id": identity["client_id"],
        "resource": identity["resource"],
        "scopes": list(identity["scopes"]),
        "grant_id": grant_id,
        "expires_at": expires_at_epoch,
        "token_hash": token_hash,
    }
    if not mcp_cache_integrity.integrity_available():
        raise McpTokenStoreUnavailable("MCP OAuth token cache signing secret unavailable")
    blob = mcp_cache_integrity.dumps_signed(entry, _INTEGRITY_TAG)
    if blob is None:
        raise McpTokenStoreUnavailable("MCP OAuth token cache signing secret unavailable")
    client = _redis()
    grant_index_key = _grant_tokens_key(grant_id)
    try:
        client.set(_access_token_key(access_token), blob, ex=ttl)
        client.sadd(grant_index_key, token_hash)
        client.expire(grant_index_key, index_ttl_seconds)
    except Exception as exc:
        raise McpTokenStoreUnavailable("MCP OAuth token cache unavailable") from exc


def invalidate_grant(grant_id: str, *, marker_ttl_seconds: int) -> None:
    """Mark the grant revoked (the marker outlives the access-token TTL so
    late validations still fail), purge every cached token the grant index
    tracks, and clear the index itself. Called before the Firestore revoke:
    the marker write is the mandatory part — if it cannot be written the
    caller must not report a successful revoke, and once written it keeps
    blocking cached entries even when a later purge step fails."""
    client = _redis()
    try:
        # A falsy SET that does not raise is still an unwritten marker — the
        # caller must never pretend the grant is revoked.
        if not client.set(_revoked_grant_key(grant_id), "1", ex=marker_ttl_seconds):
            raise McpTokenStoreUnavailable("MCP OAuth revocation marker write rejected")
        index_key = _grant_tokens_key(grant_id)
        token_hashes = client.smembers(index_key)
        keys = [_access_token_key_from_hash(_decode(token_hash) or "") for token_hash in token_hashes or ()]
        if keys:
            client.delete(*keys)
        client.delete(index_key)
    except McpTokenStoreUnavailable:
        raise
    except Exception as exc:
        raise McpTokenStoreUnavailable("MCP OAuth revocation store unavailable") from exc


def _access_token_key_from_hash(token_hash: str) -> str:
    return f"{_ACCESS_TOKEN_KEY_PREFIX}{token_hash}"


def claim_last_used_write(access_token: str) -> bool:
    """Throttle ``last_used_at`` writes to one per token per 600s: only the
    caller whose ``SET NX EX`` claim lands may write Firestore."""
    try:
        return bool(_redis().set(_last_used_key(access_token), "1", nx=True, ex=LAST_USED_THROTTLE_SECONDS))
    except Exception as exc:
        raise McpTokenStoreUnavailable("MCP OAuth throttle store unavailable") from exc


__all__: List[str] = [
    "ACCESS_TOKEN_CACHE_TTL_CAP_SECONDS",
    "LAST_USED_THROTTLE_SECONDS",
    "McpTokenStoreUnavailable",
    "claim_last_used_write",
    "fill_access_token",
    "grant_revocation_marker_exists",
    "invalidate_grant",
    "read_access_token",
]
