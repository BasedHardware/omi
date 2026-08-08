"""Finding #2: the OIDC auth adapter's ``delete_user`` must be idempotent on a missing identity.

Account deletion is durable and retried: ``services.users.account_deletion.background_wipe_user_data``
calls ``auth.delete_account`` (→ the port's ``delete_user``) and treats an *already-absent* auth user as
success so a re-run completes instead of looping forever on a "wipe failed". The Firebase adapter gets
this for free — the worker swallows ``UserNotFoundError`` by message. The OIDC adapter previously raised
a generic ``AuthError("OIDC delete_user failed: status=404")`` on a Keycloak 404, which matched neither
of the worker's already-absent markers and so was fatal. The fix makes a 404 an idempotent no-op (the
same not-found contract the object-store delete adapters already use), so retries converge.

Hermetic: the adapter imports ``httpx`` lazily inside the method, so we monkeypatch ``httpx.delete`` and
stub the admin-token/admin-api helpers — no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from utils.auth import errors
from utils.auth.adapters.oidc import OIDCAuthProvider


def _provider(monkeypatch, status_code: int):
    provider = OIDCAuthProvider()
    monkeypatch.setattr(provider, "_admin_token", lambda: "admin-token")
    monkeypatch.setattr(provider, "_admin_api", lambda: "http://keycloak:8080/admin/realms/omi")

    captured: dict = {}

    def fake_delete(url, headers=None, **kwargs):
        captured["url"] = url
        captured["headers"] = headers
        return SimpleNamespace(status_code=status_code)

    monkeypatch.setattr(httpx, "delete", fake_delete)
    return provider, captured


def test_delete_user_404_is_idempotent_no_raise(monkeypatch):
    """A Keycloak 404 (identity already removed) must NOT raise, so the deletion worker converges."""
    provider, captured = _provider(monkeypatch, 404)
    # Must not raise.
    assert provider.delete_user("missing-uid") is None
    assert captured["url"].endswith("/users/missing-uid")


@pytest.mark.parametrize("status", [200, 204])
def test_delete_user_success_no_raise(monkeypatch, status):
    provider, _captured = _provider(monkeypatch, status)
    assert provider.delete_user("uid-1") is None


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_delete_user_other_failures_still_raise(monkeypatch, status):
    """Genuine failures (auth/server errors) must still raise so the wipe is retried, not silently lost."""
    provider, _captured = _provider(monkeypatch, status)
    with pytest.raises(errors.AuthError):
        provider.delete_user("uid-1")
