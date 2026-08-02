import os
import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("ENCRYPTION_SECRET", "test-encryption-secret-for-ci-only-32chars!")

from routers import desktop_agent_vm


@pytest.mark.asyncio
async def test_provision_returns_existing_vm_without_scheduling(monkeypatch):
    vm = {"vmName": "omi-agent-user", "ip": "1.2.3.4", "authToken": "omi-token", "status": "ready"}

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setenv("AGENT_VM_ENABLED", "true")
    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda uid: vm)
    tasks = BackgroundTasks()

    response = await desktop_agent_vm.provision_agent_vm(tasks, "user")

    assert response.model_dump(by_alias=True) == {
        "status": "exists",
        "vmName": "omi-agent-user",
        "ip": None,
        "authToken": "",
        "agentStatus": "ready",
    }
    assert not tasks.tasks


@pytest.mark.asyncio
async def test_status_restarts_stopped_vm_and_returns_provisioning(monkeypatch):
    vm = {
        "vmName": "omi-agent-user",
        "zone": "us-central1-a",
        "ip": "1.2.3.4",
        "authToken": "omi-token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }
    writes = []

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setenv("AGENT_VM_ENABLED", "true")
    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", lambda *args: _stopped_instance())
    monkeypatch.setattr(desktop_agent_vm, "_set_vm", lambda *args: writes.append(args))
    tasks = BackgroundTasks()

    response = await desktop_agent_vm.get_agent_status(tasks, "user")

    assert response.status == "provisioning"
    assert response.ip is None
    assert response.auth_token == ""
    assert writes[0][2] == "provisioning"
    assert len(tasks.tasks) == 1


@pytest.mark.asyncio
async def test_agent_vm_rejects_paywalled_desktop_user(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "is_trial_paywalled", lambda uid, platform: True)

    with pytest.raises(HTTPException) as error:
        await desktop_agent_vm._authorized_desktop_user("user")

    assert error.value.status_code == 402
    assert error.value.detail == "trial_expired"


def test_agent_vm_backend_url_requires_https(monkeypatch):
    monkeypatch.setenv("AGENT_VM_BACKEND_URL", "http://api.example.test")

    with pytest.raises(RuntimeError, match="not an allowed backend"):
        desktop_agent_vm._backend_url()


def test_agent_vm_backend_url_rejects_untrusted_https_origin(monkeypatch):
    monkeypatch.setenv("AGENT_VM_BACKEND_URL", "https://attacker.example")

    with pytest.raises(RuntimeError, match="not an allowed backend"):
        desktop_agent_vm._backend_url()


def test_agent_vm_ip_accepts_private_ipv4_only():
    assert desktop_agent_vm._is_usable_vm_ip("10.0.0.5")
    assert not desktop_agent_vm._is_usable_vm_ip("34.121.9.4")
    assert not desktop_agent_vm._is_usable_vm_ip("127.0.0.1")
    assert not desktop_agent_vm._is_usable_vm_ip("unknown")


def test_agent_vm_writer_rejects_unusable_ip():
    with pytest.raises(ValueError, match="unusable"):
        desktop_agent_vm._set_vm("user", "omi-agent-user", "provisioning", "token", "now", "unknown")


@pytest.mark.asyncio
async def test_provision_is_disabled_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AGENT_VM_ENABLED", raising=False)

    with pytest.raises(HTTPException) as error:
        await desktop_agent_vm.provision_agent_vm(BackgroundTasks(), "user")

    assert error.value.status_code == 503
    assert await desktop_agent_vm.get_agent_status(BackgroundTasks(), "user") is None


@pytest.mark.asyncio
async def test_provision_names_vms_by_full_width_uid_hash(monkeypatch):
    monkeypatch.setenv("AGENT_VM_ENABLED", "true")
    names = []

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda uid: None)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_source_image", lambda project: "image")
    monkeypatch.setattr(desktop_agent_vm, "_gcs_bucket", lambda: "bucket")
    monkeypatch.setattr(desktop_agent_vm, "_set_vm", lambda *args: names.append(args[1]))

    # Two uids sharing a 12-character lowercase prefix must not collide.
    first = await desktop_agent_vm.provision_agent_vm(BackgroundTasks(), "AbCdEfGhIjKl" + "1" * 16)
    second = await desktop_agent_vm.provision_agent_vm(BackgroundTasks(), "abcdefghijkl" + "2" * 16)

    assert first.vm_name != second.vm_name
    assert len(first.vm_name) == len("omi-agent-") + 32 <= 63
    assert names == [first.vm_name, second.vm_name]


@pytest.mark.asyncio
async def test_create_vm_uses_private_network_without_public_interface(monkeypatch):
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"name": "operation"}

    async def run_blocking(_, function, *args):
        return function(*args)

    async def gce_request(method, url, token, body=None):
        captured.update({"method": method, "url": url, "body": body})
        return Response()

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_access_token", lambda: "gce-token")
    monkeypatch.setattr(desktop_agent_vm, "_gce_request", gce_request)

    async def operation(*args):
        return None

    monkeypatch.setattr(desktop_agent_vm, "_operation", operation)

    async def instance(*args):
        return "RUNNING", {"networkInterfaces": [{"networkIP": "10.0.0.5"}]}

    monkeypatch.setattr(desktop_agent_vm, "_instance", instance)

    ip = await desktop_agent_vm._create_vm("project", "image", "bucket", "omi-agent-user", "token")

    network_interface = captured["body"]["networkInterfaces"][0]
    assert ip == "10.0.0.5"
    assert network_interface == {"network": "global/networks/default"}
    assert "accessConfigs" not in network_interface
    assert {item["key"] for item in captured["body"]["metadata"]["items"]} >= {
        "backend-url",
        "auth-token",
    }


async def _stopped_instance():
    return "TERMINATED", None
