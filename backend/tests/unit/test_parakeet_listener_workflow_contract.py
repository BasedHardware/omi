"""Contract checks for the backend-listen Parakeet qualification gate.

These checks exercise the workflow's parsed job and step boundaries.  The
cloud provisioning path is intentionally left to GitHub Actions; the contract
here prevents a future edit from silently moving capacity after the listener
rollout or reusing a stale backend image.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "gcp_backend_listen_helm.yml"


def _workflow() -> dict:
    document = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    jobs = document.get("jobs")
    assert isinstance(jobs, dict)
    return jobs


def _steps(job: dict) -> list[dict]:
    steps = job.get("steps")
    assert isinstance(steps, list)
    return steps


def test_deploy_qualifies_admitted_source_before_listener_mutation():
    jobs = _workflow()
    source = jobs["backend_source"]
    qualification = jobs["parakeet_qualification"]
    listener = jobs["helm-upgrade"]

    assert source["outputs"]["source_sha"] == "${{ steps.source.outputs.source_sha }}"
    assert qualification["uses"] == "./.github/workflows/parakeet_gpu_tests.yml"
    assert qualification["needs"] == "backend_source"
    assert qualification["with"]["source_sha"] == "${{ needs.backend_source.outputs.source_sha }}"
    assert qualification["with"]["build_source"] is True
    assert qualification["with"]["stream_capacity"] == "25"
    assert listener["needs"] == ["backend_source", "parakeet_qualification"]

    names = [step.get("name") for step in _steps(listener)]
    download = names.index("Download exact Parakeet GPU qualification artifact")
    provision = names.index("Provision and verify Parakeet stream fleet")
    carry_config = names.index("Carry forward config this workflow does not own")
    backend_chart = names.index("Upgrade backend-listen Helm chart")
    assert download < provision < carry_config < backend_chart

    download_step = _steps(listener)[download]
    assert download_step["uses"] == "actions/download-artifact@v8"
    assert download_step["with"]["name"] == "${{ needs.parakeet_qualification.outputs.artifact_name }}"

    provision_step = _steps(listener)[provision]
    command = provision_step["run"]
    assert "backend/scripts/deploy_parakeet_stream.py" in command
    assert "--qualification-evidence" in command
    assert "--source-sha" in command
    assert "--allow-node-pool-provision" in command
    assert "--apply" in command


def test_listener_uses_qualification_image_and_source_identity():
    jobs = _workflow()
    source_job = jobs["backend_source"]
    source_steps = _steps(source_job)
    source_text = "\n".join(str(step.get("run", "")) for step in source_steps)

    assert any(step.get("id") == "image" for step in source_steps)
    assert source_job["outputs"]["image_ref"] == "${{ steps.image.outputs.image_ref }}"
    assert source_job["outputs"]["image_digest"] == "${{ steps.image.outputs.image_digest }}"
    assert "gcloud container images describe \"$IMAGE\"" in source_text
    assert "docker build --file backend/Dockerfile" in source_text
    assert "runtime_image_contracts.py smoke" in source_text
    assert "docker push \"$IMAGE\"" in source_text

    listener_steps = _steps(jobs["helm-upgrade"])
    provision = next(
        step for step in listener_steps if step.get("name") == "Provision and verify Parakeet stream fleet"
    )
    assert provision["env"]["QUALIFIED_IMAGE_REF"] == "${{ needs.parakeet_qualification.outputs.image_ref }}"
    assert provision["env"]["QUALIFIED_SOURCE_SHA"] == "${{ needs.parakeet_qualification.outputs.source_sha }}"
    assert provision["env"]["ADMITTED_SOURCE_SHA"] == "${{ needs.backend_source.outputs.source_sha }}"

    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "Keeping the running image tag" not in workflow_text
    assert "BACKEND_LISTEN_IMAGE_TAG=$RUNNING_TAG" not in workflow_text
    assert "BACKEND_LISTEN_IMAGE_TAG=$ADMITTED_TAG" in workflow_text


def test_source_qualification_binds_listener_checkout_to_admitted_sha():
    jobs = _workflow()
    source_step = next(step for step in _steps(jobs["backend_source"]) if step.get("id") == "source")
    listener_steps = _steps(jobs["helm-upgrade"])
    select_source = next(step for step in listener_steps if step.get("name") == "Select admitted backend source")
    admit_source = next(
        step for step in listener_steps if step.get("name") == "Admit checked-out production source and image identity"
    )

    assert 'CHECKED_OUT_SHA="$(git rev-parse HEAD)"' in source_step["run"]
    assert 'SOURCE_SHA="$CHECKED_OUT_SHA"' in source_step["run"]
    assert select_source["env"]["ADMITTED_SOURCE_SHA"] == "${{ needs.backend_source.outputs.source_sha }}"
    assert 'git checkout --detach "$ADMITTED_SOURCE_SHA"' in select_source["run"]
    assert 'CHECKED_OUT_SHA=$(git rev-parse HEAD)' in admit_source["run"]
    assert 'EXPECTED_SHA="${{ needs.backend_source.outputs.source_sha }}"' in admit_source["run"]
    assert '[[ "$CHECKED_OUT_SHA" == "$EXPECTED_SHA" ]]' in admit_source["run"]


def test_rollback_skips_qualification_and_keeps_existing_helm_path():
    jobs = _workflow()
    source_if = jobs["backend_source"]["if"]
    qualification_if = jobs["parakeet_qualification"]["if"]
    listener_if = jobs["helm-upgrade"]["if"]
    assert "github.event.inputs.mode == 'deploy'" in source_if
    assert "github.event.inputs.mode == 'deploy'" in qualification_if
    assert "github.event.inputs.mode == 'rollback'" in listener_if
    assert "needs.parakeet_qualification.result == 'success'" in listener_if

    rollback = next(
        step for step in _steps(jobs["helm-upgrade"]) if step.get("name") == "Roll back backend-listen Helm release"
    )
    assert rollback["if"] == "${{ github.event.inputs.mode == 'rollback' }}"
    assert "helm" in rollback["run"]
    assert "rollback" in rollback["run"]


def test_prod_is_manual_and_source_is_ancestry_checked():
    jobs = _workflow()
    source = jobs["backend_source"]
    listener = jobs["helm-upgrade"]
    assert source["environment"] == "${{ github.event.inputs.environment == 'prod' && 'prod' || 'development' }}"
    assert listener["environment"] == "${{ github.event.inputs.environment == 'prod' && 'prod' || 'development' }}"

    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "if [[ \"$GITHUB_EVENT_NAME\" == push && \"$DEPLOY_ENVIRONMENT\" == prod ]]" in workflow_text
    assert "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main" in workflow_text
    assert 'git merge-base --is-ancestor "$CHECKED_OUT_SHA" origin/main' in workflow_text
    assert "github.event.inputs.environment == 'prod' && 'main' || github.event.inputs.branch" in workflow_text


@pytest.mark.skipif(shutil.which("actionlint") is None, reason="actionlint is not installed")
def test_listener_workflow_passes_actionlint():
    result = subprocess.run(
        ["actionlint", str(WORKFLOW_PATH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
