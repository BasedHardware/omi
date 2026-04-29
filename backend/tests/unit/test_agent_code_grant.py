"""Unit tests for POST /v1/agent/code/wallet/grant and GET /v1/agent/code/wallet/{uid}.

Validation logic is tested without any real Firestore calls — all database
operations are replaced with MagicMock stubs via monkeypatch.
"""

import os
import sys
import types
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Minimal environment setup before any app module is imported
# ---------------------------------------------------------------------------

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ["ADMIN_KEY"] = "test-admin-secret"

# Stub Firestore client so importing database.agent_code never hits ADC.
mock_client_module = types.ModuleType("database._client")
mock_client_module.db = MagicMock()
sys.modules["database._client"] = mock_client_module

# Stub firebase_admin used by utils.other.endpoints.
firebase_admin = types.ModuleType("firebase_admin")
firebase_admin.auth = MagicMock()
sys.modules["firebase_admin"] = firebase_admin
sys.modules["firebase_admin.auth"] = firebase_admin.auth

# Stub google.cloud.firestore so the Increment/SERVER_TIMESTAMP sentinels
# exist without a real GCP connection.
google_mod = types.ModuleType("google")
google_cloud_mod = types.ModuleType("google.cloud")
firestore_mod = types.ModuleType("google.cloud.firestore")
firestore_mod.Increment = MagicMock(side_effect=lambda x: x)
firestore_mod.SERVER_TIMESTAMP = "SERVER_TIMESTAMP"
sys.modules["google"] = google_mod
sys.modules["google.cloud"] = google_cloud_mod
sys.modules["google.cloud.firestore"] = firestore_mod

# Stub the OpenRouter utility so the router module can be imported without
# httpx / aiohttp deps that may not be present in the test environment.
openrouter_mod = types.ModuleType("utils.agent_code.openrouter")
openrouter_mod.StreamUsage = MagicMock
openrouter_mod.proxy_chat_completion = MagicMock()
sys.modules["utils.agent_code"] = types.ModuleType("utils.agent_code")
sys.modules["utils.agent_code.openrouter"] = openrouter_mod

pricing_mod = types.ModuleType("utils.agent_code.pricing")
pricing_mod.MODEL_ID = "test-model"
pricing_mod.compute_charge_cents = MagicMock(return_value=1)
pricing_mod.compute_raw_cost_cents = MagicMock(return_value=1)
sys.modules["utils.agent_code.pricing"] = pricing_mod

# Stub Redis so utils.other.endpoints imports cleanly.
redis_mod = types.ModuleType("database.redis_db")
redis_mod.check_rate_limit = MagicMock()
redis_mod.try_acquire_listen_lock = MagicMock()
sys.modules["database.redis_db"] = redis_mod

rate_limit_mod = types.ModuleType("utils.rate_limit_config")
rate_limit_mod.RATE_POLICIES = {}
rate_limit_mod.RATE_LIMIT_SHADOW = False
rate_limit_mod.get_effective_limit = MagicMock(return_value=(60, 60))
sys.modules["utils.rate_limit_config"] = rate_limit_mod

# Stub redis package itself (imported by utils.other.endpoints).
sys.modules["redis"] = types.ModuleType("redis")

# ---------------------------------------------------------------------------
# Now it is safe to import the router and database module
# ---------------------------------------------------------------------------

import database.agent_code as agent_code_db  # noqa: E402  (must be after stubs)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import routers.agent_code as agent_code_router  # noqa: E402

app = FastAPI()
app.include_router(agent_code_router.router)
client = TestClient(app, raise_server_exceptions=False)

VALID_HEADERS = {"X-Admin-Key": "test-admin-secret"}
VALID_BODY = {"uid": "user-abc", "amount_cents": 500, "reason": "Test seed"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _stub_db(monkeypatch, balance_after: int = 500, grant_id: str = "grant-xyz"):
    """Patch the db functions on the router's imported module reference."""
    monkeypatch.setattr(agent_code_router.agent_code_db, "credit_balance_cents", MagicMock(return_value=balance_after))
    monkeypatch.setattr(agent_code_router.agent_code_db, "record_grant", MagicMock(return_value=grant_id))
    monkeypatch.setattr(agent_code_router.agent_code_db, "get_balance_cents", MagicMock(return_value=balance_after))


# ---------------------------------------------------------------------------
# Auth / header tests
# ---------------------------------------------------------------------------


def test_grant_missing_header_returns_422():
    # FastAPI rejects a missing required Header as 422 Unprocessable Entity.
    resp = client.post("/v1/agent/code/wallet/grant", json=VALID_BODY)
    assert resp.status_code == 422


def test_grant_wrong_key_returns_403():
    resp = client.post("/v1/agent/code/wallet/grant", headers={"X-Admin-Key": "wrong-key"}, json=VALID_BODY)
    assert resp.status_code == 403


def test_admin_wallet_read_wrong_key_returns_403():
    resp = client.get("/v1/agent/code/wallet/user-abc", headers={"X-Admin-Key": "wrong-key"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# amount_cents validation — Pydantic raises 422 for field errors
# ---------------------------------------------------------------------------


def test_grant_zero_amount_returns_422():
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "amount_cents": 0},
    )
    assert resp.status_code == 422


def test_grant_negative_amount_returns_422():
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "amount_cents": -1},
    )
    assert resp.status_code == 422


def test_grant_exceeds_cap_returns_422():
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "amount_cents": 100_001},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert any("cap" in str(e.get("msg", "")).lower() for e in body.get("detail", []))


def test_grant_at_cap_is_accepted(monkeypatch):
    _stub_db(monkeypatch, balance_after=100_000, grant_id="g1")
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "amount_cents": 100_000},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# reason validation
# ---------------------------------------------------------------------------


def test_grant_empty_reason_returns_422():
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "reason": ""},
    )
    assert resp.status_code == 422


def test_grant_whitespace_only_reason_returns_422():
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "reason": "   "},
    )
    assert resp.status_code == 422


def test_grant_oversized_reason_returns_422():
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "reason": "x" * 201},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert any("200" in str(e.get("msg", "")) for e in body.get("detail", []))


def test_grant_reason_exactly_200_chars_accepted(monkeypatch):
    _stub_db(monkeypatch)
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "reason": "a" * 200},
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# uid validation
# ---------------------------------------------------------------------------


def test_grant_empty_uid_returns_422():
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "uid": ""},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_grant_valid_request_returns_balance_and_grant_id(monkeypatch):
    _stub_db(monkeypatch, balance_after=1500, grant_id="grant-xyz")
    resp = client.post("/v1/agent/code/wallet/grant", headers=VALID_HEADERS, json=VALID_BODY)

    assert resp.status_code == 200
    data = resp.json()
    assert data["balance_cents"] == 1500
    assert data["grant_id"] == "grant-xyz"


def test_grant_calls_credit_and_record_grant_once(monkeypatch):
    _stub_db(monkeypatch, balance_after=500, grant_id="g99")

    resp = client.post("/v1/agent/code/wallet/grant", headers=VALID_HEADERS, json=VALID_BODY)
    assert resp.status_code == 200

    agent_code_router.agent_code_db.credit_balance_cents.assert_called_once_with("user-abc", 500)
    agent_code_router.agent_code_db.record_grant.assert_called_once()
    call_kwargs = agent_code_router.agent_code_db.record_grant.call_args
    assert call_kwargs.kwargs["uid"] == "user-abc"
    assert call_kwargs.kwargs["amount_cents"] == 500
    assert call_kwargs.kwargs["reason"] == "Test seed"
    # granted_by_hash must be a short sha256 snippet, never the raw key.
    granted_by_hash = call_kwargs.kwargs["granted_by_hash"]
    assert "test-admin-secret" not in granted_by_hash
    assert granted_by_hash.startswith("admin:")


def test_grant_reason_is_stripped(monkeypatch):
    _stub_db(monkeypatch, balance_after=500, grant_id="g1")
    resp = client.post(
        "/v1/agent/code/wallet/grant",
        headers=VALID_HEADERS,
        json={**VALID_BODY, "reason": "  padded reason  "},
    )
    assert resp.status_code == 200
    call_kwargs = agent_code_router.agent_code_db.record_grant.call_args
    assert call_kwargs.kwargs["reason"] == "padded reason"


# ---------------------------------------------------------------------------
# Admin wallet read
# ---------------------------------------------------------------------------


def test_admin_wallet_read_valid_key(monkeypatch):
    _stub_db(monkeypatch, balance_after=250)
    resp = client.get("/v1/agent/code/wallet/user-abc", headers=VALID_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["balance_cents"] == 250
