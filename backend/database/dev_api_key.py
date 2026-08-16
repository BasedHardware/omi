import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple, cast

import database.redis_db as redis_db
from database._client import get_firestore_client
from database.api_key_metadata import (
    DEV_API_KEY_AUTH_CONTEXT_VERSION,
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
    normalize_api_key_scopes,
    project_api_key_metadata,
)
from database.memory_app_key_grants import (
    remove_developer_api_key_memory_grant,
    seed_developer_api_key_memory_grant,
)
from models.dev_api_key import DevApiKey
from utils.dev_api_keys import generate_dev_api_key, hash_dev_api_key
from utils.scopes import AVAILABLE_SCOPES, READ_ONLY_SCOPES, Scopes

DEV_API_KEY_APP_ID = "developer_api"


def _db() -> Any:
    return get_firestore_client()


def _normalize_dev_scopes(value: object, *, new_key_default: bool = False) -> Optional[list[str]]:
    return normalize_api_key_scopes(
        value,
        allowed_scopes=AVAILABLE_SCOPES,
        missing_scopes=READ_ONLY_SCOPES if new_key_default else None,
    )


def _valid_cached_auth_context(cached_data: dict[str, Any]) -> bool:
    scopes = _normalize_dev_scopes(cached_data.get("scopes"))
    return (
        cached_data.get("auth_context_version") == DEV_API_KEY_AUTH_CONTEXT_VERSION
        and api_key_auth_user_id(cached_data) is not None
        and isinstance(cached_data.get("key_id"), str)
        and bool(cached_data["key_id"])
        and cached_data.get("app_id") == DEV_API_KEY_APP_ID
        and not api_key_scopes_need_repair(
            cached_data.get("scopes"),
            scopes,
            allowed_scopes=AVAILABLE_SCOPES,
            missing_is_valid=True,
        )
    )


def create_dev_key(user_id: str, name: str, scopes: Optional[List[str]] = None) -> Tuple[str, DevApiKey]:
    """
    Creates a new Developer API key for a user.
    If scopes are not provided, defaults to read-only scopes.
    Returns the raw key and the key's metadata.
    """
    if contains_raw_api_key(name):
        raise ApiKeyValidationError("API key name must not contain a raw API key")
    raw_key, hashed_key, key_prefix = generate_dev_api_key()

    key_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    resolved_scopes = _normalize_dev_scopes(scopes, new_key_default=True)
    firestore_client = _db()

    api_key_doc = {
        "id": key_id,
        "user_id": user_id,
        "name": name,
        "hashed_key": hashed_key,
        "key_prefix": key_prefix,
        "created_at": now,
        "last_used_at": None,
        "app_id": DEV_API_KEY_APP_ID,
        "scopes": resolved_scopes,
    }

    firestore_client.collection("dev_api_keys").document(key_id).set(api_key_doc)

    # Seed the matching app/key memory grant so a freshly created Developer key
    # with memories:read and/or memories:write is immediately usable through
    # the grant gate. Legacy scopes that do not map to memory scopes are skipped.
    grant_default_read = Scopes.MEMORIES_READ in (resolved_scopes or [])
    grant_write = Scopes.MEMORIES_WRITE in (resolved_scopes or [])
    if grant_default_read or grant_write:
        seed_developer_api_key_memory_grant(
            user_id,
            key_id,
            default_read=grant_default_read,
            write=grant_write,
            db_client=firestore_client,
        )

    api_key_data = DevApiKey(
        id=key_id,
        name=name,
        key_prefix=key_prefix,
        created_at=now,
        last_used_at=None,
        scopes=resolved_scopes,
    )
    return raw_key, api_key_data


def get_dev_keys_for_user_with_repair_info(
    user_id: str,
) -> tuple[List[DevApiKey], frozenset[ApiKeyMetadataRepair]]:
    """
    Retrieves Developer API keys and bounded metadata-repair reasons for a user.
    """
    keys_ref = _db().collection("dev_api_keys").where("user_id", "==", user_id)
    docs = keys_ref.stream()
    keys: list[DevApiKey] = []
    repairs: set[ApiKeyMetadataRepair] = set()
    for doc in docs:
        raw: object = doc.to_dict()
        data: dict[str, Any] = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        projection = project_api_key_metadata(
            document_id=doc.id,
            raw=data,
            snapshot_create_time=getattr(doc, "create_time", None),
            key_kind="dev",
        )
        projected = projection.metadata
        repairs.update(projection.repairs)
        projected["scopes"] = _normalize_dev_scopes(data.get("scopes"))
        if api_key_scopes_need_repair(
            data.get("scopes"),
            projected["scopes"],
            allowed_scopes=AVAILABLE_SCOPES,
            missing_is_valid=True,
        ):
            repairs.add(ApiKeyMetadataRepair.SCOPES)
        if data.get("app_id") not in (None, DEV_API_KEY_APP_ID):
            repairs.add(ApiKeyMetadataRepair.APP_ID)
        keys.append(DevApiKey.model_validate(projected))
    keys.sort(key=lambda key: key.id)
    keys.sort(key=lambda key: key.created_at, reverse=True)
    return keys, frozenset(repairs)


def get_dev_keys_for_user(user_id: str) -> List[DevApiKey]:
    """Retrieves all Developer API keys for a user."""
    keys, _repairs = get_dev_keys_for_user_with_repair_info(user_id)
    return keys


def delete_dev_key(user_id: str, key_id: str):
    """
    Deletes a Developer API key.
    """
    firestore_client = _db()
    key_ref = firestore_client.collection("dev_api_keys").document(key_id)
    key_doc = key_ref.get()
    if key_doc.exists:
        key_data = key_doc.to_dict()
        if key_data.get("user_id") == user_id:
            hashed_key = key_data.get("hashed_key")
            if not is_valid_api_key_hash(hashed_key):
                raise ApiKeyRevocationUnavailableError("Developer API key credential metadata is invalid")
            try:
                cache_deleted = redis_db.delete_cached_dev_api_key_strict(hashed_key)
            except Exception as exc:
                raise ApiKeyRevocationUnavailableError("Developer API key cache invalidation failed") from exc
            if cache_deleted is not True:
                raise ApiKeyRevocationUnavailableError("Developer API key cache invalidation was not confirmed")
            key_ref.delete()
            # Remove the persisted app/key memory grant for this key so a
            # deleted key can no longer pass the memory grant gate.
            remove_developer_api_key_memory_grant(user_id, key_id, db_client=firestore_client)


def get_user_id_by_api_key(api_key: str) -> Optional[str]:
    """
    Verifies a Developer API key and returns the associated user ID.
    Uses a cache to avoid frequent database lookups.
    Also updates the last_used_at timestamp on cache miss.
    """
    user_data = get_user_and_scopes_by_api_key(api_key)
    return user_data.get("user_id") if user_data else None


def get_api_key_auth_result(api_key: str) -> ApiKeyAuthLookupResult:
    """
    Verifies a Developer API key and returns the associated user ID and scopes.
    Uses a cache to avoid frequent database lookups.
    Also updates the last_used_at timestamp on cache miss.
    Returns dict with 'user_id' and 'scopes' keys, or None if invalid.
    If scopes don't exist in the database, returns None (treated as read-only by has_scope).
    """
    if not api_key.startswith("omi_dev_"):
        return ApiKeyAuthLookupResult(context=None)
    secret_part = api_key.replace("omi_dev_", "", 1)
    hashed_key = hash_dev_api_key(secret_part)

    # Check cache first
    cache_read = redis_db.read_cached_dev_api_key_data(hashed_key)
    cached_data = cache_read.data if cache_read.mode == ApiKeyCacheReadMode.HIT else None
    if cached_data and _valid_cached_auth_context(cached_data):
        return ApiKeyAuthLookupResult(
            context={
                "user_id": cached_data["user_id"],
                "scopes": _normalize_dev_scopes(cached_data.get("scopes")),
                "key_id": cached_data["key_id"],
                "app_id": cached_data["app_id"],
            }
        )

    # If not in cache, query database
    keys_ref = _db().collection("dev_api_keys").where("hashed_key", "==", hashed_key).limit(1)
    docs = list(keys_ref.stream())

    if not docs:
        return ApiKeyAuthLookupResult(context=None)

    key_doc = docs[0]
    raw: object = key_doc.to_dict()
    key_data: dict[str, Any] = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    user_id = api_key_auth_user_id(key_data)
    key_id = key_doc.id if isinstance(key_doc.id, str) and key_doc.id else None
    if user_id is None or key_id is None:
        return ApiKeyAuthLookupResult(context=None)
    repairs: set[ApiKeyAuthRepair] = set()
    if cache_read.mode == ApiKeyCacheReadMode.ERROR:
        repairs.add(ApiKeyAuthRepair.CACHE_READ)
    if key_data.get("id") != key_id:
        repairs.add(ApiKeyAuthRepair.DOCUMENT_ID)
    app_id = DEV_API_KEY_APP_ID
    if key_data.get("app_id") != app_id:
        repairs.add(ApiKeyAuthRepair.APP_ID)
    scopes = _normalize_dev_scopes(key_data.get("scopes"))
    if api_key_scopes_need_repair(
        key_data.get("scopes"),
        scopes,
        allowed_scopes=AVAILABLE_SCOPES,
        missing_is_valid=True,
    ):
        repairs.add(ApiKeyAuthRepair.SCOPES)

    cache_written = redis_db.cache_dev_api_key(
        hashed_key,
        user_id,
        scopes,
        key_id=key_id,
        app_id=app_id,
        auth_context_version=DEV_API_KEY_AUTH_CONTEXT_VERSION,
    )
    if cache_written is not True:
        repairs.add(ApiKeyAuthRepair.CACHE_WRITE)
    key_ref = key_doc.reference
    key_ref.update(
        {
            "id": key_id,
            "last_used_at": datetime.now(timezone.utc),
            "app_id": app_id,
            "scopes": scopes,
        }
    )

    return ApiKeyAuthLookupResult(
        context={"user_id": user_id, "scopes": scopes, "key_id": key_id, "app_id": app_id},
        repairs=frozenset(repairs),
    )


def get_user_and_scopes_by_api_key(api_key: str) -> Optional[dict]:
    return get_api_key_auth_result(api_key).context
