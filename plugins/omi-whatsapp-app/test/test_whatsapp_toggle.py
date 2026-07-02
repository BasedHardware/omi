"""Tests for the WhatsApp /toggle endpoint.

After the PR #8528 security redesign (Git-on-my-level review): the
endpoint no longer accepts an `access_token` in the request body. Auth
is via the plugin bearer (Authorization: Bearer header); the phone
parameter alone identifies the user/chat (the binding was made at
/start handshake time). Long-lived platform credentials never flow
through chat.

Mirrors plugins/omi-telegram-app/test/test_fixes.py in structure for the
toggle-related cases. Covers:
- Successful toggle with phone-only payload
- 403 on unknown phone
- Extra `access_token` field in body is ignored (not used for auth)
"""

from __future__ import annotations

import os

import pytest

_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
from conftest import load_main_module

main = load_main_module()


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    from conftest import load_simple_storage

    simple_storage = load_simple_storage()

    monkeypatch.setattr(simple_storage, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(simple_storage, "USERS_FILE", os.path.join(str(tmp_path), "users_data.json"))
    monkeypatch.setattr(simple_storage, "PENDING_FILE", os.path.join(str(tmp_path), "pending_setups.json"))
    monkeypatch.setattr(simple_storage, "users", {})
    monkeypatch.setattr(simple_storage, "pending_setups", {})
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(main.app)


SECRET_TOKEN = "EAATOGGLE_SECRET_DO_NOT_LOG"


def _seed_user(phone="15550001111", access_token=SECRET_TOKEN):
    from conftest import load_simple_storage

    simple_storage = load_simple_storage()

    simple_storage.save_user(
        phone=phone,
        omi_uid="u-1",
        persona_id="p-1",
        omi_dev_api_key="k-1",
        access_token=access_token,
        phone_number_id="pn-1",
        verify_token="vt-1",
        auto_reply_enabled=False,
    )


class TestToggle:
    def test_enable_with_phone_only(self, client):
        """P1 (Git-on-my-level review): the manifest must not require
        the caller to send the access_token. Verify /toggle accepts a
        request with only phone + enabled (no credential in body)."""
        _seed_user()
        r = client.post("/toggle", json={"phone": "15550001111", "enabled": True})
        assert r.status_code == 200, (
            f"phone-only toggle must work after the security redesign. "
            f"Got {r.status_code}: {r.text}"
        )
        assert r.json()["auto_reply_enabled"] is True

    def test_disable_with_phone_only(self, client):
        _seed_user()
        # First enable
        client.post("/toggle", json={"phone": "15550001111", "enabled": True})
        # Then disable
        r = client.post("/toggle", json={"phone": "15550001111", "enabled": False})
        assert r.status_code == 200
        assert r.json()["auto_reply_enabled"] is False

    def test_403_on_unknown_phone(self, client):
        """Same 403 as the old wrong-access_token path — don't leak
        which phones exist. The bearer holder can pass any phone they
        know; the only failure mode is 'no such user'."""
        _seed_user(phone="15550001111")
        r = client.post(
            "/toggle",
            json={"phone": "15559999999", "enabled": True},
        )
        assert r.status_code == 403

    def test_ignores_access_token_in_body(self, client):
        """If a caller (e.g. a misconfigured chat assistant) sends
        access_token in the body, the request must NOT silently use it
        for auth. The new ToggleRequest model has no access_token field;
        Pydantic drops extra fields by default and the auth path no
        longer reads access_token from the body."""
        _seed_user(access_token="real-token")

        client_ = client
        # Caller sends a WRONG access_token in the body. If the auth
        # path still read access_token, this would 403. Under the new
        # bearer+phone auth model, it must succeed.
        r = client_.post(
            "/toggle",
            json={"phone": "15550001111", "enabled": True, "access_token": "WRONG-TOKEN"},
        )
        assert r.status_code == 200, (
            f"access_token in body must be ignored (not used for auth). "
            f"Got {r.status_code}: {r.text}"
        )

    def test_normalizes_formatted_phone(self, client):
        """The phone normalization fix (cubic P2) still works under
        the new auth model — formatted E.164 variants match the stored
        user."""
        _seed_user(phone="15550001111")
        r = client.post(
            "/toggle",
            json={"phone": "+1 (555) 000-1111", "enabled": True},
        )
        assert r.status_code == 200
        assert r.json()["phone"] == "15550001111"
        assert r.json()["auto_reply_enabled"] is True