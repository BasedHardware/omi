import uuid
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, Tuple, cast

from google.cloud import firestore

import database.redis_db as redis_db
from database._client import get_firestore_client
from database.api_key_metadata import (
    MCP_API_KEY_AUTH_CONTEXT_VERSION,
    ApiKeyAuthLookupResult,
    ApiKeyAuthRepair,
    ApiKeyCacheReadMode,
    ApiKeyMetadataRepair,
    ApiKeyRevocationUnavailableError,
    ApiKeyValidationError,
    api_key_scopes_need_repair,
    api_key_auth_user_id,
    contains_raw_api_key,
    is_valid_api_key_hash,
    normalize_api_key_app_id,
    project_api_key_metadata,
    valid_api_key_app_id,
)
from models.mcp_api_key import McpApiKey
from utils.mcp_api_keys import generate_api_key, hash_api_key
from utils.mcp_scopes import (
    MCP_APP_KEY_MEMORY_GRANTS_DOC_ID,
    MCP_DEFAULT_APP_ID,
    MCP_FULL_ACCESS_SCOPES,
    MCP_MEMORY_CONTROL_COLLECTION,
    MCP_MEMORY_GRANT_SCOPES,
    normalize_mcp_scopes,
)

logger = logging.getLogger(__name__)


def _db() -> Any:
    return get_firestore_client()


def _seed_mcp_memory_grant(
    user_id: str,
    key_id: str,
    app_id: str = MCP_DEFAULT_APP_ID,
    firestore_client: Any = None,
) -> None:
    firestore_client = firestore_client or _db()
    grant_ref = (
        firestore_client.collection("users")
        .document(user_id)
        .collection(MCP_MEMORY_CONTROL_COLLECTION)
        .document(MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
    )
    grant_ref.set(
        {
            "grants": {
                "mcp": {
                    "apps": {
                        app_id: {
                            "keys": {
                                key_id: {
                                    "enabled": True,
                                    "scopes": MCP_MEMORY_GRANT_SCOPES,
                                    "default_read": True,
                                    "archive_read": False,
                                    "write": True,
                                }
                            }
                        }
                    }
                }
            },
            "updated_at": datetime.now(timezone.utc),
        },
        merge=True,
    )


def _ensure_mcp_memory_grant(
    user_id: str,
    key_id: str,
    app_id: str,
    firestore_client: Any,
) -> bool:
    grant_ref = (
        firestore_client.collection("users")
        .document(user_id)
        .collection(MCP_MEMORY_CONTROL_COLLECTION)
        .document(MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
    )
    snapshot = grant_ref.get()
    raw = snapshot.to_dict() if getattr(snapshot, "exists", False) else {}
    grant: object = raw
    for field in ("grants", "mcp", "apps", app_id, "keys", key_id):
        grant = grant.get(field, {}) if isinstance(grant, dict) else {}
    scopes = grant.get("scopes") if isinstance(grant, dict) else None
    is_current = (
        isinstance(grant, dict)
        and grant.get("enabled") is True
        and grant.get("default_read") is True
        and grant.get("archive_read") is False
        and grant.get("write") is True
        and isinstance(scopes, list)
        and all(isinstance(scope, str) for scope in scopes)
        and set(scopes) == set(MCP_MEMORY_GRANT_SCOPES)
    )
    if is_current:
        return False
    _seed_mcp_memory_grant(user_id, key_id, app_id, firestore_client=firestore_client)
    return True


def _delete_mcp_memory_grant(
    user_id: str,
    key_id: str,
    app_id: str = MCP_DEFAULT_APP_ID,
    firestore_client: Any = None,
) -> None:
    firestore_client = firestore_client or _db()
    grant_ref = (
        firestore_client.collection("users")
        .document(user_id)
        .collection(MCP_MEMORY_CONTROL_COLLECTION)
        .document(MCP_APP_KEY_MEMORY_GRANTS_DOC_ID)
    )
    try:
        grant_ref.update(
            {
                f"grants.mcp.apps.{app_id}.keys.{key_id}": firestore.DELETE_FIELD,
                "updated_at": datetime.now(timezone.utc),
            }
        )
    except Exception as e:
        logger.warning("Failed to delete MCP memory grant for uid=%s key_id=%s: %s", user_id, key_id, e)


def _valid_cached_auth_context(cached_data: Dict[str, Any]) -> bool:
    scopes = normalize_mcp_scopes(cached_data.get("scopes"))
    return (
        cached_data.get("auth_context_version") == MCP_API_KEY_AUTH_CONTEXT_VERSION
        and api_key_auth_user_id(cached_data) is not None
        and isinstance(cached_data.get("key_id"), str)
        and bool(cached_data["key_id"])
        and isinstance(cached_data.get("app_id"), str)
        and valid_api_key_app_id(cached_data["app_id"]) == cached_data["app_id"]
        and not api_key_scopes_need_repair(
            cached_data.get("scopes"),
            scopes,
            allowed_scopes=MCP_FULL_ACCESS_SCOPES,
            missing_is_valid=False,
        )
    )


def create_mcp_key(
    user_id: str,
    name: str,
    scopes: Optional[list[str]] = None,
    app_id: Optional[str] = MCP_DEFAULT_APP_ID,
) -> Tuple[str, McpApiKey]:
    """
    Creates a new MCP API key for a user.
    Returns the raw key and the key's metadata.
    """
    if contains_raw_api_key(name):
        raise ApiKeyValidationError("API key name must not contain a raw API key")
    if app_id is None:
        resolved_app_id = MCP_DEFAULT_APP_ID
    else:
        resolved_app_id = valid_api_key_app_id(app_id)
        if resolved_app_id is None:
            raise ApiKeyValidationError("Invalid MCP API key app_id")
    raw_key, hashed_key, key_prefix = generate_api_key()
    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    resolved_scopes = normalize_mcp_scopes(scopes)
    firestore_client = _db()

    api_key_doc = {
        "id": key_id,
        "user_id": user_id,
        "name": name,
        "hashed_key": hashed_key,
        "key_prefix": key_prefix,
        "created_at": now,
        "last_used_at": None,
        "app_id": resolved_app_id,
        "scopes": resolved_scopes,
    }
    firestore_client.collection("mcp_api_keys").document(key_id).set(api_key_doc)
    _seed_mcp_memory_grant(user_id, key_id, resolved_app_id, firestore_client=firestore_client)

    api_key_data = McpApiKey(
        id=key_id,
        name=name,
        key_prefix=key_prefix,
        created_at=now,
        last_used_at=None,
        app_id=resolved_app_id,
        scopes=resolved_scopes,
    )
    return raw_key, api_key_data


def get_mcp_keys_for_user_with_repair_info(
    user_id: str,
) -> tuple[list[McpApiKey], frozenset[ApiKeyMetadataRepair]]:
    """
    Retrieves all MCP API keys and bounded metadata-repair reasons for a user.
    """
    keys_ref = _db().collection("mcp_api_keys").where("user_id", "==", user_id)
    docs = keys_ref.stream()
    keys: list[McpApiKey] = []
    repairs: set[ApiKeyMetadataRepair] = set()
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        projection = project_api_key_metadata(
            document_id=doc.id,
            raw=data,
            snapshot_create_time=getattr(doc, "create_time", None),
            key_kind="mcp",
        )
        projected = projection.metadata
        repairs.update(projection.repairs)
        projected["app_id"] = normalize_api_key_app_id(data.get("app_id"), default=MCP_DEFAULT_APP_ID)
        if data.get("app_id") != projected["app_id"]:
            repairs.add(ApiKeyMetadataRepair.APP_ID)
        projected["scopes"] = normalize_mcp_scopes(data.get("scopes"))
        if api_key_scopes_need_repair(
            data.get("scopes"),
            projected["scopes"],
            allowed_scopes=MCP_FULL_ACCESS_SCOPES,
            missing_is_valid=False,
        ):
            repairs.add(ApiKeyMetadataRepair.SCOPES)
        keys.append(McpApiKey.model_validate(projected))
    keys.sort(key=lambda key: key.id)
    keys.sort(key=lambda key: key.created_at, reverse=True)
    return keys, frozenset(repairs)


def get_mcp_keys_for_user(user_id: str) -> list[McpApiKey]:
    """Retrieves all MCP API keys for a user."""
    keys, _repairs = get_mcp_keys_for_user_with_repair_info(user_id)
    return keys


def delete_mcp_key(user_id: str, key_id: str) -> None:
    """
    Deletes an MCP API key.
    """
    firestore_client = _db()
    key_ref = firestore_client.collection("mcp_api_keys").document(key_id)
    key_doc = key_ref.get()
    if key_doc.exists:
        raw: object = key_doc.to_dict()
        key_data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        if key_data.get("user_id") == user_id:
            hashed_key = key_data.get("hashed_key")
            if not is_valid_api_key_hash(hashed_key):
                raise ApiKeyRevocationUnavailableError("MCP API key credential metadata is invalid")
            try:
                cache_deleted = redis_db.delete_cached_mcp_api_key_strict(hashed_key)
            except Exception as exc:
                raise ApiKeyRevocationUnavailableError("MCP API key cache invalidation failed") from exc
            if cache_deleted is not True:
                raise ApiKeyRevocationUnavailableError("MCP API key cache invalidation was not confirmed")
            _delete_mcp_memory_grant(
                user_id,
                key_id,
                normalize_api_key_app_id(key_data.get("app_id"), default=MCP_DEFAULT_APP_ID),
                firestore_client=firestore_client,
            )
            key_ref.delete()


def get_user_id_by_api_key(api_key: str) -> Optional[str]:
    """
    Verifies an API key and returns the associated user ID.
    Uses a cache to avoid frequent database lookups.
    Also updates the last_used_at timestamp on cache miss.
    """
    auth_context = get_user_and_scopes_by_api_key(api_key)
    return auth_context.get("user_id") if auth_context else None


def get_api_key_auth_result(api_key: str) -> ApiKeyAuthLookupResult:
    """
    Verifies an MCP API key and returns uid plus server-owned app/key/scopes.

    MCP keys are full-access agent keys. Older key documents may be missing the
    app identity, scopes, and memory grant state introduced by the app/key grant
    layer; repair them lazily on successful authentication so existing agents
    keep working without regenerating keys.
    """
    if not api_key.startswith("omi_mcp_"):
        return ApiKeyAuthLookupResult(context=None)
    secret_part = api_key.replace("omi_mcp_", "", 1)
    hashed_key = hash_api_key(secret_part)

    cache_read = redis_db.read_cached_mcp_api_key_auth_context(hashed_key)
    cached_data = cache_read.data if cache_read.mode == ApiKeyCacheReadMode.HIT else None
    if cached_data and _valid_cached_auth_context(cached_data):
        return ApiKeyAuthLookupResult(
            context={
                "user_id": cached_data["user_id"],
                "scopes": normalize_mcp_scopes(cached_data.get("scopes")),
                "key_id": cached_data["key_id"],
                "app_id": cached_data["app_id"],
            }
        )

    firestore_client = _db()
    keys_ref = firestore_client.collection("mcp_api_keys").where("hashed_key", "==", hashed_key).limit(1)
    docs = list(keys_ref.stream())

    if not docs:
        return ApiKeyAuthLookupResult(context=None)

    key_doc = docs[0]
    raw: object = key_doc.to_dict()
    key_data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    user_id = api_key_auth_user_id(key_data)
    key_id = key_doc.id if isinstance(key_doc.id, str) and key_doc.id else None
    if user_id is None or key_id is None:
        return ApiKeyAuthLookupResult(context=None)
    repairs: set[ApiKeyAuthRepair] = set()
    if cache_read.mode == ApiKeyCacheReadMode.ERROR:
        repairs.add(ApiKeyAuthRepair.CACHE_READ)
    if key_data.get("id") != key_id:
        repairs.add(ApiKeyAuthRepair.DOCUMENT_ID)
    # Missing app identity predates the app/key grant contract and is repairable.
    # A present malformed identity is ambiguous credential state and must fail auth.
    if "app_id" not in key_data:
        app_id = MCP_DEFAULT_APP_ID
        repairs.add(ApiKeyAuthRepair.APP_ID)
    else:
        app_id = valid_api_key_app_id(key_data.get("app_id"))
        if app_id is None:
            return ApiKeyAuthLookupResult(context=None)
    scopes = normalize_mcp_scopes(key_data.get("scopes"))
    if api_key_scopes_need_repair(
        key_data.get("scopes"),
        scopes,
        allowed_scopes=MCP_FULL_ACCESS_SCOPES,
        missing_is_valid=False,
    ):
        repairs.add(ApiKeyAuthRepair.SCOPES)

    key_ref = key_doc.reference
    key_ref.update({"id": key_id, "last_used_at": datetime.now(timezone.utc), "app_id": app_id, "scopes": scopes})
    if _ensure_mcp_memory_grant(user_id, key_id, app_id, firestore_client):
        repairs.add(ApiKeyAuthRepair.MEMORY_GRANT)
    cache_written = redis_db.cache_mcp_api_key_auth_context(
        hashed_key,
        user_id,
        scopes,
        key_id=key_id,
        app_id=app_id,
        auth_context_version=MCP_API_KEY_AUTH_CONTEXT_VERSION,
    )
    if cache_written is not True:
        repairs.add(ApiKeyAuthRepair.CACHE_WRITE)

    return ApiKeyAuthLookupResult(
        context={"user_id": user_id, "scopes": scopes, "key_id": key_id, "app_id": app_id},
        repairs=frozenset(repairs),
    )


def get_user_and_scopes_by_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    return get_api_key_auth_result(api_key).context
