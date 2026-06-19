import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from google.cloud import firestore

import database.redis_db as redis_db
from database._client import db
from models.mcp_api_key import McpApiKey
from utils.mcp_api_keys import generate_api_key, hash_api_key

MCP_DEFAULT_APP_ID = "mcp-api"


def create_mcp_key(
    user_id: str,
    name: str,
    scopes: Optional[List[str]] = None,
    app_id: Optional[str] = MCP_DEFAULT_APP_ID,
) -> Tuple[str, McpApiKey]:
    """
    Creates a new MCP API key for a user.
    Returns the raw key and the key's metadata.

    New keys carry stable server-owned app/key identity for future V17
    authorization. Scopes default to None/no verified scopes so existing keys do
    not implicitly gain memory access; a server-side grant/migration must set
    scopes before V17 MCP route enforcement can authorize.
    """
    raw_key, hashed_key, key_prefix = generate_api_key()
    key_id = str(uuid.uuid4())
    now = datetime.utcnow()

    api_key_doc = {
        "id": key_id,
        "user_id": user_id,
        "name": name,
        "hashed_key": hashed_key,
        "key_prefix": key_prefix,
        "created_at": now,
        "last_used_at": None,
        "app_id": app_id,
        "scopes": scopes,
    }
    db.collection("mcp_api_keys").document(key_id).set(api_key_doc)

    api_key_data = McpApiKey(
        id=key_id,
        name=name,
        key_prefix=key_prefix,
        created_at=now,
        last_used_at=None,
        app_id=app_id,
        scopes=scopes,
    )
    return raw_key, api_key_data


def get_mcp_keys_for_user(user_id: str) -> List[McpApiKey]:
    """
    Retrieves all MCP API keys for a user.
    """
    keys_ref = (
        db.collection("mcp_api_keys")
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
    )
    docs = keys_ref.stream()
    return [McpApiKey.model_validate(doc.to_dict()) for doc in docs]


def delete_mcp_key(user_id: str, key_id: str):
    """
    Deletes an MCP API key.
    """
    key_ref = db.collection("mcp_api_keys").document(key_id)
    key_doc = key_ref.get()
    if key_doc.exists:
        key_data = key_doc.to_dict()
        if key_data.get("user_id") == user_id:
            hashed_key = key_data.get("hashed_key")
            if hashed_key:
                redis_db.delete_cached_mcp_api_key(hashed_key)
            key_ref.delete()


def get_user_id_by_api_key(api_key: str) -> Optional[str]:
    """
    Verifies an API key and returns the associated user ID.
    Uses a cache to avoid frequent database lookups.
    Also updates the last_used_at timestamp on cache miss.
    """
    user_data = get_user_and_scopes_by_api_key(api_key)
    return user_data.get("user_id") if user_data else None


def get_user_and_scopes_by_api_key(api_key: str) -> Optional[dict]:
    """Verifies an MCP API key and returns uid plus persisted app/key/scopes.

    Backward compatibility: old key docs and old Redis entries still authenticate
    uid-only. Missing persisted scopes/app_id remain None, not inferred from MCP
    tool advertisements, so V17 authorization fails closed.
    """
    if not api_key.startswith("omi_mcp_"):
        return None
    secret_part = api_key.replace("omi_mcp_", "", 1)
    hashed_key = hash_api_key(secret_part)

    cached_data = redis_db.get_cached_mcp_api_key_auth_context(hashed_key)
    if cached_data:
        return cached_data

    keys_ref = db.collection("mcp_api_keys").where("hashed_key", "==", hashed_key).limit(1)
    docs = list(keys_ref.stream())

    if not docs:
        return None

    key_doc = docs[0]
    key_data = key_doc.to_dict() or {}
    user_id = key_data.get("user_id")
    key_id = key_data.get("id") or getattr(key_doc, "id", None)
    app_id = key_data.get("app_id")
    scopes = key_data.get("scopes")

    if user_id:
        redis_db.cache_mcp_api_key_auth_context(hashed_key, user_id, scopes, key_id=key_id, app_id=app_id)
        key_ref = key_doc.reference
        key_ref.update({"last_used_at": datetime.utcnow()})

    return {"user_id": user_id, "scopes": scopes, "key_id": key_id, "app_id": app_id}
