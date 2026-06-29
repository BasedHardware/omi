"""Tests for the WhatsApp /toggle endpoint.

Mirrors plugins/omi-telegram-app/test/test_fixes.py in structure for the
toggle-related cases. Covers:
- Successful toggle (right access_token, existing phone)
- 403 on wrong access_token
- 403 on unknown phone (enumeration-safe — same response as wrong token)
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
    def test_enable_with_correct_access_token(self, client):
        _seed_user()
        r = client.post("/toggle", json={"phone": "15550001111", "enabled": True, "access_token": SECRET_TOKEN})
        assert r.status_code == 200
        assert r.json()["auto_reply_enabled"] is True

    def test_disable_with_correct_access_token(self, client):
        _seed_user()
        # First enable
        client.post("/toggle", json={"phone": "15550001111", "enabled": True, "access_token": SECRET_TOKEN})
        # Then disable
        r = client.post("/toggle", json={"phone": "15550001111", "enabled": False, "access_token": SECRET_TOKEN})
        assert r.status_code == 200
        assert r.json()["auto_reply_enabled"] is False

    def test_403_on_wrong_access_token(self, client):
        _seed_user()
        r = client.post(
            "/toggle",
            json={"phone": "15550001111", "enabled": True, "access_token": "WRONG"},
        )
        assert r.status_code == 403

    def test_403_on_unknown_phone(self, client):
        """Same 403 as wrong access_token \u2014 don't leak which phones exist."""
        _seed_user(phone="15550001111")
        r = client.post(
            "/toggle",
            json={"phone": "15559999999", "enabled": True, "access_token": SECRET_TOKEN},
        )
        assert r.status_code == 403

    def test_unknown_phone_and_wrong_token_return_same_detail(self, client):
        """Verify both error paths return identical responses (no enumeration)."""
        _seed_user(phone="15550001111")

        r_unknown = client.post(
            "/toggle",
            json={"phone": "15559999999", "enabled": True, "access_token": SECRET_TOKEN},
        )
        r_wrong = client.post(
            "/toggle",
            json={"phone": "15550001111", "enabled": True, "access_token": "WRONG"},
        )
        assert r_unknown.status_code == r_wrong.status_code == 403
        assert r_unknown.json() == r_wrong.json()
