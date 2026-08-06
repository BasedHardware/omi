from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from typing import Any

import pytest

import jobs.agent_vm_reconciler as reconciler
import services.agent_vm_lifecycle as lifecycle
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

        async def wait_for_runtime(self, private_ip: str, auth_token: str, release: AgentVmRelease) -> None:
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


def test_boot_image_migration_replaces_only_an_already_stopped_allowlisted_vm(monkeypatch):
    class MigrationApi:
        creates: list[tuple[Any, ...]] = []
        labels: list[str] = []
        waits: list[tuple[str, str]] = []
        candidate: dict[str, Any] | None = None

        def __init__(self, _project: str, _zone: str) -> None:
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

        async def create_replacement(self, *args: Any) -> None:
            type(self).creates.append(args)
            type(self).candidate = {
                "id": "candidate-id",
                "labels": {"omi-agent-migration": args[-1], "omi-agent-predecessor": "old-id"},
                "networkInterfaces": [{"networkIP": "10.128.0.9", "accessConfigs": [{"natIP": "34.1.2.3"}]}],
                "serviceAccounts": [{"email": RELEASE.service_account}],
                "disks": [{"boot": True, "source": "projects/project/zones/us-central1-a/disks/candidate-disk"}],
            }

        @staticmethod
        def private_instance_ip(_instance: dict[str, Any]) -> str:
            return "10.128.0.9"

        @staticmethod
        def instance_ip(_instance: dict[str, Any]) -> str:
            return "34.1.2.3"

        async def wait_for_runtime(self, ip: str, token: str, _release: AgentVmRelease) -> None:
            type(self).waits.append((ip, token))

    cutovers: list[dict[str, Any]] = []
    MigrationApi.creates = []
    MigrationApi.labels = []
    MigrationApi.waits = []
    MigrationApi.candidate = None
    monkeypatch.setattr(reconciler, "GceAgentVmClient", MigrationApi)
    monkeypatch.setattr(reconciler, "claim_vm_lease", lambda *_args: True)
    monkeypatch.setattr(
        reconciler, "begin_boot_image_migration", lambda *args: {"candidateAuthToken": args[-1]["candidateAuthToken"]}
    )
    monkeypatch.setattr(reconciler, "recover_missing_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(reconciler, "record_boot_image_candidate", lambda *_args: True)
    monkeypatch.setattr(reconciler, "cutover_boot_image_migration", lambda *args: cutovers.append(args[-1]) or True)
    monkeypatch.setattr(reconciler, "active_session_count", lambda *_args: 0)

    result = asyncio.run(
        reconciler.reconcile_one(
            "dev-user",
            {"vmName": "omi-agent-user", "authToken": "old-token", "status": "stopped"},
            RELEASE,
            owner="worker",
            project="project",
            boot_image_migration=reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
        )
    )

    assert result.state == "migrated"
    assert MigrationApi.labels and MigrationApi.creates and MigrationApi.waits
    assert cutovers[-1]["vmName"].startswith("omi-agent-user-m-")
    assert cutovers[-1]["authToken"] != "old-token"


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


def test_boot_image_migration_quarantine_deletes_a_failed_candidate_with_its_identity_fence(monkeypatch):
    class DriftApi(FakeApi):
        deleted: list[tuple[str, str, str]] = []

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

    async def failed_candidate(*_args: Any, **kwargs: Any) -> reconciler.ReconcileResult:
        kwargs["cleanup_context"].update({"vmName": "candidate", "instanceId": "candidate-id", "migrationId": "d" * 24})
        raise RuntimeError("candidate health failed")

    updates: list[dict[str, Any]] = []
    DriftApi.deleted = []
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
                "reconcile": {"retryCount": 2, "releaseId": RELEASE.release_id},
            },
            RELEASE,
            owner="worker",
            project="project",
            boot_image_migration=reconciler.BootImageMigrationPlan(frozenset({"dev-user"}), 1, 60),
        )
    )

    assert result.state == "quarantined"
    assert DriftApi.deleted == [("candidate", "candidate-id", "d" * 24)]
    assert updates[-1]["state"] == "quarantined"


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
    }

    journal = lifecycle.begin_boot_image_migration(
        "dev-user", "omi-agent-user", "us-central1-a", "old-token", "worker", migration_id, migration, now=now
    )
    assert journal and journal["candidateAuthToken"] == "candidate-token"
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
    assert lifecycle.reconcile_requested({"reconcile": {"state": "missing"}}, now=100)
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
