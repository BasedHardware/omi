import uuid
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional, Tuple, cast

from google.cloud import firestore
from pydantic import ValidationError

import database.redis_db as redis_db
from database._client import get_firestore_client
from models.mcp_api_key import McpApiKey
from utils.mcp_api_keys import generate_api_key, hash_api_key
from utils.mcp_scopes import (
    MCP_API_KEY_AUTH_CONTEXT_VERSION,
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


def _cache_repair_needed(cached_data: Dict[str, Any]) -> bool:
    if cached_data.get("auth_context_version") != MCP_API_KEY_AUTH_CONTEXT_VERSION:
        return True
    if not cached_data.get("app_id"):
        return True
    return not set(MCP_FULL_ACCESS_SCOPES).issubset(set(cached_data.get("scopes") or []))


def _repair_mcp_key_access(
    user_id: str,
    key_id: str,
    app_id: str,
    scopes: list[str],
    firestore_client: Any = None,
) -> None:
    firestore_client = firestore_client or _db()
    firestore_client.collection("mcp_api_keys").document(key_id).update(
        {"id": key_id, "app_id": app_id, "scopes": scopes, "updated_at": datetime.now(timezone.utc)}
    )
    _seed_mcp_memory_grant(user_id, key_id, app_id, firestore_client=firestore_client)


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
    raw_key, hashed_key, key_prefix = generate_api_key()
    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    resolved_app_id = app_id or MCP_DEFAULT_APP_ID
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


def get_mcp_keys_for_user(user_id: str) -> list[McpApiKey]:
    """
    Retrieves all MCP API keys for a user.
    """
    keys_ref = (
        _db()
        .collection("mcp_api_keys")
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
    )
    docs = keys_ref.stream()
    keys: list[McpApiKey] = []
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        # Older key docs may omit the id field; fall back to the document id, mirroring the other
        # readers in this module. Skip a genuinely malformed/legacy key rather than 500 the whole list.
        data["id"] = data.get("id") or doc.id
        try:
            keys.append(McpApiKey.model_validate(data))
        except ValidationError as e:
            logger.warning("Skipping malformed MCP key %s: %s", doc.id, e)
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
            if hashed_key:
                redis_db.delete_cached_mcp_api_key(hashed_key)
            _delete_mcp_memory_grant(
                user_id,
                key_data.get("id") or key_id,
                key_data.get("app_id") or MCP_DEFAULT_APP_ID,
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


def get_user_and_scopes_by_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Verifies an MCP API key and returns uid plus server-owned app/key/scopes.

    MCP keys are full-access agent keys. Older key documents may be missing the
    app identity, scopes, and memory grant state introduced by the app/key grant
    layer; repair them lazily on successful authentication so existing agents
    keep working without regenerating keys.
    """
    if not api_key.startswith("omi_mcp_"):
        return None
    secret_part = api_key.replace("omi_mcp_", "", 1)
    hashed_key = hash_api_key(secret_part)

    cached_data: Optional[Dict[str, Any]] = redis_db.get_cached_mcp_api_key_auth_context(hashed_key)
    if cached_data and cached_data.get("user_id") and cached_data.get("key_id"):
        cached_data["app_id"] = cached_data.get("app_id") or MCP_DEFAULT_APP_ID
        cached_data["scopes"] = normalize_mcp_scopes(cached_data.get("scopes"))
        if _cache_repair_needed(cached_data):
            try:
                _repair_mcp_key_access(
                    cached_data["user_id"],
                    cached_data["key_id"],
                    cached_data["app_id"],
                    cached_data["scopes"],
                )
            except Exception as e:
                logger.warning(
                    "Failed to repair cached MCP key access for uid=%s key_id=%s: %s",
                    cached_data["user_id"],
                    cached_data["key_id"],
                    e,
                )
        redis_db.cache_mcp_api_key_auth_context(
            hashed_key,
            cached_data["user_id"],
            cached_data["scopes"],
            key_id=cached_data["key_id"],
            app_id=cached_data["app_id"],
        )
        return cached_data

    firestore_client = _db()
    keys_ref = firestore_client.collection("mcp_api_keys").where("hashed_key", "==", hashed_key).limit(1)
    docs = list(keys_ref.stream())

    if not docs:
        return None

    key_doc = docs[0]
    raw: object = key_doc.to_dict()
    key_data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
    user_id = key_data.get("user_id")
    key_id = key_data.get("id") or key_doc.id
    app_id = key_data.get("app_id") or MCP_DEFAULT_APP_ID
    scopes = normalize_mcp_scopes(key_data.get("scopes"))

    if user_id:
        key_ref = key_doc.reference
        key_ref.update({"id": key_id, "last_used_at": datetime.now(timezone.utc), "app_id": app_id, "scopes": scopes})
        _seed_mcp_memory_grant(user_id, key_id, app_id, firestore_client=firestore_client)
        redis_db.cache_mcp_api_key_auth_context(hashed_key, user_id, scopes, key_id=key_id, app_id=app_id)

    return {"user_id": user_id, "scopes": scopes, "key_id": key_id, "app_id": app_id}
