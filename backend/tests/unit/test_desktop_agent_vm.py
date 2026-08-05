import os
import sys
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
    monkeypatch.setattr(desktop_agent_vm, "_create_vm", lambda *_args: _async_result("34.1.2.3"))
    monkeypatch.setattr(desktop_agent_vm, "_delete_vm", delete_vm)
    monkeypatch.setattr(
        desktop_agent_vm.users_db,
        "record_late_agent_vm_cleanup",
        lambda *args: persisted.append(args),
    )

    await desktop_agent_vm._provision_background(
        "uid", "project", "image", "bucket", "omi-agent-uid", "omi-token", "service-account"
    )

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

    await desktop_agent_vm._provision_background(
        "uid", "project", "image", "bucket", "omi-agent-uid", "omi-token", "service-account"
    )

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
    monkeypatch.setattr(desktop_agent_vm, "_service_account", lambda: "service-account")
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


@pytest.mark.asyncio
async def test_create_vm_attaches_dedicated_service_account_with_cloud_platform_scope(monkeypatch):
    requests = []

    async def fake_gce_request(method, url, token, body=None):
        requests.append((method, url, body))
        return httpx.Response(200, json={"name": "operation"}, request=httpx.Request(method, url))

    async def fake_operation(*args):
        return None

    async def fake_instance(*args):
        return "RUNNING", {"networkInterfaces": [{"accessConfigs": [{"natIP": "203.0.113.10"}]}]}

    monkeypatch.setattr(desktop_agent_vm, "_get_access_token", lambda: "gce-token")
    monkeypatch.setattr(desktop_agent_vm, "_gce_request", fake_gce_request)
    monkeypatch.setattr(desktop_agent_vm, "_operation", fake_operation)
    monkeypatch.setattr(desktop_agent_vm, "_instance", fake_instance)
    monkeypatch.setattr(desktop_agent_vm, "_wait_for_vm_ready", lambda *_args: _async_result(None))

    ip = await desktop_agent_vm._create_vm(
        "project",
        "source-image",
        "bucket",
        "omi-agent-user",
        "omi-token",
        "agent-bootstrap@example.iam.gserviceaccount.com",
    )

    assert ip == "203.0.113.10"
    assert requests[0][0] == "POST"
    assert requests[0][2]["serviceAccounts"] == [
        {
            "email": "agent-bootstrap@example.iam.gserviceaccount.com",
            "scopes": ["https://www.googleapis.com/auth/cloud-platform"],
        }
    ]


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

    async def wrong_instance(*_args):
        return "RUNNING", {"id": "987654321", "name": "omi-agent-user"}

    monkeypatch.setattr(desktop_agent_vm, "_instance", wrong_instance)
    with pytest.raises(HTTPException, match="runtime identity does not match") as instance_error:
        await desktop_agent_vm.stop_self(Request())
    assert instance_error.value.status_code == 403


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
    monkeypatch.setenv("AGENT_VM_BOOT_IMAGE", "projects/project/global/images/family/omi-agent")

    metadata = desktop_agent_vm._agent_vm_startup_metadata("bucket")

    assert "sha256sum /tmp/omi-startup.sh" in metadata["startup-script"]
    assert metadata["omi-agent-startup-sha256"] == "c" * 64
    assert metadata["omi-agent-boot-image"].endswith("/family/omi-agent")


@pytest.mark.asyncio
async def test_restart_sets_bootstrap_identity_and_waits_for_health(monkeypatch):
    calls = []

    async def set_service_account(*args):
        calls.append(("service-account", args))

    async def start_vm(*args):
        calls.append(("start", args))
        return "203.0.113.10"

    async def wait_for_ready(*args):
        calls.append(("health", args))

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_set_service_account", set_service_account)
    monkeypatch.setattr(desktop_agent_vm, "_start_vm", start_vm)
    monkeypatch.setattr(desktop_agent_vm, "_wait_for_vm_ready", wait_for_ready)
    monkeypatch.setattr(desktop_agent_vm, "_set_vm_if_current", lambda *args: calls.append(("ready", args)))

    await desktop_agent_vm._restart_background(
        "uid",
        "project",
        {"vmName": "omi-agent-user", "zone": "zone", "authToken": "omi-token"},
        "agent-bootstrap@example.iam.gserviceaccount.com",
    )

    assert [name for name, _ in calls] == ["service-account", "start", "health", "ready"]


@pytest.mark.asyncio
async def test_rebootstrap_stops_legacy_running_vm_before_identity_migration(monkeypatch):
    calls = []

    async def stop_vm(*args):
        calls.append(("stop", args))

    async def set_service_account(*args):
        calls.append(("service-account", args))

    async def start_vm(*args):
        calls.append(("start", args))
        return "203.0.113.10"

    async def wait_for_ready(*args):
        calls.append(("health", args))

    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_agent_vm, "run_blocking", run_blocking)
    monkeypatch.setattr(desktop_agent_vm, "_stop_vm", stop_vm)
    monkeypatch.setattr(desktop_agent_vm, "_set_service_account", set_service_account)
    monkeypatch.setattr(desktop_agent_vm, "_start_vm", start_vm)
    monkeypatch.setattr(desktop_agent_vm, "_wait_for_vm_ready", wait_for_ready)
    monkeypatch.setattr(desktop_agent_vm, "_set_vm_if_current", lambda *args: calls.append(("ready", args)))

    await desktop_agent_vm._rebootstrap_background(
        "uid",
        "project",
        {"vmName": "omi-agent-user", "zone": "zone", "authToken": "omi-token"},
        "agent-bootstrap@example.iam.gserviceaccount.com",
    )

    assert [name for name, _ in calls] == ["stop", "service-account", "start", "health", "ready"]


@pytest.mark.asyncio
async def test_health_readiness_requires_unauthenticated_rejection(monkeypatch):
    calls = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, headers=None):
            calls.append(headers)
            if headers is None:
                return httpx.Response(401)
            return httpx.Response(200, json={"status": "ok"})

    monkeypatch.setattr(desktop_agent_vm.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    await desktop_agent_vm._wait_for_vm_ready("203.0.113.10", "omi-token")

    assert calls == [None, {"Authorization": "Bearer omi-token"}]


async def _stopped_instance():
    return "TERMINATED", None


async def _async_result(value):
    return value
