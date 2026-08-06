from __future__ import annotations

import json
from pathlib import Path

import pytest

import jobs.agent_vm_reconciler as reconciler
import services.agent_vm_lifecycle as lifecycle
from scripts.agent_vm_release import canonical_bytes
from services.agent_vm_lifecycle import (
    AgentVmRelease,
    AgentVmReleaseError,
    GceAgentVmClient,
    TrustedAgentVmHealthChannelUnavailable,
    drift_reasons,
    expected_release_metadata,
    release_manifest_bytes,
    retry_delay_seconds,
    rollout_selected,
    runtime_matches,
    startup_wrapper,
    validate_release_manifest,
)

RELEASE = {
    "schemaVersion": 1,
    "environment": "development",
    "sourceSha": "a" * 40,
    "imageDigest": "gcr.io/based-hardware-dev/agent-vm@sha256:" + "b" * 64,
    "startupUri": "gs://based-hardware-dev-agent/agent-vm/releases/" + "a" * 40 + "/startup.sh",
    "startupSha256": "c" * 64,
    "bootImage": "projects/based-hardware-dev/global/images/family/omi-agent",
    "serviceAccount": "omi-agent-vm-bootstrap@based-hardware-dev.iam.gserviceaccount.com",
}


def test_release_manifest_rejects_mutable_or_cross_environment_artifacts():
    release = validate_release_manifest(RELEASE)
    assert release.release_id == "a" * 40
    with pytest.raises(AgentVmReleaseError, match="immutable"):
        validate_release_manifest({**RELEASE, "imageDigest": "gcr.io/project/agent-vm:latest"})
    with pytest.raises(AgentVmReleaseError, match="startupUri"):
        validate_release_manifest({**RELEASE, "startupUri": "https://example.com/startup.sh"})


def test_manifest_hash_is_canonical_and_checked():
    unsigned = dict(RELEASE)
    declared = "9a14a1b42df027d76d667ee4196011d0c54f785aacfb26009e13af1718805572"
    assert release_manifest_bytes(unsigned) == canonical_bytes(unsigned)
    validate_release_manifest({**unsigned, "manifestSha256": declared})
    with pytest.raises(AgentVmReleaseError, match="manifestSha256"):
        validate_release_manifest({**unsigned, "manifestSha256": "d" * 64})


def test_active_release_rejects_an_invalid_rollout_phase(monkeypatch):
    malformed = {**RELEASE, "rollout": {"phase": "remaindr"}}
    monkeypatch.setattr(reconciler, "_read_gcs_uri", lambda _uri: json.dumps(malformed).encode())
    monkeypatch.setenv("AGENT_VM_ACTIVE_RELEASE_URI", "gs://bucket/active.json")

    with pytest.raises(ValueError, match="unsupported Agent VM rollout phase"):
        reconciler.load_active_release()


def test_legacy_instance_is_drift_and_current_instance_is_not():
    release = AgentVmRelease.from_mapping(RELEASE)
    current = {
        "serviceAccounts": [{"email": release.service_account}],
        "metadata": {
            "items": [{"key": key, "value": value} for key, value in expected_release_metadata(release).items()]
        },
    }
    assert drift_reasons({"serviceAccounts": []}, release)
    assert drift_reasons(current, release) == []
    assert (
        startup_wrapper(release.startup_uri, release.startup_sha256)
        == expected_release_metadata(release)["startup-script"]
    )
    assert "omi-agent-boot-image" in expected_release_metadata(release)


def test_runtime_verification_requires_all_release_identity_fields():
    release = AgentVmRelease.from_mapping(RELEASE)
    payload = {
        "status": "ok",
        "release": release.release_id,
        "imageDigest": release.image_digest,
        "startupSha256": release.startup_sha256,
    }
    assert runtime_matches(payload, release)
    assert not runtime_matches({**payload, "imageDigest": "gcr.io/project/agent-vm@sha256:" + "e" * 64}, release)


def test_reconciler_readiness_selects_only_an_rfc1918_instance_address():
    instance = {"networkInterfaces": [{"networkIP": "10.128.0.9", "accessConfigs": [{"natIP": "34.1.2.3"}]}]}
    assert GceAgentVmClient.instance_ip(instance) == "34.1.2.3"
    assert GceAgentVmClient.private_instance_ip(instance) == "10.128.0.9"
    assert (
        GceAgentVmClient.private_instance_ip(
            {"networkInterfaces": [{"networkIP": "203.0.113.9", "accessConfigs": [{"natIP": "34.1.2.3"}]}]}
        )
        is None
    )


@pytest.mark.asyncio
async def test_reconciler_readiness_fails_before_sending_auth_without_a_trusted_channel(monkeypatch):
    monkeypatch.delenv("AGENT_VM_TRUSTED_HEALTH_CHANNEL", raising=False)
    constructed = False

    class Client:
        def __init__(self, *_args, **_kwargs):
            nonlocal constructed
            constructed = True

    monkeypatch.setattr(lifecycle.httpx, "AsyncClient", Client)

    with pytest.raises(TrustedAgentVmHealthChannelUnavailable, match="private VPC reachability"):
        await GceAgentVmClient("project").runtime_is_current(
            "10.128.0.9", "owner-bearer", AgentVmRelease.from_mapping(RELEASE)
        )
    assert constructed is False


@pytest.mark.asyncio
async def test_reconciler_readiness_uses_the_private_vpc_channel_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("AGENT_VM_TRUSTED_HEALTH_CHANNEL", "private-vpc")
    release = AgentVmRelease.from_mapping(RELEASE)
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "status": "ok",
                "release": release.release_id,
                "imageDigest": release.image_digest,
                "startupSha256": release.startup_sha256,
            }

    class Client:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, *, headers):
            captured.update({"url": url, "headers": headers})
            return Response()

    monkeypatch.setattr(lifecycle.httpx, "AsyncClient", Client)

    assert await GceAgentVmClient("project").runtime_is_current("10.128.0.9", "owner-bearer", release)
    assert captured == {
        "url": "http://10.128.0.9:8080/health",
        "headers": {"Authorization": "Bearer owner-bearer"},
    }


@pytest.mark.asyncio
async def test_metadata_repair_can_restore_the_owner_fenced_auth_token():
    captured = {}

    class Client(GceAgentVmClient):
        async def _mutate(self, method, url, body=None):
            captured.update({"method": method, "url": url, "body": body})

    await Client("project").set_metadata(
        "omi-agent-user",
        {"metadata": {"fingerprint": "fingerprint", "items": [{"key": "auth-token", "value": "stale"}]}},
        AgentVmRelease.from_mapping(RELEASE),
        auth_token="owner-bearer",
    )

    assert {item["key"]: item["value"] for item in captured["body"]["items"]}["auth-token"] == "owner-bearer"


@pytest.mark.asyncio
async def test_boot_image_replacement_scopes_vpc_creation_to_the_explicit_subnet_and_required_create_fields():
    captured = {}

    class Client(GceAgentVmClient):
        async def _mutate(self, method, url, body=None):
            captured.update({"method": method, "url": url, "body": body})

    release = AgentVmRelease.from_mapping(RELEASE)
    await Client("based-hardware-dev").create_replacement(
        "omi-agent-user-m-migration",
        {
            "id": "predecessor-id",
            "machineType": "zones/us-central1-a/machineTypes/e2-small",
            "networkInterfaces": [
                {
                    "network": "projects/based-hardware-dev/global/networks/default",
                    "subnetwork": "projects/based-hardware-dev/regions/us-central1/subnetworks/default",
                    "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
                }
            ],
        },
        release,
        "candidate-owner-bearer",
        "migration-id",
    )

    body = captured["body"]
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/zones/us-central1-a/instances")
    assert body["networkInterfaces"] == [
        {
            "subnetwork": "projects/based-hardware-dev/regions/us-central1/subnetworks/default",
            "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
        }
    ]
    assert body["serviceAccounts"] == [
        {"email": release.service_account, "scopes": ["https://www.googleapis.com/auth/cloud-platform"]}
    ]
    assert body["tags"] == {"items": ["omi-agent-vm"]}
    assert body["labels"] == {"omi-agent-migration": "migration-id", "omi-agent-predecessor": "predecessor-id"}
    metadata = {item["key"]: item["value"] for item in body["metadata"]["items"]}
    assert metadata["auth-token"] == "candidate-owner-bearer"
    assert metadata["omi-agent-migration"] == "migration-id"
    assert body["disks"][0]["initializeParams"]["sourceImage"] == release.boot_image


def test_startup_wrapper_rejects_tampered_artifact_before_execution():
    wrapper = startup_wrapper("gs://bucket/releases/startup.sh", "d" * 64)
    assert "sha256sum /tmp/omi-startup.sh" in wrapper
    assert "Agent VM startup artifact checksum mismatch" in wrapper


def test_rollout_selection_is_stable_and_backoff_is_bounded():
    selected = rollout_selected("uid-1", "a" * 40, 5)
    assert selected == rollout_selected("uid-1", "a" * 40, 5)
    assert rollout_selected("uid-1", "a" * 40, 100)
    assert not rollout_selected("uid-1", "a" * 40, 0)
    assert retry_delay_seconds(1) == 120
    assert retry_delay_seconds(20) == 3600


def test_release_renderer_script_is_checked_in():
    script = Path(__file__).resolve().parents[2] / "scripts" / "agent_vm_release.py"
    assert script.is_file()
    assert "gcloud storage cp -n" in script.read_text(encoding="utf-8")
