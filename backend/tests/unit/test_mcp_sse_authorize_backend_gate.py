"""The MCP /authorize consent flow is Firebase-only (loads the Firebase JS SDK, posts a
firebase_id_token) and must be gated off under non-Firebase backends, exactly like /v1/oauth/authorize
(cubic review PR 10887, review 4939247683). Under AUTH_BACKEND=oidc it must fail 501, not dead-end the
MCP OIDC flow on a page that can't work.

``auth_backend_name()`` reads AUTH_BACKEND at call time, so monkeypatch.setenv selects the backend.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers.mcp_sse import _guard_firebase_authorize_backend


def test_authorize_gated_501_on_oidc_backend(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    with pytest.raises(HTTPException) as exc:
        _guard_firebase_authorize_backend()
    assert exc.value.status_code == 501


def test_authorize_allowed_on_firebase_backend(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    _guard_firebase_authorize_backend()  # must not raise
