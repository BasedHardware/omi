from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from typing import Any, Mapping

import pytest

import jobs.agent_vm_reconciler as reconciler
import services.agent_vm_lifecycle as lifecycle
import services.agent_vm_migration_control as migration_control
from services.agent_vm_lifecycle import AgentVmRelease
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

RELEASE = AgentVmRelease.from_mapping(
    {
        "schemaVersion": 1,
        "environment": "development",
        "sourceSha": "a" * 40,
        "imageDigest": "gcr.io/project/agent-vm@sha256:" + "b" * 64,
        "startupUri": "gs://bucket/agent-vm/releases/a/startup.sh",
        "startupSha256": "c" * 64,
        "bootImage": "projects/project/global/images/omi-agent-20260805",
        "serviceAccount": "omi-agent-vm-bootstrap@project.iam.gserviceaccount.com",
    }
)


class FakeApi:
    instances: dict[str, dict[str, Any]] = {
        "omi-agent-user": {
            "status": "STOPPED",
            "metadata": {},
            "serviceAccounts": [],
            "disks": [{"boot": True, "source": "projects/project/zones/us-central1-a/disks/omi-agent-user"}],
        }
    }
    starts = 0

    def __init__(self, _project: str, _zone: str) -> None:
        pass

    async def get_instance(self, vm_name: str) -> dict[str, Any] | None:
        return self.instances.get(vm_name)

    async def request(self, _method: str, _url: str) -> Any:
        class Response:
            @staticmethod
            def raise_for_status() -> None:
                return None

            @staticmethod
            def json() -> dict[str, str]:
                return {"sourceImage": "projects/project/global/images/omi-agent-20260805"}

        return Response()

    def instance_ip(self, _instance: dict[str, Any]) -> str | None:
        return None

    def private_instance_ip(self, _instance: dict[str, Any]) -> str | None:
        return None

    async def start(self, _vm_name: str) -> None:
        self.starts += 1


def test_reconcile_preserves_a_healthy_stopped_vm(monkeypatch):
    updates: list[dict[str, Any]] = []
    FakeApi.starts = 0
    monkeypatch.setattr(reconciler, "GceAgentVmClient", FakeApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "drift_reasons", lambda *_args: [])
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *_args, **kwargs: updates.append(kwargs) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {"vmName": "omi-agent-user", "authToken": "token"},
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "ready"
    assert "idle self-stop preserved" in result.detail
    assert FakeApi.starts == 0
    assert updates[-1]["vm_fields"] == {"status": "stopped"}


def test_reconcile_starts_a_current_vm_only_after_fenced_start_request(monkeypatch):
    class StartRequestedApi:
        starts = 0
        waits: list[tuple[str, str, AgentVmRelease]] = []

        def __init__(self, _project: str, _zone: str) -> None:
            self.instance = {
                "status": "STOPPED",
                "metadata": {},
                "serviceAccounts": [],
                "disks": [{"boot": True, "source": "projects/project/zones/us-central1-a/disks/omi-agent-user"}],
                "networkInterfaces": [{"networkIP": "10.128.0.9", "accessConfigs": [{"natIP": "34.1.2.3"}]}],
            }

        async def get_instance(self, _vm_name: str) -> dict[str, Any] | None:
            return self.instance

        async def request(self, _method: str, _url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {"sourceImage": "projects/project/global/images/omi-agent-20260805"}

            return Response()

        async def start(self, _vm_name: str) -> None:
            type(self).starts += 1
            self.instance["status"] = "RUNNING"

        def private_instance_ip(self, _instance: dict[str, Any]) -> str:
            return "10.128.0.9"

        def instance_ip(self, _instance: dict[str, Any]) -> str:
            return "34.1.2.3"

        async def wait_for_runtime(
            self, private_ip: str, auth_token: str, release: AgentVmRelease, **_kwargs: Any
        ) -> None:
            type(self).waits.append((private_ip, auth_token, release))

    updates: list[dict[str, Any]] = []
    StartRequestedApi.starts = 0
    StartRequestedApi.waits = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", StartRequestedApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "renew_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "drift_reasons", lambda *_args: [])
    monkeypatch.setattr(
        reconciler, "update_vm_reconcile", lambda *args, **kwargs: updates.append((args, kwargs)) or True
    )

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {"vmName": "omi-agent-user", "authToken": "token", "reconcile": {"startRequested": True}},
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "ready"
    assert StartRequestedApi.starts == 1
    assert StartRequestedApi.waits == [("10.128.0.9", "token", RELEASE)]
    assert updates[-1][0][4]["state"] == "ready"
    assert updates[-1][1]["vm_fields"] == {"status": "ready", "privateIp": "10.128.0.9", "ip": "34.1.2.3"}


def test_boot_image_drift_requires_operator_recreate_without_mutating_vm(monkeypatch):
    class DriftApi(FakeApi):
        mutated = False

        async def request(self, _method: str, _url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {"sourceImage": "projects/project/global/images/omi-agent-old"}

            return Response()

        async def start(self, _vm_name: str) -> None:
            type(self).mutated = True

        async def stop(self, _vm_name: str) -> None:
            type(self).mutated = True

        async def set_metadata(self, *_args: Any) -> None:
            type(self).mutated = True

        async def set_service_account(self, *_args: Any) -> None:
            type(self).mutated = True

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", DriftApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {"vmName": "omi-agent-user", "authToken": "token"},
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "recreate_required"
    assert "operator must recreate" in result.detail
    assert updates[-1]["state"] == "recreate_required"
    assert updates[-1]["observedBootImage"].endswith("/omi-agent-old")
    assert not DriftApi.mutated


def test_boot_image_migration_plan_is_explicit_allowlisted_and_dev_only(monkeypatch):
    raw = RELEASE.to_mapping() | {
        "bootImageMigration": {
            "enabled": True,
            "allowedUids": ["dev-user"],
            "maxConcurrency": 1,
            "soakSeconds": 60,
        }
    }
    monkeypatch.setenv("AGENT_VM_ENVIRONMENT", "development")
    monkeypatch.setenv("GCE_PROJECT_ID", "based-hardware-dev")

    plan = reconciler._boot_image_migration_plan(raw, RELEASE)

    assert plan is not None
    assert plan.allowed_uids == frozenset({"dev-user"})
    assert plan.max_concurrency == 1
    with pytest.raises(ValueError, match="development-only"):
        reconciler._boot_image_migration_plan(raw, replace(RELEASE, environment="production"))


def test_boot_image_migration_plan_rejects_whitespace_only_allowed_uids(monkeypatch):
    raw = RELEASE.to_mapping() | {
        "bootImageMigration": {
            "enabled": True,
            "allowedUids": ["  "],
            "maxConcurrency": 1,
            "soakSeconds": 60,
        }
    }
    monkeypatch.setenv("AGENT_VM_ENVIRONMENT", "development")
    monkeypatch.setenv("GCE_PROJECT_ID", "based-hardware-dev")

    with pytest.raises(ValueError, match="allowedUids"):
        reconciler._boot_image_migration_plan(raw, RELEASE)


def test_boot_image_migration_plan_normalizes_allowlisted_uids(monkeypatch):
    monkeypatch.setenv("AGENT_VM_ENVIRONMENT", "development")
    monkeypatch.setenv("GCE_PROJECT_ID", "based-hardware-dev")

    plan = reconciler._boot_image_migration_plan(
        {
            "bootImageMigration": {
                "enabled": True,
                "allowedUids": ["  dev-user  "],
                "maxConcurrency": 1,
                "soakSeconds": 60,
            }
        },
        RELEASE,
    )

    assert plan == reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60)


@pytest.mark.parametrize("firestore_status", ["stopped", "ready"])
@pytest.mark.parametrize("stale_journal_disk_ids", [False, True], ids=["first-attempt", "recreated-disks"])
def test_boot_image_migration_replaces_only_a_provider_stopped_allowlisted_vm(
    monkeypatch, firestore_status, stale_journal_disk_ids
):
    class MigrationApi:
        creates: list[tuple[Any, ...]] = []
        labels: list[str] = []
        waits: list[tuple[str, str]] = []
        candidate: dict[str, Any] | None = None
        disks: dict[str, dict[str, Any]] = {}
        events: list[tuple[Any, ...]] = []

        def __init__(self, _project: str, _zone: str) -> None:
            self.project = _project
            self.old = {
                "id": "old-id",
                "status": "TERMINATED",
                "machineType": "zones/us-central1-a/machineTypes/e2-small",
                "networkInterfaces": [{"network": "global/networks/default", "networkIP": "10.128.0.8"}],
                "metadata": {},
                "serviceAccounts": [],
                "disks": [{"boot": True, "source": "projects/project/zones/us-central1-a/disks/omi-agent-user"}],
                "labelFingerprint": "fingerprint",
            }

        async def get_instance(self, name: str) -> dict[str, Any] | None:
            return self.old if name == "omi-agent-user" else type(self).candidate

        async def request(self, _method: str, url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {
                        "sourceImage": (
                            "projects/project/global/images/omi-agent-20260805"
                            if "candidate-disk" in url
                            else "projects/project/global/images/omi-agent-old"
                        )
                    }

            return Response()

        async def set_migration_labels(self, _name: str, _instance: dict[str, Any], migration_id: str) -> None:
            type(self).labels.append(migration_id)

        async def get_disk(self, name: str) -> dict[str, Any] | None:
            return type(self).disks.get(name)

        async def create_disk(self, name: str, **kwargs: Any) -> dict[str, Any]:
            disk = {
                "id": f"{name}-id",
                "status": "READY",
                "labels": {
                    "omi-agent-migration": kwargs["migration_id"],
                    "omi-agent-role": kwargs["role"],
                    "omi-agent-owner": kwargs["owner_hash"],
                },
                "users": [],
                **({"sourceDisk": kwargs["source_disk"]} if kwargs.get("source_disk") else {}),
            }
            type(self).disks[name] = disk
            return disk

        async def create_replacement(self, *args: Any) -> None:
            type(self).creates.append(args)
            migration_id = args[4]
            state_name = str(args[5]).rsplit("/", 1)[-1]
            type(self).candidate = {
                "id": "candidate-id",
                "labels": {
                    "omi-agent-migration": migration_id,
                    "omi-agent-predecessor": "old-id",
                    "omi-agent-owner": args[7],
                },
                "networkInterfaces": [{"networkIP": "10.128.0.9", "accessConfigs": [{"natIP": "34.1.2.3"}]}],
                "serviceAccounts": [{"email": RELEASE.service_account}],
                "disks": [
                    {"boot": True, "source": "projects/project/zones/us-central1-a/disks/candidate-disk"},
                    {
                        "boot": False,
                        "deviceName": "omi-agent-state",
                        "source": f"projects/project/zones/us-central1-a/disks/{state_name}",
                    },
                ],
            }

        async def attach_disk(
            self,
            vm_name: str,
            source: str,
            *,
            device_name: str,
            read_only: bool,
            auto_delete: bool,
        ) -> None:
            type(self).events.append(("attach", vm_name, source, device_name, read_only, auto_delete))
            assert type(self).candidate is not None
            type(self).candidate["disks"].append(
                {
                    "boot": False,
                    "deviceName": device_name,
                    "mode": "READ_ONLY" if read_only else "READ_WRITE",
                    "autoDelete": auto_delete,
                    "source": source,
                }
            )

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.128.0.9"

        @staticmethod
        def instance_ip(_instance: dict[str, Any]) -> str:
            return "34.1.2.3"

        async def wait_for_runtime(self, ip: str, token: str, _release: AgentVmRelease, **_kwargs: Any) -> None:
            type(self).waits.append((ip, token))

        async def detach_disk(self, _vm_name: str, _device_name: str) -> None:
            type(self).events.append(("detach", _vm_name, _device_name))
            return None

        async def delete_disk(self, name: str, *_args: Any) -> bool:
            type(self).disks.pop(name, None)
            return True

        async def set_disk_auto_delete(self, _vm_name: str, _device_name: str, _value: bool) -> None:
            type(self).events.append(("auto_delete", _vm_name, _device_name, _value))
            return None

    cutovers: list[dict[str, Any]] = []
    MigrationApi.creates = []
    MigrationApi.labels = []
    MigrationApi.waits = []
    MigrationApi.candidate = None
    MigrationApi.disks = {}
    MigrationApi.events = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", MigrationApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)

    def begin_boot_image_migration(*args: Any) -> dict[str, Any]:
        journal = dict(args[-1])
        if stale_journal_disk_ids:
            journal.update({"stateDiskId": "deleted-state-id", "sourceCloneDiskId": "deleted-source-id"})
        return journal

    monkeypatch.setattr(reconciler, "begin_boot_image_migration", begin_boot_image_migration)
    monkeypatch.setattr(reconciler, "recover_missing_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(reconciler, "record_boot_image_state_disks", lambda *_args: True)
    monkeypatch.setattr(reconciler, "record_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(reconciler, "cutover_boot_image_migration", lambda *args: cutovers.append(args[-1]) or True)
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "renew_vm_lease", lambda *_args: True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {"vmName": "omi-agent-user", "authToken": "old-token", "status": firestore_status},
            RELEASE,
            owner="worker",
            project="project",
            boot_image_migration=reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
        )
    )

    assert result.state == "migrated"
    assert MigrationApi.labels and MigrationApi.creates and MigrationApi.waits
    assert any(event[0] == "attach" and event[4:] == (True, False) for event in MigrationApi.events)
    assert cutovers[-1]["vmName"].startswith("omi-agent-user-m-")
    assert cutovers[-1]["authToken"] != "old-token"
    assert cutovers[-1]["reconcile"]["state"] == "migration_soaking"
    assert any(name.startswith("omi-agent-state-") for name in MigrationApi.disks)
    assert any(name.startswith("omi-agent-source-") for name in MigrationApi.disks)
    assert cutovers[-1]["reconcile"]["migration"]["sourceCloneCleanup"] == {
        "state": "pending",
        "deviceName": "omi-agent-state-source",
        "diskName": next(name for name in MigrationApi.disks if name.startswith("omi-agent-source-")),
        "diskId": next(disk["id"] for name, disk in MigrationApi.disks.items() if name.startswith("omi-agent-source-")),
    }
    assert cutovers[-1]["stateDisk"]["diskId"].endswith("-id")


def test_boot_image_migration_never_replaces_a_provider_running_vm_with_stale_ready_status():
    class RunningApi:
        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {"id": "old-id", "status": "RUNNING"}

    result = asyncio.run(
        reconciler._replace_stopped_boot_image_drift(
            "dev-user",
            {"vmName": "omi-agent-user", "authToken": "old-token", "status": "ready"},
            {"id": "old-id", "status": "RUNNING"},
            RELEASE,
            reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
            owner="worker",
            api=RunningApi(),
        )
    )

    assert result == reconciler.ReconcileResult(
        "dev-user", "recreate_required", "boot-image migration requires an already stopped VM"
    )


def test_migration_allowlist_owners_are_selected_outside_the_rollout_cohort(monkeypatch):
    """An explicitly allowlisted, stopped VM that is not in the normal rollout
    cohort must still be selected so its boot-image drift can be replaced."""
    monkeypatch.setattr(reconciler, "GceAgentVmClient", FakeApi)
    monkeypatch.setattr(reconciler, "_init_firebase", lambda: None)
    monkeypatch.setattr(reconciler, "claim_reconciler_run_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "renew_reconciler_run_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "release_reconciler_run_lease", lambda *_args: None)
    monkeypatch.setattr(reconciler, "_rollout_phase", lambda *_args, **_kwargs: "remainder")
    raw_manifest = RELEASE.to_mapping() | {
        "bootImageMigration": {
            "enabled": True,
            "allowedUids": ["migration-owner"],
            "maxConcurrency": 1,
            "soakSeconds": 60,
        }
    }

    def fake_owners() -> list[tuple[str, dict[str, Any]]]:
        return [
            ("migration-owner", {"vmName": "omi-agent-migration-owner", "status": "stopped"}),
            ("rollout-owner", {"vmName": "omi-agent-rollout-owner", "status": "stopped"}),
        ]

    captured_uids: list[str] = []

    async def fake_reconcile_one(uid, vm, release, **kwargs):
        captured_uids.append(uid)
        return reconciler.ReconcileResult(uid, "ready", "test")

    monkeypatch.setattr(reconciler, "_owners", fake_owners)
    monkeypatch.setattr(reconciler, "reconcile_one", fake_reconcile_one)
    monkeypatch.setattr(reconciler, "_advance_rollout", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(reconciler, "load_active_release", lambda: (RELEASE, raw_manifest))
    monkeypatch.setenv("GCE_PROJECT_ID", "based-hardware-dev")
    monkeypatch.setenv("AGENT_VM_ENVIRONMENT", "development")

    asyncio.run(reconciler.run_reconciler())

    assert (
        "migration-owner" in captured_uids
    ), "allowlisted migration owner must be selected even when outside the rollout cohort"


def test_boot_image_migration_fails_closed_for_an_unverifiable_source(monkeypatch):
    class UnverifiableApi(FakeApi):
        async def request(self, _method: str, _url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {}

            return Response()

        async def create_replacement(self, *_args: Any) -> None:
            pytest.fail("unverifiable source images must never create candidates")

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", UnverifiableApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {"vmName": "omi-agent-user", "authToken": "token", "status": "stopped"},
            RELEASE,
            owner="worker",
            project="project",
            boot_image_migration=reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
        )
    )

    assert result.state == "recreate_required"
    assert updates[-1]["lastError"] == "boot_image_source_unverifiable"


@pytest.mark.parametrize("reused", [False, True])
@pytest.mark.parametrize("retry_count, expected_state", [(0, "retry"), (2, "quarantined")])
def test_boot_image_migration_failure_restores_or_deletes_the_fenced_state_disk(
    monkeypatch, reused, retry_count, expected_state
):
    class DriftApi(FakeApi):
        project = "project"
        zone = "us-central1-a"
        deleted: list[tuple[str, str, str]] = []
        deleted_disks: list[tuple[str, str]] = []
        attached_disks: list[tuple[str, str, bool]] = []

        async def get_instance(self, vm_name: str) -> dict[str, Any] | None:
            if vm_name == "candidate":
                return {
                    "id": "candidate-id",
                    "labels": {"omi-agent-migration": "d" * 24, "omi-agent-predecessor": "old-id"},
                }
            if vm_name == "omi-agent-user":
                return {
                    "id": "old-id",
                    "labels": {"omi-agent-migration": "d" * 24},
                    "disks": [
                        {
                            "boot": True,
                            "source": "projects/project/zones/us-central1-a/disks/omi-agent-user",
                        }
                    ],
                }
            return None

        async def get_disk(self, disk_name: str) -> dict[str, Any] | None:
            if disk_name != "omi-agent-state-test":
                return None
            return {
                "id": "state-id",
                "labels": {
                    **({"omi-agent-migration": "d" * 24} if not reused else {}),
                    "omi-agent-role": "state",
                    "omi-agent-owner": "owner-label",
                },
                "users": [],
            }

        async def request(self, _method: str, _url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {"sourceImage": "projects/project/global/images/omi-agent-old"}

            return Response()

        async def delete_replacement(self, vm_name: str, instance_id: str, migration_id: str) -> bool:
            type(self).deleted.append((vm_name, instance_id, migration_id))
            return True

        async def delete_disk(self, disk_name: str, disk_id: str, *_args: Any) -> bool:
            type(self).deleted_disks.append((disk_name, disk_id))
            return True

        async def attach_disk(self, vm_name: str, source: str, *, auto_delete: bool, **_kwargs: Any) -> None:
            type(self).attached_disks.append((vm_name, source, auto_delete))

    async def failed_candidate(*_args: Any, **kwargs: Any) -> reconciler.ReconcileResult:
        kwargs["cleanup_context"].update(
            {
                "vmName": "candidate",
                "instanceId": "candidate-id",
                "oldInstanceId": "old-id",
                "migrationId": "d" * 24,
                "stateDiskName": "omi-agent-state-test",
                "stateDiskId": "state-id",
                "stateDiskReused": "true" if reused else "false",
                "ownerLabel": "owner-label",
                "sourceCloneDiskName": "",
                "sourceCloneDiskId": "",
            }
        )
        raise RuntimeError("candidate health failed")

    updates: list[dict[str, Any]] = []
    DriftApi.deleted = []
    DriftApi.deleted_disks = []
    DriftApi.attached_disks = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", DriftApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "_replace_stopped_boot_image_drift", failed_candidate)
    monkeypatch.setattr(reconciler, "mark_boot_image_migration_candidate_deleted", lambda *_args: True)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {
                "vmName": "omi-agent-user",
                "authToken": "token",
                "status": "stopped",
                "reconcile": {"retryCount": retry_count, "releaseId": RELEASE.release_id},
            },
            RELEASE,
            owner="worker",
            project="project",
            boot_image_migration=reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
        )
    )

    assert result.state == expected_state
    assert DriftApi.deleted == [("candidate", "candidate-id", "d" * 24)]
    if reused:
        assert DriftApi.attached_disks == [
            (
                "omi-agent-user",
                "projects/project/zones/us-central1-a/disks/omi-agent-state-test",
                True,
            )
        ]
        assert DriftApi.deleted_disks == []
    else:
        assert DriftApi.attached_disks == []
        assert DriftApi.deleted_disks == [("omi-agent-state-test", "state-id")]
    assert updates[-1]["state"] == expected_state


def test_boot_image_migration_cleanup_failure_keeps_admission_drained(monkeypatch):
    async def boot_drift(*_args: Any) -> tuple[str, str]:
        return "boot_image_recreate_required", "projects/project/global/images/old"

    async def failed_candidate(*_args: Any, **kwargs: Any) -> reconciler.ReconcileResult:
        kwargs["cleanup_context"].update(
            {
                "vmName": "candidate",
                "oldInstanceId": "old-id",
                "migrationId": "d" * 24,
                "stateDiskName": "state",
                "stateDiskId": "state-id",
                "stateDiskReused": "true",
                "ownerLabel": "owner",
            }
        )
        raise RuntimeError("candidate health failed")

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", FakeApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "_boot_image_drift", boot_drift)
    monkeypatch.setattr(reconciler, "_replace_stopped_boot_image_drift", failed_candidate)
    monkeypatch.setattr(
        reconciler,
        "_rollback_failed_boot_image_candidate",
        lambda *_args: asyncio.sleep(0, result=False),
    )
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {"vmName": "omi-agent-user", "authToken": "token", "status": "stopped"},
            RELEASE,
            owner="worker",
            project="project",
            boot_image_migration=reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
        )
    )

    assert result.state == "quarantined"
    assert updates[-1]["drainRequested"] is True


def test_reused_state_rollback_repairs_auto_delete_before_detach_completed():
    migration_id = "d" * 24
    events: list[tuple[Any, ...]] = []

    class Api:
        project = "project"
        zone = "us-central1-a"

        @staticmethod
        def instance_url(name: str) -> str:
            return f"https://compute.googleapis.com/compute/v1/projects/project/zones/us-central1-a/instances/{name}"

        async def get_instance(self, name: str) -> dict[str, Any] | None:
            if name == "candidate":
                return None
            return {
                "id": "old-id",
                "labels": {},
                "disks": [
                    {
                        "deviceName": lifecycle.STATE_DISK_DEVICE_NAME,
                        "source": "projects/project/zones/us-central1-a/disks/state",
                        "autoDelete": False,
                    }
                ],
            }

        async def get_disk(self, _name: str) -> dict[str, Any]:
            return {
                "id": "state-id",
                "labels": {"omi-agent-role": "state", "omi-agent-owner": "owner"},
                "users": ["projects/project/zones/us-central1-a/instances/old"],
            }

        async def set_disk_auto_delete(self, *args: Any) -> None:
            events.append(args)

    restored = asyncio.run(
        reconciler._rollback_failed_boot_image_candidate(
            Api(),
            "uid",
            "old",
            {
                "migrationId": migration_id,
                "vmName": "candidate",
                "oldInstanceId": "old-id",
                "stateDiskName": "state",
                "stateDiskId": "state-id",
                "stateDiskReused": "true",
                "ownerLabel": "owner",
            },
        )
    )

    assert restored is True
    assert events == [("old", lifecycle.STATE_DISK_DEVICE_NAME, True)]


def test_reused_state_rollback_treats_omitted_disk_users_as_detached():
    migration_id = "d" * 24
    attachments: list[tuple[Any, ...]] = []

    class Api:
        project = "project"
        zone = "us-central1-a"

        async def get_instance(self, name: str) -> dict[str, Any] | None:
            if name == "candidate":
                return None
            return {"id": "old-id", "labels": {}, "disks": []}

        async def get_disk(self, _name: str) -> dict[str, Any]:
            return {
                "id": "state-id",
                "labels": {"omi-agent-role": "state", "omi-agent-owner": "owner"},
            }

        async def attach_disk(self, *args: Any, **kwargs: Any) -> None:
            attachments.append((*args, kwargs))

    restored = asyncio.run(
        reconciler._rollback_failed_boot_image_candidate(
            Api(),
            "uid",
            "old",
            {
                "migrationId": migration_id,
                "vmName": "candidate",
                "oldInstanceId": "old-id",
                "stateDiskName": "state",
                "stateDiskId": "state-id",
                "stateDiskReused": "true",
                "ownerLabel": "owner",
            },
        )
    )

    assert restored is True
    assert attachments == [
        (
            "old",
            "projects/project/zones/us-central1-a/disks/state",
            {"auto_delete": True},
        )
    ]


def test_reused_state_disk_requires_exact_predecessor_attachment_user_before_detach(monkeypatch):
    expected_user = "projects/project/zones/us-central1-a/instances/omi-agent-user"
    events: list[str] = []

    class Api:
        project = "project"
        zone = "us-central1-a"

        @staticmethod
        def instance_url(name: str) -> str:
            return f"https://compute.googleapis.com/compute/v1/projects/project/zones/us-central1-a/instances/{name}"

        async def get_instance(self, name: str) -> dict[str, Any] | None:
            if name.startswith("omi-agent-user-m-"):
                return None
            return {"id": "old-id", "status": "TERMINATED", "labels": {}}

        async def get_disk(self, _name: str) -> dict[str, Any]:
            return {
                "id": "state-id",
                "labels": {"omi-agent-role": "state", "omi-agent-owner": reconciler._owner_disk_label("dev-user")},
                "users": [expected_user, "projects/project/zones/us-central1-a/instances/other"],
            }

        async def set_migration_labels(self, *_args: Any) -> None:
            return None

        async def create_replacement(self, *_args: Any) -> None:
            pytest.fail("ambiguous state ownership must block candidate creation")

        async def set_disk_auto_delete(self, *_args: Any) -> None:
            events.append("auto-delete")

        async def detach_disk(self, *_args: Any) -> None:
            events.append("detach")

    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "begin_boot_image_migration", lambda *args: dict(args[-1]))
    monkeypatch.setattr(reconciler, "recover_missing_boot_image_candidate", lambda *_args: True)

    with pytest.raises(RuntimeError, match="state disk identity is ambiguous"):
        asyncio.run(
            reconciler._replace_stopped_boot_image_drift(
                "dev-user",
                {
                    "vmName": "omi-agent-user",
                    "zone": "us-central1-a",
                    "authToken": "old-token",
                    "status": "stopped",
                    "stateDisk": {"diskId": "state-id"},
                },
                {
                    "id": "old-id",
                    "status": "TERMINATED",
                    "disks": [
                        {
                            "boot": False,
                            "deviceName": "omi-agent-state",
                            "source": "projects/project/zones/us-central1-a/disks/legacy-state",
                        }
                    ],
                },
                RELEASE,
                reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
                owner="worker",
                api=Api(),
                cleanup_context={},
            )
        )

    assert events == []


def test_pre_cutover_session_deferral_compensates_candidate_and_reused_disk(monkeypatch):
    migration_id = reconciler._boot_image_migration_id("dev-user", "omi-agent-user", "old-id", RELEASE.release_id)
    expected_user = "projects/project/zones/us-central1-a/instances/omi-agent-user"

    class Api:
        project = "project"
        zone = "us-central1-a"

        def __init__(self) -> None:
            self.detached = False
            self.candidate: dict[str, Any] | None = None
            self.events: list[tuple[Any, ...]] = []

        @staticmethod
        def instance_url(name: str) -> str:
            return f"https://compute.googleapis.com/compute/v1/projects/project/zones/us-central1-a/instances/{name}"

        def old_instance(self) -> dict[str, Any]:
            return {
                "id": "old-id",
                "status": "TERMINATED",
                "labels": {"omi-agent-migration": migration_id},
                "disks": [
                    {"boot": True, "source": "projects/project/zones/us-central1-a/disks/omi-agent-user"},
                    *(
                        []
                        if self.detached
                        else [
                            {
                                "boot": False,
                                "deviceName": "omi-agent-state",
                                "source": "projects/project/zones/us-central1-a/disks/legacy-state",
                            }
                        ]
                    ),
                ],
            }

        async def get_instance(self, name: str) -> dict[str, Any] | None:
            return self.candidate if name.startswith("omi-agent-user-m-") else self.old_instance()

        async def request(self, _method: str, _url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {"sourceImage": RELEASE.boot_image}

            return Response()

        async def set_migration_labels(self, *_args: Any) -> None:
            return None

        async def get_disk(self, _name: str) -> dict[str, Any]:
            return {
                "id": "state-id",
                "labels": {"omi-agent-role": "state", "omi-agent-owner": reconciler._owner_disk_label("dev-user")},
                "users": [] if self.detached else [expected_user],
            }

        async def create_replacement(self, *args: Any) -> None:
            self.candidate = {
                "id": "candidate-id",
                "labels": {
                    "omi-agent-migration": migration_id,
                    "omi-agent-predecessor": "old-id",
                    "omi-agent-owner": args[7],
                },
                "serviceAccounts": [{"email": RELEASE.service_account}],
                "disks": [
                    {"boot": True, "source": "projects/project/zones/us-central1-a/disks/candidate-disk"},
                    {
                        "boot": False,
                        "deviceName": "omi-agent-state",
                        "source": "projects/project/zones/us-central1-a/disks/legacy-state",
                    },
                ],
                "networkInterfaces": [{"networkIP": "10.128.0.9"}],
            }

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.128.0.9"

        @staticmethod
        def instance_ip(_instance: dict[str, Any]) -> None:
            return None

        async def wait_for_runtime(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def set_disk_auto_delete(self, vm_name: str, device_name: str, enabled: bool) -> None:
            self.events.append(("auto-delete", vm_name, device_name, enabled))

        async def detach_disk(self, vm_name: str, device_name: str) -> None:
            self.events.append(("detach", vm_name, device_name))
            self.detached = True

        async def delete_replacement(self, vm_name: str, instance_id: str, migration: str) -> bool:
            self.events.append(("delete-candidate", vm_name, instance_id, migration))
            self.candidate = None
            return True

        async def attach_disk(self, vm_name: str, source: str, *, auto_delete: bool, **_kwargs: Any) -> None:
            self.events.append(("attach", vm_name, source, auto_delete))
            self.detached = False

        async def delete_disk(self, *_args: Any) -> bool:
            pytest.fail("reused state disk must be restored, not deleted")

    api = Api()
    session_calls = 0

    def active_sessions(*_args: Any) -> int:
        nonlocal session_calls
        session_calls += 1
        return 1 if session_calls == 2 else 0

    cleanup_context: dict[str, str] = {}
    monkeypatch.setattr(reconciler, "active_session_count", active_sessions)
    monkeypatch.setattr(reconciler, "begin_boot_image_migration", lambda *args: dict(args[-1]))
    monkeypatch.setattr(reconciler, "recover_missing_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(
        reconciler, "record_boot_image_state_disks", lambda *_args: api.events.append(("journal",)) or True
    )
    monkeypatch.setattr(reconciler, "record_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(reconciler, "mark_boot_image_migration_candidate_deleted", lambda *_args: True)
    monkeypatch.setattr(reconciler, "renew_vm_lease", lambda *_args: True)
    monkeypatch.setattr(
        reconciler,
        "cutover_boot_image_migration",
        lambda *_args: pytest.fail("session deferral must compensate before cutover"),
    )

    result = asyncio.run(
        reconciler._replace_stopped_boot_image_drift(
            "dev-user",
            {"vmName": "omi-agent-user", "zone": "us-central1-a", "authToken": "old-token", "status": "stopped"},
            {
                "id": "old-id",
                "status": "TERMINATED",
                "disks": [
                    {
                        "boot": False,
                        "deviceName": "omi-agent-state",
                        "source": "projects/project/zones/us-central1-a/disks/legacy-state",
                    }
                ],
            },
            RELEASE,
            reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
            owner="worker",
            api=api,
            cleanup_context=cleanup_context,
        )
    )

    assert result.state == "deferred"
    assert cleanup_context == {}
    assert [event[0] for event in api.events] == ["journal", "auto-delete", "detach", "delete-candidate", "attach"]
    assert api.events[1][3] is False
    assert api.events[-1][3] is True


@pytest.mark.parametrize("retry_count", [0, 3])
def test_post_cutover_state_failure_keeps_admission_drained_and_retryable(monkeypatch, retry_count):
    async def no_boot_drift(*_args: Any) -> None:
        pytest.fail("active release boot drift must wait until migration retirement")

    async def state_failure(*_args: Any) -> None:
        raise RuntimeError("active state disk is ambiguous")

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", FakeApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "_boot_image_drift", no_boot_drift)
    monkeypatch.setattr(reconciler, "_active_state_disk_info", state_failure)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {
                "vmName": "omi-agent-user",
                "authToken": "token",
                "instanceId": "candidate-id",
                "status": "ready",
                "reconcile": {
                    "releaseId": RELEASE.release_id,
                    "retryCount": retry_count,
                    "migration": {"candidateInstanceId": "candidate-id"},
                },
            },
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "retry"
    assert updates[-1]["drainRequested"] is True


def test_first_post_cutover_reconcile_keeps_candidate_state_disk_protected(monkeypatch):
    auto_delete_repairs: list[tuple[str, str, bool]] = []

    class CandidateApi:
        def __init__(self, _project: str, _zone: str) -> None:
            self.instance = {
                "id": "candidate-id",
                "status": "RUNNING",
                "disks": [
                    {
                        "boot": False,
                        "deviceName": lifecycle.STATE_DISK_DEVICE_NAME,
                        "source": "projects/project/zones/us-central1-a/disks/candidate-state",
                        "autoDelete": False,
                    }
                ],
            }

        async def get_instance(self, _vm_name: str) -> dict[str, Any]:
            return self.instance

        async def get_disk(self, _disk_name: str) -> dict[str, Any]:
            return {
                "id": "candidate-state-id",
                "labels": {
                    "omi-agent-role": "state",
                    "omi-agent-owner": reconciler._owner_disk_label("dev-user"),
                },
                "users": ["projects/project/zones/us-central1-a/instances/candidate"],
            }

        @staticmethod
        def instance_url(name: str) -> str:
            return "https://compute.googleapis.com/compute/v1/projects/project/zones/" f"us-central1-a/instances/{name}"

        async def set_disk_auto_delete(self, vm_name: str, device_name: str, enabled: bool) -> None:
            auto_delete_repairs.append((vm_name, device_name, enabled))

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.0.0.2"

        async def runtime_is_current(self, *_args: Any, **_kwargs: Any) -> bool:
            return True

    async def no_boot_drift(*_args: Any) -> None:
        pytest.fail("active release boot drift must wait until migration retirement")

    monkeypatch.setattr(reconciler, "GceAgentVmClient", CandidateApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "_boot_image_drift", no_boot_drift)
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "claim_boot_image_migration_retirement", lambda *_args: {"state": "soaking"})

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {
                "vmName": "candidate",
                "zone": "us-central1-a",
                "status": "ready",
                "instanceId": "candidate-id",
                "authToken": "candidate-token",
                "stateDisk": {
                    "deviceName": lifecycle.STATE_DISK_DEVICE_NAME,
                    "diskName": "candidate-state",
                    "diskId": "candidate-state-id",
                },
                "reconcile": {
                    "state": "migration_soaking",
                    "migration": {
                        "migrationId": "a" * 24,
                        "oldVmName": "old-vm",
                        "oldInstanceId": "old-id",
                        "candidateInstanceId": "candidate-id",
                    },
                },
            },
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "soaking"
    assert auto_delete_repairs == []


def test_existing_candidate_failure_populates_compensating_cleanup_context(monkeypatch):
    migration_id = "f" * 24
    journal = {
        "migrationId": migration_id,
        "oldInstanceId": "old-id",
        "candidateVmName": "candidate",
        "candidateAuthToken": "candidate-token",
        "candidateInstanceId": "candidate-id",
        "stateDiskName": "state-disk",
        "stateDiskId": "state-id",
        "stateDiskReused": True,
        "sourceCloneDiskName": "",
    }

    class ExistingCandidateApi:
        project = "project"
        zone = "us-central1-a"

        async def set_migration_labels(self, *_args: Any) -> None:
            return None

        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {"id": "candidate-id", "labels": {"omi-agent-migration": "foreign"}}

    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "begin_boot_image_migration", lambda *_args: journal)
    context: dict[str, str] = {}

    with pytest.raises(RuntimeError, match="identity is ambiguous"):
        asyncio.run(
            reconciler._replace_stopped_boot_image_drift(
                "dev-user",
                {"vmName": "old", "zone": "us-central1-a", "authToken": "old-token", "status": "stopped"},
                {"id": "old-id", "status": "STOPPED"},
                RELEASE,
                reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
                owner="worker",
                api=ExistingCandidateApi(),
                cleanup_context=context,
            )
        )

    assert context["instanceId"] == "candidate-id"
    assert context["stateDiskId"] == "state-id"
    assert context["stateDiskReused"] == "true"


def test_boot_image_migration_soak_retries_an_unhealthy_candidate():
    class SoakApi:
        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {"id": "candidate-id", "status": "RUNNING"}

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.0.0.2"

        async def runtime_is_current(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

        async def get_disk(self, _name: str) -> dict[str, Any]:
            pytest.fail("source cleanup must not precede soak health")

    migration = {
        "migrationId": "e" * 24,
        "oldVmName": "old-vm",
        "oldInstanceId": "old-id",
        "candidateInstanceId": "candidate-id",
    }
    with pytest.raises(RuntimeError, match="not healthy"):
        asyncio.run(
            reconciler._retire_soaked_boot_image_predecessor(
                "dev-user",
                {
                    "vmName": "candidate",
                    "authToken": "candidate-token",
                    "instanceId": "candidate-id",
                    "reconcile": {"migration": migration},
                },
                owner="worker",
                api=SoakApi(),
                release=RELEASE,
            )
        )


def test_boot_image_migration_soak_uses_its_pinned_release_after_active_release_advances(monkeypatch):
    observed_releases: list[AgentVmRelease] = []

    class SoakApi:
        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {"id": "candidate-id", "status": "RUNNING"}

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.0.0.2"

        async def runtime_is_current(
            self, _ip: str, _token: str, checked_release: AgentVmRelease, **_kwargs: Any
        ) -> bool:
            observed_releases.append(checked_release)
            return True

    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "claim_boot_image_migration_retirement", lambda *_args: {"state": "soaking"})
    migration = {
        "migrationId": "9" * 24,
        "oldVmName": "old-vm",
        "oldInstanceId": "old-id",
        "candidateInstanceId": "candidate-id",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "targetReleaseManifest": RELEASE.to_mapping(),
    }
    active_release = replace(
        RELEASE,
        source_sha="d" * 40,
        image_digest="gcr.io/project/agent-vm@sha256:" + "e" * 64,
    )

    result = asyncio.run(
        reconciler._retire_soaked_boot_image_predecessor(
            "dev-user",
            {
                "vmName": "candidate",
                "authToken": "candidate-token",
                "instanceId": "candidate-id",
                "reconcile": {"migration": migration},
            },
            owner="worker",
            api=SoakApi(),
            release=active_release,
        )
    )

    assert result and result.state == "soaking"
    assert observed_releases == [RELEASE]


def test_boot_image_migration_retains_source_clone_until_retirement_claim(monkeypatch):
    class SoakApi:
        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {"id": "candidate-id", "status": "RUNNING"}

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.0.0.2"

        async def runtime_is_current(self, *_args: Any, **_kwargs: Any) -> bool:
            return True

        async def get_disk(self, _name: str) -> dict[str, Any]:
            pytest.fail("source clone cleanup must wait for the retirement gate")

    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "claim_boot_image_migration_retirement", lambda *_args: {"state": "soaking"})
    migration = {
        "migrationId": "3" * 24,
        "oldVmName": "old-vm",
        "oldInstanceId": "old-id",
        "candidateInstanceId": "candidate-id",
        "sourceCloneDiskName": "source-disk",
        "sourceCloneDiskId": "source-id",
    }

    result = asyncio.run(
        reconciler._retire_soaked_boot_image_predecessor(
            "dev-user",
            {
                "vmName": "candidate",
                "authToken": "candidate-token",
                "instanceId": "candidate-id",
                "reconcile": {"migration": migration},
            },
            owner="worker",
            api=SoakApi(),
            release=RELEASE,
        )
    )

    assert result and result.state == "soaking"
    assert "within its journaled soak" in result.detail


@pytest.mark.parametrize("auto_delete_fails", [False, True])
def test_boot_image_migration_retirement_enables_state_auto_delete_after_journal_claim(monkeypatch, auto_delete_fails):
    events: list[tuple[Any, ...]] = []
    fallback_events: list[dict[str, Any]] = []

    class RetirementApi:
        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {"id": "candidate-id", "status": "RUNNING"}

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.0.0.2"

        async def runtime_is_current(self, *_args: Any, **_kwargs: Any) -> bool:
            return True

        async def set_disk_auto_delete(self, vm_name: str, device_name: str, enabled: bool) -> None:
            events.append(("auto-delete", vm_name, device_name, enabled))
            if auto_delete_fails:
                raise RuntimeError("provider unavailable")

        async def delete_replacement(self, vm_name: str, instance_id: str, migration_id: str) -> bool:
            events.append(("delete-predecessor", vm_name, instance_id, migration_id))
            return True

    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "record_fallback", lambda **kwargs: fallback_events.append(kwargs))
    monkeypatch.setattr(
        reconciler,
        "claim_boot_image_migration_retirement",
        lambda *_args: events.append(("claim-retirement",))
        or {"state": "retiring", "oldVmName": "old-vm", "oldInstanceId": "old-id"},
    )
    monkeypatch.setattr(
        reconciler,
        "complete_boot_image_migration",
        lambda *_args: events.append(("complete-migration",)) or True,
    )
    migration = {
        "migrationId": "4" * 24,
        "oldVmName": "old-vm",
        "oldInstanceId": "old-id",
        "candidateInstanceId": "candidate-id",
        "sourceCloneDiskName": "",
    }

    result = asyncio.run(
        reconciler._retire_soaked_boot_image_predecessor(
            "dev-user",
            {
                "vmName": "candidate",
                "authToken": "candidate-token",
                "instanceId": "candidate-id",
                "reconcile": {"migration": migration},
            },
            owner="worker",
            api=RetirementApi(),
            release=RELEASE,
        )
    )

    assert result and result.state == "retired"
    assert events == [
        ("claim-retirement",),
        ("delete-predecessor", "old-vm", "old-id", migration["migrationId"]),
        ("complete-migration",),
        ("auto-delete", "candidate", lifecycle.STATE_DISK_DEVICE_NAME, True),
    ]
    if auto_delete_fails:
        assert "state disk protected" in result.detail
        assert fallback_events == [
            {
                "component": "agent_vm_reconciler",
                "from_mode": "automatic_state_disk_lifecycle",
                "to_mode": "protected_disk_repair",
                "reason": "other",
                "outcome": "degraded",
                "log": reconciler.logger,
            }
        ]
    else:
        assert fallback_events == []


def test_boot_image_migration_retirement_keeps_state_disk_protected_when_source_cleanup_fails(monkeypatch):
    events: list[tuple[Any, ...]] = []

    class RetirementApi:
        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {
                "id": "candidate-id",
                "status": "RUNNING",
                "disks": [
                    {
                        "boot": False,
                        "deviceName": lifecycle.STATE_SOURCE_DEVICE_NAME,
                        "source": "projects/project/zones/us-central1-a/disks/source-disk",
                    }
                ],
            }

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.0.0.2"

        async def runtime_is_current(self, *_args: Any, **_kwargs: Any) -> bool:
            return True

        async def get_disk(self, _disk_name: str) -> dict[str, Any]:
            return {"id": "foreign-source-id"}

        async def set_disk_auto_delete(self, *_args: Any) -> None:
            events.append(("auto-delete",))

        async def delete_replacement(self, *_args: Any) -> bool:
            events.append(("delete-predecessor",))
            return True

    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(
        reconciler,
        "claim_boot_image_migration_retirement",
        lambda *_args: {"state": "retiring", "oldVmName": "old-vm", "oldInstanceId": "old-id"},
    )
    monkeypatch.setattr(
        reconciler,
        "complete_boot_image_migration",
        lambda *_args: pytest.fail("source cleanup must complete before the migration commit"),
    )

    result = asyncio.run(
        reconciler._retire_soaked_boot_image_predecessor(
            "dev-user",
            {
                "vmName": "candidate",
                "authToken": "candidate-token",
                "instanceId": "candidate-id",
                "reconcile": {
                    "migration": {
                        "migrationId": "5" * 24,
                        "oldVmName": "old-vm",
                        "oldInstanceId": "old-id",
                        "candidateInstanceId": "candidate-id",
                        "sourceCloneDiskName": "source-disk",
                        "sourceCloneDiskId": "source-id",
                    }
                },
            },
            owner="worker",
            api=RetirementApi(),
            release=RELEASE,
        )
    )

    assert result == reconciler.ReconcileResult(
        "dev-user", "stale", "migration source clone identity changed before cleanup"
    )
    assert events == []


def test_durable_pre_cutover_journal_recovers_detached_state_without_manifest_opt_in(monkeypatch):
    migration_id = "6" * 24
    journal = {
        "migrationId": migration_id,
        "state": "candidate_creating",
        "oldVmName": "omi-agent-user",
        "oldZone": "us-central1-a",
        "oldAuthToken": "old-token",
        "oldInstanceId": "old-id",
        "candidateVmName": "omi-agent-user-m-666666666666",
        "candidateAuthToken": "candidate-token",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "soakSeconds": 60,
        "stateDiskName": "legacy-state",
        "stateDiskId": "state-id",
        "stateDiskReused": True,
        "sourceCloneDiskName": "",
    }

    class RecoveryApi:
        project = "project"
        zone = "us-central1-a"

        def __init__(self, _project: str, _zone: str) -> None:
            self.candidate: dict[str, Any] | None = None
            self.created = False

        async def get_instance(self, name: str) -> dict[str, Any] | None:
            if name == "omi-agent-user":
                return {
                    "id": "old-id",
                    "status": "TERMINATED",
                    "machineType": "zones/us-central1-a/machineTypes/e2-small",
                    "networkInterfaces": [{"network": "global/networks/default", "networkIP": "10.0.0.1"}],
                    "metadata": {},
                    "serviceAccounts": [],
                    "disks": [{"boot": True, "source": "projects/project/zones/us-central1-a/disks/old-boot"}],
                    "labelFingerprint": "fingerprint",
                }
            return self.candidate

        @staticmethod
        def instance_url(name: str) -> str:
            return f"https://compute.googleapis.com/compute/v1/projects/project/zones/us-central1-a/instances/{name}"

        async def set_migration_labels(self, *_args: Any) -> None:
            return None

        async def get_disk(self, name: str) -> dict[str, Any] | None:
            if name != "legacy-state":
                return None
            return {
                "id": "state-id",
                "labels": {
                    "omi-agent-role": "state",
                    "omi-agent-owner": reconciler._owner_disk_label("dev-user"),
                },
                # The crash happened after detach, so the durable disk is not
                # owned by the predecessor while the journal remains active.
                "users": [],
            }

        async def create_disk(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            pytest.fail("recovery must reuse the journaled state disk")

        async def create_replacement(self, *_args: Any) -> None:
            self.created = True
            self.candidate = {
                "id": "candidate-id",
                "status": "RUNNING",
                "labels": {
                    "omi-agent-migration": migration_id,
                    "omi-agent-predecessor": "old-id",
                    "omi-agent-owner": reconciler._owner_disk_label("dev-user"),
                },
                "serviceAccounts": [{"email": RELEASE.service_account}],
                "networkInterfaces": [{"networkIP": "10.0.0.2", "accessConfigs": [{"natIP": "34.0.0.2"}]}],
                "disks": [
                    {"boot": True, "source": "projects/project/zones/us-central1-a/disks/candidate-boot"},
                    {
                        "boot": False,
                        "deviceName": lifecycle.STATE_DISK_DEVICE_NAME,
                        "source": "projects/project/zones/us-central1-a/disks/legacy-state",
                    },
                ],
            }

        async def delete_replacement(self, *_args: Any) -> bool:
            self.candidate = None
            return True

        async def request(self, _method: str, _url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {"sourceImage": RELEASE.boot_image}

            return Response()

        @staticmethod
        def private_instance_ip(_instance: Mapping[str, Any]) -> str:
            return "10.0.0.2"

        @staticmethod
        def instance_ip(_instance: Mapping[str, Any]) -> str:
            return "34.0.0.2"

        async def wait_for_runtime(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    cutovers: list[Mapping[str, Any]] = []
    vm = {
        "vmName": "omi-agent-user",
        "zone": "us-central1-a",
        "status": "stopped",
        "instanceId": "old-id",
        "authToken": "old-token",
        "reconcile": {
            "state": "quarantined",
            "releaseId": RELEASE.release_id,
            "lastError": "RuntimeError",
            "durableMigration": migration_id,
            "drainRequested": True,
            "drainRequestedAt": 90.0,
        },
    }
    client = StrictFirestore(
        {
            ("users", "dev-user"): {"agentVm": vm},
            ("users", "dev-user", "agentVmMigrations", migration_id): journal,
        }
    )
    monkeypatch.setattr(reconciler, "GceAgentVmClient", RecoveryApi)
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)
    monkeypatch.setattr(reconciler, "begin_boot_image_migration", lambda *_args: dict(journal))
    monkeypatch.setattr(reconciler, "recover_missing_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(reconciler, "record_boot_image_state_disks", lambda *_args: True)
    monkeypatch.setattr(reconciler, "record_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler, "renew_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "cutover_boot_image_migration", lambda *args: cutovers.append(args[-1]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            vm,
            RELEASE,
            owner="worker",
            project="project",
            # No boot_image_migration manifest plan is supplied.
        )
    )

    assert result.state == "migrated"
    assert client.transactions[0].updates[-1][1]["agentVm.reconcile.state"] == "claimed"
    assert cutovers and cutovers[-1]["instanceId"] == "candidate-id"


def test_older_candidate_deleted_journal_is_superseded_only_after_provider_rollback(monkeypatch):
    migration_id = "6" * 24
    current_release = replace(RELEASE, source_sha="d" * 40)
    predecessor_name = "omi-agent-user"
    state_disk_name = "omi-agent-state-6666666666666666"
    instance = {
        "id": "old-id",
        "status": "TERMINATED",
        "disks": [
            {
                "boot": True,
                "source": "projects/project/zones/us-central1-a/disks/old-boot",
                "autoDelete": True,
            },
            {
                "boot": False,
                "deviceName": lifecycle.STATE_DISK_DEVICE_NAME,
                "source": f"projects/project/zones/us-central1-a/disks/{state_disk_name}",
                "autoDelete": True,
            },
        ],
    }
    journal = {
        "migrationId": migration_id,
        "state": "candidate_deleted",
        "candidateDeletedAt": 90.0,
        "oldVmName": predecessor_name,
        "oldZone": "us-central1-a",
        "oldAuthToken": "old-token",
        "oldInstanceId": "old-id",
        "candidateVmName": "omi-agent-user-m-666666666666",
        "candidateAuthToken": "candidate-token",
        "candidateInstanceId": "candidate-id",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "soakSeconds": 60,
        "stateDiskName": state_disk_name,
        "stateDiskId": "state-id",
        "stateDiskReused": True,
        "sourceCloneDiskName": "",
    }

    class RolledBackApi:
        project = "project"
        zone = "us-central1-a"

        async def get_instance(self, name: str) -> dict[str, Any] | None:
            return instance if name == predecessor_name else None

        async def get_disk(self, name: str) -> dict[str, Any] | None:
            assert name == state_disk_name
            return {
                "id": "state-id",
                "labels": {
                    "omi-agent-role": "state",
                    "omi-agent-owner": reconciler._owner_disk_label("dev-user"),
                },
                "users": [f"projects/project/zones/us-central1-a/instances/{predecessor_name}"],
            }

    superseded: list[tuple[Any, ...]] = []
    cleanup_context: dict[str, str] = {}
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(
        migration_control,
        "supersede_failed_boot_image_migration",
        lambda *args: superseded.append(args) or True,
    )

    result = asyncio.run(
        reconciler._replace_stopped_boot_image_drift(
            "dev-user",
            {
                "vmName": predecessor_name,
                "zone": "us-central1-a",
                "status": "stopped",
                "instanceId": "old-id",
                "authToken": "old-token",
            },
            instance,
            current_release,
            reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
            owner="worker",
            api=RolledBackApi(),
            cleanup_context=cleanup_context,
            recovery_journal=journal,
        )
    )

    assert result == reconciler.ReconcileResult(
        "dev-user", "retry", "superseded a rolled-back migration from an older release"
    )
    assert superseded and superseded[-1][-2:] == (migration_id, current_release.release_id)
    assert cleanup_context == {}


def test_older_candidate_deleted_journal_stays_fail_closed_when_provider_rollback_is_ambiguous(monkeypatch):
    migration_id = "8" * 24
    cleanup_context: dict[str, str] = {}
    superseded: list[tuple[Any, ...]] = []

    async def ambiguous_rollback(_context: Mapping[str, str]) -> bool:
        return False

    monkeypatch.setattr(
        migration_control,
        "supersede_failed_boot_image_migration",
        lambda *args: superseded.append(args) or True,
    )

    with pytest.raises(RuntimeError, match="provider state is ambiguous"):
        asyncio.run(
            migration_control.supersede_rolled_back_boot_image_migration(
                uid="dev-user",
                vm_name="omi-agent-user",
                zone="us-central1-a",
                auth_token="old-token",
                owner="worker",
                old_instance_id="old-id",
                replacement_release_id=replace(RELEASE, source_sha="d" * 40).release_id,
                recovery_journal={
                    "migrationId": migration_id,
                    "state": "candidate_deleted",
                    "candidateDeletedAt": 90.0,
                    "oldVmName": "omi-agent-user",
                    "oldInstanceId": "old-id",
                    "candidateVmName": "omi-agent-user-m-888888888888",
                    "candidateInstanceId": "candidate-id",
                    "targetRelease": RELEASE.release_id,
                    "stateDiskName": "omi-agent-state-8888888888888888",
                    "stateDiskId": "state-id",
                    "stateDiskReused": True,
                },
                owner_label=reconciler._owner_disk_label("dev-user"),
                cleanup_context=cleanup_context,
                rollback=ambiguous_rollback,
            )
        )

    assert superseded == []
    assert cleanup_context["migrationId"] == migration_id


def test_older_candidate_deleted_journal_reports_stale_when_firestore_fence_changes(monkeypatch):
    migration_id = "9" * 24
    cleanup_context: dict[str, str] = {}
    blocking_calls: list[tuple[Any, ...]] = []

    async def rolled_back(_context: Mapping[str, str]) -> bool:
        return True

    async def bounded_run(executor: Any, function: Any, *args: Any) -> bool:
        blocking_calls.append((executor, function, *args))
        return False

    monkeypatch.setattr(migration_control, "run_blocking", bounded_run)

    result = asyncio.run(
        migration_control.supersede_rolled_back_boot_image_migration(
            uid="dev-user",
            vm_name="omi-agent-user",
            zone="us-central1-a",
            auth_token="old-token",
            owner="worker",
            old_instance_id="old-id",
            replacement_release_id=replace(RELEASE, source_sha="d" * 40).release_id,
            recovery_journal={
                "migrationId": migration_id,
                "state": "candidate_deleted",
                "candidateDeletedAt": 90.0,
                "oldVmName": "omi-agent-user",
                "oldInstanceId": "old-id",
                "candidateVmName": "omi-agent-user-m-999999999999",
                "candidateInstanceId": "candidate-id",
                "targetRelease": RELEASE.release_id,
                "stateDiskName": "omi-agent-state-9999999999999999",
                "stateDiskId": "state-id",
                "stateDiskReused": True,
            },
            owner_label=reconciler._owner_disk_label("dev-user"),
            cleanup_context=cleanup_context,
            rollback=rolled_back,
        )
    )

    assert result == "stale"
    assert blocking_calls and blocking_calls[-1][0] is migration_control.db_executor
    assert blocking_calls[-1][1] is migration_control.supersede_failed_boot_image_migration
    assert cleanup_context == {}


def test_terminal_quarantine_with_non_pre_cutover_journal_stays_fail_closed(monkeypatch):
    migration_id = "7" * 24

    class StaleJournalApi(FakeApi):
        async def get_instance(self, _name: str) -> dict[str, Any]:
            return {"id": "old-id", "status": "TERMINATED"}

    monkeypatch.setattr(reconciler, "GceAgentVmClient", StaleJournalApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "active_boot_image_migration", lambda *_args: {"state": "cutover"})

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {
                "vmName": "omi-agent-user",
                "zone": "us-central1-a",
                "status": "ready",
                "authToken": "old-token",
                "reconcile": {
                    "state": "quarantined",
                    "releaseId": RELEASE.release_id,
                    "lastError": "RuntimeError",
                    "durableMigration": migration_id,
                },
            },
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result == reconciler.ReconcileResult("dev-user", "quarantined", "RuntimeError")


def test_quarantine_lease_rejects_non_pre_cutover_journal(monkeypatch):
    migration_id = "8" * 24
    vm = {
        "vmName": "omi-agent-user",
        "instanceId": "old-id",
        "authToken": "old-token",
        "reconcile": {
            "state": "quarantined",
            "releaseId": RELEASE.release_id,
            "durableMigration": migration_id,
        },
    }
    client = StrictFirestore(
        {
            ("users", "dev-user"): {"agentVm": vm},
            ("users", "dev-user", "agentVmMigrations", migration_id): {
                "migrationId": migration_id,
                "state": "cutover",
                "oldVmName": vm["vmName"],
                "oldInstanceId": vm["instanceId"],
                "oldAuthToken": vm["authToken"],
                "targetRelease": RELEASE.release_id,
            },
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)

    assert not lifecycle.claim_vm_lease(
        "dev-user",
        vm["vmName"],
        vm["authToken"],
        "worker",
        RELEASE.release_id,
        migration_id,
        now=100.0,
    )
    assert client.transactions[0].updates == []


def test_boot_image_migration_never_creates_for_an_active_session(monkeypatch):
    class DriftApi(FakeApi):
        async def request(self, _method: str, _url: str) -> Any:
            class Response:
                @staticmethod
                def raise_for_status() -> None:
                    return None

                @staticmethod
                def json() -> dict[str, str]:
                    return {"sourceImage": "projects/project/global/images/omi-agent-old"}

            return Response()

        async def create_replacement(self, *_args: Any) -> None:
            pytest.fail("active sessions must block replacement")

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", DriftApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 1)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {"vmName": "omi-agent-user", "authToken": "token", "status": "stopped"},
            RELEASE,
            owner="worker",
            project="project",
            boot_image_migration=reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
        )
    )

    assert result.state == "recreate_required"
    assert updates[-1]["state"] == "recreate_required"


def test_boot_image_migration_journal_fences_predecessor_and_resumes_candidate_ready(monkeypatch):
    now = 100.0
    migration_id = "a" * 24
    user = {
        "agentVm": {
            "vmName": "omi-agent-user",
            "zone": "us-central1-a",
            "status": "stopped",
            "instanceId": "old-id",
            "authToken": "old-token",
            "reconcile": {"lease": {"owner": "worker", "expiresAt": 200.0}},
        }
    }
    client = StrictFirestore({("users", "dev-user"): user})
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)
    migration = {
        "migrationId": migration_id,
        "oldVmName": "omi-agent-user",
        "oldZone": "us-central1-a",
        "oldAuthToken": "old-token",
        "oldInstanceId": "old-id",
        "candidateVmName": "omi-agent-user-m-aaaaaaaaaaaa",
        "candidateAuthToken": "candidate-token",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "soakSeconds": 60,
        "stateDiskName": "omi-agent-state-aaaaaaaaaaaaaaaa",
        "stateDiskReused": False,
        "sourceCloneDiskName": "omi-agent-source-aaaaaaaaaaaaaaaa",
    }

    journal = lifecycle.begin_boot_image_migration(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, migration, now=now
    )
    assert journal and journal["candidateAuthToken"] == "candidate-token"
    assert client.transactions[-1].updates[-1][1]["agentVm.reconcile.durableMigration"] == migration_id
    assert (
        lifecycle.active_boot_image_migration(
            "dev-user",
            "omi-agent-user",
            "old-id",
            migration_id,
            firestore_client=client,
        )
        == journal
    )
    assert lifecycle.record_boot_image_state_disks(
        "dev-user",
        "omi-agent-user",
        "us-central1-a",
        "old-token",
        "worker",
        migration_id,
        {
            "stateDiskName": migration["stateDiskName"],
            "stateDiskId": "state-disk-id",
            "stateDiskReused": False,
            "sourceCloneDiskName": migration["sourceCloneDiskName"],
            "sourceCloneDiskId": "source-disk-id",
        },
        now=now,
    )
    assert client.transactions[-1].updates[-1][1]["stateDiskId"] == "state-disk-id"
    assert lifecycle.record_boot_image_candidate(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, "candidate-id", now=now
    )
    # A health-check retry sees the same candidate identity and does not need
    # to create a second VM or change its bearer token.
    assert lifecycle.record_boot_image_candidate(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, "candidate-id", now=now + 1
    )
    assert lifecycle.mark_boot_image_migration_candidate_deleted(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, "candidate-id", now=now + 2
    )
    assert client.transactions[-1].updates[-1][1]["state"] == "candidate_deleted"
    # A terminal cleanup resumes with the same deterministic candidate name and
    # token, but removes the stale provider ID before replacement is retried.
    journal = lifecycle.begin_boot_image_migration(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, migration, now=now + 3
    )
    assert journal and journal["state"] == "candidate_creating"
    assert client.transactions[-1].updates[-1][1]["candidateInstanceId"] is lifecycle.DELETE_FIELD

    # If deletion succeeded just before the worker could journal it, the next
    # worker first observes the candidate absent in GCE and may reset the
    # still-ready journal before it creates a replacement.
    missing_candidate_client = StrictFirestore(
        {
            ("users", "dev-user"): user,
            ("users", "dev-user", "agentVmMigrations", migration_id): {
                **migration,
                "state": "candidate_ready",
                "candidateInstanceId": "candidate-id",
            },
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: missing_candidate_client)
    assert lifecycle.recover_missing_boot_image_candidate(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, now=now + 4
    )
    assert missing_candidate_client.transactions[-1].updates[-1][1]["state"] == "candidate_creating"

    bad_client = StrictFirestore(
        {
            ("users", "dev-user"): {
                "agentVm": {**user["agentVm"], "instanceId": "repointed-id"},
            },
            ("users", "dev-user", "agentVmMigrations", migration_id): {
                **migration,
                "state": "candidate_ready",
                "candidateInstanceId": "candidate-id",
            },
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: bad_client)
    assert not lifecycle.cutover_boot_image_migration(
        "dev-user",
        "omi-agent-user",
        "us-central1-a",
        "old-token",
        "worker",
        migration_id,
        {"vmName": migration["candidateVmName"], "instanceId": "candidate-id"},
        now=now,
    )


def test_candidate_deleted_journal_supersession_requires_exact_owner_lease_and_new_release(monkeypatch):
    now = 100.0
    migration_id = "f" * 24
    replacement_release_id = "d" * 40
    vm = {
        "vmName": "omi-agent-user",
        "zone": "us-central1-a",
        "status": "stopped",
        "instanceId": "old-id",
        "authToken": "old-token",
        "reconcile": {
            "state": "claimed",
            "durableMigration": migration_id,
            "lease": {"owner": "worker", "expiresAt": 200.0},
        },
    }
    journal = {
        "migrationId": migration_id,
        "state": "candidate_deleted",
        "candidateDeletedAt": 90.0,
        "oldVmName": vm["vmName"],
        "oldZone": vm["zone"],
        "oldAuthToken": vm["authToken"],
        "oldInstanceId": vm["instanceId"],
        "targetRelease": RELEASE.release_id,
    }
    client = StrictFirestore(
        {
            ("users", "dev-user"): {"agentVm": vm},
            ("users", "dev-user", "agentVmMigrations", migration_id): journal,
        }
    )
    monkeypatch.setattr(migration_control, "get_firestore_client", lambda: client)

    assert migration_control.supersede_failed_boot_image_migration(
        "dev-user",
        vm["vmName"],
        vm["zone"],
        vm["authToken"],
        "worker",
        migration_id,
        replacement_release_id,
        now=now,
    )
    owner_update = client.transactions[-1].updates[-2][1]
    journal_update = client.transactions[-1].updates[-1][1]
    assert owner_update["agentVm.reconcile.durableMigration"] is lifecycle.DELETE_FIELD
    assert owner_update["agentVm.reconcile.lease"] is lifecycle.DELETE_FIELD
    assert owner_update["agentVm.reconcile.state"] == "ready"
    assert journal_update == {
        "state": "superseded",
        "supersededAt": now,
        "supersededByRelease": replacement_release_id,
        "updatedAt": now,
    }

    same_release_client = StrictFirestore(
        {
            ("users", "dev-user"): {"agentVm": vm},
            ("users", "dev-user", "agentVmMigrations", migration_id): journal,
        }
    )
    monkeypatch.setattr(migration_control, "get_firestore_client", lambda: same_release_client)
    assert not migration_control.supersede_failed_boot_image_migration(
        "dev-user",
        vm["vmName"],
        vm["zone"],
        vm["authToken"],
        "worker",
        migration_id,
        RELEASE.release_id,
        now=now,
    )
    assert same_release_client.transactions[-1].updates == []


def test_boot_image_state_journal_respects_account_deletion_fence(monkeypatch):
    migration_id = "4" * 24
    user = {
        "agentVm": {
            "vmName": "omi-agent-user",
            "zone": "us-central1-a",
            "status": "stopped",
            "authToken": "old-token",
            "reconcile": {"lease": {"owner": "worker", "expiresAt": 200.0}},
        }
    }
    migration = {
        "migrationId": migration_id,
        "oldVmName": "omi-agent-user",
        "oldZone": "us-central1-a",
        "oldAuthToken": "old-token",
        "oldInstanceId": "old-id",
        "candidateVmName": "candidate",
        "candidateAuthToken": "candidate-token",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "soakSeconds": 60,
        "stateDiskName": "state-disk",
        "stateDiskReused": True,
        "sourceCloneDiskName": "",
        "state": "candidate_creating",
    }
    client = StrictFirestore(
        {
            ("account_deletions", "dev-user"): {"wipe_status": "deleting"},
            ("users", "dev-user"): user,
            ("users", "dev-user", "agentVmMigrations", migration_id): migration,
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)

    assert not lifecycle.record_boot_image_state_disks(
        "dev-user",
        "omi-agent-user",
        "us-central1-a",
        "old-token",
        "worker",
        migration_id,
        {"stateDiskName": "state-disk", "stateDiskId": "state-id", "stateDiskReused": True, "sourceCloneDiskName": ""},
        now=100.0,
    )
    assert not client.transactions[-1].updates


def test_boot_image_migration_binds_a_legacy_pointer_to_the_provider_instance_id(monkeypatch):
    migration_id = "c" * 24
    client = StrictFirestore(
        {
            ("users", "dev-user"): {
                "agentVm": {
                    "vmName": "omi-agent-user",
                    "zone": "us-central1-a",
                    "status": "stopped",
                    "authToken": "old-token",
                    "reconcile": {"lease": {"owner": "worker", "expiresAt": 200.0}},
                }
            }
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)
    migration = {
        "migrationId": migration_id,
        "oldVmName": "omi-agent-user",
        "oldAuthToken": "old-token",
        "oldInstanceId": "old-id",
        "candidateVmName": "omi-agent-user-m-cccccccccccc",
        "candidateAuthToken": "candidate-token",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "soakSeconds": 60,
    }

    assert lifecycle.begin_boot_image_migration(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, migration, now=100
    )
    assert client.transactions[-1].updates[-1][1]["agentVm.instanceId"] == "old-id"


@pytest.mark.parametrize("demand_field", ["startRequested", "drainRequested"])
def test_boot_image_migration_cas_rejects_ready_legacy_status_with_new_demand(monkeypatch, demand_field):
    migration_id = "7" * 24
    client = StrictFirestore(
        {
            ("users", "dev-user"): {
                "agentVm": {
                    "vmName": "omi-agent-user",
                    "zone": "us-central1-a",
                    "status": "ready",
                    "instanceId": "old-id",
                    "authToken": "old-token",
                    "reconcile": {
                        "lease": {"owner": "worker", "expiresAt": 200.0},
                        demand_field: True,
                    },
                }
            }
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)

    assert (
        lifecycle.begin_boot_image_migration(
            "dev-user",
            "omi-agent-user",
            "us-central1-a",
            "old-token",
            "worker",
            migration_id,
            {
                "migrationId": migration_id,
                "oldVmName": "omi-agent-user",
                "oldAuthToken": "old-token",
                "oldInstanceId": "old-id",
                "candidateVmName": "candidate",
                "candidateAuthToken": "candidate-token",
                "targetRelease": RELEASE.release_id,
                "soakSeconds": 60,
            },
            now=100.0,
        )
        is None
    )
    assert not client.transactions[-1].updates


def test_boot_image_migration_recovery_drain_requires_exact_durable_marker(monkeypatch):
    migration_id = "8" * 24
    migration = {
        "migrationId": migration_id,
        "state": "candidate_creating",
        "oldVmName": "omi-agent-user",
        "oldAuthToken": "old-token",
        "oldInstanceId": "old-id",
        "candidateVmName": "candidate",
        "candidateAuthToken": "candidate-token",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "soakSeconds": 60,
    }
    client = StrictFirestore(
        {
            ("users", "dev-user"): {
                "agentVm": {
                    "vmName": "omi-agent-user",
                    "zone": "us-central1-a",
                    "status": "ready",
                    "instanceId": "old-id",
                    "authToken": "old-token",
                    "reconcile": {
                        "lease": {"owner": "worker", "expiresAt": 200.0},
                        "durableMigration": "9" * 24,
                        "drainRequested": True,
                    },
                }
            },
            ("users", "dev-user", "agentVmMigrations", migration_id): migration,
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)

    assert (
        lifecycle.begin_boot_image_migration(
            "dev-user",
            "omi-agent-user",
            "us-central1-a",
            "old-token",
            "worker",
            migration_id,
            migration,
            now=100.0,
        )
        is None
    )
    assert not client.transactions[-1].updates


def test_boot_image_migration_recovery_atomically_replaces_crash_retained_drain(monkeypatch):
    migration_id = "8" * 24
    migration = {
        "migrationId": migration_id,
        "state": "candidate_creating",
        "oldVmName": "omi-agent-user",
        "oldAuthToken": "old-token",
        "oldInstanceId": "old-id",
        "candidateVmName": "candidate",
        "candidateAuthToken": "candidate-token",
        "targetRelease": RELEASE.release_id,
        "targetBootImage": RELEASE.boot_image,
        "soakSeconds": 60,
    }
    client = StrictFirestore(
        {
            ("users", "dev-user"): {
                "agentVm": {
                    "vmName": "omi-agent-user",
                    "zone": "us-central1-a",
                    "status": "ready",
                    "instanceId": "old-id",
                    "authToken": "old-token",
                    "reconcile": {
                        "state": "claimed",
                        "lease": {"owner": "worker", "expiresAt": 200.0},
                        "durableMigration": migration_id,
                        "drainRequested": True,
                        "drainRequestedAt": 90.0,
                    },
                }
            },
            ("users", "dev-user", "agentVmMigrations", migration_id): migration,
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)

    assert (
        lifecycle.begin_boot_image_migration(
            "dev-user",
            "omi-agent-user",
            "us-central1-a",
            "old-token",
            "worker",
            migration_id,
            migration,
            now=100.0,
        )
        == migration
    )
    recovery_update = client.transactions[-1].updates[-1][1]
    assert recovery_update["agentVm.reconcile.state"] == "migration_claimed"
    assert recovery_update["agentVm.reconcile.drainRequested"] is lifecycle.DELETE_FIELD
    assert recovery_update["agentVm.reconcile.drainRequestedAt"] is lifecycle.DELETE_FIELD


def test_boot_image_migration_completion_requires_candidate_pointer_and_lease(monkeypatch):
    now = 200.0
    migration_id = "b" * 24
    candidate_name = "omi-agent-user-m-bbbbbbbbbbbb"
    migration = {
        "migrationId": migration_id,
        "oldVmName": "omi-agent-user",
        "oldInstanceId": "old-id",
        "candidateVmName": candidate_name,
        "candidateInstanceId": "candidate-id",
        "state": "retiring",
    }
    client = StrictFirestore(
        {
            ("users", "dev-user"): {
                "agentVm": {
                    "vmName": candidate_name,
                    "zone": "us-central1-a",
                    "instanceId": "candidate-id",
                    "authToken": "candidate-token",
                    "reconcile": {
                        "migration": dict(migration),
                        "lease": {"owner": "worker", "expiresAt": 300.0},
                    },
                }
            },
            ("users", "dev-user", "agentVmMigrations", migration_id): migration,
        }
    )
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)

    assert lifecycle.complete_boot_image_migration(
        "dev-user", candidate_name, "us-central1-a", "candidate-token", "worker", migration_id, "candidate-id", now=now
    )
    updates = client.transactions[-1].updates
    assert updates[-2][1]["agentVm.reconcile.migration"] is lifecycle.DELETE_FIELD
    assert updates[-2][1]["agentVm.reconcile.durableMigration"] is lifecycle.DELETE_FIELD
    assert updates[-2][1]["agentVm.reconcile.lease"] is lifecycle.DELETE_FIELD
    assert updates[-1][1]["state"] == "completed"


def test_boot_image_migration_retirement_claim_uses_the_journaled_deadline(monkeypatch):
    migration_id = "e" * 24
    candidate_name = "omi-agent-user-m-eeeeeeeeeeee"
    migration = {
        "migrationId": migration_id,
        "oldVmName": "omi-agent-user",
        "oldInstanceId": "old-id",
        "candidateVmName": candidate_name,
        "candidateInstanceId": "candidate-id",
        "state": "cutover",
        "retireAfter": 300.0,
    }
    rows = {
        ("users", "dev-user"): {
            "agentVm": {
                "vmName": candidate_name,
                "zone": "us-central1-a",
                "instanceId": "candidate-id",
                "authToken": "candidate-token",
                "reconcile": {"migration": dict(migration), "lease": {"owner": "worker", "expiresAt": 400.0}},
            }
        },
        ("users", "dev-user", "agentVmMigrations", migration_id): migration,
    }
    client = StrictFirestore(rows)
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)

    soaking = lifecycle.claim_boot_image_migration_retirement(
        "dev-user", candidate_name, "us-central1-a", "candidate-token", "worker", migration_id, "candidate-id", now=299
    )
    assert soaking and soaking["state"] == "soaking"
    assert not client.transactions[-1].updates
    claimed = lifecycle.claim_boot_image_migration_retirement(
        "dev-user", candidate_name, "us-central1-a", "candidate-token", "worker", migration_id, "candidate-id", now=300
    )
    assert claimed and claimed["state"] == "retiring"
    assert client.transactions[-1].updates[-1][1]["state"] == "retiring"


def test_mutable_boot_image_manifest_fails_closed_without_disk_lookup():
    class NoRequestApi(FakeApi):
        async def request(self, _method: str, _url: str) -> Any:
            raise AssertionError("mutable desired image must be rejected before disk lookup")

    mutable_release = replace(RELEASE, boot_image="projects/project/global/images/family/omi-agent")

    assert asyncio.run(reconciler._boot_image_drift(NoRequestApi("project", "zone"), {}, mutable_release)) == (
        "boot_image_manifest_not_immutable",
        "unknown",
    )


class FakeSnapshot:
    exists = False

    def to_dict(self) -> dict[str, Any]:
        return {}


class FakeRef:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def get(self) -> FakeSnapshot:
        snapshot = FakeSnapshot()
        snapshot.exists = bool(self.data)
        snapshot.to_dict = lambda: dict(self.data)  # type: ignore[method-assign]
        return snapshot

    def set(self, fields: dict[str, Any], merge: bool = False) -> None:
        if merge:
            self.data.update(fields)
        else:
            self.data = dict(fields)


class FakeCollection:
    def __init__(self) -> None:
        self.ref = FakeRef()

    def document(self, _name: str) -> FakeRef:
        return self.ref


class FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def collection(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


def test_empty_rollout_cohort_cannot_advance_without_observed_success(monkeypatch):
    client = FakeClient()
    client.collection("agent_vm_rollouts").document("development").set(
        {"releaseId": RELEASE.release_id, "phase": "sentinel", "successfulRuns": 2}
    )
    monkeypatch.setattr(reconciler, "get_firestore_client", lambda: client)

    reconciler._advance_rollout("development", RELEASE.release_id, "sentinel", [], 0)

    state = client.collection("agent_vm_rollouts").document("development").data
    assert state["phase"] == "sentinel"
    assert state["successfulRuns"] == 0


def test_small_fleet_selects_one_deterministic_sentinel(monkeypatch):
    owners = [("uid-b", {"vmName": "b"}), ("uid-a", {"vmName": "a"})]
    monkeypatch.setattr(reconciler, "rollout_selected", lambda *_args: False)

    first = reconciler._select_rollout_owners(owners, RELEASE.release_id, 1)
    second = reconciler._select_rollout_owners(list(reversed(owners)), RELEASE.release_id, 1)

    assert len(first) == 1
    assert first == second


def test_start_requests_bypass_the_release_cohort_without_displacing_it(monkeypatch):
    owners = [
        ("cohort", {"vmName": "cohort"}),
        ("demand", {"vmName": "demand", "reconcile": {"startRequested": True}}),
    ]
    monkeypatch.setattr(reconciler, "rollout_selected", lambda uid, *_args: uid == "cohort")

    assert reconciler._select_reconcile_owners(owners, RELEASE.release_id, 1) == owners


def test_terminal_missing_records_bypass_the_release_cohort_without_displacing_it(monkeypatch):
    owners = [
        ("cohort", {"vmName": "cohort"}),
        ("missing", {"vmName": "missing", "reconcile": {"state": "missing", "missingSince": 1.0}}),
    ]
    monkeypatch.setattr(reconciler, "rollout_selected", lambda uid, *_args: uid == "cohort")

    assert reconciler._select_reconcile_owners(owners, RELEASE.release_id, 1) == owners


def test_active_migrations_bypass_the_release_cohort_until_retired(monkeypatch):
    owners = [
        ("cohort", {"vmName": "cohort"}),
        (
            "migration",
            {
                "vmName": "candidate",
                "status": "ready",
                "reconcile": {"state": "migration_soaking", "migration": {"migrationId": "a" * 24}},
            },
        ),
    ]
    monkeypatch.setattr(reconciler, "rollout_selected", lambda uid, *_args: uid == "cohort")

    assert reconciler._select_reconcile_owners(owners, RELEASE.release_id, 1) == owners


def test_terminal_reconcile_write_preserves_a_newer_start_request():
    terminal_fields = lifecycle.clear_vm_reconcile_lease_fields()

    preserved = lifecycle._reconcile_update_fields(terminal_fields, {"startRequestedAt": 20.0}, 10.0)
    consumed = lifecycle._reconcile_update_fields(terminal_fields, {"startRequestedAt": 10.0}, 10.0)

    assert "startRequested" not in preserved
    assert "startRequestedAt" not in preserved
    assert consumed["startRequested"] is lifecycle.DELETE_FIELD
    assert consumed["startRequestedAt"] is lifecycle.DELETE_FIELD


def test_active_lifecycle_lease_blocks_new_session_admission():
    assert lifecycle.reconcile_requested({"reconcile": {"lease": {"expiresAt": 101}}}, now=100)
    assert lifecycle.reconcile_requested({"reconcile": {"state": "claimed"}}, now=100)
    assert lifecycle.reconcile_requested({"reconcile": {"state": "migration_claimed"}}, now=100)
    assert lifecycle.reconcile_requested({"reconcile": {"state": "missing"}}, now=100)
    assert lifecycle.reconcile_requested({"reconcile": {"state": "migration_soaking"}}, now=100)
    assert not lifecycle.reconcile_requested({"reconcile": {"lease": {"expiresAt": 100}}}, now=100)


def test_recognized_rollout_phase_honors_manifest_and_environment_overrides(monkeypatch):
    assert reconciler._rollout_spec(
        {"rollout": {"phase": "sentinel", "targetPercent": 7, "maxConcurrency": 3}}, "sentinel"
    ) == (7, 3)

    monkeypatch.setenv("AGENT_VM_ROLLOUT_TARGET_PERCENT", "9")
    monkeypatch.setenv("AGENT_VM_RECONCILER_MAX_CONCURRENCY", "4")
    assert reconciler._rollout_spec(
        {"rollout": {"phase": "sentinel", "targetPercent": 7, "maxConcurrency": 3}}, "sentinel"
    ) == (9, 4)


def test_stored_invalid_rollout_phase_fails_closed(monkeypatch):
    client = FakeClient()
    client.collection("agent_vm_rollouts").document("development").set(
        {"releaseId": RELEASE.release_id, "phase": "remaindr", "successfulRuns": 0}
    )
    monkeypatch.setattr(reconciler, "get_firestore_client", lambda: client)

    with pytest.raises(ValueError, match="stored Agent VM rollout phase is invalid"):
        reconciler._rollout_phase("development", RELEASE.release_id, RELEASE.to_mapping())


def test_empty_reconciler_run_does_not_report_normal_lease_shutdown_as_loss(monkeypatch):
    released: list[str] = []
    monkeypatch.setenv("GCE_PROJECT_ID", "project")
    monkeypatch.setattr(reconciler, "_init_firebase", lambda: None)
    monkeypatch.setattr(reconciler, "load_active_release", lambda: (RELEASE, RELEASE.to_mapping()))
    monkeypatch.setattr(reconciler, "claim_reconciler_run_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "renew_reconciler_run_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "release_reconciler_run_lease", lambda _env, owner: released.append(owner) or True)
    monkeypatch.setattr(reconciler, "_rollout_phase", lambda *_args, **_kwargs: "remainder")
    monkeypatch.setattr(reconciler, "_rollout_spec", lambda *_args: (100, 1))
    monkeypatch.setattr(reconciler, "_owners", lambda: [])
    monkeypatch.setattr(reconciler, "_advance_rollout", lambda *_args: None)

    assert asyncio.run(reconciler.run_reconciler()) == []
    assert released


def test_lease_heartbeat_exception_marks_lease_lost(monkeypatch):
    """A transient exception in renew_reconciler_run_lease must set lease_lost so
    the run stops before the TTL lapses, rather than continuing to mutate VMs."""
    monkeypatch.setenv("GCE_PROJECT_ID", "project")
    monkeypatch.setattr(reconciler, "LEASE_HEARTBEAT_SECONDS", 0)
    monkeypatch.setattr(reconciler, "_init_firebase", lambda: None)
    monkeypatch.setattr(reconciler, "load_active_release", lambda: (RELEASE, RELEASE.to_mapping()))
    monkeypatch.setattr(reconciler, "claim_reconciler_run_lease", lambda *_args: True)

    call_count = 0

    def _flaky_renew(*_args):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("firestore heartbeat error")

    monkeypatch.setattr(reconciler, "renew_reconciler_run_lease", _flaky_renew)
    monkeypatch.setattr(reconciler, "release_reconciler_run_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "_rollout_phase", lambda *_args, **_kwargs: "remainder")
    monkeypatch.setattr(reconciler, "_rollout_spec", lambda *_args: (100, 1))

    owner_block = asyncio.Event()

    async def _blocking_reconcile_one(*_args, **_kwargs):
        """Keep the gather alive long enough for at least one heartbeat cycle."""
        try:
            await asyncio.wait_for(owner_block.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        return reconciler.ReconcileResult(state="noop", uid="user")

    monkeypatch.setattr(reconciler, "reconcile_one", _blocking_reconcile_one)
    monkeypatch.setattr(
        reconciler,
        "_owners",
        lambda: [("user", {"vmName": "omi-agent-user", "authToken": "token"})],
    )
    monkeypatch.setattr(reconciler, "_advance_rollout", lambda *_args: None)

    with pytest.raises(reconciler.AgentVmLeaseLost, match="lease lost"):
        try:
            asyncio.run(reconciler.run_reconciler())
        finally:
            owner_block.set()


def test_new_release_starts_quarantined_vm_with_a_fresh_retry_budget(monkeypatch):
    class FailingApi:
        def __init__(self, _project: str, _zone: str) -> None:
            pass

        async def get_instance(self, _vm_name: str) -> dict[str, Any] | None:
            raise RuntimeError("provider unavailable")

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", FailingApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **kwargs: calls.append((args, kwargs)) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {
                "vmName": "omi-agent-user",
                "authToken": "token",
                "reconcile": {"releaseId": "d" * 40, "retryCount": 3},
            },
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "retry"
    assert calls[-1][0][4]["retryCount"] == 1


def test_demanded_retry_retains_start_request_until_terminal_quarantine(monkeypatch):
    class FailingApi:
        def __init__(self, _project: str, _zone: str) -> None:
            pass

        async def get_instance(self, _vm_name: str) -> dict[str, Any] | None:
            raise RuntimeError("provider unavailable")

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", FailingApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **kwargs: calls.append((args, kwargs)) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {
                "vmName": "omi-agent-user",
                "authToken": "token",
                "reconcile": {"releaseId": RELEASE.release_id, "startRequested": True, "startRequestedAt": 10.0},
            },
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "retry"
    fields, kwargs = calls[-1][0][4], calls[-1][1]
    assert "startRequested" not in fields
    assert kwargs["consume_start_request_at"] is None


def test_same_release_quarantine_remains_visible_without_reclaim(monkeypatch):
    monkeypatch.setattr(
        reconciler,
        "claim_vm_lease",
        lambda *_args: pytest.fail("same-release quarantine must not be hidden behind a rejected claim"),
    )

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {
                "vmName": "omi-agent-user",
                "authToken": "token",
                "reconcile": {
                    "releaseId": RELEASE.release_id,
                    "state": "quarantined",
                    "lastError": "RuntimeError",
                },
            },
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result == reconciler.ReconcileResult("user", "quarantined", "RuntimeError")


def test_firestore_claim_and_update_are_offloaded_from_event_loop(monkeypatch):
    loop_thread = threading.get_ident()
    call_threads: list[int] = []

    class MissingApi:
        def __init__(self, _project: str, _zone: str) -> None:
            pass

        async def get_instance(self, _vm_name: str) -> None:
            return None

    def claim(*_args: Any) -> bool:
        call_threads.append(threading.get_ident())
        return True

    def update(*_args: Any, **_kwargs: Any) -> bool:
        call_threads.append(threading.get_ident())
        return True

    monkeypatch.setattr(reconciler, "GceAgentVmClient", MissingApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", claim)
    monkeypatch.setattr(reconciler, "update_vm_reconcile", update)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {"vmName": "omi-agent-user", "authToken": "token"},
            RELEASE,
            owner="worker",
            project="project",
        )
    )

    assert result.state == "cleanup_pending"
    assert len(call_threads) == 2
    assert all(thread_id != loop_thread for thread_id in call_threads)


def test_missing_vm_is_cleaned_only_after_grace_without_sessions_or_demand(monkeypatch):
    now = 500.0
    deleted: list[tuple[Any, ...]] = []

    class MissingApi:
        def __init__(self, _project: str, _zone: str) -> None:
            pass

        async def get_instance(self, _vm_name: str) -> None:
            return None

    monkeypatch.setattr(reconciler, "GceAgentVmClient", MissingApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)
    monkeypatch.setattr(reconciler.time, "time", lambda: now)
    monkeypatch.setattr(reconciler, "clear_missing_vm_if_current", lambda *args: deleted.append(args) or True)
    monkeypatch.setattr(
        reconciler, "update_vm_reconcile", lambda *_args, **_kwargs: pytest.fail("cleaned records stay deleted")
    )

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {
                "vmName": "omi-agent-user",
                "zone": "us-central1-a",
                "status": "ready",
                "authToken": "token",
                "reconcile": {"state": "missing", "missingSince": now - 120},
            },
            RELEASE,
            owner="worker",
            project="project",
            missing_cleanup_grace_seconds=60,
        )
    )

    assert result.state == "cleaned"
    assert deleted == [("user", "omi-agent-user", "us-central1-a", "token", "worker", now - 120)]


def test_missing_post_cutover_candidate_preserves_migration_and_retries(monkeypatch):
    class MissingApi:
        def __init__(self, _project: str, _zone: str) -> None:
            pass

        async def get_instance(self, _vm_name: str) -> None:
            return None

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", MissingApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(
        reconciler,
        "clear_missing_vm_if_current",
        lambda *_args: pytest.fail("an active migration record must never be cleared as terminal missing"),
    )
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {
                "vmName": "candidate",
                "zone": "us-central1-a",
                "status": "ready",
                "instanceId": "candidate-id",
                "authToken": "token",
                "reconcile": {
                    "state": "migration_soaking",
                    "releaseId": RELEASE.release_id,
                    "migration": {"migrationId": "a" * 24, "candidateInstanceId": "candidate-id"},
                },
            },
            RELEASE,
            owner="worker",
            project="project",
            missing_cleanup_grace_seconds=0,
        )
    )

    assert result.state == "retry"
    assert updates[-1]["state"] == "retry"
    assert updates[-1]["drainRequested"] is True


def test_missing_404_consumes_the_observed_start_request_before_cleanup_grace(monkeypatch):
    class MissingApi:
        def __init__(self, _project: str, _zone: str) -> None:
            pass

        async def get_instance(self, _vm_name: str) -> None:
            return None

    updates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", MissingApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "clear_missing_vm_if_current", lambda *_args: pytest.fail("grace has not elapsed"))
    monkeypatch.setattr(
        reconciler, "update_vm_reconcile", lambda *args, **kwargs: updates.append((args[4], kwargs)) or True
    )
    monkeypatch.setattr(reconciler.time, "time", lambda: 500.0)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {
                "vmName": "omi-agent-user",
                "status": "ready",
                "authToken": "token",
                "reconcile": {
                    "state": "missing",
                    "missingSince": 1.0,
                    "startRequested": True,
                    "startRequestedAt": 450.0,
                },
            },
            RELEASE,
            owner="worker",
            project="project",
            missing_cleanup_grace_seconds=60,
        )
    )

    assert result.state == "cleanup_pending"
    fields, kwargs = updates[-1]
    assert fields["startRequested"] is lifecycle.DELETE_FIELD
    assert fields["startRequestedAt"] is lifecycle.DELETE_FIELD
    assert kwargs["consume_start_request_at"] == 450.0


def test_terminal_cleanup_refuses_an_active_missing_vm(monkeypatch):
    class MissingApi:
        def __init__(self, _project: str, _zone: str) -> None:
            pass

        async def get_instance(self, _vm_name: str) -> None:
            return None

    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(reconciler, "GceAgentVmClient", MissingApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 1)
    monkeypatch.setattr(
        reconciler, "clear_missing_vm_if_current", lambda *_args: pytest.fail("terminal cleanup must be fenced")
    )
    monkeypatch.setattr(reconciler, "update_vm_reconcile", lambda *args, **_kwargs: updates.append(args[4]) or True)
    monkeypatch.setattr(reconciler.time, "time", lambda: 500.0)

    result = asyncio.run(
        reconciler.reconcile_one(
            "user",
            {
                "vmName": "omi-agent-user",
                "status": "ready",
                "authToken": "token",
                "reconcile": {"state": "missing", "missingSince": 1.0},
            },
            RELEASE,
            owner="worker",
            project="project",
            missing_cleanup_grace_seconds=60,
        )
    )

    assert result.state == "missing"
    assert "1 active session" in result.detail
    assert updates[-1]["missingSince"] == 1.0


def test_missing_cleanup_lifecycle_compare_and_swap_requires_exact_owner_generation(monkeypatch):
    def database(
        *, start_requested: bool = False, zone: str | None = "us-central1-a", status: str = "ready"
    ) -> StrictFirestore:
        return StrictFirestore(
            {
                (
                    "users",
                    "user",
                ): {
                    "agentVm": {
                        "vmName": "omi-agent-user",
                        "zone": zone,
                        "status": status,
                        "authToken": "token",
                        "reconcile": {
                            "state": "claimed",
                            "missingSince": 100.0,
                            "startRequested": start_requested,
                            "lease": {"owner": "worker", "expiresAt": 200.0},
                        },
                    }
                }
            }
        )

    client = database()
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: client)
    assert lifecycle.clear_missing_vm_if_current(
        "user", "omi-agent-user", "us-central1-a", "token", "worker", 100.0, now=150
    )
    assert client.transactions[-1].updates[-1][1] == {"agentVm": lifecycle.DELETE_FIELD}

    legacy_zone_client = database(zone=None)
    monkeypatch.setattr(lifecycle, "get_firestore_client", lambda: legacy_zone_client)
    assert lifecycle.clear_missing_vm_if_current(
        "user", "omi-agent-user", "us-central1-a", "token", "worker", 100.0, now=150
    )

    for bad_client, zone, missing_since in [
        (database(start_requested=True), "us-central1-a", 100.0),
        (database(status="provisioning"), "us-central1-a", 100.0),
        (database(), "wrong-zone", 100.0),
        (database(), "us-central1-a", 99.0),
    ]:
        monkeypatch.setattr(lifecycle, "get_firestore_client", lambda client=bad_client: client)
        assert not lifecycle.clear_missing_vm_if_current(
            "user", "omi-agent-user", zone, "token", "worker", missing_since, now=150
        )
        assert not bad_client.transactions[-1].updates


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, reconciler.DEFAULT_MISSING_CLEANUP_GRACE_SECONDS), ("60", 60)],
)
def test_missing_cleanup_grace_uses_a_safe_default_or_valid_override(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("AGENT_VM_MISSING_CLEANUP_GRACE_SECONDS", raising=False)
    else:
        monkeypatch.setenv("AGENT_VM_MISSING_CLEANUP_GRACE_SECONDS", value)
    assert reconciler._missing_cleanup_grace_seconds() == expected


@pytest.mark.parametrize("value", ["not-a-number", "59"])
def test_missing_cleanup_grace_rejects_unsafe_configuration(monkeypatch, value):
    monkeypatch.setenv("AGENT_VM_MISSING_CLEANUP_GRACE_SECONDS", value)
    with pytest.raises(ValueError, match="AGENT_VM_MISSING_CLEANUP_GRACE_SECONDS"):
        reconciler._missing_cleanup_grace_seconds()


@pytest.mark.parametrize("state", ["quarantined", "missing", "stale", "recreate_required"])
def test_main_reports_nonconverged_states_as_failed_job(monkeypatch, state):
    async def run_reconciler(*, dry_run: bool = False) -> list[reconciler.ReconcileResult]:
        assert not dry_run
        return [reconciler.ReconcileResult("uid", state)]

    monkeypatch.setattr(reconciler, "run_reconciler", run_reconciler)

    assert reconciler.main([]) == 1


@pytest.mark.parametrize("state", ["cleanup_pending", "cleaned"])
def test_main_accepts_expected_terminal_cleanup_states(monkeypatch, state):
    async def run_reconciler(*, dry_run: bool = False) -> list[reconciler.ReconcileResult]:
        assert not dry_run
        return [reconciler.ReconcileResult("uid", state)]

    monkeypatch.setattr(reconciler, "run_reconciler", run_reconciler)

    assert reconciler.main([]) == 0


class OwnerSnapshot:
    def __init__(self, uid: str, data: dict[str, Any]) -> None:
        self.id = uid
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        return self.data


class OwnerQuery:
    def __init__(self, snapshots: list[OwnerSnapshot], *, query_error: bool = False) -> None:
        self.snapshots = snapshots
        self.query_error = query_error
        self.filter: Any = None
        self.limit_value = 0

    def where(self, *, filter: Any) -> "OwnerQuery":
        if self.query_error:
            raise RuntimeError("legacy emulator")
        self.filter = filter
        return self

    def limit(self, value: int) -> "OwnerQuery":
        self.limit_value = value
        return self

    def stream(self) -> list[OwnerSnapshot]:
        return self.snapshots[: self.limit_value]


class OwnerClient:
    def __init__(self, query: OwnerQuery) -> None:
        self.query = query

    def collection(self, name: str) -> OwnerQuery:
        assert name == "users"
        return self.query


def test_owner_discovery_uses_targeted_existing_user_field(monkeypatch):
    query = OwnerQuery(
        [
            OwnerSnapshot("owner", {"agentVm": {"vmName": "omi-agent-owner", "authToken": "token"}}),
            OwnerSnapshot("invalid", {"agentVm": {"vmName": "missing-token"}}),
        ]
    )
    monkeypatch.setattr(reconciler, "get_firestore_client", lambda: OwnerClient(query))

    assert reconciler._owners() == [("owner", {"vmName": "omi-agent-owner", "authToken": "token"})]
    assert query.filter.field_path == "agentVm.vmName"
    assert query.limit_value == reconciler.OWNER_DISCOVERY_LIMIT + 1


def test_owner_discovery_legacy_fallback_is_bounded_and_fails_closed(monkeypatch):
    query = OwnerQuery(
        [OwnerSnapshot(str(index), {}) for index in range(3)],
        query_error=True,
    )
    monkeypatch.setenv("AGENT_VM_OWNER_FALLBACK_SCAN_LIMIT", "2")
    monkeypatch.setattr(reconciler, "get_firestore_client", lambda: OwnerClient(query))

    with pytest.raises(RuntimeError, match="compatibility scan exhausted"):
        reconciler._owners()


def test_owner_discovery_legacy_fallback_supports_existing_small_fleets(monkeypatch):
    query = OwnerQuery(
        [
            OwnerSnapshot("non-owner", {}),
            OwnerSnapshot("owner", {"agentVm": {"vmName": "omi-agent-owner", "authToken": "token"}}),
        ],
        query_error=True,
    )
    monkeypatch.setenv("AGENT_VM_OWNER_FALLBACK_SCAN_LIMIT", "3")
    monkeypatch.setattr(reconciler, "get_firestore_client", lambda: OwnerClient(query))

    assert reconciler._owners() == [("owner", {"vmName": "omi-agent-owner", "authToken": "token"})]


def test_owner_discovery_selects_a_durable_migration_without_manifest_opt_in(monkeypatch):
    users = OwnerQuery(
        [
            OwnerSnapshot("cohort", {"agentVm": {"vmName": "cohort", "authToken": "token"}}),
            OwnerSnapshot(
                "journal-owner",
                {
                    "agentVm": {
                        "vmName": "omi-agent-journal-owner",
                        "authToken": "token",
                        "reconcile": {"durableMigration": "6" * 24},
                    }
                },
            ),
        ]
    )

    class DurableClient:
        def collection(self, name: str) -> OwnerQuery:
            assert name == "users"
            return users

    monkeypatch.setattr(reconciler, "get_firestore_client", lambda: DurableClient())

    owners = reconciler._owners()

    assert owners[-1] == (
        "journal-owner",
        {
            "vmName": "omi-agent-journal-owner",
            "authToken": "token",
            "reconcile": {"durableMigration": "6" * 24},
        },
    )
    assert reconciler._select_reconcile_owners(owners, RELEASE.release_id, 0)[-1] == owners[-1]
