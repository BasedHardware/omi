"""Per-key MCP scope authority: a key carries exactly the scopes it was issued with."""

from datetime import datetime, timezone

import database.mcp_api_key as mcp_api_key_db
from tests.unit.test_mcp_api_key_full_access import _DB, _Redis, _grant_for
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES, normalize_mcp_scopes

_VALID_HASH = "a" * 64


def _install(monkeypatch, module, db, redis):
    monkeypatch.setattr(module, "get_firestore_client", lambda: db)
    monkeypatch.setattr(module, "redis_db", redis)


def test_normalize_keeps_requested_scopes_and_drops_unknown_ones():
    assert normalize_mcp_scopes(["memories.read"]) == ["memories.read"]
    assert normalize_mcp_scopes(["memories.read", "not.a.scope"]) == ["memories.read"]
    assert normalize_mcp_scopes(["memories.write", "memories.read"]) == ["memories.read", "memories.write"]


def test_normalize_fails_closed_for_present_but_malformed_scope_lists():
    """A recorded list is authoritative: empty or unknown-only lists must not
    widen to full access. Only genuinely absent scope state is legacy."""
    assert normalize_mcp_scopes([]) == []
    assert normalize_mcp_scopes(["not.a.scope"]) == []
    assert normalize_mcp_scopes([1, 2, 3]) == []


def test_normalize_legacy_full_access_only_for_absent_scope_state():
    """A key without a recorded scopes field keeps full access."""
    assert normalize_mcp_scopes(None) == sorted(MCP_FULL_ACCESS_SCOPES)
    assert normalize_mcp_scopes("memories.read") == sorted(MCP_FULL_ACCESS_SCOPES)


def test_unmigrated_key_without_recorded_scopes_still_authorizes_with_full_access(monkeypatch):
    """Legacy principal: a key issued before per-key scopes keeps working."""
    db = _DB()
    db.collection("mcp_api_keys").document("legacy-key").set(
        {
            "id": "legacy-key",
            "user_id": "user-1",
            "name": "Legacy",
            "hashed_key": _VALID_HASH,
            "key_prefix": "omi_mcp",
            "created_at": datetime.now(timezone.utc),
        }
    )
    redis = _Redis()
    _install(monkeypatch, mcp_api_key_db, db, redis)
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: _VALID_HASH)

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")

    assert auth["user_id"] == "user-1"
    assert auth["scopes"] == sorted(MCP_FULL_ACCESS_SCOPES)
    grant = _grant_for(db, "user-1", "legacy-key")
    assert grant["default_read"] is True
    assert grant["write"] is True


def test_scoped_key_authorizes_only_its_own_scopes_and_narrows_its_memory_grant(monkeypatch):
    db = _DB()
    redis = _Redis()
    _install(monkeypatch, mcp_api_key_db, db, redis)
    monkeypatch.setattr(mcp_api_key_db, "generate_api_key", lambda: ("omi_mcp_secret", _VALID_HASH, "omi_mcp"))
    monkeypatch.setattr(mcp_api_key_db, "uuid", type("_U", (), {"uuid4": staticmethod(lambda: "key-1")}))
    monkeypatch.setattr(mcp_api_key_db, "hash_api_key", lambda _secret: _VALID_HASH)

    _raw_key, key = mcp_api_key_db.create_mcp_key("user-1", "Reader", scopes=["memories.read"])

    assert key.scopes == ["memories.read"]
    assert db.collection("mcp_api_keys").document("key-1").get().to_dict()["scopes"] == ["memories.read"]
    grant = _grant_for(db, "user-1", "key-1")
    assert grant == {
        "enabled": True,
        "scopes": ["memories.read"],
        "default_read": True,
        "archive_read": False,
        "write": False,
    }

    auth = mcp_api_key_db.get_user_and_scopes_by_api_key("omi_mcp_secret")
    assert auth["scopes"] == ["memories.read"]
    # A scoped key's grant is already correct, so authentication must not
    # repeatedly "repair" it back to full memory access.
    assert _grant_for(db, "user-1", "key-1")["write"] is False
