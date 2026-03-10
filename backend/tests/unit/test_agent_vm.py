"""Tests for agent VM endpoints — vm-ensure and vm-status.

Verifies:
- vm-ensure creates new VMs for users with no existing VM
- vm-ensure restarts stopped/terminated VMs
- vm-ensure is idempotent (doesn't double-provision)
- vm-status returns full VM fields (vm_name, ip, auth_token, zone, created_at)
- vm-status triggers restart for stopped VMs (Rust parity)
- Response JSON matches desktop Swift AgentProvisionResponse/AgentStatusResponse
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# Stub heavy imports before importing the router
sys.modules.setdefault('database._client', MagicMock())
sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('utils.retrieval.agentic', MagicMock(agent_config_context=MagicMock(), CORE_TOOLS=[]))
sys.modules.setdefault('utils.retrieval.tools.app_tools', MagicMock())

from routers.agent_tools import router, _vm_response, GCE_ZONE
from utils.other.endpoints import get_current_user_uid

app = FastAPI()
app.include_router(router)

TEST_UID = "testuser1234abcd"

app.dependency_overrides[get_current_user_uid] = lambda: TEST_UID
client = TestClient(app)


SAMPLE_VM = {
    "vmName": "omi-agent-testuser1234",
    "zone": "us-central1-a",
    "ip": "35.192.1.1",
    "status": "ready",
    "authToken": "omi-abc123",
    "createdAt": "2026-03-10T00:00:00+00:00",
    "lastQueryAt": "2026-03-10T01:00:00+00:00",
}


# --------------- vm-status tests ---------------


@patch("routers.agent_tools.get_agent_vm", return_value=None)
def test_vm_status_no_vm(mock_get):
    """vm-status returns has_vm=False when user has no VM."""
    resp = client.get("/v1/agent/vm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_vm"] is False


@patch("routers.agent_tools._check_gce_status", new_callable=AsyncMock, return_value="RUNNING")
@patch("routers.agent_tools.get_agent_vm", return_value=SAMPLE_VM)
def test_vm_status_returns_full_fields(mock_get, mock_gce):
    """vm-status returns all fields desktop needs: vm_name, ip, auth_token, zone, created_at."""
    resp = client.get("/v1/agent/vm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_vm"] is True
    assert data["vm_name"] == "omi-agent-testuser1234"
    assert data["ip"] == "35.192.1.1"
    assert data["auth_token"] == "omi-abc123"
    assert data["zone"] == "us-central1-a"
    assert data["created_at"] == "2026-03-10T00:00:00+00:00"
    assert data["last_query_at"] == "2026-03-10T01:00:00+00:00"
    assert data["status"] == "ready"


@patch("routers.agent_tools._restart_vm_background")
@patch("routers.agent_tools._update_firestore_vm")
@patch("routers.agent_tools._check_gce_status", new_callable=AsyncMock, return_value="TERMINATED")
@patch("routers.agent_tools.get_agent_vm", return_value=SAMPLE_VM)
def test_vm_status_restarts_stopped_vm(mock_get, mock_gce, mock_update, mock_restart):
    """vm-status triggers restart when GCE status is TERMINATED (Rust parity)."""
    resp = client.get("/v1/agent/vm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "provisioning"
    mock_update.assert_called_once_with(TEST_UID, None, "provisioning")


@patch("routers.agent_tools._check_gce_status", new_callable=AsyncMock, side_effect=Exception("GCE unreachable"))
@patch("routers.agent_tools.get_agent_vm", return_value=SAMPLE_VM)
def test_vm_status_gce_failure_returns_firestore_data(mock_get, mock_gce):
    """vm-status returns Firestore data when GCE check fails."""
    resp = client.get("/v1/agent/vm-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_vm"] is True
    assert data["status"] == "ready"
    assert data["vm_name"] == "omi-agent-testuser1234"


# --------------- vm-ensure tests ---------------


@patch("routers.agent_tools._provision_vm_background")
@patch("routers.agent_tools._set_firestore_vm")
@patch("routers.agent_tools.get_agent_vm", return_value=None)
def test_vm_ensure_creates_new_vm(mock_get, mock_set_fs, mock_provision):
    """vm-ensure creates a new VM when no Firestore record exists."""
    resp = client.post("/v1/agent/vm-ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_vm"] is True
    assert data["status"] == "provisioning"
    assert data["vm_name"] == "omi-agent-testuser1234"
    assert data["auth_token"].startswith("omi-")
    assert data["zone"] == "us-central1-a"
    assert data["ip"] is None

    # Verify Firestore was written
    mock_set_fs.assert_called_once()
    call_args = mock_set_fs.call_args
    assert call_args[0][0] == TEST_UID
    assert call_args[0][1] == "omi-agent-testuser1234"
    assert call_args[0][4] == "provisioning"


@patch(
    "routers.agent_tools.get_agent_vm",
    return_value={"vmName": "omi-agent-testuser1234", "status": "provisioning", "authToken": "omi-xyz"},
)
def test_vm_ensure_idempotent_provisioning(mock_get):
    """vm-ensure doesn't double-provision when already provisioning."""
    resp = client.post("/v1/agent/vm-ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_vm"] is True
    assert data["status"] == "provisioning"


@patch("routers.agent_tools._restart_vm_background")
@patch("routers.agent_tools._update_firestore_vm")
@patch("routers.agent_tools._check_gce_status", new_callable=AsyncMock, return_value="STOPPED")
@patch("routers.agent_tools.get_agent_vm", return_value=SAMPLE_VM)
def test_vm_ensure_restarts_stopped_vm(mock_get, mock_gce, mock_update, mock_restart):
    """vm-ensure restarts a stopped VM."""
    resp = client.post("/v1/agent/vm-ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "provisioning"
    mock_update.assert_called_once_with(TEST_UID, None, "provisioning")


@patch("routers.agent_tools._update_firestore_vm")
@patch("routers.agent_tools._check_gce_status", new_callable=AsyncMock, return_value="RUNNING")
@patch(
    "routers.agent_tools.get_agent_vm",
    return_value={**SAMPLE_VM, "status": "error"},
)
def test_vm_ensure_recovers_running_but_error_status(mock_get, mock_gce, mock_update):
    """vm-ensure recovers when GCE is RUNNING but Firestore says error."""
    resp = client.post("/v1/agent/vm-ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    mock_update.assert_called_once_with(TEST_UID, "35.192.1.1", "ready")


@patch("routers.agent_tools._check_gce_status", new_callable=AsyncMock, return_value="RUNNING")
@patch("routers.agent_tools.get_agent_vm", return_value=SAMPLE_VM)
def test_vm_ensure_returns_full_fields_for_ready_vm(mock_get, mock_gce):
    """vm-ensure returns full VM fields when VM is ready."""
    resp = client.post("/v1/agent/vm-ensure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_vm"] is True
    assert data["vm_name"] == "omi-agent-testuser1234"
    assert data["ip"] == "35.192.1.1"
    assert data["auth_token"] == "omi-abc123"


# --------------- _vm_response tests ---------------


def test_vm_response_maps_firestore_fields():
    """_vm_response correctly maps Firestore camelCase to snake_case."""
    result = _vm_response(SAMPLE_VM)
    assert result["vm_name"] == "omi-agent-testuser1234"
    assert result["auth_token"] == "omi-abc123"
    assert result["created_at"] == "2026-03-10T00:00:00+00:00"
    assert result["last_query_at"] == "2026-03-10T01:00:00+00:00"


def test_vm_response_status_override():
    """_vm_response applies status_override correctly."""
    result = _vm_response(SAMPLE_VM, status_override="provisioning")
    assert result["status"] == "provisioning"
    assert result["vm_name"] == "omi-agent-testuser1234"


# --------------- vm_name generation tests ---------------


@patch("routers.agent_tools._provision_vm_background")
@patch("routers.agent_tools._set_firestore_vm")
@patch("routers.agent_tools.get_agent_vm", return_value=None)
def test_vm_name_truncates_long_uid(mock_get, mock_set_fs, mock_provision):
    """VM name uses first 12 chars of UID, lowercased."""
    app.dependency_overrides[get_current_user_uid] = lambda: "ABCDEFghijklmnopqrstuvwxyz"
    try:
        resp = client.post("/v1/agent/vm-ensure")
        data = resp.json()
        assert data["vm_name"] == "omi-agent-abcdefghijkl"
    finally:
        app.dependency_overrides[get_current_user_uid] = lambda: TEST_UID


@patch("routers.agent_tools._provision_vm_background")
@patch("routers.agent_tools._set_firestore_vm")
@patch("routers.agent_tools.get_agent_vm", return_value=None)
def test_vm_name_short_uid(mock_get, mock_set_fs, mock_provision):
    """Short UIDs use the full UID in VM name."""
    app.dependency_overrides[get_current_user_uid] = lambda: "ShortUid"
    try:
        resp = client.post("/v1/agent/vm-ensure")
        data = resp.json()
        assert data["vm_name"] == "omi-agent-shortuid"
    finally:
        app.dependency_overrides[get_current_user_uid] = lambda: TEST_UID
