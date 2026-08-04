import os
import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from routers import desktop_agent_vm


def test_vm_publish_transaction_refuses_deletion_admitted_before_commit():
    deletion = type('Snapshot', (), {'exists': True, 'to_dict': lambda self: {'wipe_status': 'running'}})()

    class Ref:
        def __init__(self, snapshot):
            self.snapshot = snapshot
            self.reads = 0

        def get(self, transaction=None):
            self.reads += 1
            return self.snapshot

    deletion_ref = Ref(deletion)
    user_ref = Ref(type('Snapshot', (), {'exists': True, 'to_dict': lambda self: {'agentVm': {}}})())
    transaction = type('Transaction', (), {'set': lambda *args, **kwargs: None})()
    raw = getattr(desktop_agent_vm._set_vm_if_current_txn, 'to_wrap', desktop_agent_vm._set_vm_if_current_txn)

    assert raw(transaction, deletion_ref, user_ref, 'vm', 'token', 'ready', '34.1.2.3', 'zone') is False
    assert deletion_ref.reads == 1
    assert user_ref.reads == 0


@pytest.mark.asyncio
async def test_provision_returns_existing_vm_without_scheduling(monkeypatch):
    vm = {"vmName": "omi-agent-user", "ip": "1.2.3.4", "authToken": "omi-token", "status": "ready"}

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_source_image", lambda _project: "image")
    monkeypatch.setattr(desktop_agent_vm, "_gcs_bucket", lambda: "bucket")
    monkeypatch.setattr(desktop_agent_vm, "_claim_vm_if_allowed", lambda _uid, _candidate: (vm, False))
    tasks = BackgroundTasks()

    response = await desktop_agent_vm.provision_agent_vm(tasks, "user")

    assert response.model_dump(by_alias=True) == {
        "status": "exists",
        "vmName": "omi-agent-user",
        "ip": "1.2.3.4",
        "authToken": "omi-token",
        "agentStatus": "ready",
    }
    assert not tasks.tasks


@pytest.mark.asyncio
async def test_sparse_new_uid_is_persisted_as_provisioning_and_scheduled(monkeypatch):
    writes = []

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_source_image", lambda _project: "image")
    monkeypatch.setattr(desktop_agent_vm, "_gcs_bucket", lambda: "bucket")
    monkeypatch.setattr(
        desktop_agent_vm,
        "_claim_vm_if_allowed",
        lambda uid, candidate: writes.append((uid, candidate)) or (candidate, True),
    )
    tasks = BackgroundTasks()

    response = await desktop_agent_vm.provision_agent_vm(tasks, "fresh-firebase-uid")

    assert response.status == "provisioning"
    assert response.agent_status == "provisioning"
    assert response.ip is None
    assert writes[0][0] == "fresh-firebase-uid"
    assert writes[0][1]["status"] == "provisioning"
    assert writes[0][1]["vmName"].startswith("omi-agent-")
    assert writes[0][1]["vmName"].endswith(writes[0][1]["authToken"].removeprefix("omi-")[:8])
    assert len(tasks.tasks) == 1


@pytest.mark.asyncio
async def test_late_created_vm_cleanup_is_persisted_when_provider_delete_fails(monkeypatch):
    lifecycle_checks = iter([True, False])
    persisted = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def delete_vm(*_args):
        raise RuntimeError("GCE unavailable")

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_vm_lifecycle_allowed", lambda *_args: next(lifecycle_checks))
    monkeypatch.setattr(desktop_agent_vm, "_create_vm", lambda *_args: _async_result("34.1.2.3"))
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm", delete_vm)
    monkeypatch.setattr(
        desktop_agent_vm.users_db,
        "record_late_agent_vm_cleanup",
        lambda *args: persisted.append(args),
    )

    await desktop_agent_vm._provision_background("uid", "project", "image", "bucket", "omi-agent-uid", "omi-token")

    assert persisted == [("uid", "omi-agent-uid", "us-central1-a")]


@pytest.mark.asyncio
async def test_create_error_after_deletion_admission_still_records_possible_late_vm(monkeypatch):
    lifecycle_checks = iter([True, False])
    persisted = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def create_vm(*_args):
        raise desktop_agent_vm.AgentVmCreateOutcomeUnknown("create request outcome unknown")

    async def delete_vm(*_args):
        raise RuntimeError("GCE unavailable")

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_vm_lifecycle_allowed", lambda *_args: next(lifecycle_checks))
    monkeypatch.setattr(desktop_agent_vm, "_create_vm", create_vm)
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm", delete_vm)
    monkeypatch.setattr(
        desktop_agent_vm.users_db,
        "record_late_agent_vm_cleanup",
        lambda *args: persisted.append(args),
    )

    await desktop_agent_vm._provision_background("uid", "project", "image", "bucket", "omi-agent-uid", "omi-token")

    assert persisted == [("uid", "omi-agent-uid", "us-central1-a")]


@pytest.mark.asyncio
async def test_pre_dispatch_create_error_never_deletes_a_superseding_vm(monkeypatch):
    lifecycle_checks = iter([True, False])
    deleted = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def create_vm(*_args):
        raise RuntimeError("credential refresh failed before POST")

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_vm_lifecycle_allowed", lambda *_args: next(lifecycle_checks))
    monkeypatch.setattr(desktop_agent_vm, "_create_vm", create_vm)
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm", lambda *args: deleted.append(args))

    await desktop_agent_vm._provision_background("uid", "project", "image", "bucket", "old-generation", "old-token")

    assert deleted == []


def test_ready_state_rejects_unknown_or_invalid_address():
    with pytest.raises(ValueError, match="usable IP"):
        desktop_agent_vm._validate_ready_vm_ip("ready", "unknown")
    with pytest.raises(ValueError, match="usable IP"):
        desktop_agent_vm._validate_ready_vm_ip("ready", "not-an-ip")


def test_instance_address_parser_never_returns_unknown_placeholder():
    assert desktop_agent_vm._ip({}) is None
    assert desktop_agent_vm._ip({"networkInterfaces": [{"accessConfigs": [{"natIP": "unknown"}]}]}) is None
    assert desktop_agent_vm._ip({"networkInterfaces": [{"accessConfigs": [{"natIP": "34.1.2.3"}]}]}) == "34.1.2.3"


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

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", lambda *args: _stopped_instance())
    monkeypatch.setattr(desktop_agent_vm, "_set_vm_if_current", lambda *args: writes.append(args) or True)
    tasks = BackgroundTasks()

    response = await desktop_agent_vm.get_agent_status(tasks, "user")

    assert response.status == "provisioning"
    assert response.ip is None
    assert writes[0][3] == "provisioning"
    assert len(tasks.tasks) == 1


@pytest.mark.asyncio
async def test_status_clears_stale_gce_pointer_with_current_vm_fence(monkeypatch):
    vm = {
        "vmName": "omi-agent-stale",
        "zone": "us-central1-a",
        "ip": "34.1.2.3",
        "authToken": "old-token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }
    clears = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def not_found(*_args):
        return "NOT_FOUND", None

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", not_found)
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm_if_current", lambda *args: clears.append(args) or True)

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response is None
    assert clears == [("uid", "omi-agent-stale", "old-token")]


@pytest.mark.asyncio
async def test_status_deletes_running_vm_without_usable_ip_and_cas_clears_pointer(monkeypatch):
    vm = {
        "vmName": "omi-agent-unreachable",
        "zone": "us-central1-a",
        "ip": None,
        "authToken": "current-token",
        "status": "error",
        "createdAt": "2026-07-26T00:00:00Z",
    }
    gce_deletes = []
    pointer_clears = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def running_without_ip(*_args):
        return "RUNNING", {"networkInterfaces": []}

    async def delete_vm(*args):
        gce_deletes.append(args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", running_without_ip)
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm", delete_vm)
    monkeypatch.setattr(
        desktop_agent_vm,
        "_delete_vm_if_current",
        lambda *args: pointer_clears.append(args) or True,
    )

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response is None
    assert gce_deletes == [("project", "omi-agent-unreachable", "us-central1-a")]
    assert pointer_clears == [("uid", "omi-agent-unreachable", "current-token")]


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


async def _stopped_instance():
    return "TERMINATED", None


async def _async_result(value):
    return value
