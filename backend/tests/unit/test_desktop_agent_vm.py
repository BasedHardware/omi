import os
import sys
import time
from pathlib import Path

import httpx
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
    monkeypatch.setattr(desktop_agent_vm, "_service_account", lambda: "service-account")
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


def test_claim_allows_replacement_when_reconciler_marked_missing():
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    database = StrictFirestore(
        {
            ("users", "uid"): {
                "agentVm": {
                    "vmName": "omi-agent-stale",
                    "authToken": "old",
                    "status": "ready",
                    "reconcile": {"state": "missing", "missingSince": 1.0},
                }
            }
        }
    )
    candidate = {"vmName": "omi-agent-new", "status": "provisioning", "authToken": "new"}
    raw = getattr(desktop_agent_vm._claim_vm_if_allowed_txn, "to_wrap", desktop_agent_vm._claim_vm_if_allowed_txn)

    claimed_vm, claimed = raw(
        database.transaction(),
        database.collection("account_deletions").document("uid"),
        database.collection("users").document("uid"),
        candidate,
    )

    assert claimed is True
    assert claimed_vm == candidate
    stored = database.rows[("users", "uid")]["agentVm"]
    assert stored == candidate
    assert "reconcile" not in stored
    assert database.transactions[-1].updates[-1][1] == {"agentVm": candidate}


def test_record_provider_missing_rejects_active_reconcile_lease(monkeypatch):
    from services import agent_vm_read
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    now = 1_700_000_000.0
    database = StrictFirestore(
        {
            ("users", "uid"): {
                "agentVm": {
                    "vmName": "omi-agent-stale",
                    "zone": "us-central1-a",
                    "authToken": "token",
                    "status": "ready",
                    "reconcile": {
                        "state": "claimed",
                        "lease": {"owner": "worker-1", "expiresAt": now + 60},
                    },
                }
            }
        }
    )
    monkeypatch.setattr(agent_vm_read, "get_firestore_client", lambda: database)
    raw = getattr(
        agent_vm_read._record_provider_missing_if_current_txn,
        "to_wrap",
        agent_vm_read._record_provider_missing_if_current_txn,
    )

    marked = raw(
        database.transaction(),
        database.collection("account_deletions").document("uid"),
        database.collection("users").document("uid"),
        "omi-agent-stale",
        "us-central1-a",
        "token",
        now,
    )

    assert marked is False
    assert database.rows[("users", "uid")]["agentVm"]["reconcile"]["state"] == "claimed"
    assert database.transactions[-1].updates == []


def test_record_provider_missing_rejects_quarantined_state():
    from services import agent_vm_read
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

    now = 1_700_000_000.0
    database = StrictFirestore(
        {
            ("users", "uid"): {
                "agentVm": {
                    "vmName": "omi-agent-stale",
                    "zone": "us-central1-a",
                    "authToken": "token",
                    "status": "ready",
                    "reconcile": {"state": "quarantined", "releaseId": "rel-1"},
                }
            }
        }
    )
    raw = getattr(
        agent_vm_read._record_provider_missing_if_current_txn,
        "to_wrap",
        agent_vm_read._record_provider_missing_if_current_txn,
    )

    marked = raw(
        database.transaction(),
        database.collection("account_deletions").document("uid"),
        database.collection("users").document("uid"),
        "omi-agent-stale",
        "us-central1-a",
        "token",
        now,
    )

    assert marked is False
    assert database.rows[("users", "uid")]["agentVm"]["reconcile"]["state"] == "quarantined"
    assert database.transactions[-1].updates == []


@pytest.mark.asyncio
async def test_status_keeps_demotion_when_start_request_loses_same_owner_race(monkeypatch):
    vm = {
        "vmName": "omi-agent-stale",
        "zone": "us-central1-a",
        "ip": "34.1.2.3",
        "authToken": "old-token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }

    async def run_blocking(_, function, *args):
        return function(*args)

    async def not_found(*_args):
        return "NOT_FOUND", None

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", not_found)
    monkeypatch.setattr(desktop_agent_vm, "request_vm_start", lambda *_args: False)
    monkeypatch.setattr(desktop_agent_vm, "record_provider_missing_if_current", lambda *_args: True)

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response.status == "updating"
    assert response.ip is None


@pytest.mark.asyncio
async def test_sparse_new_uid_is_persisted_as_provisioning_and_scheduled(monkeypatch):
    writes = []

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_source_image", lambda _project: "image")
    monkeypatch.setattr(desktop_agent_vm, "_gcs_bucket", lambda: "bucket")
    monkeypatch.setattr(desktop_agent_vm, "_service_account", lambda: "service-account")
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
    monkeypatch.setattr(desktop_agent_vm, "_create_vm", lambda *_args: _async_result(("34.1.2.3", "123456789")))
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm", delete_vm)
    monkeypatch.setattr(
        desktop_agent_vm.users_db,
        "record_late_agent_vm_cleanup",
        lambda *args: persisted.append(args),
    )

    await desktop_agent_vm._provision_background(
        "uid", "project", "image", "bucket", "omi-agent-uid", "omi-token", "service-account"
    )

    assert persisted == [("uid", "omi-agent-uid", "us-central1-a", "123456789")]


@pytest.mark.asyncio
async def test_successful_provision_persists_provider_instance_identity(monkeypatch):
    updates: list[tuple[object, ...]] = []

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_vm_lifecycle_allowed", lambda *_args: True)
    monkeypatch.setattr(
        desktop_agent_vm,
        "_create_vm",
        lambda *_args: _async_result(("34.1.2.3", "123456789")),
    )
    monkeypatch.setattr(desktop_agent_vm, "_set_vm_if_current", lambda *args: updates.append(args) or True)

    await desktop_agent_vm._provision_background(
        "uid", "project", "image", "bucket", "omi-agent-uid", "omi-token", "service-account"
    )

    assert updates[-1][3:] == ("ready", "34.1.2.3", "us-central1-a", "123456789")


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

    await desktop_agent_vm._provision_background(
        "uid", "project", "image", "bucket", "omi-agent-uid", "omi-token", "service-account"
    )

    assert persisted == [("uid", "omi-agent-uid", "us-central1-a", None)]


@pytest.mark.asyncio
async def test_readiness_failure_after_create_uses_identity_fenced_cleanup(monkeypatch):
    deleted: list[tuple[object, ...]] = []
    updates: list[tuple[object, ...]] = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def create_vm(*_args):
        raise desktop_agent_vm.AgentVmReadinessError("health timeout", "123456789")

    async def delete_vm(*args):
        deleted.append(args)
        return True

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_vm_lifecycle_allowed", lambda *_args: True)
    monkeypatch.setattr(desktop_agent_vm, "_create_vm", create_vm)
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm", delete_vm)
    monkeypatch.setattr(desktop_agent_vm, "_set_vm_if_current", lambda *args: updates.append(args) or True)

    await desktop_agent_vm._provision_background(
        "uid", "project", "image", "bucket", "omi-agent-uid", "omi-token", "service-account"
    )

    assert deleted == [
        (
            "project",
            "omi-agent-uid",
            "us-central1-a",
            "123456789",
            desktop_agent_vm._agent_vm_owner_hash("uid"),
        )
    ]
    assert updates[-1][3] == "error"


@pytest.mark.asyncio
async def test_late_cleanup_refuses_a_reused_name_with_a_different_provider_identity(monkeypatch):
    async def foreign_instance(*_args):
        return "RUNNING", {
            "id": "987654321",
            "labels": {"omi-agent-owner": desktop_agent_vm._agent_vm_owner_hash("uid")},
        }

    monkeypatch.setattr(desktop_agent_vm, "_instance", foreign_instance)

    with pytest.raises(desktop_agent_vm.AgentVmIdentityMismatch):
        await desktop_agent_vm._delete_vm(
            "project",
            "omi-agent-uid",
            "us-central1-a",
            "123456789",
            desktop_agent_vm._agent_vm_owner_hash("uid"),
        )


@pytest.mark.asyncio
async def test_create_vm_preserves_provider_identity_when_readiness_fails(monkeypatch):
    async def fake_gce_request(method, url, token, body=None):
        return httpx.Response(200, json={"name": "operation"}, request=httpx.Request(method, url))

    async def readiness_failure(*_args):
        raise RuntimeError("health timeout")

    monkeypatch.setattr(desktop_agent_vm, "_get_access_token", lambda: "gce-token")
    monkeypatch.setattr(desktop_agent_vm, "_gce_request", fake_gce_request)
    monkeypatch.setattr(desktop_agent_vm, "_operation", lambda *_args: _async_result(None))
    monkeypatch.setattr(
        desktop_agent_vm,
        "_instance",
        lambda *_args: _async_result(
            (
                "RUNNING",
                {
                    "id": "123456789",
                    "networkInterfaces": [{"networkIP": "10.128.0.9", "accessConfigs": [{"natIP": "34.1.2.3"}]}],
                },
            )
        ),
    )
    monkeypatch.setattr(desktop_agent_vm, "_wait_for_vm_ready", readiness_failure)
    monkeypatch.setenv("AGENT_VM_STARTUP_URI", "https://storage.googleapis.com/bucket/releases/a/startup.sh")
    monkeypatch.setenv("AGENT_VM_STARTUP_SHA256", "c" * 64)
    monkeypatch.setenv("AGENT_VM_RELEASE_ID", "a" * 40)
    monkeypatch.setenv("AGENT_VM_IMAGE_DIGEST", "gcr.io/project/agent-vm@sha256:" + "b" * 64)
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/omi-agent-20260805")

    with pytest.raises(desktop_agent_vm.AgentVmReadinessError) as error:
        await desktop_agent_vm._create_vm(
            "project",
            "source-image",
            "bucket",
            "omi-agent-uid",
            "omi-token",
            "agent-bootstrap@example.iam.gserviceaccount.com",
            "a" * 20,
        )

    assert error.value.instance_id == "123456789"


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

    await desktop_agent_vm._provision_background(
        "uid", "project", "image", "bucket", "old-generation", "old-token", "service-account"
    )

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
async def test_status_requests_reconciler_start_for_stopped_vm(monkeypatch):
    vm = {
        "vmName": "omi-agent-user",
        "zone": "us-central1-a",
        "ip": "1.2.3.4",
        "authToken": "omi-token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }
    requests = []

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", lambda *args: _stopped_instance())
    monkeypatch.setattr(desktop_agent_vm, "request_vm_start", lambda *args: requests.append(args) or True)
    tasks = BackgroundTasks()

    response = await desktop_agent_vm.get_agent_status(tasks, "user")

    assert response.status == "updating"
    assert response.ip is None
    assert requests == [("user", "omi-agent-user", "omi-token")]
    assert not tasks.tasks


@pytest.mark.asyncio
async def test_status_does_not_restart_a_vm_while_the_reconciler_lease_is_active(monkeypatch):
    vm = {
        "vmName": "omi-agent-user",
        "zone": "us-central1-a",
        "ip": "1.2.3.4",
        "authToken": "omi-token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
        "reconcile": {"lease": {"owner": "reconciler", "expiresAt": time.time() + 60}},
    }

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_instance", lambda *_args: pytest.fail("status must not inspect GCE"))

    tasks = BackgroundTasks()
    response = await desktop_agent_vm.get_agent_status(tasks, "user")

    assert response.status == "updating"
    assert response.ip is None
    assert not tasks.tasks


@pytest.mark.asyncio
async def test_provision_reports_updating_without_overriding_a_reconciler_request(monkeypatch):
    vm = {
        "vmName": "omi-agent-user",
        "authToken": "omi-token",
        "status": "ready",
        "reconcile": {"startRequested": True},
    }

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_claim_vm_if_allowed", lambda *_args: (vm, False))
    monkeypatch.setattr(desktop_agent_vm, "_agent_disabled", lambda: False)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_source_image", lambda _project: "image")
    monkeypatch.setattr(desktop_agent_vm, "_gcs_bucket", lambda: "bucket")
    monkeypatch.setattr(desktop_agent_vm, "_service_account", lambda: "service-account")

    response = await desktop_agent_vm.provision_agent_vm(BackgroundTasks(), "user")

    assert response.status == "exists"
    assert response.agent_status == "updating"
    assert response.ip is None


@pytest.mark.asyncio
async def test_status_defers_missing_gce_pointer_to_the_fenced_reconciler(monkeypatch):
    vm = {
        "vmName": "omi-agent-stale",
        "zone": "us-central1-a",
        "ip": "34.1.2.3",
        "authToken": "old-token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }
    requests = []
    marked = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def not_found(*_args):
        return "NOT_FOUND", None

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", not_found)
    monkeypatch.setattr(desktop_agent_vm, "request_vm_start", lambda *args: requests.append(args) or True)
    monkeypatch.setattr(
        desktop_agent_vm, "record_provider_missing_if_current", lambda *args: marked.append(args) or True
    )

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response.status == "updating"
    assert response.ip is None
    assert requests == [("uid", "omi-agent-stale", "old-token")]
    assert marked == [("uid", "omi-agent-stale", "us-central1-a", "old-token")]


@pytest.mark.asyncio
async def test_status_queues_start_when_missing_marker_raises(monkeypatch):
    vm = {
        "vmName": "omi-agent-stale",
        "zone": "us-central1-a",
        "ip": "34.1.2.3",
        "authToken": "old-token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }
    requests = []
    fallbacks = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def not_found(*_args):
        return "NOT_FOUND", None

    def boom(*_args):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", not_found)
    monkeypatch.setattr(desktop_agent_vm, "request_vm_start", lambda *args: requests.append(args) or True)
    monkeypatch.setattr(desktop_agent_vm, "record_provider_missing_if_current", boom)
    monkeypatch.setattr(desktop_agent_vm, "record_fallback", lambda **fields: fallbacks.append(fields))

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response.status == "updating"
    assert response.ip is None
    assert requests == [("uid", "omi-agent-stale", "old-token")]
    assert fallbacks and fallbacks[0]["from_mode"] == "missing_marker"


@pytest.mark.asyncio
async def test_status_preserves_ready_when_gce_probe_fails(monkeypatch):
    vm = {
        "vmName": "omi-agent-blip",
        "zone": "us-central1-a",
        "ip": "34.1.2.3",
        "authToken": "token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }

    async def run_blocking(_, function, *args):
        return function(*args)

    async def probe_failed(*_args):
        raise RuntimeError("GCE unavailable")

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", probe_failed)
    monkeypatch.setattr(
        desktop_agent_vm, "request_vm_start", lambda *_args: pytest.fail("API blip must preserve ownership")
    )

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response.status == "ready"
    assert response.ip == "34.1.2.3"


@pytest.mark.asyncio
async def test_status_leaves_ready_running_instance_unchanged(monkeypatch):
    vm = {
        "vmName": "omi-agent-live",
        "zone": "us-central1-a",
        "ip": "34.1.2.3",
        "authToken": "token",
        "status": "ready",
        "createdAt": "2026-07-26T00:00:00Z",
    }

    async def run_blocking(_, function, *args):
        return function(*args)

    async def running(*_args):
        return "RUNNING", {"networkInterfaces": [{"accessConfigs": [{"natIP": "34.1.2.3"}]}]}

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", running)
    monkeypatch.setattr(
        desktop_agent_vm, "request_vm_start", lambda *_args: pytest.fail("healthy ready VM must not queue repair")
    )

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response.status == "ready"
    assert response.ip == "34.1.2.3"


@pytest.mark.asyncio
async def test_status_does_not_probe_a_missing_record_while_reconciler_cleanup_is_pending(monkeypatch):
    vm = {
        "vmName": "omi-agent-missing",
        "zone": "us-central1-a",
        "authToken": "current-token",
        "status": "ready",
        "reconcile": {"state": "missing", "missingSince": time.time() - 60},
    }

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_instance", lambda *_args: pytest.fail("reconciler owns missing records"))

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response.status == "updating"
    assert response.ip is None


@pytest.mark.asyncio
async def test_status_defers_running_vm_without_usable_ip_to_reconciler(monkeypatch):
    vm = {
        "vmName": "omi-agent-unreachable",
        "zone": "us-central1-a",
        "ip": None,
        "authToken": "current-token",
        "status": "error",
        "createdAt": "2026-07-26T00:00:00Z",
    }
    requests = []

    async def run_blocking(_, function, *args):
        return function(*args)

    async def running_without_ip(*_args):
        return "RUNNING", {"networkInterfaces": []}

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_get_vm", lambda _uid: vm)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setattr(desktop_agent_vm, "_instance", running_without_ip)
    monkeypatch.setattr(desktop_agent_vm, "request_vm_start", lambda *args: requests.append(args) or True)

    response = await desktop_agent_vm.get_agent_status(BackgroundTasks(), "uid")

    assert response.status == "updating"
    assert response.ip is None
    assert requests == [("uid", "omi-agent-unreachable", "current-token")]


@pytest.mark.asyncio
async def test_agent_vm_rejects_paywalled_desktop_user(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "is_desktop_trial_paywalled", lambda uid, platform: True)

    with pytest.raises(HTTPException) as error:
        await desktop_agent_vm._authorized_desktop_user("user")

    assert error.value.status_code == 402
    assert error.value.detail == "trial_expired"


@pytest.mark.asyncio
async def test_create_vm_attaches_dedicated_service_account_with_cloud_platform_scope(monkeypatch):
    requests = []
    readiness_calls = []
    owner_hash = "a" * 20
    vm_name = f"omi-agent-{owner_hash}-12345678"

    async def fake_gce_request(method, url, token, body=None):
        requests.append((method, url, body))
        return httpx.Response(200, json={"name": "operation"}, request=httpx.Request(method, url))

    async def fake_operation(*args):
        return None

    async def fake_instance(*args):
        return "RUNNING", {
            "id": "123456789",
            "networkInterfaces": [{"networkIP": "10.128.0.9", "accessConfigs": [{"natIP": "203.0.113.10"}]}],
        }

    async def fake_wait_for_vm_ready(*args):
        readiness_calls.append(args)

    monkeypatch.setattr(desktop_agent_vm, "_get_access_token", lambda: "gce-token")
    monkeypatch.setattr(desktop_agent_vm, "_gce_request", fake_gce_request)
    monkeypatch.setattr(desktop_agent_vm, "_operation", fake_operation)
    monkeypatch.setattr(desktop_agent_vm, "_instance", fake_instance)
    monkeypatch.setattr(desktop_agent_vm, "_wait_for_vm_ready", fake_wait_for_vm_ready)
    monkeypatch.setenv("AGENT_VM_STARTUP_URI", "https://storage.googleapis.com/bucket/releases/a/startup.sh")
    monkeypatch.setenv("AGENT_VM_STARTUP_SHA256", "c" * 64)
    monkeypatch.setenv("AGENT_VM_RELEASE_ID", "a" * 40)
    monkeypatch.setenv("AGENT_VM_IMAGE_DIGEST", "gcr.io/project/agent-vm@sha256:" + "b" * 64)
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/omi-agent-20260805")

    ip, instance_id = await desktop_agent_vm._create_vm(
        "project",
        "source-image",
        "bucket",
        vm_name,
        "omi-token",
        "agent-bootstrap@example.iam.gserviceaccount.com",
        owner_hash,
    )

    assert ip == "203.0.113.10"
    assert instance_id == "123456789"
    assert readiness_calls[0][0:3] == ("project", "10.128.0.9", "omi-token")
    assert readiness_calls[0][4] == vm_name
    assert requests[0][0] == "POST"
    assert requests[0][2]["serviceAccounts"] == [
        {
            "email": "agent-bootstrap@example.iam.gserviceaccount.com",
            "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
        }
    ]
    assert requests[0][2]["labels"] == {"omi-agent-owner": owner_hash}
    assert requests[0][2]["disks"] == [
        {
            "boot": True,
            "autoDelete": True,
            "initializeParams": {
                "sourceImage": "source-image",
                "diskSizeGb": "50",
                "diskType": "zones/us-central1-a/diskTypes/pd-balanced",
            },
        },
        {
            "boot": False,
            "deviceName": "omi-agent-state",
            "mode": "READ_WRITE",
            "autoDelete": True,
            "initializeParams": {
                "diskName": f"{vm_name}-state",
                "diskSizeGb": "50",
                "diskType": "zones/us-central1-a/diskTypes/pd-balanced",
                "labels": {
                    "omi-agent-role": "state",
                    "omi-agent-owner": owner_hash,
                },
            },
        },
    ]
    metadata = {item["key"]: item["value"] for item in requests[0][2]["metadata"]["items"]}
    assert metadata["omi-agent-state-required"] == "true"
    assert metadata["omi-agent-state-source-required"] == "false"


def test_stop_broker_rejects_identity_from_the_wrong_project_or_service_account(monkeypatch):
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setenv("GCE_RUNTIME_SERVICE_ACCOUNT", "runtime@project.iam.gserviceaccount.com")

    with pytest.raises(ValueError, match="outside the broker scope"):
        desktop_agent_vm._compute_identity_fields(
            {
                "email": "runtime@project.iam.gserviceaccount.com",
                "email_verified": True,
                "google": {
                    "compute_engine": {
                        "project_id": "other-project",
                        "instance_name": "omi-agent-user",
                        "instance_id": "123456789",
                        "zone": "us-central1-a",
                    }
                },
            }
        )

    with pytest.raises(ValueError, match="runtime identity"):
        desktop_agent_vm._compute_identity_fields(
            {
                "email": "other@project.iam.gserviceaccount.com",
                "email_verified": True,
                "google": {
                    "compute_engine": {
                        "project_id": "project",
                        "instance_name": "omi-agent-user",
                        "instance_id": "123456789",
                        "zone": "us-central1-a",
                    }
                },
            }
        )


def test_stop_broker_reads_the_full_nested_compute_identity(monkeypatch):
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setenv("GCE_RUNTIME_SERVICE_ACCOUNT", "runtime@project.iam.gserviceaccount.com")

    assert desktop_agent_vm._compute_identity_fields(
        {
            "email": "runtime@project.iam.gserviceaccount.com",
            "email_verified": True,
            "google": {
                "compute_engine": {
                    "project_id": "project",
                    "instance_name": "omi-agent-user",
                    "instance_id": 123456789,
                    "zone": "us-central1-a",
                    "instance_creation_timestamp": 1785900000,
                }
            },
        }
    ) == ("project", "us-central1-a", "omi-agent-user", "runtime@project.iam.gserviceaccount.com", "123456789")


def test_stop_broker_owner_lookup_is_a_bounded_indexed_query(monkeypatch):
    calls = []
    snapshot = type(
        "Snapshot",
        (),
        {
            "id": "uid",
            "to_dict": lambda self: {"agentVm": {"vmName": "omi-agent-user", "zone": "us-central1-a"}},
        },
    )()

    class Query:
        def where(self, *, filter):
            calls.append(("where", filter.field_path, filter.op_string, filter.value))
            return self

        def limit(self, count):
            calls.append(("limit", count))
            return self

        def stream(self):
            return iter([snapshot])

    class Firestore:
        def collection(self, name):
            calls.append(("collection", name))
            return Query()

    monkeypatch.setattr(desktop_agent_vm, "get_firestore_client", Firestore)

    uid, vm = desktop_agent_vm._find_vm_owner("omi-agent-user") or (None, None)

    assert uid == "uid"
    assert vm["vmName"] == "omi-agent-user"
    assert calls == [
        ("collection", "users"),
        ("where", "agentVm.vmName", "==", "omi-agent-user"),
        ("limit", 2),
    ]


@pytest.mark.asyncio
async def test_stop_broker_binds_token_zone_and_instance_id_to_owner_and_runtime(monkeypatch):
    class Request:
        headers = {"authorization": "Bearer identity-token"}
        client = None

    claims = {
        "email": "runtime@project.iam.gserviceaccount.com",
        "email_verified": True,
        "google": {
            "compute_engine": {
                "project_id": "project",
                "instance_name": "omi-agent-user",
                "instance_id": "123456789",
                "zone": "us-central1-a",
            }
        },
    }

    async def direct_run_blocking(_executor, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_stop_broker_rate_allowed", lambda _request: True)
    monkeypatch.setattr(desktop_agent_vm, "_verify_agent_vm_identity", lambda _token: claims)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setenv("GCE_RUNTIME_SERVICE_ACCOUNT", "runtime@project.iam.gserviceaccount.com")
    monkeypatch.setattr(
        desktop_agent_vm,
        "_find_vm_owner",
        lambda _name: (
            "uid",
            {"vmName": "omi-agent-user", "zone": "us-central1-b", "authToken": "owner-token"},
        ),
    )

    with pytest.raises(HTTPException, match="zone does not match") as zone_error:
        await desktop_agent_vm.stop_self(Request())
    assert zone_error.value.status_code == 403

    monkeypatch.setattr(
        desktop_agent_vm,
        "_find_vm_owner",
        lambda _name: (
            "uid",
            {"vmName": "omi-agent-user", "zone": "us-central1-a", "authToken": "owner-token"},
        ),
    )
    monkeypatch.setattr(desktop_agent_vm, "_vm_lifecycle_allowed", lambda *_args: True)
    monkeypatch.setattr(desktop_agent_vm, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(desktop_agent_vm, "update_vm_reconcile", lambda *_args: True)

    async def wrong_instance(*_args):
        return "RUNNING", {"id": "987654321", "name": "omi-agent-user"}

    monkeypatch.setattr(desktop_agent_vm, "_instance", wrong_instance)
    with pytest.raises(HTTPException, match="runtime identity does not match") as instance_error:
        await desktop_agent_vm.stop_self(Request())
    assert instance_error.value.status_code == 403


@pytest.mark.asyncio
async def test_stop_broker_never_stops_a_vm_while_reconciliation_is_requested(monkeypatch):
    class Request:
        headers = {"authorization": "Bearer identity-token"}
        client = None

    claims = {
        "email": "runtime@project.iam.gserviceaccount.com",
        "email_verified": True,
        "google": {
            "compute_engine": {
                "project_id": "project",
                "instance_name": "omi-agent-user",
                "instance_id": "123456789",
                "zone": "us-central1-a",
            }
        },
    }

    async def direct_run_blocking(_executor, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", direct_run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_stop_broker_rate_allowed", lambda _request: True)
    monkeypatch.setattr(desktop_agent_vm, "_verify_agent_vm_identity", lambda _token: claims)
    monkeypatch.setattr(desktop_agent_vm, "_project", lambda: "project")
    monkeypatch.setenv("GCE_RUNTIME_SERVICE_ACCOUNT", "runtime@project.iam.gserviceaccount.com")
    monkeypatch.setattr(
        desktop_agent_vm,
        "_find_vm_owner",
        lambda _name: (
            "uid",
            {
                "vmName": "omi-agent-user",
                "zone": "us-central1-a",
                "authToken": "owner-token",
                "reconcile": {"startRequested": True},
            },
        ),
    )
    monkeypatch.setattr(desktop_agent_vm, "_vm_lifecycle_allowed", lambda *_args: True)
    monkeypatch.setattr(
        desktop_agent_vm, "_instance", lambda *_args: pytest.fail("stop must defer before provider access")
    )

    assert await desktop_agent_vm.stop_self(Request()) == {"status": "updating", "vmName": "omi-agent-user"}


def test_stop_broker_rate_limit_is_bounded(monkeypatch):
    class Client:
        host = "198.51.100.10"

    class Request:
        client = Client()

    desktop_agent_vm._stop_broker_attempts.clear()
    monkeypatch.setattr(desktop_agent_vm, "_STOP_BROKER_RATE_LIMIT", 2)
    assert desktop_agent_vm._stop_broker_rate_allowed(Request())
    assert desktop_agent_vm._stop_broker_rate_allowed(Request())
    assert not desktop_agent_vm._stop_broker_rate_allowed(Request())


def test_new_vm_startup_metadata_contains_release_checksum_and_boot_image(monkeypatch):
    monkeypatch.setenv("AGENT_VM_STARTUP_URI", "https://storage.googleapis.com/bucket/releases/a/startup.sh")
    monkeypatch.setenv("AGENT_VM_STARTUP_SHA256", "c" * 64)
    monkeypatch.setenv("AGENT_VM_RELEASE_ID", "a" * 40)
    monkeypatch.setenv("AGENT_VM_IMAGE_DIGEST", "gcr.io/project/agent-vm@sha256:" + "b" * 64)
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/omi-agent-20260805")

    metadata = desktop_agent_vm._agent_vm_startup_metadata("bucket")

    assert "sha256sum /tmp/omi-startup.sh" in metadata["startup-script"]
    assert metadata["omi-agent-startup-sha256"] == "c" * 64
    assert metadata["omi-agent-boot-image"].endswith("/omi-agent-20260805")
    assert metadata["omi-agent-state-required"] == "true"
    assert metadata["omi-agent-state-source-required"] == "false"


def test_new_vm_requires_an_immutable_boot_image_and_complete_release_contract(monkeypatch):
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/family/omi-agent")
    with pytest.raises(RuntimeError, match="exact immutable image"):
        desktop_agent_vm._source_image("project")

    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/omi-agent-20260805")
    monkeypatch.delenv("AGENT_VM_STARTUP_SHA256", raising=False)
    with pytest.raises(RuntimeError, match="complete immutable release contract"):
        desktop_agent_vm._agent_vm_startup_metadata("bucket")


@pytest.mark.asyncio
async def test_health_readiness_uses_the_trusted_private_vpc_channel(monkeypatch):
    monkeypatch.setenv("GCE_PROJECT_ID", "project")
    monkeypatch.setenv("AGENT_VM_TRUSTED_HEALTH_CHANNEL", "private-vpc")
    monkeypatch.setenv("AGENT_VM_STARTUP_URI", "https://storage.googleapis.com/bucket/releases/a/startup.sh")
    monkeypatch.setenv("AGENT_VM_STARTUP_SHA256", "c" * 64)
    monkeypatch.setenv("AGENT_VM_RELEASE_ID", "a" * 40)
    monkeypatch.setenv("AGENT_VM_IMAGE_DIGEST", "gcr.io/project/agent-vm@sha256:" + "b" * 64)
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/omi-agent-20260805")
    release = desktop_agent_vm._agent_vm_release("service-account")
    calls = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, headers):
            calls.append((url, headers))
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "release": release.release_id,
                    "imageDigest": release.image_digest,
                    "startupSha256": release.startup_sha256,
                    "stateReady": True,
                    "stateMigrationId": "omi-agent-new",
                    "stateDatabaseExpected": True,
                    "databaseReady": True,
                },
            )

    monkeypatch.setattr(desktop_agent_vm.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    await desktop_agent_vm._wait_for_vm_ready("project", "10.128.0.9", "omi-token", release, "omi-agent-new")

    assert calls == [("http://10.128.0.9:8080/health", {"Authorization": "Bearer omi-token"})]


@pytest.mark.asyncio
async def test_health_readiness_refuses_public_ip_without_an_explicit_private_channel(monkeypatch):
    monkeypatch.setenv("GCE_PROJECT_ID", "project")
    monkeypatch.delenv("AGENT_VM_TRUSTED_HEALTH_CHANNEL", raising=False)
    monkeypatch.setenv("AGENT_VM_STARTUP_URI", "https://storage.googleapis.com/bucket/releases/a/startup.sh")
    monkeypatch.setenv("AGENT_VM_STARTUP_SHA256", "c" * 64)
    monkeypatch.setenv("AGENT_VM_RELEASE_ID", "a" * 40)
    monkeypatch.setenv("AGENT_VM_IMAGE_DIGEST", "gcr.io/project/agent-vm@sha256:" + "b" * 64)
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/omi-agent-20260805")
    release = desktop_agent_vm._agent_vm_release("service-account")

    class UnexpectedClient:
        def __init__(self, **_kwargs):
            pytest.fail("readiness must fail before opening an untrusted health channel")

    monkeypatch.setattr(desktop_agent_vm.httpx, "AsyncClient", UnexpectedClient)

    with pytest.raises(RuntimeError, match="private VPC"):
        await desktop_agent_vm._wait_for_vm_ready("project", "203.0.113.10", "omi-token", release, "omi-agent-new")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field, value",
    [("release", "wrong"), ("stateReady", False), ("stateMigrationId", "other"), ("databaseReady", False)],
)
async def test_health_readiness_rejects_incomplete_runtime_identity_or_state(monkeypatch, field, value):
    import services.agent_vm_lifecycle as lifecycle

    monkeypatch.setenv("GCE_PROJECT_ID", "project")
    monkeypatch.setenv("AGENT_VM_TRUSTED_HEALTH_CHANNEL", "private-vpc")
    monkeypatch.setenv("AGENT_VM_STARTUP_URI", "https://storage.googleapis.com/bucket/releases/a/startup.sh")
    monkeypatch.setenv("AGENT_VM_STARTUP_SHA256", "c" * 64)
    monkeypatch.setenv("AGENT_VM_RELEASE_ID", "a" * 40)
    monkeypatch.setenv("AGENT_VM_IMAGE_DIGEST", "gcr.io/project/agent-vm@sha256:" + "b" * 64)
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/omi-agent-20260805")
    release = desktop_agent_vm._agent_vm_release("service-account")
    payload = {
        "status": "ok",
        "release": release.release_id,
        "imageDigest": release.image_digest,
        "startupSha256": release.startup_sha256,
        "stateReady": True,
        "stateMigrationId": "omi-agent-new",
        "stateDatabaseExpected": True,
        "databaseReady": True,
    }
    payload[field] = value
    clock = iter([0.0, 0.0, 2.0])

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, *, headers):
            assert headers == {"Authorization": "Bearer omi-token"}
            return httpx.Response(200, json=payload)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(lifecycle.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(lifecycle, "time", type("FakeTime", (), {"monotonic": lambda _self: next(clock)})())
    monkeypatch.setattr(lifecycle.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(desktop_agent_vm, "_READY_TIMEOUT_SECONDS", 1)

    with pytest.raises(RuntimeError, match="activated release"):
        await desktop_agent_vm._wait_for_vm_ready("project", "10.128.0.9", "omi-token", release, "omi-agent-new")


async def _stopped_instance():
    return "TERMINATED", None


async def _async_result(value):
    return value
