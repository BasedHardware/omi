"""Client ID Metadata Document (CIMD) fetch/validation/cache tests.

All network access is mocked at the ``socket.getaddrinfo`` /
``urllib3.HTTPSConnectionPool`` seams — these tests never perform real DNS or
TLS. Redis is replaced with a hermetic fake via ``redis_db.r``.
"""

import base64
import hashlib
import json
import os
import time
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.mcp_client_metadata as cimd
import database.redis_db as redis_db

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

CLIENT_ID = "https://app.example.com/oauth/client-metadata.json"
REDIRECT_URI = "https://app.example.com/oauth/callback"
CODE_VERIFIER = "verifier-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGH"
CODE_CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(CODE_VERIFIER.encode("ascii")).digest()).decode("ascii").rstrip("=")
)


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


class _FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._body = body
        self.read_sizes = []
        self.closed = False
        self.released = False

    def read(self, amt=None):
        self.read_sizes.append(amt)
        return self._body if amt is None else self._body[:amt]

    def release_conn(self):
        self.released = True

    def close(self):
        self.closed = True


class _FakePool:
    """Stand-in for ``urllib3.HTTPSConnectionPool``; class-level ``response``
    configures what the next request returns and ``instances`` records every
    construction for SSRF assertions."""

    response = _FakeResponse()
    instances = []
    failure = None

    def __init__(self, host, port=None, **kwargs):
        if _FakePool.failure is not None:
            raise _FakePool.failure
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.requests = []
        self.closed = False
        _FakePool.instances.append(self)

    def request(self, method, target, headers=None, redirect=True, preload_content=True):
        self.requests.append(
            {
                "method": method,
                "target": target,
                "headers": headers,
                "redirect": redirect,
                "preload_content": preload_content,
            }
        )
        return _FakePool.response

    def close(self):
        self.closed = True


def _public_dns(hostname, port, **_kwargs):
    return [(2, 1, 6, "", ("93.184.216.34", 443))]


def _install_network(monkeypatch, addresses=("93.184.216.34",), response=None):
    def fake_getaddrinfo(hostname, port, **_kwargs):
        return [(2, 1, 6, "", (address, port or 443)) for address in addresses]

    monkeypatch.setattr(cimd.socket, "getaddrinfo", fake_getaddrinfo)
    _FakePool.instances = []
    _FakePool.response = response if response is not None else _FakeResponse()
    _FakePool.failure = None
    monkeypatch.setattr(cimd.urllib3, "HTTPSConnectionPool", _FakePool)


def _metadata_body(**overrides):
    document = {
        "client_id": CLIENT_ID,
        "client_name": "Example App",
        "redirect_uris": [REDIRECT_URI],
        "token_endpoint_auth_method": "none",
    }
    document.update(overrides)
    return json.dumps(document).encode("utf-8")


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(redis_db, "r", fake)
    return fake


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Default-deny: any un-mocked fetch attempt explodes rather than escaping."""

    def boom(hostname, port, **kwargs):
        raise AssertionError(f"unexpected DNS resolution for {hostname}")

    monkeypatch.setattr(cimd.socket, "getaddrinfo", boom)


# --- URL shape ------------------------------------------------------------


@pytest.mark.parametrize(
    "client_id",
    [
        "http://app.example.com/meta.json",  # non-HTTPS scheme
        "https://user@app.example.com/meta.json",  # userinfo
        "https://user:pw@app.example.com/meta.json",  # userinfo password
        "https://app.example.com/meta.json#frag",  # fragment
        "https://app.example.com:8443/meta.json",  # non-443 port
        "https://app.example.com\\meta.json",  # backslash
        "https://app.example.com/m\x07eta.json",  # control char
        "https://app.example.com/" + "a" * 2100,  # excessive length
        "https://exämple.com/meta.json",  # non-ASCII host (must be punycode)
        "https://app.example.com/mëtadata.json",  # non-ASCII path
        "not-a-url/",
    ],
    ids=[
        "non_https",
        "userinfo",
        "userinfo_password",
        "fragment",
        "non443_port",
        "backslash",
        "control_char",
        "too_long",
        "nonascii_host",
        "nonascii_path",
        "garbage",
    ],
)
def test_url_form_client_id_rejected_without_network(client_id, monkeypatch):
    called = []
    monkeypatch.setattr(cimd.urllib3, "HTTPSConnectionPool", lambda *a, **k: called.append(a))
    assert cimd.get_url_client(client_id) is None
    assert called == []


# --- DNS / SSRF ------------------------------------------------------------


@pytest.mark.parametrize(
    "addresses",
    [
        ("10.0.0.5",),  # private
        ("192.168.1.9",),  # private
        ("127.0.0.1",),  # loopback
        ("169.254.169.254",),  # link-local metadata service
        ("224.0.0.5",),  # multicast
        ("::1",),  # IPv6 loopback
        ("fe80::1",),  # IPv6 link-local
        ("fd00::5",),  # IPv6 ULA
        ("::ffff:10.0.0.5",),  # unsafe IPv4-mapped
        ("93.184.216.34", "10.0.0.5"),  # one private among publics
    ],
    ids=[
        "private_10",
        "private_192",
        "loopback",
        "link_local_metadata",
        "multicast",
        "v6_loopback",
        "v6_link_local",
        "v6_ula",
        "v4_mapped_private",
        "mixed_private",
    ],
)
def test_non_global_dns_results_rejected(addresses, monkeypatch):
    _install_network(monkeypatch, addresses=addresses)
    assert cimd.get_url_client(CLIENT_ID) is None
    assert _FakePool.instances == []


def test_dns_failure_returns_unknown_client(monkeypatch):
    def fail(hostname, port, **kwargs):
        raise OSError("NXDOMAIN")

    monkeypatch.setattr(cimd.socket, "getaddrinfo", fail)
    assert cimd.get_url_client(CLIENT_ID) is None


def test_fetch_pins_resolved_ip_and_preserves_hostname(monkeypatch):
    _install_network(monkeypatch, addresses=("8.8.8.8",), response=_FakeResponse(body=_metadata_body()))
    assert cimd.get_url_client(CLIENT_ID) is not None

    pool = _FakePool.instances[0]
    assert pool.host == "8.8.8.8"
    assert pool.port == 443
    assert pool.kwargs["server_hostname"] == "app.example.com"
    assert pool.kwargs["assert_hostname"] == "app.example.com"
    assert pool.kwargs["cert_reqs"] == "CERT_REQUIRED"
    assert pool.kwargs["retries"] is False
    request = pool.requests[0]
    assert request["method"] == "GET"
    assert request["target"] == "/oauth/client-metadata.json"
    assert request["headers"]["Host"] == "app.example.com"
    assert request["redirect"] is False
    assert request["preload_content"] is False
    assert _FakePool.response.released or _FakePool.response.closed


def test_fetch_rejects_redirect_responses(monkeypatch):
    """3xx is never followed — a redirect could point at a private target."""
    _install_network(
        monkeypatch,
        response=_FakeResponse(status=302, headers={"Location": "https://169.254.169.254/latest/meta-data"}),
    )
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize("status", [400, 404, 500])
def test_fetch_requires_http_200(status, monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(status=status))
    assert cimd.get_url_client(CLIENT_ID) is None


def test_fetch_requires_json_content_type(monkeypatch):
    _install_network(
        monkeypatch,
        response=_FakeResponse(headers={"Content-Type": "text/html"}, body=_metadata_body()),
    )
    assert cimd.get_url_client(CLIENT_ID) is None


def test_fetch_accepts_json_charset_parameter(monkeypatch):
    _install_network(
        monkeypatch,
        response=_FakeResponse(headers={"Content-Type": "application/json; charset=utf-8"}, body=_metadata_body()),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None


def test_fetch_rejects_oversized_document(monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body() + b" " * (17 * 1024)))
    assert cimd.get_url_client(CLIENT_ID) is None
    assert _FakePool.response.read_sizes == [cimd.CIMD_MAX_BODY_BYTES + 1]


def test_fetch_rejects_non_object_json(monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=b"[1,2,3]"))
    assert cimd.get_url_client(CLIENT_ID) is None


# --- Document validation ---------------------------------------------------


def test_document_client_id_must_match_request_url(monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body(client_id="https://evil.example/x")))
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize(
    "redirect_uris",
    [
        [],
        "not-a-list",
        [REDIRECT_URI, REDIRECT_URI],  # duplicates
        [f"https://app.example.com/cb/{i}" for i in range(21)],  # too many
        ["https://app.example.com/cb#frag"],
        ["https://u:p@app.example.com/cb"],
        ["javascript:alert(1)"],
        ["ftp://app.example.com/cb"],
        ["http://app.example.com/cb"],  # http only allowed on loopback
        ["com.example.app:/oauth"],  # custom scheme rejected
        [REDIRECT_URI, 7],  # non-string member
    ],
    ids=[
        "empty",
        "not_a_list",
        "duplicate",
        "too_many",
        "fragment",
        "userinfo",
        "javascript",
        "ftp",
        "http_remote",
        "custom_scheme",
        "non_string_member",
    ],
)
def test_document_rejects_invalid_redirect_uris(redirect_uris, monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body(redirect_uris=redirect_uris)))
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize(
    "loopback_uri",
    [
        "http://localhost:8080/callback",
        "http://127.0.0.1:9999/callback",
        "http://[::1]:8080/callback",
        "http://my-app.localhost/callback",
    ],
    ids=["localhost", "ipv4_loopback", "ipv6_loopback", "localhost_subdomain"],
)
def test_document_allows_native_loopback_redirects(loopback_uri, monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body(redirect_uris=[loopback_uri])))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None
    assert client["allowed_redirect_uris"] == [loopback_uri]


@pytest.mark.parametrize(
    "document_extra",
    [
        {"token_endpoint_auth_method": "client_secret_post"},
        {"client_secret": "secret"},
        {"client_secret_hash": "abc"},
        {"code_challenge_methods_supported": ["plain"]},
    ],
    ids=["confidential_method", "client_secret", "secret_hash", "non_s256_methods"],
)
def test_document_rejects_secrets_and_non_pkce_methods(document_extra, monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body(**document_extra)))
    assert cimd.get_url_client(CLIENT_ID) is None


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("<script>alert(1)</script>", "<script>alert(1)</script>"),  # kept literal, escaped at render
        ("Omi " + "\u202e" + "support", "Omi support"),  # bidi override stripped
        ("A" * 100, "A" * 64),  # clamped to 64 chars
        ("Ｅｘａｍｐｌｅ　Ａｐｐ", "Example App"),  # NFKC fullwidth normalization
        ("line\nbreak\tapp", "linebreakapp"),  # control chars removed
    ],
    ids=["xss_literal", "bidi_strip", "long_clamp", "nfkc_normalize", "control_strip"],
)
def test_client_name_sanitized(raw_name, expected, monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body(client_name=raw_name)))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None
    assert client["name"] == expected


def test_client_name_falls_back_to_host(monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body(client_name="   ")))
    client = cimd.get_url_client(CLIENT_ID)
    assert client["name"] == "app.example.com"


def test_client_record_shape_and_public_pkce(monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client["registration_mode"] == "client_id_metadata_document"
    assert client["token_endpoint_auth_method"] == "none"
    assert client["client_secret_hash"] == ""
    assert client["metadata_host"] == "app.example.com"
    assert client["allowed_redirect_uri_prefixes"] == []


# --- Redis cache ------------------------------------------------------------


def _cache_key(client_id=CLIENT_ID):
    return f"mcp:cimd:{hashlib.sha256(client_id.encode('utf-8')).hexdigest()}"


def test_validated_metadata_cached_with_clamped_ttl(monkeypatch, _fake_redis):
    _install_network(
        monkeypatch,
        response=_FakeResponse(
            headers={"Content-Type": "application/json", "Cache-Control": "max-age=7200"}, body=_metadata_body()
        ),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None
    entry = _fake_redis.strings[_cache_key()]
    assert 3500 <= entry[1] - time.time() <= 3600
    envelope = json.loads(entry[0])
    assert set(envelope["data"]) == {"client_id", "client_name", "redirect_uris"}  # whitelist only
    assert isinstance(envelope["mac"], str) and envelope["mac"]


@pytest.mark.parametrize("cache_control", ["no-store", "no-cache", "private"], ids=["no_store", "no_cache", "private"])
def test_no_caching_directives_not_cached(cache_control, monkeypatch, _fake_redis):
    _install_network(
        monkeypatch,
        response=_FakeResponse(
            headers={"Content-Type": "application/json", "Cache-Control": cache_control}, body=_metadata_body()
        ),
    )
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert _cache_key() not in _fake_redis.strings


def test_cache_hit_reuses_metadata_without_fetch(monkeypatch, _fake_redis):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    assert cimd.get_url_client(CLIENT_ID) is not None
    _FakePool.instances = []
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert _FakePool.instances == []  # served from cache


def test_poisoned_cache_entry_is_revalidated_and_refetched(monkeypatch, _fake_redis):
    _fake_redis.set(
        _cache_key(),
        json.dumps({"client_id": "https://evil.example/other", "client_name": "Evil", "redirect_uris": [REDIRECT_URI]}),
        ex=3600,
    )
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None and client["name"] == "Example App"
    assert len(_FakePool.instances) == 1  # bad cache value was not trusted


def test_forged_unsigned_cached_document_never_reaches_consent(monkeypatch, _fake_redis):
    """A validly-shaped but unsigned cached document — attacker-controlled
    name and redirect URIs — fails the MAC check and is never served."""
    forged = {
        "client_id": CLIENT_ID,
        "client_name": "Trusted Connector",
        "redirect_uris": ["https://evil.example/callback"],
    }
    _fake_redis.set(_cache_key(), json.dumps(forged), ex=3600)
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None
    assert client["name"] == "Example App"  # fetched document, not the forge
    assert client["allowed_redirect_uris"] == [REDIRECT_URI]
    assert len(_FakePool.instances) == 1


def test_document_signed_with_foreign_secret_is_refetched(monkeypatch, _fake_redis):
    import database.mcp_cache_integrity as integrity

    monkeypatch.setenv("ENCRYPTION_SECRET", "foreign-test-secret-foreign-test-secret")
    blob = integrity.dumps_signed(
        {"client_id": CLIENT_ID, "client_name": "Trusted Connector", "redirect_uris": ["https://evil.example/cb"]}
    )
    monkeypatch.setenv("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
    _fake_redis.set(_cache_key(), blob, ex=3600)
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    client = cimd.get_url_client(CLIENT_ID)
    assert client is not None and client["name"] == "Example App"
    assert len(_FakePool.instances) == 1


def test_missing_signing_secret_skips_cache_entirely(monkeypatch, _fake_redis):
    monkeypatch.delenv("ENCRYPTION_SECRET", raising=False)
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    assert cimd.get_url_client(CLIENT_ID) is not None
    assert _cache_key() not in _fake_redis.strings  # nothing is ever written unsigned


def test_pool_constructor_failure_returns_unknown_client(monkeypatch, _fake_redis):
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    _FakePool.failure = RuntimeError("constructor boom")
    assert cimd.get_url_client(CLIENT_ID) is None


# --- End-to-end authorize/token flow ---------------------------------------


@pytest.fixture()
def mcp_client(monkeypatch):
    """TestClient with the CIMD network seams mocked and a valid document."""
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body()))
    from routers import mcp_sse as module

    app = FastAPI()
    app.include_router(module.router)
    return TestClient(app), module


def _authorize_params(**overrides):
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "opaque-state",
        "code_challenge": CODE_CHALLENGE,
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return params


def test_cimd_authorize_get_renders_unverified_consent(mcp_client):
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params())
    assert response.status_code == 200
    assert "Unverified third-party app" in response.text
    assert "Client ID host:" in response.text
    assert "app.example.com" in response.text
    assert "Example App" in response.text


def test_cimd_authorize_get_missing_scope_defaults_to_read_scopes_only(mcp_client):
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params())
    assert "Read your Omi memories" in response.text
    assert "Search and read your Omi conversations" in response.text
    assert "Read your Omi action items" in response.text
    assert "Read your Omi goals" in response.text
    assert "Read your Omi chat history" in response.text
    assert "Read your Omi screen activity" in response.text
    assert "Read people saved in your Omi account" in response.text
    assert "Create, edit, and delete your Omi memories" not in response.text
    assert "Create, update, and delete your Omi action items" not in response.text


def test_cimd_authorize_get_explicit_write_scope_shown_in_consent(mcp_client):
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params(scope="memories.read memories.write"))
    assert "Create, edit, and delete your Omi memories" in response.text


def test_cimd_consent_post_redirects_with_code_state_and_iss(mcp_client, monkeypatch):
    client, module = mcp_client
    monkeypatch.setattr(module.firebase_admin.auth, "verify_id_token", lambda token: {"uid": "user-cimd"})
    captured = {}

    def fake_grant(uid, client_id, redirect_uri, resource, scopes, code_challenge):
        captured["client_id"] = client_id
        captured["scopes"] = scopes
        return {"id": "grant-1"}, "auth-code-1"

    monkeypatch.setattr(module.mcp_oauth_db, "create_grant_and_authorization_code_if_allowed", fake_grant)
    form = _authorize_params()
    form["firebase_id_token"] = "firebase-token"
    response = client.post("/authorize", data=form)
    assert response.status_code == 200
    params = dict(parse_qsl(urlsplit(response.json()["redirect_uri"]).query))
    assert params["code"] == "auth-code-1"
    assert params["state"] == "opaque-state"
    assert params["iss"] == "https://api.omi.me"
    assert captured["client_id"] == CLIENT_ID
    assert captured["scopes"] == sorted(
        scope for scope in module.mcp_oauth_db.SUPPORTED_SCOPES if scope.endswith(".read")
    )


def test_cimd_metadata_cached_across_get_and_post(mcp_client, monkeypatch):
    client, module = mcp_client
    assert client.get("/authorize", params=_authorize_params()).status_code == 200
    fetch_count = len(_FakePool.instances)
    monkeypatch.setattr(module.firebase_admin.auth, "verify_id_token", lambda token: {"uid": "user-cimd"})
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "create_grant_and_authorization_code_if_allowed",
        lambda *a: ({"id": "g"}, "code-1"),
    )
    form = _authorize_params()
    form["firebase_id_token"] = "firebase-token"
    assert client.post("/authorize", data=form).status_code == 200
    assert len(_FakePool.instances) == fetch_count  # POST reused the cached document


def test_cimd_token_exchange_uses_metadata_client(mcp_client, monkeypatch):
    client, module = mcp_client
    exchanged = {}
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "exchange_authorization_code_for_tokens",
        lambda code, cid, uri, res, ver: exchanged.update(client_id=cid)
        or {
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "memories.read",
        },
    )
    response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": "auth-code-1",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
    )
    assert response.status_code == 200
    assert response.json()["access_token"] == "at-1"
    assert exchanged["client_id"] == CLIENT_ID


def test_refresh_grant_returns_503_when_revocation_store_unavailable(mcp_client, monkeypatch):
    """A refresh whose replay-revoke cannot be written to Redis is a
    retryable 503 temporarily_unavailable — never a silent success and never
    a 401."""
    import database.mcp_token_cache as token_cache

    client, module = mcp_client

    def boom(*args, **kwargs):
        raise token_cache.McpTokenStoreUnavailable("redis down")

    monkeypatch.setattr(module.mcp_oauth_db, "rotate_refresh_token", boom)
    response = client.post(
        "/token",
        data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "omi_rt_x"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "temporarily_unavailable"
    assert "Retry-After" in response.headers


def test_cimd_redirect_uri_must_exactly_match_document(mcp_client):
    client, _ = mcp_client
    response = client.get(
        "/authorize",
        params=_authorize_params(redirect_uri="https://app.example.com/oauth/callback/evil"),
        follow_redirects=False,
    )
    # Mismatched redirect_uri: JSON error, never a redirect.
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_cimd_unknown_document_gives_json_error_never_redirect(mcp_client, monkeypatch):
    _install_network(monkeypatch, response=_FakeResponse(status=404))
    client, _ = mcp_client
    response = client.get("/authorize", params=_authorize_params(), follow_redirects=False)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_request"


def test_cimd_error_redirect_carries_iss_after_client_and_redirect_validated(mcp_client):
    client, _ = mcp_client
    response = client.get(
        "/authorize",
        params=_authorize_params(resource="https://evil.example/v1/mcp/sse"),
        follow_redirects=False,
    )
    assert response.status_code == 302
    params = dict(parse_qsl(urlsplit(response.headers["location"]).query))
    assert params["error"] == "invalid_target"
    assert params["iss"] == "https://api.omi.me"
    assert params["state"] == "opaque-state"


def test_redirect_clears_conflicting_query_params(mcp_client, monkeypatch):
    """A registered redirect URI carrying stale code/error/state params gets
    them replaced, while unrelated params survive."""
    redirect_with_params = "https://app.example.com/oauth/callback?code=stale&keep=1&error=stale"
    _install_network(monkeypatch, response=_FakeResponse(body=_metadata_body(redirect_uris=[redirect_with_params])))
    client, module = mcp_client
    monkeypatch.setattr(module.firebase_admin.auth, "verify_id_token", lambda token: {"uid": "user-cimd"})
    monkeypatch.setattr(
        module.mcp_oauth_db,
        "create_grant_and_authorization_code_if_allowed",
        lambda *a: ({"id": "g"}, "fresh-code"),
    )
    form = _authorize_params(redirect_uri=redirect_with_params)
    form["firebase_id_token"] = "firebase-token"
    response = client.post("/authorize", data=form)
    params = dict(parse_qsl(urlsplit(response.json()["redirect_uri"]).query))
    assert params["code"] == "fresh-code"
    assert params["keep"] == "1"
    assert "error" not in params
    assert params["iss"] == "https://api.omi.me"


def test_explicit_scope_not_in_allowed_rejected_via_error_redirect(mcp_client, monkeypatch):
    """Write scopes are granted only when the client is allowed them — a
    restricted client requesting ``memories.write`` gets an invalid_scope
    redirect, not a silent grant."""
    client, module = mcp_client
    registered = {
        "id": "omi-claude-prod",
        "name": "Claude",
        "registration_mode": "claude_env",
        "allowed_redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": [module.mcp_oauth_db.MCP_RESOURCE_URL],
        "allowed_scopes": ["memories.read"],
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }
    monkeypatch.setattr(module.mcp_oauth_db, "get_client", lambda cid: registered)
    response = client.get(
        "/authorize",
        params=_authorize_params(
            client_id="omi-claude-prod",
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            scope="memories.write",
        ),
        follow_redirects=False,
    )
    assert response.status_code == 302
    params = dict(parse_qsl(urlsplit(response.headers["location"]).query))
    assert params["error"] == "invalid_scope"
    assert params["iss"] == "https://api.omi.me"


def test_preregistered_client_unaffected_by_cimd_path(mcp_client, monkeypatch):
    client, module = mcp_client
    registered = {
        "id": "omi-claude-prod",
        "name": "Claude",
        "registration_mode": "claude_env",
        "allowed_redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": [module.mcp_oauth_db.MCP_RESOURCE_URL],
        "allowed_scopes": list(module.mcp_oauth_db.SUPPORTED_SCOPES),
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }
    monkeypatch.setattr(module.mcp_oauth_db, "get_client", lambda cid: registered if cid == "omi-claude-prod" else None)
    response = client.get(
        "/authorize",
        params=_authorize_params(client_id="omi-claude-prod", redirect_uri="https://claude.ai/api/mcp/auth_callback"),
    )
    assert response.status_code == 200
    assert "Unverified third-party app" not in response.text
    assert "Connect <span dir=\"ltr\">Claude</span>" in response.text


def test_authorization_server_metadata_advertises_cimd():
    from utils.mcp_server.metadata import authorization_server_document

    assert authorization_server_document()["client_id_metadata_document_supported"] is True
