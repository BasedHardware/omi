"""cubic review 4909186286: the OIDC adapter's ``get_user_profile`` crashed with IndexError when
Keycloak returned the ``phone_number`` attribute PRESENT but EMPTY (``{"phone_number": []}``). A plain
``.get("phone_number", [None])`` default only fires when the key is absent, so ``[][0]`` raised. The
fix uses ``... or [None]`` so an empty list falls back too.

Hermetic: the adapter imports ``httpx`` lazily; monkeypatch ``httpx.get`` + stub the admin helpers.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from utils.auth.adapters.oidc import OIDCAuthProvider


def _provider(monkeypatch, rep: dict):
    provider = OIDCAuthProvider()
    monkeypatch.setattr(provider, "_admin_token", lambda: "admin-token")
    monkeypatch.setattr(provider, "_admin_api", lambda: "http://keycloak:8080/admin/realms/omi")
    monkeypatch.setattr(httpx, "get", lambda url, headers=None, **k: SimpleNamespace(status_code=200, json=lambda: rep))
    return provider


def test_phone_number_empty_list_is_none_not_indexerror(monkeypatch):
    provider = _provider(monkeypatch, {"id": "u1", "attributes": {"phone_number": []}})
    profile = provider.get_user_profile("u1")  # must not raise IndexError
    assert profile.phone_number is None


def test_phone_number_present_returns_first(monkeypatch):
    provider = _provider(monkeypatch, {"id": "u1", "attributes": {"phone_number": ["+15551234567"]}})
    assert provider.get_user_profile("u1").phone_number == "+15551234567"


def test_phone_number_absent_is_none(monkeypatch):
    provider = _provider(monkeypatch, {"id": "u1"})
    assert provider.get_user_profile("u1").phone_number is None
