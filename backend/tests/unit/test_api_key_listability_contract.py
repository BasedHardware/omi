import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.dev_api_key as dev_api_key_db
import database.mcp_api_key as mcp_api_key_db
import database.redis_db as redis_db
from database.api_key_metadata import (
    ApiKeyAuthRepair,
    ApiKeyCacheReadMode,
    ApiKeyCacheReadResult,
    ApiKeyMetadataRepair,
    ApiKeyRevocationUnavailableError,
    ApiKeyValidationError,
)
from tests.store_fakes import FakeDocumentStore


def _dev_store(seed=()):
    """Build a FakeDocumentStore for the (migrated) dev_api_key module over ``dev_api_keys``.

    ``seed`` is an iterable of ``(doc_id, data, create_time)``. ``create_time`` maps to the
    neutral last-write revision (``StoredDocument.updated_at``) the migrated module reads as the
    legacy ``created_at`` fallback; pass ``None`` to leave a doc without a revision (→ epoch
    fallback). Docs are placed directly in the backing dict so pre-seeded revisions are exactly
    what the test asked for, not a write timestamp.
    """
    docs: dict[str, Any] = {}
    updated: dict[str, Any] = {}
    for doc_id, data, create_time in seed:
        path = f"dev_api_keys/{doc_id}"
        docs[path] = dict(data)
        if create_time is not None:
            updated[path] = create_time
    store = FakeDocumentStore(backing=docs)
    store._updated.update(updated)
    return store


def _mcp_store(seed=()):
    """Build a FakeDocumentStore for the (migrated) mcp_api_key module over ``mcp_api_keys``.

    Same contract as ``_dev_store`` but scoped to the ``mcp_api_keys`` collection. ``create_time``
    maps to ``StoredDocument.updated_at`` — the neutral revision the migrated module reads as the
    legacy ``created_at`` fallback — and is seeded directly into the backing so a pre-seeded
    revision stays exact rather than becoming a write timestamp.
    """
    docs: dict[str, Any] = {}
    updated: dict[str, Any] = {}
    for doc_id, data, create_time in seed:
        path = f"mcp_api_keys/{doc_id}"
        docs[path] = dict(data)
        if create_time is not None:
            updated[path] = create_time
    store = FakeDocumentStore(backing=docs)
    store._updated.update(updated)
    return store


def _mcp_grant_path(user_id: str) -> str:
    return (
        f"users/{user_id}/{mcp_api_key_db.MCP_MEMORY_CONTROL_COLLECTION}"
        f"/{mcp_api_key_db.MCP_APP_KEY_MEMORY_GRANTS_DOC_ID}"
    )


class _Redis:
    def __init__(self):
        self.mcp_context: Optional[dict[str, Any]] = None
        self.dev_context: Optional[dict[str, Any]] = None

    def read_cached_mcp_api_key_auth_context(self, _hashed_key: str) -> ApiKeyCacheReadResult:
        if self.mcp_context is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.HIT, data=dict(self.mcp_context))

    def cache_mcp_api_key_auth_context(
        self,
        _hashed_key: str,
        user_id: str,
        scopes: Optional[list[str]] = None,
        key_id: Optional[str] = None,
        app_id: Optional[str] = None,
        memory_grant_seeded: bool = True,
        auth_context_version: int = mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION,
    ) -> bool:
        self.mcp_context = {
            "user_id": user_id,
            "scopes": scopes,
            "key_id": key_id,
            "app_id": app_id,
            "memory_grant_seeded": memory_grant_seeded,
            "auth_context_version": auth_context_version,
        }
        return True

    def delete_cached_mcp_api_key_strict(self, _hashed_key: str) -> bool:
        self.mcp_context = None
        return True

    def read_cached_dev_api_key_data(self, _hashed_key: str) -> ApiKeyCacheReadResult:
        if self.dev_context is None:
            return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.MISS)
        return ApiKeyCacheReadResult(mode=ApiKeyCacheReadMode.HIT, data=dict(self.dev_context))

    def cache_dev_api_key(
        self,
        _hashed_key: str,
        user_id: str,
        scopes: Optional[list[str]] = None,
        ttl: int = 3600,
        key_id: Optional[str] = None,
        app_id: Optional[str] = None,
        auth_context_version: int = dev_api_key_db.DEV_API_KEY_AUTH_CONTEXT_VERSION,
    ) -> bool:
        del ttl
        self.dev_context = {
            "user_id": user_id,
            "scopes": scopes,
            "key_id": key_id,
            "app_id": app_id,
            "auth_context_version": auth_context_version,
        }
        return True

    def delete_cached_dev_api_key_strict(self, _hashed_key: str) -> bool:
        self.dev_context = None
        return True


class _RedisKeyValueStore:
    def __init__(self):
        self.values: dict[str, object] = {}

    def set(self, key: str, value: object, ex: Optional[int] = None) -> None:
        del ex
        self.values[key] = value

    def get(self, key: str) -> object:
        value = self.values.get(key)
        return value.encode() if isinstance(value, str) else value

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.values.pop(key, None)


class _FailingRedisKeyValueStore(_RedisKeyValueStore):
    def set(self, key: str, value: object, ex: Optional[int] = None) -> None:
        del key, value, ex
        raise RuntimeError("redis unavailable")


class _ReadFailingRedisKeyValueStore(_RedisKeyValueStore):
    def get(self, key: str) -> object:
        del key
        raise RuntimeError("redis read unavailable")


class _DeleteFailingRedisKeyValueStore(_RedisKeyValueStore):
    def __init__(self):
        super().__init__()
        self.delete_calls: list[tuple[str, ...]] = []

    def delete(self, *keys: str) -> None:
        self.delete_calls.append(keys)
        raise RuntimeError("redis delete unavailable")


def _mcp_grant_keys(store: FakeDocumentStore, user_id: str) -> dict[str, Any]:
    grant = store.get(_mcp_grant_path(user_id)).to_dict()
    return grant["grants"]["mcp"]["apps"][mcp_api_key_db.MCP_DEFAULT_APP_ID]["keys"]


def test_mcp_key_authentication_metadata_projection_and_revocation_share_document_identity(monkeypatch):
    raw_token = "omi_mcp_0123456789abcdef0123456789abcdef"
    store = _mcp_store(
        [
            (
                "canonical-mcp-id",
                {
                    "id": "embedded-wrong-id",
                    "user_id": "user-1",
                    "hashed_key": mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_")),
                    "name": raw_token,
                    "key_prefix": raw_token,
                    "created_at": "not-a-time",
                    "last_used_at": "not-a-time",
                    "scopes": "memories.read",
                },
                datetime(2024, 1, 2),
            )
        ]
    )
    redis = _Redis()
    redis.mcp_context = {
        "user_id": "user-1",
        "key_id": "embedded-wrong-id",
        "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
        "scopes": mcp_api_key_db.MCP_FULL_ACCESS_SCOPES,
    }
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)

    auth_result = mcp_api_key_db.get_api_key_auth_result(raw_token)
    auth = auth_result.context

    assert auth == {
        "user_id": "user-1",
        "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        "key_id": "canonical-mcp-id",
        "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
    }
    assert auth_result.repairs == {
        ApiKeyAuthRepair.DOCUMENT_ID,
        ApiKeyAuthRepair.APP_ID,
        ApiKeyAuthRepair.SCOPES,
        ApiKeyAuthRepair.MEMORY_GRANT,
    }
    assert redis.mcp_context["auth_context_version"] == mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION
    assert redis.mcp_context["key_id"] == "canonical-mcp-id"
    assert set(_mcp_grant_keys(store, "user-1")) == {"canonical-mcp-id"}

    listed, repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info("user-1")

    assert [key.id for key in listed] == ["canonical-mcp-id"]
    assert listed[0].name == "Legacy MCP API key"
    assert listed[0].key_prefix == "omi_mcp_legacy"
    # Corrupt stored created_at falls back to the document's neutral last-write revision; the auth
    # call above rewrote the document, so that revision is now the current write, not the seeded one.
    assert listed[0].created_at == store.get("mcp_api_keys/canonical-mcp-id").updated_at
    assert listed[0].created_at.tzinfo == timezone.utc
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in listed])
    assert repairs == {
        ApiKeyMetadataRepair.NAME,
        ApiKeyMetadataRepair.KEY_PREFIX,
        ApiKeyMetadataRepair.CREATED_AT,
    }

    mcp_api_key_db.delete_mcp_key("user-1", listed[0].id)

    assert _mcp_grant_keys(store, "user-1") == {}
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token) is None


def test_developer_key_authentication_metadata_projection_and_revocation_share_document_identity(monkeypatch):
    raw_token = "omi_dev_0123456789abcdef0123456789abcdef"
    store = _dev_store(
        [
            (
                "canonical-dev-id",
                {
                    "id": "embedded-wrong-id",
                    "user_id": "user-1",
                    "hashed_key": dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_")),
                    "name": raw_token,
                    "key_prefix": raw_token,
                    "created_at": None,
                    "last_used_at": {"invalid": True},
                    "app_id": raw_token,
                    "scopes": ["memories:read", "unknown", 7],
                },
                datetime(2024, 2, 3, tzinfo=timezone.utc),
            )
        ]
    )
    redis = _Redis()
    redis.dev_context = {
        "user_id": "user-1",
        "key_id": "embedded-wrong-id",
        "app_id": "developer_api",
        "scopes": ["memories:write"],
    }
    removed_grants: list[tuple[str, str]] = []
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(dev_api_key_db, "redis_db", redis)
    monkeypatch.setattr(
        dev_api_key_db,
        "remove_developer_api_key_memory_grant",
        lambda user_id, key_id, **_kwargs: removed_grants.append((user_id, key_id)),
    )

    initial_list, initial_repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info("user-1")

    assert initial_repairs == set(ApiKeyMetadataRepair)
    # Corrupt stored created_at falls back to the document's neutral last-write revision; before any
    # write that revision is exactly the seeded one.
    assert initial_list[0].created_at == datetime(2024, 2, 3, tzinfo=timezone.utc)
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in initial_list])

    auth_result = dev_api_key_db.get_api_key_auth_result(raw_token)
    auth = auth_result.context

    assert auth == {
        "user_id": "user-1",
        "scopes": ["memories:read"],
        "key_id": "canonical-dev-id",
        "app_id": "developer_api",
    }
    assert auth_result.repairs == {
        ApiKeyAuthRepair.DOCUMENT_ID,
        ApiKeyAuthRepair.APP_ID,
        ApiKeyAuthRepair.SCOPES,
    }
    assert redis.dev_context["auth_context_version"] == dev_api_key_db.DEV_API_KEY_AUTH_CONTEXT_VERSION
    assert redis.dev_context["key_id"] == "canonical-dev-id"

    listed = dev_api_key_db.get_dev_keys_for_user("user-1")

    assert [key.id for key in listed] == ["canonical-dev-id"]
    assert listed[0].name == "Legacy Developer API key"
    assert listed[0].key_prefix == "omi_dev_legacy"
    # The auth call above rewrote the document, so the corrupt-created_at fallback now tracks the
    # document's current neutral revision (a valid UTC datetime), not the original seeded time.
    assert listed[0].created_at == store.get("dev_api_keys/canonical-dev-id").updated_at
    assert listed[0].created_at.tzinfo == timezone.utc
    assert listed[0].scopes == ["memories:read"]
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in listed])

    dev_api_key_db.delete_dev_key("user-1", listed[0].id)

    assert removed_grants == [("user-1", "canonical-dev-id")]
    assert dev_api_key_db.get_user_and_scopes_by_api_key(raw_token) is None


def test_mcp_present_poisoned_app_identity_fails_auth_but_remains_safely_listable(monkeypatch):
    raw_token = "omi_mcp_fedcba9876543210fedcba9876543210"
    overflowing_datetime = datetime.max.replace(tzinfo=timezone(-timedelta(hours=23)))
    store = _mcp_store(
        [
            (
                "poisoned-mcp-id",
                {
                    "user_id": "user-1",
                    "hashed_key": mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_")),
                    "name": f"Unsafe {raw_token}",
                    "key_prefix": raw_token,
                    "created_at": overflowing_datetime,
                    "last_used_at": raw_token,
                    "app_id": raw_token,
                    "scopes": [raw_token],
                },
                None,
            )
        ]
    )
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)

    listed, repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info("user-1")

    assert repairs == set(ApiKeyMetadataRepair)
    assert listed[0].name == "Legacy MCP API key"
    assert listed[0].key_prefix == "omi_mcp_legacy"
    assert listed[0].app_id == mcp_api_key_db.MCP_DEFAULT_APP_ID
    assert listed[0].created_at == datetime(1970, 1, 1, tzinfo=timezone.utc)
    assert raw_token not in json.dumps([key.model_dump(mode="json") for key in listed])
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token) is None


def test_missing_created_at_uses_snapshot_time_then_epoch_with_deterministic_ties(monkeypatch):
    mcp_store = _mcp_store(
        (
            doc_id,
            {"user_id": "user-1", "created_at": "invalid", "key_prefix": "omi_mcp_raw-secret"},
            create_time,
        )
        for doc_id, create_time in (
            ("mcp-b-epoch", None),
            ("mcp-newer", datetime(2025, 1, 1, tzinfo=timezone.utc)),
            ("mcp-a-epoch", None),
        )
    )
    store = _dev_store(
        (
            doc_id,
            {"user_id": "user-1", "created_at": "invalid", "key_prefix": "omi_dev_raw-secret"},
            create_time,
        )
        for doc_id, create_time in (
            ("dev-b-epoch", None),
            ("dev-newer", datetime(2025, 1, 1, tzinfo=timezone.utc)),
            ("dev-a-epoch", None),
        )
    )
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: mcp_store)
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: store)

    mcp_keys = mcp_api_key_db.get_mcp_keys_for_user("user-1")
    dev_keys = dev_api_key_db.get_dev_keys_for_user("user-1")

    assert [key.id for key in mcp_keys] == ["mcp-newer", "mcp-a-epoch", "mcp-b-epoch"]
    assert [key.id for key in dev_keys] == ["dev-newer", "dev-a-epoch", "dev-b-epoch"]
    assert all(key.created_at.tzinfo == timezone.utc for key in [*mcp_keys, *dev_keys])
    assert {key.key_prefix for key in mcp_keys} == {"omi_mcp_legacy"}
    assert {key.key_prefix for key in dev_keys} == {"omi_dev_legacy"}


def test_equivalent_reordered_scope_lists_keep_canonical_order_without_repairs(monkeypatch):
    mcp_token = "omi_mcp_11111111111111111111111111111111"
    dev_token = "omi_dev_22222222222222222222222222222222"
    mcp_scopes = sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES)
    dev_scopes = ["conversations:read", "memories:read"]
    mcp_store = _mcp_store(
        [
            (
                "mcp-key",
                {
                    "id": "mcp-key",
                    "user_id": "user-1",
                    "hashed_key": mcp_api_key_db.hash_api_key(mcp_token.removeprefix("omi_mcp_")),
                    "name": "MCP key",
                    "key_prefix": "omi_mcp_abcd...1234",
                    "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
                    "scopes": list(reversed(mcp_scopes)),
                },
                None,
            )
        ]
    )
    store = _dev_store(
        [
            (
                "dev-key",
                {
                    "id": "dev-key",
                    "user_id": "user-1",
                    "hashed_key": dev_api_key_db.hash_dev_api_key(dev_token.removeprefix("omi_dev_")),
                    "name": "Developer key",
                    "key_prefix": "omi_dev_abcd...1234",
                    "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
                    "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
                    "scopes": list(reversed(dev_scopes)),
                },
                None,
            )
        ]
    )
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: mcp_store)
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: store)
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(dev_api_key_db, "redis_db", redis)

    mcp_keys, mcp_repairs = mcp_api_key_db.get_mcp_keys_for_user_with_repair_info("user-1")
    dev_keys, dev_repairs = dev_api_key_db.get_dev_keys_for_user_with_repair_info("user-1")

    assert mcp_repairs == frozenset()
    assert dev_repairs == frozenset()
    assert mcp_keys[0].scopes == mcp_scopes
    assert dev_keys[0].scopes == dev_scopes

    mcp_auth = mcp_api_key_db.get_api_key_auth_result(mcp_token)
    dev_auth = dev_api_key_db.get_api_key_auth_result(dev_token)

    assert ApiKeyAuthRepair.SCOPES not in mcp_auth.repairs
    assert ApiKeyAuthRepair.SCOPES not in dev_auth.repairs


def test_authentication_fails_when_auth_critical_user_identity_is_whitespace(monkeypatch):
    mcp_token = "omi_mcp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    dev_token = "omi_dev_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    mcp_store = _mcp_store(
        [
            (
                "mcp-whitespace-user",
                {
                    "hashed_key": mcp_api_key_db.hash_api_key(mcp_token.removeprefix("omi_mcp_")),
                    "user_id": "   ",
                },
                None,
            )
        ]
    )
    store = _dev_store(
        [
            (
                "dev-whitespace-user",
                {
                    "hashed_key": dev_api_key_db.hash_dev_api_key(dev_token.removeprefix("omi_dev_")),
                    "user_id": "\t",
                },
                None,
            )
        ]
    )
    redis = _Redis()
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: mcp_store)
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "redis_db", redis)
    monkeypatch.setattr(dev_api_key_db, "redis_db", redis)

    assert mcp_api_key_db.get_user_and_scopes_by_api_key(mcp_token) is None
    assert dev_api_key_db.get_user_and_scopes_by_api_key(dev_token) is None


def test_developer_auth_survives_redis_cache_write_failure(monkeypatch):
    raw_token = "omi_dev_cccccccccccccccccccccccccccccccc"
    store = _dev_store(
        [
            (
                "dev-cache-failure",
                {
                    "hashed_key": dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_")),
                    "user_id": "user-1",
                    "scopes": ["memories:read"],
                },
                None,
            )
        ]
    )
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(redis_db, "r", _FailingRedisKeyValueStore())

    auth_result = dev_api_key_db.get_api_key_auth_result(raw_token)
    auth = auth_result.context

    assert auth == {
        "user_id": "user-1",
        "scopes": ["memories:read"],
        "key_id": "dev-cache-failure",
        "app_id": "developer_api",
    }
    assert auth_result.repairs == {
        ApiKeyAuthRepair.DOCUMENT_ID,
        ApiKeyAuthRepair.APP_ID,
        ApiKeyAuthRepair.CACHE_WRITE,
    }
    repaired = store.get("dev_api_keys/dev-cache-failure").to_dict()
    assert repaired["last_used_at"] is not None


def test_mcp_auth_reports_redis_cache_write_failure_after_full_recovery(monkeypatch):
    raw_token = "omi_mcp_33333333333333333333333333333333"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    store = _mcp_store(
        [
            (
                "mcp-cache-failure",
                {
                    "id": "mcp-cache-failure",
                    "user_id": "user-1",
                    "hashed_key": hashed_key,
                    "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
                    "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
                },
                None,
            )
        ]
    )
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "mcp-cache-failure")
    monkeypatch.setattr(redis_db, "r", _FailingRedisKeyValueStore())

    auth_result = mcp_api_key_db.get_api_key_auth_result(raw_token)

    assert auth_result.context is not None
    assert auth_result.context["key_id"] == "mcp-cache-failure"
    assert auth_result.repairs == {ApiKeyAuthRepair.CACHE_WRITE}


def test_mcp_auth_reports_cache_read_error_after_firestore_recovery(monkeypatch):
    raw_token = "omi_mcp_44444444444444444444444444444444"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    store = _mcp_store(
        [
            (
                "mcp-cache-read-failure",
                {
                    "id": "mcp-cache-read-failure",
                    "user_id": "user-1",
                    "hashed_key": hashed_key,
                    "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
                    "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
                },
                None,
            )
        ]
    )
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: store)
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "mcp-cache-read-failure")
    monkeypatch.setattr(redis_db, "r", _ReadFailingRedisKeyValueStore())

    auth_result = mcp_api_key_db.get_api_key_auth_result(raw_token)

    assert auth_result.context is not None
    assert auth_result.context["key_id"] == "mcp-cache-read-failure"
    assert auth_result.repairs == {ApiKeyAuthRepair.CACHE_READ}


def test_developer_auth_reports_cache_read_error_after_firestore_recovery(monkeypatch):
    raw_token = "omi_dev_55555555555555555555555555555555"
    hashed_key = dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_"))
    store = _dev_store(
        [
            (
                "dev-cache-read-failure",
                {
                    "id": "dev-cache-read-failure",
                    "user_id": "user-1",
                    "hashed_key": hashed_key,
                    "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
                    "scopes": ["memories:read"],
                },
                None,
            )
        ]
    )
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(redis_db, "r", _ReadFailingRedisKeyValueStore())

    auth_result = dev_api_key_db.get_api_key_auth_result(raw_token)

    assert auth_result.context is not None
    assert auth_result.context["key_id"] == "dev-cache-read-failure"
    assert auth_result.repairs == {ApiKeyAuthRepair.CACHE_READ}


def test_cache_delete_failure_preserves_mcp_document_grant_and_current_auth(monkeypatch):
    raw_token = "omi_mcp_dddddddddddddddddddddddddddddddd"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    doc_store = _mcp_store(
        [
            (
                "mcp-revoke-failure",
                {
                    "id": "mcp-revoke-failure",
                    "user_id": "user-1",
                    "hashed_key": hashed_key,
                    "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
                    "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
                },
                None,
            )
        ]
    )
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: doc_store)
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "mcp-revoke-failure")
    store = _DeleteFailingRedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)
    assert redis_db.cache_mcp_api_key_auth_context(
        hashed_key,
        "user-1",
        sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        key_id="mcp-revoke-failure",
        app_id=mcp_api_key_db.MCP_DEFAULT_APP_ID,
    )

    with pytest.raises(ApiKeyRevocationUnavailableError):
        mcp_api_key_db.delete_mcp_key("user-1", "mcp-revoke-failure")

    assert store.delete_calls == [
        (f"mcp_api_key:{hashed_key}", f"mcp_api_key_auth:{hashed_key}"),
    ]
    assert doc_store.exists("mcp_api_keys/mcp-revoke-failure") is True
    assert set(_mcp_grant_keys(doc_store, "user-1")) == {"mcp-revoke-failure"}
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "mcp-revoke-failure"


def test_cache_delete_failure_preserves_developer_document_and_current_auth(monkeypatch):
    raw_token = "omi_dev_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    hashed_key = dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_"))
    doc_store = _dev_store(
        [
            (
                "dev-revoke-failure",
                {
                    "id": "dev-revoke-failure",
                    "user_id": "user-1",
                    "hashed_key": hashed_key,
                    "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
                    "scopes": ["memories:read"],
                },
                None,
            )
        ]
    )
    store = _DeleteFailingRedisKeyValueStore()
    remove_grant = MagicMock()
    monkeypatch.setattr(redis_db, "r", store)
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: doc_store)
    monkeypatch.setattr(dev_api_key_db, "remove_developer_api_key_memory_grant", remove_grant)
    assert redis_db.cache_dev_api_key(
        hashed_key,
        "user-1",
        ["memories:read"],
        key_id="dev-revoke-failure",
        app_id=dev_api_key_db.DEV_API_KEY_APP_ID,
    )

    with pytest.raises(ApiKeyRevocationUnavailableError):
        dev_api_key_db.delete_dev_key("user-1", "dev-revoke-failure")

    assert store.delete_calls == [(f"dev_api_key:{hashed_key}",)]
    assert doc_store.exists("dev_api_keys/dev-revoke-failure") is True
    remove_grant.assert_not_called()
    assert dev_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "dev-revoke-failure"


@pytest.mark.parametrize("corrupt_hash", [None, "", " ", 7, "not-a-hash"])
def test_corrupt_hash_blocks_mcp_revocation_before_document_grant_or_current_cache_mutation(monkeypatch, corrupt_hash):
    raw_token = "omi_mcp_66666666666666666666666666666666"
    hashed_key = mcp_api_key_db.hash_api_key(raw_token.removeprefix("omi_mcp_"))
    doc_store = _mcp_store(
        [
            (
                "mcp-corrupt-hash",
                {
                    "id": "mcp-corrupt-hash",
                    "user_id": "user-1",
                    "hashed_key": corrupt_hash,
                    "app_id": mcp_api_key_db.MCP_DEFAULT_APP_ID,
                    "scopes": sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
                },
                None,
            )
        ]
    )
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: doc_store)
    mcp_api_key_db._seed_mcp_memory_grant("user-1", "mcp-corrupt-hash")
    store = _RedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)
    assert redis_db.cache_mcp_api_key_auth_context(
        hashed_key,
        "user-1",
        sorted(mcp_api_key_db.MCP_FULL_ACCESS_SCOPES),
        key_id="mcp-corrupt-hash",
        app_id=mcp_api_key_db.MCP_DEFAULT_APP_ID,
    )
    cached_before = dict(store.values)

    with pytest.raises(ApiKeyRevocationUnavailableError):
        mcp_api_key_db.delete_mcp_key("user-1", "mcp-corrupt-hash")

    assert store.values == cached_before
    assert doc_store.exists("mcp_api_keys/mcp-corrupt-hash") is True
    assert set(_mcp_grant_keys(doc_store, "user-1")) == {"mcp-corrupt-hash"}
    assert mcp_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "mcp-corrupt-hash"


@pytest.mark.parametrize("corrupt_hash", [None, "", " ", 7, "not-a-hash"])
def test_corrupt_hash_blocks_developer_revocation_before_document_grant_or_current_cache_mutation(
    monkeypatch, corrupt_hash
):
    raw_token = "omi_dev_77777777777777777777777777777777"
    hashed_key = dev_api_key_db.hash_dev_api_key(raw_token.removeprefix("omi_dev_"))
    doc_store = _dev_store(
        [
            (
                "dev-corrupt-hash",
                {
                    "id": "dev-corrupt-hash",
                    "user_id": "user-1",
                    "hashed_key": corrupt_hash,
                    "app_id": dev_api_key_db.DEV_API_KEY_APP_ID,
                    "scopes": ["memories:read"],
                },
                None,
            )
        ]
    )
    store = _RedisKeyValueStore()
    remove_grant = MagicMock()
    monkeypatch.setattr(redis_db, "r", store)
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: doc_store)
    monkeypatch.setattr(dev_api_key_db, "remove_developer_api_key_memory_grant", remove_grant)
    assert redis_db.cache_dev_api_key(
        hashed_key,
        "user-1",
        ["memories:read"],
        key_id="dev-corrupt-hash",
        app_id=dev_api_key_db.DEV_API_KEY_APP_ID,
    )
    cached_before = dict(store.values)

    with pytest.raises(ApiKeyRevocationUnavailableError):
        dev_api_key_db.delete_dev_key("user-1", "dev-corrupt-hash")

    assert store.values == cached_before
    assert doc_store.exists("dev_api_keys/dev-corrupt-hash") is True
    remove_grant.assert_not_called()
    assert dev_api_key_db.get_user_and_scopes_by_api_key(raw_token)["key_id"] == "dev-corrupt-hash"


def test_raw_token_names_are_rejected_before_generation_or_write(monkeypatch):
    mcp_store = _mcp_store()
    store = _dev_store()
    mcp_generate = MagicMock()
    dev_generate = MagicMock()
    monkeypatch.setattr(mcp_api_key_db, "_store", lambda: mcp_store)
    monkeypatch.setattr(dev_api_key_db, "_store", lambda: store)
    monkeypatch.setattr(mcp_api_key_db, "generate_api_key", mcp_generate)
    monkeypatch.setattr(dev_api_key_db, "generate_dev_api_key", dev_generate)

    with pytest.raises(ApiKeyValidationError, match="must not contain a raw API key"):
        mcp_api_key_db.create_mcp_key("user-1", "omi_mcp_ffffffffffffffffffffffffffffffff")
    with pytest.raises(ApiKeyValidationError, match="must not contain a raw API key"):
        dev_api_key_db.create_dev_key("user-1", "omi_dev_ffffffffffffffffffffffffffffffff")

    mcp_generate.assert_not_called()
    dev_generate.assert_not_called()
    assert mcp_store.query("mcp_api_keys") == []
    assert store.query("dev_api_keys") == []


def test_redis_auth_context_adapters_persist_current_schema_versions(monkeypatch):
    store = _RedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)

    redis_db.cache_mcp_api_key_auth_context(
        "mcp-hash",
        "user-1",
        ["memories.read"],
        key_id="mcp-key",
        app_id="mcp-api",
    )
    redis_db.cache_dev_api_key(
        "dev-hash",
        "user-1",
        ["memories:read"],
        key_id="dev-key",
        app_id="developer_api",
    )

    mcp_context = redis_db.get_cached_mcp_api_key_auth_context("mcp-hash")
    dev_context = redis_db.get_cached_dev_api_key_data("dev-hash")
    assert mcp_context is not None
    assert dev_context is not None
    assert mcp_context["auth_context_version"] == mcp_api_key_db.MCP_API_KEY_AUTH_CONTEXT_VERSION
    assert dev_context["auth_context_version"] == dev_api_key_db.DEV_API_KEY_AUTH_CONTEXT_VERSION


def test_redis_auth_cache_reads_distinguish_hit_miss_error_and_legacy_uid(monkeypatch):
    store = _RedisKeyValueStore()
    monkeypatch.setattr(redis_db, "r", store)

    assert redis_db.read_cached_mcp_api_key_auth_context("mcp-hash").mode == ApiKeyCacheReadMode.MISS
    assert redis_db.read_cached_dev_api_key_data("dev-hash").mode == ApiKeyCacheReadMode.MISS

    store.values["mcp_api_key_auth:mcp-hash"] = "not-json"
    store.values["dev_api_key:dev-hash"] = "not-json"
    assert redis_db.read_cached_mcp_api_key_auth_context("mcp-hash").mode == ApiKeyCacheReadMode.ERROR
    assert redis_db.read_cached_dev_api_key_data("dev-hash").mode == ApiKeyCacheReadMode.ERROR

    store.values.pop("mcp_api_key_auth:mcp-hash")
    store.values["mcp_api_key:mcp-hash"] = "user-1"
    legacy = redis_db.read_cached_mcp_api_key_auth_context("mcp-hash")
    assert legacy.mode == ApiKeyCacheReadMode.HIT
    assert legacy.data == {"user_id": "user-1", "scopes": None, "key_id": None, "app_id": None}
