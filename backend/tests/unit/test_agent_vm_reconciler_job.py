from __future__ import annotations

import asyncio
import threading
from dataclasses import replace
from typing import Any

import pytest

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

    assert result.state == "missing"
    assert len(call_threads) == 2
    assert all(thread_id != loop_thread for thread_id in call_threads)


@pytest.mark.parametrize("state", ["quarantined", "missing", "stale", "recreate_required"])
def test_main_reports_nonconverged_states_as_failed_job(monkeypatch, state):
    async def run_reconciler(*, dry_run: bool = False) -> list[reconciler.ReconcileResult]:
        assert not dry_run
        return [reconciler.ReconcileResult("uid", state)]

    monkeypatch.setattr(reconciler, "run_reconciler", run_reconciler)

    assert reconciler.main([]) == 1


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
