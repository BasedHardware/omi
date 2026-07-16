"""Tests for plugins/_shared/auth.py — the shared bearer-token dependency.

Covers the policy matrix documented in auth.py:
  | AI_CLONE_PLUGIN_TOKEN | OMI_DEV_MODE | Outcome                              |
  |-----------------------|--------------|--------------------------------------|
  | set                   | (any)        | bearer must match (secrets.compare)  |
  | unset                 | 1            | allow all (dev only — explicit)      |
  | unset                 | unset        | 503 Service Unavailable (misconfig)  |

The dependency is FastAPI-shaped so we wire it into a tiny throwaway
FastAPI app per test rather than reaching into either plugin's main.py.
This is also what the plugin test files do for `/setup` regression
coverage (test_auth_setup.py).

Uses TestClient (sync) + httpx.AsyncClient via httpx transport — no live
network. Bearer value comparison is verified via a parallel call that
sends the WRONG token and asserts the request is rejected with the same
status code as a missing token (no oracle leak).
"""

from __future__ import annotations

import os

import pytest
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

# Import the module under test directly. _HERE/_SHARED setup is at the
# bottom of plugins/_shared/test/test_auth.py — added to sys.path so
# `from auth import require_bearer` resolves.
import sys as _sys
import os as _os

_HERE = _os.path.dirname(_os.path.abspath(__file__))
_SHARED = _os.path.abspath(_os.path.join(_HERE, ".."))
if _SHARED not in _sys.path:
    _sys.path.insert(0, _SHARED)

from auth import get_plugin_token, require_bearer  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_app():
    """Build a tiny FastAPI app that mounts require_bearer on /protected."""
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(require_bearer)])
    def protected():
        return {"ok": True}

    return app


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip AI_CLONE_PLUGIN_TOKEN and OMI_DEV_MODE before each test.

    Individual tests opt into specific combinations via monkeypatch.setenv.
    Stripping first ensures no inherited env var from the shell leaks
    into a test.
    """
    monkeypatch.delenv("AI_CLONE_PLUGIN_TOKEN", raising=False)
    monkeypatch.delenv("OMI_DEV_MODE", raising=False)
    yield


# ---------------------------------------------------------------------------
# 1. Policy matrix
# ---------------------------------------------------------------------------
class TestPolicyMatrix:
    def test_no_token_no_dev_mode_returns_503(self, monkeypatch):
        """Misconfigured production: no token, no dev mode -> 503."""
        # Both env vars are stripped by _clean_env.
        app = _make_app()
        client = TestClient(app)
        r = client.get("/protected")
        assert r.status_code == 503, (
            "Misconfigured production MUST fail closed (503), not silently " "allow all callers."
        )
        assert "not configured" in r.json()["detail"].lower()

    def test_no_token_with_dev_mode_allows(self, monkeypatch):
        """Dev mode explicit: no token, OMI_DEV_MODE=1 -> 200."""
        monkeypatch.setenv("OMI_DEV_MODE", "1")
        app = _make_app()
        client = TestClient(app)
        r = client.get("/protected")
        assert r.status_code == 200

    def test_token_set_with_dev_mode_still_enforces(self, monkeypatch):
        """Dev mode + token: must enforce bearer match.

        The dev mode opt-out is for "I forgot to set the token in dev" —
        not "I want to skip auth even though I have a token configured".
        Otherwise a dev who's already set AI_CLONE_PLUGIN_TOKEN could
        accidentally bypass auth by toggling dev mode on.
        """
        monkeypatch.setenv("OMI_DEV_MODE", "1")
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "secret-abc")
        app = _make_app()
        client = TestClient(app)
        r = client.get("/protected")
        assert r.status_code == 401, (
            "Dev mode must NOT bypass auth when a token is configured. "
            "Otherwise a misconfigured dev would silently allow all callers."
        )


# ---------------------------------------------------------------------------
# 2. Bearer match behavior
# ---------------------------------------------------------------------------
class TestBearerMatch:
    def test_correct_bearer_returns_200(self, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret-token")
        app = _make_app()
        client = TestClient(app)
        r = client.get("/protected", headers={"Authorization": "Bearer the-secret-token"})
        assert r.status_code == 200

    def test_wrong_bearer_returns_401(self, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret-token")
        app = _make_app()
        client = TestClient(app)
        r = client.get("/protected", headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_missing_header_returns_401(self, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret-token")
        app = _make_app()
        client = TestClient(app)
        r = client.get("/protected")
        assert r.status_code == 401

    def test_non_bearer_scheme_returns_401(self, monkeypatch):
        """Anything that isn't 'Bearer <token>' is rejected.

        The plugin only honors the bearer scheme — Basic / Digest /
        arbitrary custom schemes must not bypass the check.
        """
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret-token")
        app = _make_app()
        client = TestClient(app)
        r = client.get("/protected", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r.status_code == 401

    def test_wrong_and_missing_responses_are_indistinguishable(self, monkeypatch):
        """Same status + body for wrong vs missing — no oracle leak.

        An attacker probing the endpoint shouldn't be able to distinguish
        "wrong token" from "no header" via the response shape.
        """
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret-token")
        app = _make_app()
        client = TestClient(app)

        r_missing = client.get("/protected")
        r_wrong = client.get("/protected", headers={"Authorization": "Bearer wrong"})

        assert r_missing.status_code == r_wrong.status_code
        assert r_missing.json() == r_wrong.json()

    def test_comparison_is_constant_time(self, monkeypatch):
        """Smoke test for the secrets.compare_digest path.

        We can't directly assert timing non-leakage in a unit test, but
        we can verify the function rejects the right tokens and accepts
        the right one — anything more would need a statistical timing
        analysis (out of scope).
        """
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "abc")
        app = _make_app()
        client = TestClient(app)
        assert client.get("/protected", headers={"Authorization": "Bearer abc"}).status_code == 200
        # Prefix-match should NOT succeed.
        assert client.get("/protected", headers={"Authorization": "Bearer ab"}).status_code == 401
        # Suffix-match should NOT succeed.
        assert client.get("/protected", headers={"Authorization": "Bearer bc"}).status_code == 401

    def test_non_ascii_header_returns_401_not_500(self, monkeypatch):
        """Identified by cubic (P1): secrets.compare_digest raises
        TypeError on non-ASCII input. Without a guard, a non-ASCII
        Authorization header surfaces as an unhandled 500, which an
        attacker can probe to distinguish 'invalid token' (401) from
        'token triggered a 500'. We must convert the 500 path into the
        same uniform 401.

        httpx (used by FastAPI's TestClient) itself rejects non-ASCII
        header values BEFORE they reach our dependency. So we exercise
        the dependency directly via asyncio — the dependency is the
        one place that could otherwise leak a TypeError as a 500.
        """
        import asyncio
        from auth import require_bearer

        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret")

        async def _call():
            # Pass a non-ASCII Authorization string directly — this is
            # what would arrive at the dependency if anything between
            # the client and our code failed to sanitize (e.g. a proxy
            # or a misbehaving client).
            return await require_bearer(authorization="Bearer \u4e2d\u6587")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(_call())
        assert exc_info.value.status_code == 401, (
            "Non-ASCII Authorization header must yield uniform 401, not a "
            "500 from TypeError leaking past the dependency."
        )
        assert exc_info.value.detail == "Invalid bearer token"

    def test_non_ascii_configured_token_returns_401_not_500(self, monkeypatch):
        """Same guard for the configured-token side: a server-side
        misconfiguration with a non-ASCII AI_CLONE_PLUGIN_TOKEN must
        not produce TypeErrors for every caller."""
        import asyncio
        from auth import require_bearer

        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "tok\u00e9n")  # accented

        async def _call():
            return await require_bearer(authorization="Bearer anything")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(_call())
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# 3. get_plugin_token sentinel
# ---------------------------------------------------------------------------
class TestGetPluginToken:
    def test_returns_empty_string_when_unset(self, monkeypatch):
        monkeypatch.delenv("AI_CLONE_PLUGIN_TOKEN", raising=False)
        assert get_plugin_token() == ""

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "x")
        assert get_plugin_token() == "x"
