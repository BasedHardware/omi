from __future__ import annotations

import asyncio
from typing import Any

import jobs.agent_vm_reconciler as reconciler
from services.agent_vm_lifecycle import AgentVmRelease

RELEASE = AgentVmRelease.from_mapping(
    {
        "schemaVersion": 1,
        "environment": "development",
        "sourceSha": "a" * 40,
        "imageDigest": "gcr.io/project/agent-vm@sha256:" + "b" * 64,
        "startupUri": "gs://bucket/agent-vm/releases/a/startup.sh",
        "startupSha256": "c" * 64,
        "bootImage": "projects/project/global/images/family/omi-agent",
        "serviceAccount": "omi-agent-vm-bootstrap@project.iam.gserviceaccount.com",
    }
)


class FakeApi:
    instances: dict[str, dict[str, Any]] = {
        "omi-agent-user": {"status": "STOPPED", "metadata": {}, "serviceAccounts": []}
    }
    starts = 0

    def __init__(self, _project: str, _zone: str) -> None:
        pass

    async def get_instance(self, vm_name: str) -> dict[str, Any] | None:
        return self.instances.get(vm_name)

    def instance_ip(self, _instance: dict[str, Any]) -> str | None:
        return None

    async def start(self, _vm_name: str) -> None:
        self.starts += 1


def test_reconcile_preserves_a_healthy_stopped_vm(monkeypatch):
    updates: list[dict[str, Any]] = []
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


def test_empty_rollout_cohort_can_advance_without_fabricating_success(monkeypatch):
    client = FakeClient()
    client.collection("agent_vm_rollouts").document("development").set(
        {"releaseId": RELEASE.release_id, "phase": "sentinel", "successfulRuns": 2}
    )
    monkeypatch.setattr(reconciler, "get_firestore_client", lambda: client)

    reconciler._advance_rollout("development", RELEASE.release_id, "sentinel", [], 0)

    state = client.collection("agent_vm_rollouts").document("development").data
    assert state["phase"] == "canary"
    assert state["successfulRuns"] == 0


def test_empty_reconciler_run_does_not_report_normal_lease_shutdown_as_loss(monkeypatch):
    released: list[str] = []
    monkeypatch.setenv("GCE_PROJECT_ID", "project")
    monkeypatch.setattr(reconciler, "_init_firebase", lambda: None)
    monkeypatch.setattr(reconciler, "load_active_release", lambda: (RELEASE, RELEASE.to_mapping()))
    monkeypatch.setattr(reconciler, "claim_reconciler_run_lease", lambda *_args: True)
    monkeypatch.setattr(reconciler, "release_reconciler_run_lease", lambda _env, owner: released.append(owner) or True)
    monkeypatch.setattr(reconciler, "_rollout_phase", lambda *_args, **_kwargs: "remainder")
    monkeypatch.setattr(reconciler, "_rollout_spec", lambda *_args: (100, 1))
    monkeypatch.setattr(reconciler, "_owners", lambda: [])
    monkeypatch.setattr(reconciler, "_advance_rollout", lambda *_args: None)

    assert asyncio.run(reconciler.run_reconciler()) == []
    assert released


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
