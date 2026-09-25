"""Contract tests for the retired Agent VM broker tombstones.

These pin the response shapes every desktop client released before the
retirement still depends on. They are the regression guard for the only
server change that hits all old clients at once:

- provision/stop-self answer 410 — never 401, because the desktop APIClient
  signs the user out on any 401 here (signOutOn401) and a retirement must
  not force sign-outs;
- status answers 200 with a null body — never a 200 body claiming
  ``status: "provisioning"`` without an IP, which released clients would
  treat as progress and poll for ~6.25 minutes.
"""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import desktop_agent_vm  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(desktop_agent_vm.router)
    return TestClient(app)


def test_provision_is_gone_not_unauthorized(client: TestClient) -> None:
    response = client.post("/v2/agent/provision")
    assert response.status_code == 410
    assert response.status_code != 401


def test_provision_surfaces_a_machine_readable_detail(client: TestClient) -> None:
    response = client.post("/v2/agent/provision")
    assert response.json()["detail"]


def test_stop_self_is_gone_not_unauthorized(client: TestClient) -> None:
    response = client.post("/v2/agent/vm/stop-self")
    assert response.status_code == 410
    assert response.status_code != 401


def test_status_is_200_with_null_body(client: TestClient) -> None:
    response = client.get("/v2/agent/status")
    assert response.status_code == 200
    assert response.json() is None


def test_status_never_reports_provisioning_without_ip(client: TestClient) -> None:
    """A provisioning body without an IP makes old clients poll 75x5s."""
    response = client.get("/v2/agent/status")
    body = response.json()
    assert not (isinstance(body, dict) and body.get("status") == "provisioning" and not body.get("ip"))


def test_tombstones_do_not_require_authentication(client: TestClient) -> None:
    """No Authorization header anywhere: auth failures are the 401 class the
    retirement must never emit, so the tombstones skip auth entirely."""
    for method, path in (("post", "/v2/agent/provision"), ("get", "/v2/agent/status")):
        response = getattr(client, method)(path, headers={"Authorization": "Bearer stale-or-absent"})
        assert response.status_code in (200, 410)
