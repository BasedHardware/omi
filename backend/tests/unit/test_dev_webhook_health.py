"""Unit tests for GET /v1/users/developer/webhook/{wtype}/health.

The db helper (get_dev_webhook_health) is verified directly against a patched Redis
proxy. The router endpoint's response mapping is verified in CI, where routers.users'
heavy STT imports resolve; locally those deps are absent, so the endpoint cases skip
while the db-helper cases still run. Uses the sanctioned seams (import + patch.object,
no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from unittest.mock import patch

import pytest

import database.webhook_health as wh

try:
    from routers import users as users_router

    _USERS_IMPORTABLE = True
except Exception:  # heavy STT deps unavailable locally; present in CI
    users_router = None
    _USERS_IMPORTABLE = False


class _Wtype:
    """Stand-in for a WebhookType enum member (only .value is used)."""

    def __init__(self, value):
        self.value = value


# ---------------------------------------------------------------------------
# db helper: get_dev_webhook_health
# ---------------------------------------------------------------------------
def test_db_health_none_when_no_data():
    with patch.object(wh, "r") as r:
        r.hgetall.return_value = {}
        assert wh.get_dev_webhook_health("u1", _Wtype("audio_bytes")) is None


def test_db_health_decodes_and_uses_value_key():
    with patch.object(wh, "r") as r:
        r.hgetall.return_value = {b"failure_count": b"3", b"disabled": b"1", b"last_error": b"boom"}
        out = wh.get_dev_webhook_health("u1", _Wtype("audio_bytes"))
    assert out == {"failure_count": "3", "disabled": "1", "last_error": "boom"}
    assert r.hgetall.call_args[0][0] == "dev_webhook_health:u1:audio_bytes"


def test_db_health_fail_open_on_redis_error():
    with patch.object(wh, "r") as r:
        r.hgetall.side_effect = RuntimeError("redis down")
        assert wh.get_dev_webhook_health("u1", _Wtype("audio_bytes")) is None


def test_db_health_stringifies_non_enum_type():
    with patch.object(wh, "r") as r:
        r.hgetall.return_value = {b"failure_count": b"0"}
        wh.get_dev_webhook_health("u1", "memory_created")
    assert r.hgetall.call_args[0][0] == "dev_webhook_health:u1:memory_created"


# ---------------------------------------------------------------------------
# router endpoint mapping (runs in CI where routers.users imports)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _USERS_IMPORTABLE, reason="routers.users heavy deps unavailable locally")
def test_endpoint_has_data_false_when_absent():
    with patch.object(users_router, "get_dev_webhook_health", return_value=None):
        resp = users_router.get_user_webhook_health_endpoint(wtype=_Wtype("audio_bytes"), uid="u1")
    assert resp == {
        "type": "audio_bytes",
        "has_data": False,
        "failure_count": 0,
        "last_success_at": None,
        "last_failure_at": None,
        "last_status": None,
        "last_error": None,
        "disabled": False,
    }


@pytest.mark.skipif(not _USERS_IMPORTABLE, reason="routers.users heavy deps unavailable locally")
def test_endpoint_maps_recorded_fields():
    health = {
        "failure_count": "4",
        "last_success_at": "1700000000",
        "last_failure_at": "",  # reset -> None
        "last_status": "500",
        "last_error": "",  # reset -> None
        "disabled": "1",
    }
    with patch.object(users_router, "get_dev_webhook_health", return_value=health):
        resp = users_router.get_user_webhook_health_endpoint(wtype=_Wtype("audio_bytes"), uid="u1")
    assert resp["type"] == "audio_bytes"
    assert resp["has_data"] is True
    assert resp["failure_count"] == 4
    assert resp["last_success_at"] == 1700000000
    assert resp["last_failure_at"] is None
    assert resp["last_status"] == 500
    assert resp["last_error"] is None
    assert resp["disabled"] is True
