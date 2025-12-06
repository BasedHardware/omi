import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from google.cloud import firestore

import database.redis_db as redis_db
from database._client import db
from models.dev_api_key import DevApiKey
from utils.dev_api_keys import generate_dev_api_key, hash_dev_api_key
from utils.scopes import READ_ONLY_SCOPES


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
        keys.append(DevApiKey.model_validate(key_dict))
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
        return cached_data

    # If not in cache, query database
    keys_ref = db.collection("dev_api_keys").where("hashed_key", "==", hashed_key).limit(1)
    docs = list(keys_ref.stream())

    if not docs:
        return None

    key_doc = docs[0]
    key_data = key_doc.to_dict()
    user_id = key_data.get("user_id")
    # If scopes field doesn't exist, return None (will be treated as read-only)
    scopes = key_data.get("scopes")

    if user_id:
        # Cache the key with scopes (None if not present) and update last_used_at
        redis_db.cache_dev_api_key(hashed_key, user_id, scopes)
        key_ref = key_doc.reference
        key_ref.update({"last_used_at": datetime.utcnow()})

    return {"user_id": user_id, "scopes": scopes}
