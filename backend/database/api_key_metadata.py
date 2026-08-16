from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Optional, Sequence, TypeGuard

# Bumped to 4 when per-key MCP scopes became authoritative. An entry written by a
# revision whose normalize_mcp_scopes() always widened to full access must not be
# honored by a revision that treats a recorded scope list as the whole grant.
MCP_API_KEY_AUTH_CONTEXT_VERSION = 4
DEV_API_KEY_AUTH_CONTEXT_VERSION = 1


def retired_hash_fences_cache(retirement: Optional[bool]) -> bool:
    """Whether a rotation tombstone forbids trusting or writing this hash's auth cache.

    ``retirement`` is the tri-state read of the durable retirement tombstone:
    ``True`` retired, ``False`` provably active, ``None`` unreadable.

    Deleting the auth cache before the credential swap is not sufficient on its
    own: an authentication that already read the pre-swap Firestore document can
    write its entry back afterwards, keeping the retired secret valid for the
    remainder of the cache TTL. The tombstone outlives that TTL, so a cache entry
    is only honored while the fence is provably absent — an unreadable fence is
    treated as retired, which costs a Firestore lookup and never authorizes a
    rotated-away secret.
    """
    return retirement is not False


_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)
_PREFIX_PATTERNS = {
    "mcp": re.compile(r"omi_mcp_[0-9a-f]{4}\.\.\.[0-9a-f]{4}"),
    "dev": re.compile(r"omi_dev_[0-9a-f]{4}\.\.\.[0-9a-f]{4}"),
}
_LEGACY_PREFIXES = {
    "mcp": "omi_mcp_legacy",
    "dev": "omi_dev_legacy",
}
_LEGACY_NAMES = {
    "mcp": "Legacy MCP API key",
    "dev": "Legacy Developer API key",
}
_APP_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
_RAW_TOKEN_PATTERN = re.compile(r"omi_(?:mcp|dev)_[0-9a-f]{32}")
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


class ApiKeyMetadataRepair(str, Enum):
    NAME = "name"
    KEY_PREFIX = "key_prefix"
    CREATED_AT = "created_at"
    LAST_USED_AT = "last_used_at"
    APP_ID = "app_id"
    SCOPES = "scopes"


class ApiKeyAuthRepair(str, Enum):
    DOCUMENT_ID = "document_id"
    APP_ID = "app_id"
    SCOPES = "scopes"
    MEMORY_GRANT = "memory_grant"
    CACHE_READ = "cache_read"
    CACHE_WRITE = "cache_write"


class ApiKeyCacheReadMode(str, Enum):
    HIT = "hit"
    MISS = "miss"
    ERROR = "error"


class ApiKeyValidationError(ValueError):
    """Raised only for caller-correctable API-key creation input."""


class ApiKeyRevocationUnavailableError(RuntimeError):
    """Raised when revocation cannot invalidate an active auth cache safely."""


class ApiKeyNotFoundError(LookupError):
    """Raised when a key id does not resolve to a key owned by the caller."""


@dataclass(frozen=True)
class ApiKeyMetadataProjection:
    metadata: dict[str, Any]
    repairs: frozenset[ApiKeyMetadataRepair]


@dataclass(frozen=True)
class ApiKeyAuthLookupResult:
    context: Optional[dict[str, Any]]
    repairs: frozenset[ApiKeyAuthRepair] = frozenset()


@dataclass(frozen=True)
class ApiKeyCacheReadResult:
    mode: ApiKeyCacheReadMode
    data: Optional[dict[str, Any]] = None


def _coerce_utc_datetime(value: object) -> Optional[datetime]:
    try:
        parsed: Optional[datetime]
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            candidate = value.strip()
            if candidate.endswith("Z"):
                candidate = f"{candidate[:-1]}+00:00"
            parsed = datetime.fromisoformat(candidate)
        else:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def contains_raw_api_key(value: object) -> bool:
    return isinstance(value, str) and _RAW_TOKEN_PATTERN.search(value) is not None


def is_valid_api_key_hash(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and _HASH_PATTERN.fullmatch(value) is not None


def project_api_key_metadata(
    *,
    document_id: object,
    raw: object,
    snapshot_create_time: object,
    key_kind: str,
) -> ApiKeyMetadataProjection:
    """Project non-auth key metadata into a complete, safe API response shape.

    Firestore's document ID is the sole public identity. Malformed display-only
    fields are repaired at this read boundary so a key that can authenticate is
    still visible and revocable, without echoing a possible raw token from the
    stored ``key_prefix`` field.
    """
    if key_kind not in _PREFIX_PATTERNS:
        raise ValueError(f"Unsupported API key kind: {key_kind}")
    if not isinstance(document_id, str) or not document_id:
        raise ValueError("Firestore API key document must have an ID")

    data = raw if isinstance(raw, dict) else {}
    repairs: set[ApiKeyMetadataRepair] = set()
    raw_name = data.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    if not name or contains_raw_api_key(name):
        name = _LEGACY_NAMES[key_kind]
        repairs.add(ApiKeyMetadataRepair.NAME)

    raw_prefix = data.get("key_prefix")
    prefix = raw_prefix if isinstance(raw_prefix, str) and _PREFIX_PATTERNS[key_kind].fullmatch(raw_prefix) else None
    if prefix is None:
        repairs.add(ApiKeyMetadataRepair.KEY_PREFIX)

    created_at = _coerce_utc_datetime(data.get("created_at"))
    if created_at is None:
        repairs.add(ApiKeyMetadataRepair.CREATED_AT)
        created_at = _coerce_utc_datetime(snapshot_create_time) or _EPOCH_UTC

    last_used_at = _coerce_utc_datetime(data.get("last_used_at"))
    if data.get("last_used_at") is not None and last_used_at is None:
        repairs.add(ApiKeyMetadataRepair.LAST_USED_AT)

    return ApiKeyMetadataProjection(
        metadata={
            "id": document_id,
            "name": name,
            "key_prefix": prefix or _LEGACY_PREFIXES[key_kind],
            "created_at": created_at,
            "last_used_at": last_used_at,
        },
        repairs=frozenset(repairs),
    )


def normalize_api_key_scopes(
    value: object,
    *,
    allowed_scopes: Sequence[str],
    required_scopes: Sequence[str] = (),
    missing_scopes: Optional[Sequence[str]] = None,
) -> Optional[list[str]]:
    """Return scopes in canonical order, dropping malformed or unknown values."""
    if value is None and not required_scopes:
        return list(missing_scopes) if missing_scopes is not None else None

    selected = set(required_scopes)
    if isinstance(value, list):
        selected.update(scope for scope in value if isinstance(scope, str) and scope in allowed_scopes)
    return [scope for scope in allowed_scopes if scope in selected]


def api_key_scopes_need_repair(
    value: object,
    normalized: Optional[Sequence[str]],
    *,
    allowed_scopes: Sequence[str],
    missing_is_valid: bool,
) -> bool:
    """Compare scope sets without treating equivalent list ordering as damage."""
    if value is None:
        return not missing_is_valid
    if not isinstance(value, list):
        return True
    allowed = set(allowed_scopes)
    if any(not isinstance(scope, str) or scope not in allowed for scope in value):
        return True
    return set(value) != set(normalized or ())


def normalize_api_key_app_id(value: object, *, default: str) -> str:
    """Return a bounded app identity, or the credential type's stable default."""
    return valid_api_key_app_id(value) or default


def valid_api_key_app_id(value: object) -> Optional[str]:
    """Validate a persisted app identity without repairing malformed values."""
    if not isinstance(value, str) or value != value.strip():
        return None
    candidate = value
    if contains_raw_api_key(candidate):
        return None
    return candidate if _APP_ID_PATTERN.fullmatch(candidate) else None


def api_key_auth_user_id(raw: object) -> Optional[str]:
    """Extract the only data field required to authenticate a matching key doc."""
    if not isinstance(raw, dict):
        return None
    value = raw.get("user_id")
    if not isinstance(value, str) or not value or value != value.strip() or contains_raw_api_key(value):
        return None
    return value
