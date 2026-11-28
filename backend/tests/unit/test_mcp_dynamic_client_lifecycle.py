"""Dynamically registered MCP clients expire, and expiry is enforced end to end.

RFC 7591 lets an authorization server expire the clients it registers. Omi's
dynamic public PKCE clients carry ``expires_at``: a short unused window after
registration, slid forward by the idle TTL after each successful token
response. These tests drive the real ``/authorize`` and ``/token`` routes
through FastAPI's TestClient against an in-memory ``mcp_oauth_clients``
collection, so the expiry check in ``database.mcp_oauth.get_client`` and the
token-path refresh are exercised the way production calls them. Registration
idempotency and the expiry math itself are covered in test_mcp_oauth.py.
"""

import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

CODE_VERIFIER = "dynamic-client-lifecycle-verifier-0123456789abcdefghijkl"
CODE_CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(CODE_VERIFIER.encode("ascii")).digest()).decode("ascii").rstrip("=")
)
CLIENT_ID = "omi-dcr-lifecycle-test"
FINGERPRINT = "f" * 64
REDIRECT_URI = "https://lifecycle.example/oauth/callback"
REGISTERED_AT = datetime(2026, 11, 17, 5, 0, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Doc:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self, transaction=None, **_kwargs):
        return _Snapshot(self._store.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self._store:
            self._store[self.id].update(data)
        else:
            self._store[self.id] = dict(data)


class _DB:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        store = self.collections.setdefault(name, {})
        return type("_Collection", (), {"document": lambda _self, doc_id: _Doc(store, doc_id)})()


class _Clock:
    def __init__(self):
        self.now = REGISTERED_AT

    def __call__(self):
        return self.now


@pytest.fixture()
def mcp_sse():
    from routers import mcp_sse as module

    return module


@pytest.fixture()
def oauth_db(mcp_sse):
    return mcp_sse.mcp_oauth_db


@pytest.fixture()
def fake_db(oauth_db, monkeypatch):
    db = _DB()
    db.collection("mcp_oauth_clients").document(CLIENT_ID).set(
        {
            "id": CLIENT_ID,
            "name": "Lifecycle client",
            "registration_mode": oauth_db.DYNAMIC_CLIENT_REGISTRATION_MODE,
            "registration_fingerprint": FINGERPRINT,
            "allowed_redirect_uris": [REDIRECT_URI],
            "allowed_redirect_uri_prefixes": [],
            "allowed_resources": [oauth_db.MCP_RESOURCE_URL],
            "allowed_scopes": list(oauth_db.SUPPORTED_SCOPES),
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
            "client_secret_hash": "",
            "created_at": REGISTERED_AT,
            "last_used_at": None,
            "expires_at": REGISTERED_AT + timedelta(hours=oauth_db.DYNAMIC_CLIENT_UNUSED_TTL_HOURS),
            "disabled_at": None,
        }
    )
    monkeypatch.setattr(oauth_db, "db", db)
    return db


@pytest.fixture()
def clock(oauth_db, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(oauth_db, "_now", clock)
    return clock


@pytest.fixture()
def client(mcp_sse):
    app = FastAPI()
    app.include_router(mcp_sse.router)
    return TestClient(app)


def _authorize(client):
    return client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "state": "opaque-state",
            "code_challenge": CODE_CHALLENGE,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )


def _token(client):
    return client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": "auth-code-1",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
    )


@pytest.fixture()
def token_pair(oauth_db, monkeypatch):
    calls = []

    def fake_exchange(code, client_id, redirect_uri, resource, code_verifier):
        calls.append(client_id)
        return {
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "memories.read",
        }

    monkeypatch.setattr(oauth_db, "exchange_authorization_code_for_tokens", fake_exchange)
    return calls


def test_live_dynamic_client_can_authorize_and_exchange(client, fake_db, clock, token_pair):
    assert _authorize(client).status_code == 200
    response = _token(client)

    assert response.status_code == 200
    assert token_pair == [CLIENT_ID]


def test_expired_dynamic_client_is_rejected_at_authorize(client, oauth_db, fake_db, clock):
    clock.now = REGISTERED_AT + timedelta(hours=oauth_db.DYNAMIC_CLIENT_UNUSED_TTL_HOURS, seconds=1)

    response = _authorize(client)

    # Unknown clients never get an error redirect: the redirect URI cannot be trusted.
    assert response.status_code == 400
    assert "location" not in response.headers
    assert response.json() == {"error": "invalid_request", "error_description": "Invalid authorization request"}


def test_expired_dynamic_client_is_rejected_at_token(client, oauth_db, fake_db, clock, token_pair):
    clock.now = REGISTERED_AT + timedelta(hours=oauth_db.DYNAMIC_CLIENT_UNUSED_TTL_HOURS, seconds=1)

    response = _token(client)

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_client"
    assert token_pair == []


def test_successful_token_response_slides_dynamic_client_expiry(client, oauth_db, fake_db, clock, token_pair):
    clock.now = REGISTERED_AT + timedelta(hours=2)

    assert _token(client).status_code == 200

    stored = fake_db.collections["mcp_oauth_clients"][CLIENT_ID]
    idle_expiry = clock.now + timedelta(days=oauth_db.DYNAMIC_CLIENT_IDLE_TTL_DAYS)
    assert stored["last_used_at"] == clock.now
    assert stored["expires_at"] == idle_expiry
    assert fake_db.collections[oauth_db.DYNAMIC_CLIENT_REGISTRATIONS_COLLECTION][FINGERPRINT] == {
        "client_id": CLIENT_ID,
        "expires_at": idle_expiry,
    }

    # Past the unused window, a used client keeps working.
    clock.now = REGISTERED_AT + timedelta(hours=oauth_db.DYNAMIC_CLIENT_UNUSED_TTL_HOURS * 2)
    assert _authorize(client).status_code == 200


def test_expiry_refresh_failure_does_not_fail_the_token_response(
    client, oauth_db, fake_db, clock, token_pair, monkeypatch
):
    def broken_touch(_client):
        raise RuntimeError("firestore down")

    monkeypatch.setattr(oauth_db, "touch_dynamic_client", broken_touch)

    response = _token(client)

    assert response.status_code == 200
    assert response.json()["access_token"] == "at-1"


def test_dynamic_client_consent_is_marked_unverified_with_redirect_host(client, fake_db, clock):
    # The client name comes from an unauthenticated POST /register, so anyone
    # can pick "ChatGPT". Consent must flag it and show the redirect host.
    fake_db.collections["mcp_oauth_clients"][CLIENT_ID]["name"] = "ChatGPT"

    response = _authorize(client)

    assert response.status_code == 200
    assert "Unverified third-party app" in response.text
    assert "Redirect host:" in response.text
    assert "Client ID host:" not in response.text
    assert re.findall(r'<span class="unverified-client-host">([^<]*)</span>', response.text) == ["lifecycle.example"]


def test_successful_refresh_slides_dynamic_client_expiry(client, oauth_db, fake_db, clock, monkeypatch):
    rotations = []

    def fake_rotate(refresh_token, client_id, resource, scope, on_outcome=None):
        rotations.append((refresh_token, client_id))
        if on_outcome is not None:
            on_outcome("rotated")
        return {
            "access_token": "at-2",
            "refresh_token": "rt-2",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "memories.read",
        }

    monkeypatch.setattr(oauth_db, "rotate_refresh_token", fake_rotate)
    clock.now = REGISTERED_AT + timedelta(hours=3)

    response = client.post(
        "/token",
        data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "rt-1"},
    )

    assert response.status_code == 200
    assert rotations == [("rt-1", CLIENT_ID)]
    stored = fake_db.collections["mcp_oauth_clients"][CLIENT_ID]
    assert stored["last_used_at"] == clock.now
    assert stored["expires_at"] == clock.now + timedelta(days=oauth_db.DYNAMIC_CLIENT_IDLE_TTL_DAYS)
