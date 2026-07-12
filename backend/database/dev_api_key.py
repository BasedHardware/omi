import logging
import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from google.cloud import firestore
from pydantic import ValidationError

import database.redis_db as redis_db
from database._client import db
from database.memory_app_key_grants import (
    remove_developer_api_key_memory_grant,
    seed_developer_api_key_memory_grant,
)
from models.dev_api_key import DevApiKey
from utils.dev_api_keys import generate_dev_api_key, hash_dev_api_key
from utils.scopes import READ_ONLY_SCOPES, Scopes

logger = logging.getLogger(__name__)


def create_dev_key(user_id: str, name: str, scopes: Optional[List[str]] = None) -> Tuple[str, DevApiKey]:
    """
    Creates a new Developer API key for a user.
    If scopes are not provided, defaults to read-only scopes.
    Returns the raw key and the key's metadata.
    """
    raw_key, hashed_key, key_prefix = generate_dev_api_key()

    key_id = str(uuid.uuid4())
    now = datetime.utcnow()

    if scopes is None:
        scopes = READ_ONLY_SCOPES

    api_key_doc = {
        "id": key_id,
        "user_id": user_id,
        "name": name,
        "hashed_key": hashed_key,
        "key_prefix": key_prefix,
        "created_at": now,
        "last_used_at": None,
        "scopes": scopes,
    }

    db.collection("dev_api_keys").document(key_id).set(api_key_doc)

    # Seed the matching app/key memory grant so a freshly created Developer key
    # with memories:read and/or memories:write is immediately usable through
    # the grant gate. Legacy scopes that do not map to memory scopes are skipped.
    grant_default_read = Scopes.MEMORIES_READ in (scopes or [])
    grant_write = Scopes.MEMORIES_WRITE in (scopes or [])
    if grant_default_read or grant_write:
        seed_developer_api_key_memory_grant(
            user_id,
            key_id,
            default_read=grant_default_read,
            write=grant_write,
        )

    api_key_data = DevApiKey(
        id=key_id,
        name=name,
        key_prefix=key_prefix,
        created_at=now,
        last_used_at=None,
        scopes=scopes,
    )
    return raw_key, api_key_data


def get_dev_keys_for_user(user_id: str) -> List[DevApiKey]:
    """
    Retrieves all Developer API keys for a user.
    """
    keys_ref = (
        db.collection("dev_api_keys")
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
    )
    docs = keys_ref.stream()
    keys = []
    for doc in docs:
        key_dict = doc.to_dict()
        # Ensure scopes field is present (None for backward compat)
        if "scopes" not in key_dict:
            key_dict["scopes"] = None
        # Older key docs may omit the id field; fall back to the document id, mirroring
        # get_mcp_keys_for_user. Skip a malformed/legacy key rather than 500 the whole list.
        key_dict["id"] = key_dict.get("id") or doc.id
        try:
            keys.append(DevApiKey.model_validate(key_dict))
        except ValidationError as e:
            logger.warning("Skipping malformed dev API key %s: %s", doc.id, e)
    return keys


def delete_dev_key(user_id: str, key_id: str):
    """
    Deletes a Developer API key.
    """
    key_ref = db.collection("dev_api_keys").document(key_id)
    key_doc = key_ref.get()
    if key_doc.exists:
        key_data = key_doc.to_dict()
        if key_data.get("user_id") == user_id:
            hashed_key = key_data.get("hashed_key")
            if hashed_key:
                redis_db.delete_cached_dev_api_key(hashed_key)
            key_ref.delete()
            # Remove the persisted app/key memory grant for this key so a
            # deleted key can no longer pass the memory grant gate.
            remove_developer_api_key_memory_grant(user_id, key_id)


def get_user_id_by_api_key(api_key: str) -> Optional[str]:
    """
    Verifies a Developer API key and returns the associated user ID.
    Uses a cache to avoid frequent database lookups.
    Also updates the last_used_at timestamp on cache miss.
    """
    user_data = get_user_and_scopes_by_api_key(api_key)
    return user_data.get("user_id") if user_data else None


def get_user_and_scopes_by_api_key(api_key: str) -> Optional[dict]:
    """
    Verifies a Developer API key and returns the associated user ID and scopes.
    Uses a cache to avoid frequent database lookups.
    Also updates the last_used_at timestamp on cache miss.
    Returns dict with 'user_id' and 'scopes' keys, or None if invalid.
    If scopes don't exist in the database, returns None (treated as read-only by has_scope).
    """
    if not api_key.startswith("omi_dev_"):
        return None
    secret_part = api_key.replace("omi_dev_", "", 1)
    hashed_key = hash_dev_api_key(secret_part)

    # Check cache first
    cached_data = redis_db.get_cached_dev_api_key_data(hashed_key)
    if cached_data:
        # Legacy Redis entries predate app/key identity and only contain
        # user_id/scopes. Do not return those for memory authorization paths:
        # fall through to Firestore so otherwise-valid keys recover their real
        # key_id/app_id immediately instead of 403ing until cache TTL expiry.
        if cached_data.get("key_id") and cached_data.get("app_id"):
            return cached_data

    # If not in cache, query database
    keys_ref = db.collection("dev_api_keys").where("hashed_key", "==", hashed_key).limit(1)
    docs = list(keys_ref.stream())

    if not docs:
        return None

    key_doc = docs[0]
    key_data = key_doc.to_dict()
    user_id = key_data.get("user_id")
    key_id = key_data.get("id") or getattr(key_doc, "id", None)
    app_id = key_data.get("app_id") or "developer_api"
    # If scopes field doesn't exist, return None (will be treated as read-only)
    scopes = key_data.get("scopes")

    if user_id:
        # Cache the key with scopes/app/key context (None scopes remain read-only compatible) and update last_used_at
        redis_db.cache_dev_api_key(hashed_key, user_id, scopes, key_id=key_id, app_id=app_id)
        key_ref = key_doc.reference
        key_ref.update({"last_used_at": datetime.utcnow()})

    return {"user_id": user_id, "scopes": scopes, "key_id": key_id, "app_id": app_id}
