from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from services.agent_vm_lifecycle import (
    AgentVmRelease,
    AgentVmReleaseError,
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
    declared = hashlib.sha256(release_manifest_bytes(unsigned)).hexdigest()
    validate_release_manifest({**unsigned, "manifestSha256": declared})
    with pytest.raises(AgentVmReleaseError, match="manifestSha256"):
        validate_release_manifest({**unsigned, "manifestSha256": "d" * 64})


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
