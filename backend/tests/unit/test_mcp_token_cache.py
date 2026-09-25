"""Redis token-cache tests for ``database.mcp_token_cache`` wired through a
fresh-loaded ``database.mcp_oauth`` against the in-memory Firestore stand-in.

Covers: positive-only caching, the 60s TTL cap, per-hit revalidation (shape,
scopes, expiry, audience equivalence), the revocation marker and grant token
index, the cache-fill race, ``last_used_at`` throttling, and outage semantics:
validation degrades to Firestore-only when Redis is down while revocation
writes stay fail-closed. Redis is hermetic throughout.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from types import ModuleType

import google.api_core.retry  # noqa: F401 — land the real module in sys.modules before the firestore stub
import pytest

from testing.import_isolation import load_module_fresh, stub_modules

import database.mcp_cache_integrity as integrity
import database.mcp_token_cache as token_cache
import database.redis_db as redis_db
from utils.mcp_server import auth as mcp_auth

_BACKEND = Path(__file__).resolve().parents[2]

os.environ.setdefault('MCP_OAUTH_CHATGPT_CLIENT_ID', 'omi-chatgpt-prod')
os.environ.setdefault('MCP_OAUTH_CHATGPT_REDIRECT_URIS', 'https://chatgpt.com/connector_platform_oauth_redirect')
os.environ.setdefault('MCP_OAUTH_PUBLIC_REDIRECT_URIS', 'https://chatgpt.com/connector_platform_oauth_redirect')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


class _DocSnapshot:
    def __init__(self, reference, data=None):
        self.reference = reference
        self.id = reference.id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _DocReference:
    def __init__(self, collection, doc_id):
        self._collection = collection
        self.id = doc_id

    def get(self, transaction=None, **_read_options):
        return _DocSnapshot(self, self._collection._docs.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self._collection._docs:
            _deep_merge(self._collection._docs[self.id], data)
        else:
            self._collection._docs[self.id] = dict(data)

    def update(self, data):
        self._collection._docs.setdefault(self.id, {}).update(data)

    def delete(self):
        self._collection._docs.pop(self.id, None)


class _Query:
    def __init__(self, collection, field, expected):
        self._collection = collection
        self._field = field
        self._expected = expected

    def stream(self, **_read_options):
        for doc_id, data in list(self._collection._docs.items()):
            if data.get(self._field) == self._expected:
                yield _DocSnapshot(_DocReference(self._collection, doc_id), data)


def _deep_merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


class _Collection:
    def __init__(self):
        self._docs = {}

    def document(self, doc_id):
        return _DocReference(self, doc_id)

    def where(self, field, op, expected):
        assert op == '=='
        return _Query(self, field, expected)


class _DB:
    def __init__(self):
        self._collections = {}

    def collection(self, name):
        self._collections.setdefault(name, _Collection())
        return self._collections[name]

    def transaction(self):
        return _Transaction()


class _Transaction:
    def update(self, ref, data):
        ref.update(data)

    def set(self, ref, data, merge=False):
        ref.set(data, merge=merge)


class _FailDB:
    """Any Firestore access explodes — proves a cache hit stays off Firestore."""

    def collection(self, name):
        raise AssertionError(f"Firestore touched on cache hit: {name}")

    def transaction(self):
        raise AssertionError("Firestore touched on cache hit")


class _FakeRedis:
    def __init__(self):
        self.strings = {}
        self.sets = {}
        self.failing = False

    def _check(self):
        if self.failing:
            raise ConnectionError("fake redis outage")

    @staticmethod
    def _live(store, key):
        entry = store.get(key)
        if entry is not None and entry[1] is not None and entry[1] <= time.time():
            store.pop(key, None)
            return None
        return entry

    def get(self, key):
        self._check()
        entry = self._live(self.strings, key)
        return entry[0] if entry else None

    def set(self, key, value, ex=None, nx=False, **_kwargs):
        self._check()
        if nx and self._live(self.strings, key) is not None:
            return None
        self.strings[key] = [value, (time.time() + ex) if ex else None]
        return True

    def exists(self, *keys):
        self._check()
        return sum(
            1 for key in keys if self._live(self.strings, key) is not None or self._live(self.sets, key) is not None
        )

    def delete(self, *keys):
        self._check()
        removed = 0
        for key in keys:
            removed += self.strings.pop(key, None) is not None
            removed += self.sets.pop(key, None) is not None
        return removed

    def sadd(self, key, *members):
        self._check()
        entry = self.sets.setdefault(key, [set(), None])
        entry[0].update(members)
        return len(members)

    def smembers(self, key):
        self._check()
        entry = self._live(self.sets, key)
        return set(entry[0]) if entry else set()

    def expire(self, key, seconds):
        self._check()
        for store in (self.strings, self.sets):
            entry = store.get(key)
            if entry is not None:
                entry[1] = time.time() + seconds
                return True
        return False

    def ttl(self, key):
        self._check()
        entry = self._live(self.strings, key) or self._live(self.sets, key)
        if entry is None:
            return -2
        if entry[1] is None:
            return -1
        return int(entry[1] - time.time())


@pytest.fixture(scope="module", autouse=True)
def _mcp_oauth_module():
    """Fresh ``database.mcp_oauth`` against the in-memory ``_DB`` (same
    isolation pattern as ``test_mcp_oauth.py``)."""
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.transactional = lambda fn: fn

    fakes = {
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.mcp_oauth",
            os.path.join(str(_BACKEND), "database", "mcp_oauth.py"),
        )
        module.db = _DB()
        globals()["mcp_oauth"] = module
        yield module


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_db, "r", fake)
    globals()["fake_redis"] = fake
    return fake


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _at_key(token: str) -> str:
    return f"mcp:oauth:at:{_sha(token)}"


def _revoked_key(grant_id: str) -> str:
    return f"mcp:oauth:revoked:{_sha(grant_id)}"


def _index_key(grant_id: str) -> str:
    return f"mcp:oauth:grant_tokens:{_sha(grant_id)}"


def _last_used_key(token: str) -> str:
    return f"mcp:oauth:last_used:{_sha(token)}"


def _issue_token(uid="cache-user", scopes=None):
    scopes = scopes or ["memories.read"]
    grant = mcp_oauth.create_or_update_grant(uid, "omi-chatgpt-prod", mcp_oauth.MCP_RESOURCE_URL, scopes)
    return grant, mcp_oauth.issue_token_pair(grant, scopes=scopes)


# --- Positive cache ---------------------------------------------------------


def test_cache_hit_serves_identity_with_zero_firestore_access(_fake_redis):
    grant, pair = _issue_token("hit-user")
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)["uid"] == "hit-user"

    # The throttle key is deliberately absent: a hit performs zero Firestore
    # work — no token read, no memory grant, and no last_used_at write.
    real_db = mcp_oauth.db
    mcp_oauth.db = _FailDB()
    try:
        identity = mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    finally:
        mcp_oauth.db = real_db
    assert identity["uid"] == "hit-user"
    assert identity["grant_id"] == grant["id"]
    assert identity["scopes"] == ["memories.read"]


def test_cached_entry_ttl_capped_at_sixty_seconds(_fake_redis):
    grant, pair = _issue_token("ttl-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    assert fake_redis.ttl(_at_key(pair["access_token"])) <= token_cache.ACCESS_TOKEN_CACHE_TTL_CAP_SECONDS
    # Grant token index tracks the token hash at the access-token TTL.
    assert fake_redis.smembers(_index_key(grant["id"])) == {_sha(pair["access_token"])}
    assert fake_redis.ttl(_index_key(grant["id"])) > 60


def test_canonical_and_sse_audiences_share_cache_but_cross_host_rejected(_fake_redis):
    grant, pair = _issue_token("audience-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)

    hit = mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_LEGACY_RESOURCE_URL)
    assert hit is not None

    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.BETA_MCP_RESOURCE_URL) is None
    assert mcp_oauth.validate_access_token(pair["access_token"], "https://evil.example/v1/mcp/sse") is None
    # Canonical audience still works after the cross-host rejection.
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is not None


@pytest.mark.parametrize(
    "case",
    [
        "garbage",
        "missing_fields",
        "bad_scopes",
        "expired",
        "cross_host",
    ],
)
def test_malformed_or_invalid_cache_entries_are_not_served(case, _fake_redis):
    entries = {
        "garbage": "not-json",
        "missing_fields": {"uid": "u"},
        "bad_scopes": {
            "uid": "u",
            "client_id": "c",
            "grant_id": "g",
            "resource": mcp_oauth.MCP_RESOURCE_URL,
            "scopes": ["bogus.scope"],
            "expires_at": time.time() + 30,
        },
        "expired": {
            "uid": "u",
            "client_id": "c",
            "grant_id": "g",
            "resource": mcp_oauth.MCP_RESOURCE_URL,
            "scopes": ["memories.read"],
            "expires_at": time.time() - 5,
        },
        "cross_host": {
            "uid": "u",
            "client_id": "c",
            "grant_id": "g",
            "resource": mcp_oauth.BETA_MCP_RESOURCE_URL,
            "scopes": ["memories.read"],
            "expires_at": time.time() + 30,
        },
    }
    entry = entries[case]
    payload = entry if isinstance(entry, str) else json.dumps(entry)
    fake_redis.set(_at_key("omi_oat_test"), payload)
    assert token_cache.read_access_token("omi_oat_test", mcp_oauth.MCP_RESOURCE_URL) is None


# --- Cache integrity ---------------------------------------------------------


def _forged_entry(grant_id="g", uid="attacker-uid", scopes=None):
    return {
        "uid": uid,
        "client_id": "omi-chatgpt-prod",
        "grant_id": grant_id,
        "resource": mcp_oauth.MCP_RESOURCE_URL,
        "scopes": scopes or ["conversations.read"],
        "expires_at": time.time() + 300,
    }


def test_forged_unsigned_entry_falls_through_to_firestore(_fake_redis):
    """An attacker-controlled unsigned Redis write can never mint an
    identity: the MAC check drops it and validation falls through to the
    authoritative Firestore path, which returns the real uid and scopes."""
    grant, pair = _issue_token("forge-user")  # real scopes: ["memories.read"]
    fake_redis.set(_at_key(pair["access_token"]), json.dumps(_forged_entry(grant_id=grant["id"])))
    identity = mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    assert identity["uid"] == "forge-user"
    assert identity["scopes"] == ["memories.read"]


def test_forged_entry_for_unknown_token_cannot_authenticate(_fake_redis):
    fake_redis.set(_at_key("omi_oat_forged"), json.dumps(_forged_entry()))
    assert mcp_oauth.validate_access_token("omi_oat_forged", mcp_oauth.MCP_RESOURCE_URL) is None


def test_tampered_signed_entry_is_not_served(_fake_redis):
    """Rewriting fields inside a signed envelope leaves a stale MAC — the
    entry is dropped and the Firestore path serves the real identity."""
    grant, pair = _issue_token("tamper-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    raw = fake_redis.strings[_at_key(pair["access_token"])][0]
    envelope = json.loads(raw)
    envelope["data"]["uid"] = "attacker-uid"
    envelope["data"]["scopes"] = ["conversations.read"]
    fake_redis.set(_at_key(pair["access_token"]), json.dumps(envelope))
    identity = mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    assert identity["uid"] == "tamper-user"
    assert identity["scopes"] == ["memories.read"]


def test_entry_signed_with_foreign_secret_is_not_served(_fake_redis, monkeypatch):
    import database.mcp_cache_integrity as integrity

    monkeypatch.setenv("ENCRYPTION_SECRET", "foreign-test-secret-foreign-test-secret")
    blob = integrity.dumps_signed(_forged_entry(), "at")
    monkeypatch.setenv("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
    fake_redis.set(_at_key("omi_oat_foreign"), blob)
    assert mcp_oauth.validate_access_token("omi_oat_foreign", mcp_oauth.MCP_RESOURCE_URL) is None


def test_copied_signed_blob_cannot_authenticate_a_different_token(_fake_redis):
    """Copying a victim's valid signed blob to another token key cannot
    transfer the identity: the signed payload binds its own token hash, so
    the copied blob is dropped and the unknown token falls through to an
    authoritative Firestore miss."""
    grant, pair = _issue_token("victim-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    blob = fake_redis.strings[_at_key(pair["access_token"])][0]
    fake_redis.set(_at_key("omi_oat_attacker"), blob, ex=60)
    assert mcp_oauth.validate_access_token("omi_oat_attacker", mcp_oauth.MCP_RESOURCE_URL) is None
    # The victim's own key still serves the real identity.
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)["uid"] == "victim-user"


def test_missing_signing_secret_fails_closed(_fake_redis, monkeypatch):
    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    with pytest.raises(token_cache.McpTokenStoreUnavailable):
        mcp_oauth.validate_access_token("omi_oat_whatever", mcp_oauth.MCP_RESOURCE_URL)


def test_dumps_signed_returns_none_without_signing_secret(monkeypatch):
    """An unsigned envelope must never be produced — no key means ``None``,
    and callers treat that as "do not cache"."""
    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    assert integrity.dumps_signed({"a": 1}, "at") is None
    assert integrity.dumps_signed({"a": 1}, "cimd") is None


# --- Revocation -------------------------------------------------------------


def test_revoke_grant_marks_revoked_purges_token_and_clears_index(_fake_redis):
    grant, pair = _issue_token("revoke-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    assert fake_redis.get(_at_key(pair["access_token"])) is not None

    mcp_oauth.revoke_grant(grant["id"])

    assert fake_redis.get(_at_key(pair["access_token"])) is None  # purged via index
    assert fake_redis.exists(_index_key(grant["id"])) == 0  # index cleared
    assert fake_redis.ttl(_revoked_key(grant["id"])) >= mcp_oauth.ACCESS_TOKEN_TTL_SECONDS - 5

    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None


def test_marker_blocks_entries_written_during_revoke_race(_fake_redis):
    """A revoke landing between the marker check and the cache fill must deny
    the racing request itself — not only the next one."""
    grant, pair = _issue_token("race-user")
    original_fill = token_cache.fill_access_token

    def fill_then_mark(access_token, identity, expires_at_epoch, *, index_ttl_seconds):
        original_fill(access_token, identity, expires_at_epoch, index_ttl_seconds=index_ttl_seconds)
        fake_redis.set(_revoked_key(grant["id"]), "1", ex=mcp_oauth.ACCESS_TOKEN_TTL_SECONDS)

    import database.mcp_token_cache as cache_module

    original = cache_module.fill_access_token
    cache_module.fill_access_token = fill_then_mark
    try:
        # The marker is re-checked after the fill, so even this request fails.
        assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None
    finally:
        cache_module.fill_access_token = original

    # The just-filled entry is invalidated by the marker on the next read too.
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None
    assert fake_redis.get(_at_key(pair["access_token"])) is None


def test_revoke_fails_closed_when_redis_is_down_and_retries_safely(_fake_redis):
    """No successful revoke may be reported while the marker cannot be
    written: the call raises, the Firestore grant stays active (so the cached
    token is legitimately still valid), and a retry after recovery revokes."""
    grant, pair = _issue_token("revoke-down-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    assert fake_redis.get(_at_key(pair["access_token"])) is not None

    fake_redis.failing = True
    with pytest.raises(token_cache.McpTokenStoreUnavailable):
        mcp_oauth.revoke_grant(grant["id"])

    fake_redis.failing = False
    # No marker was written, but the Firestore revoke never ran either.
    assert mcp_oauth.get_active_grant(grant["id"]) is not None
    assert fake_redis.exists(_revoked_key(grant["id"])) == 0

    # Retrying the revoke once Redis recovers succeeds and invalidates.
    mcp_oauth.revoke_grant(grant["id"])
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None


def test_replay_outage_propagates_and_retry_completes_revocation(_fake_redis):
    """A replayed refresh token during a Redis outage raises rather than
    leaving a half-revoked grant; after recovery the same replay re-enters
    the revoke path, completes it, and cached access tokens are denied."""
    grant, pair = _issue_token("replay-outage-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    rotated = mcp_oauth.rotate_refresh_token(pair["refresh_token"], "omi-chatgpt-prod", mcp_oauth.MCP_RESOURCE_URL)
    mcp_oauth.validate_access_token(rotated["access_token"], mcp_oauth.MCP_RESOURCE_URL)

    fake_redis.failing = True
    with pytest.raises(token_cache.McpTokenStoreUnavailable):
        mcp_oauth.rotate_refresh_token(pair["refresh_token"], "omi-chatgpt-prod", mcp_oauth.MCP_RESOURCE_URL)

    fake_redis.failing = False
    # Nothing was half-revoked — the grant stays active so the cached token
    # was never stale, and the replay retry can complete the revoke.
    assert mcp_oauth.get_active_grant(grant["id"]) is not None
    assert mcp_oauth.rotate_refresh_token(pair["refresh_token"], "omi-chatgpt-prod", mcp_oauth.MCP_RESOURCE_URL) is None
    assert fake_redis.exists(_revoked_key(grant["id"])) == 1
    assert mcp_oauth.validate_access_token(rotated["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None


def test_falsy_marker_write_fails_closed(_fake_redis, monkeypatch):
    """A SET that returns falsy without raising is still an unwritten marker —
    the revoke fails closed and the grant is not reported revoked."""
    grant, pair = _issue_token("falsy-marker-user")
    original_set = fake_redis.set

    def flaky_set(key, value, **kwargs):
        if key.startswith("mcp:oauth:revoked:"):
            return False
        return original_set(key, value, **kwargs)

    monkeypatch.setattr(fake_redis, "set", flaky_set)
    with pytest.raises(token_cache.McpTokenStoreUnavailable):
        mcp_oauth.revoke_grant(grant["id"])
    assert mcp_oauth.get_active_grant(grant["id"]) is not None


def test_refresh_replay_revokes_and_invalidates_cached_token(_fake_redis):
    grant, pair = _issue_token("replay-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    rotated = mcp_oauth.rotate_refresh_token(pair["refresh_token"], "omi-chatgpt-prod", mcp_oauth.MCP_RESOURCE_URL)
    mcp_oauth.validate_access_token(rotated["access_token"], mcp_oauth.MCP_RESOURCE_URL)

    # Replaying the used refresh token revokes the whole grant family.
    assert mcp_oauth.rotate_refresh_token(pair["refresh_token"], "omi-chatgpt-prod", mcp_oauth.MCP_RESOURCE_URL) is None
    assert fake_redis.exists(_revoked_key(grant["id"])) == 1
    assert mcp_oauth.validate_access_token(rotated["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None


def test_revoke_user_grant_and_credential_delete_invalidate_cache(_fake_redis):
    grant, pair = _issue_token("delete-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    mcp_oauth.revoke_user_grant("delete-user", grant["id"])
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None

    grant2, pair2 = _issue_token("wipe-user")
    mcp_oauth.validate_access_token(pair2["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    mcp_oauth.delete_user_oauth_credentials("wipe-user")
    assert mcp_oauth.validate_access_token(pair2["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None


# --- last_used_at throttling -------------------------------------------------


def test_last_used_written_at_most_once_per_token_per_window(_fake_redis, monkeypatch):
    writes = []
    monkeypatch.setattr(mcp_oauth, "_record_grant_last_used", lambda grant_id: writes.append(grant_id))
    grant, pair = _issue_token("throttle-user")

    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)  # miss → claims
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)  # hit → claim fails

    assert writes == [grant["id"]]


def test_invalid_token_never_writes_or_caches(_fake_redis, monkeypatch):
    writes = []
    monkeypatch.setattr(mcp_oauth, "_record_grant_last_used", lambda grant_id: writes.append(grant_id))
    assert mcp_oauth.validate_access_token("omi_oat_nonexistent", mcp_oauth.MCP_RESOURCE_URL) is None
    assert writes == []
    assert all(not key.startswith("mcp:oauth:at:") for key in fake_redis.strings)


def test_cache_keys_never_contain_plaintext_tokens(_fake_redis):
    grant, pair = _issue_token("plaintext-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    mcp_oauth.revoke_grant(grant["id"])
    for key in list(fake_redis.strings) + list(fake_redis.sets):
        assert pair["access_token"] not in key
        assert pair["refresh_token"] not in key
    for value in fake_redis.strings.values():
        assert pair["access_token"] not in str(value)


def test_cimd_grant_document_id_is_sanitized_but_preregistered_id_unchanged(_fake_redis):
    """A URL-form client id contains '/', which is invalid in a Firestore
    document id — the grant id hashes only that component, while existing
    preregistered client grant ids stay byte-for-byte identical."""
    url_client_id = "https://app.example.com/oauth/client.json"
    cimd_grant = mcp_oauth.create_or_update_grant(
        "grant-user", url_client_id, mcp_oauth.MCP_RESOURCE_URL, ["memories.read"]
    )
    assert "/" not in cimd_grant["id"]
    assert url_client_id not in cimd_grant["id"]

    prereg_grant = mcp_oauth.create_or_update_grant(
        "grant-user", "omi-chatgpt-prod", mcp_oauth.MCP_RESOURCE_URL, ["memories.read"]
    )
    assert (
        prereg_grant["id"]
        == f"grant-user:omi-chatgpt-prod:{mcp_oauth.hash_secret(mcp_oauth.MCP_LEGACY_RESOURCE_URL)[:16]}"
    )


# --- Outage semantics --------------------------------------------------------


def test_redis_outage_validates_against_firestore_only(_fake_redis):
    """Redis down is not an auth outage: cache read, revocation marker,
    cache fill, and last_used writes are all skipped while the authoritative
    Firestore grant decides — a valid token still validates and an unknown
    one still misses."""
    grant, pair = _issue_token("outage-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    fake_redis.failing = True
    identity = mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    assert identity["uid"] == "outage-user"
    assert identity["grant_id"] == grant["id"]
    assert mcp_oauth.validate_access_token("omi_oat_nonexistent", mcp_oauth.MCP_RESOURCE_URL) is None


def test_redis_outage_still_denies_firestore_revoked_grants(_fake_redis):
    """Fail-open cache reads never resurrect a revoked grant: with the marker
    unreadable, the authoritative Firestore document still denies."""
    grant, pair = _issue_token("outage-revoked-user")
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    # Marker written while Redis was up; Firestore revoke then completed and
    # Redis died — validation must still deny off the grant document alone.
    mcp_oauth.db.collection("mcp_oauth_grants").document(grant["id"]).set(
        {"revoked_at": mcp_oauth._now(), "status": "revoked"}, merge=True
    )
    fake_redis.failing = True
    assert mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL) is None


def test_redis_outage_skips_last_used_writes(_fake_redis, monkeypatch):
    """During a Redis outage last_used_at writes are skipped too — an
    unthrottled write per validated request would add ~150k+ Firestore
    writes/day at steady traffic."""
    writes = []
    monkeypatch.setattr(mcp_oauth, "_record_grant_last_used", lambda grant_id: writes.append(grant_id))
    grant, pair = _issue_token("outage-throttle-user")
    fake_redis.failing = True
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    mcp_oauth.validate_access_token(pair["access_token"], mcp_oauth.MCP_RESOURCE_URL)
    assert writes == []


def test_redis_outage_maps_to_503_not_401(monkeypatch):
    from fastapi import HTTPException

    def boom(token, resource):
        raise token_cache.McpTokenStoreUnavailable("redis down")

    monkeypatch.setattr(mcp_auth.mcp_oauth_db, "validate_access_token", boom)
    with pytest.raises(HTTPException) as excinfo:
        mcp_auth.authenticate_mcp_request("Bearer omi_oat_whatever")
    assert excinfo.value.status_code == 503
    assert "Retry-After" in (excinfo.value.headers or {})


def test_firestore_outage_on_cache_miss_maps_to_503(monkeypatch):
    from fastapi import HTTPException
    from google.api_core.exceptions import ServiceUnavailable

    def boom(token, resource):
        raise ServiceUnavailable("firestore down")

    monkeypatch.setattr(mcp_auth.mcp_oauth_db, "validate_access_token", boom)
    with pytest.raises(HTTPException) as excinfo:
        mcp_auth.authenticate_mcp_request("Bearer omi_oat_whatever")
    assert excinfo.value.status_code == 503
    assert "Retry-After" in (excinfo.value.headers or {})


def test_401_challenge_advertises_read_scope_hint():
    exc = mcp_auth.invalid_mcp_auth_exception()
    challenge = exc.headers["WWW-Authenticate"]
    assert 'scope="' in challenge
    for read_scope in sorted(s for s in mcp_auth.MCP_FULL_ACCESS_SCOPES if s.endswith(".read")):
        assert read_scope in challenge
    assert "memories.write" not in challenge
