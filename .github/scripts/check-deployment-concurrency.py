#!/usr/bin/env python3
"""Enforce target-scoped serialization for persistent Cloud Run/GKE writers.

This is intentionally a narrow, stdlib-only structural policy check. Actionlint
validates workflow syntax, but it cannot prove that separate workflow entry
points which mutate the same remote resource resolve to the same concurrency
group.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


@dataclass(frozen=True)
class LockContract:
    group: str


# Group strings are a deployment API: manual and automatic entry points for a
# shared target must keep resolving to the same value. Keep this explicit so a
# new deploy writer cannot silently bypass the audited lock graph.
LOCK_CONTRACTS = {
    "desktop_backend_auto_dev.yml": LockContract("desktop-backend-auto-dev"),
    "desktop_promote_prod.yml": LockContract("desktop-backend-promote-prod"),
    "gcp_admin.yml": LockContract(
        "deploy-cloud-run-omi-admin-dashboard-${{ github.ref == 'refs/heads/development' && 'development' || github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id) }}"
    ),
    "gcp_app.yml": LockContract(
        "deploy-cloud-run-omi-web-app-${{ github.ref == 'refs/heads/development' && 'development' || github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id) }}"
    ),
    "gcp_apps_js.yml": LockContract(
        "deploy-cloud-run-apps-js-${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || github.ref == 'refs/heads/development' && 'development' || github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id) }}"
    ),
    "gcp_backend.yml": LockContract("deploy-backend-stack-${{ github.event.inputs.environment }}"),
    "gcp_backend_agent_proxy.yml": LockContract(
        "deploy-gke-agent-proxy-${{ github.event.inputs.environment }}"
    ),
    "gcp_backend_agent_proxy_auto_deploy.yml": LockContract("deploy-gke-agent-proxy-development"),
    "gcp_backend_auto_dev.yml": LockContract("deploy-backend-stack-development"),
    "gcp_backend_listen_helm.yml": LockContract(
        "deploy-backend-stack-${{ github.event.inputs.environment || 'development' }}"
    ),
    "gcp_backend_pusher.yml": LockContract(
        "${{ (github.event.inputs.service || 'pusher') == 'llm-gateway' && format('deploy-backend-stack-{0}', github.event.inputs.environment) || format('deploy-gke-pusher-{0}', github.event.inputs.environment) }}"
    ),
    "gcp_backend_pusher_auto_deploy.yml": LockContract("deploy-gke-pusher-development"),
    "gcp_diarizer.yml": LockContract("deploy-gke-diarizer-${{ github.event.inputs.environment }}"),
    "gcp_frontend.yml": LockContract(
        "deploy-cloud-run-frontend-${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || github.ref == 'refs/heads/development' && 'development' || github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id) }}"
    ),
    "gcp_llm_gateway.yml": LockContract("deploy-backend-stack-${{ github.event.inputs.environment }}"),
    "gcp_llm_gateway_auto_dev.yml": LockContract("deploy-backend-stack-development"),
    "gcp_memory_maintenance_job.yml": LockContract(
        "deploy-cloud-run-memory-maintenance-job-${{ github.event.inputs.environment }}"
    ),
    "gcp_memory_maintenance_job_auto_dev.yml": LockContract(
        "deploy-cloud-run-memory-maintenance-job-development"
    ),
    "gcp_models.yml": LockContract("deploy-gke-vad-${{ github.event.inputs.environment }}"),
    "gcp_nllb_translation.yml": LockContract(
        "deploy-gke-nllb-translation-${{ github.event.inputs.environment }}"
    ),
    "gcp_notifications_job.yml": LockContract(
        "deploy-cloud-run-notifications-job-${{ github.event.inputs.environment }}"
    ),
    "gcp_parakeet.yml": LockContract("deploy-gke-parakeet-${{ github.event.inputs.environment }}"),
    "gcp_personas.yml": LockContract(
        "deploy-cloud-run-omi-web-${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || github.ref == 'refs/heads/development' && 'development' || github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id) }}"
    ),
    "gcp_plugins.yml": LockContract("deploy-cloud-run-plugins-${{ github.event.inputs.environment }}"),
}


# This workflow writes a run-ID-scoped Kubernetes Job and does not mutate the
# persistent Parakeet release. The required marker makes the exemption fail
# closed if that isolation is removed.
RUN_SCOPED_EXEMPTIONS = {
    "parakeet_gpu_tests.yml": "JOB_NAME: parakeet-gpu-test-${{ github.run_id }}",
}

# The manual pusher workflow routes its default pusher service and its
# llm-gateway compatibility mode to different lock domains. The default pusher
# development rendering is asserted explicitly rather than trying to evaluate
# the full GitHub expression with a partial string replacement.
DEVELOPMENT_GROUP_OVERRIDES = {
    "gcp_backend_pusher.yml": "deploy-gke-pusher-development",
}


WRITER_MARKERS = (
    "google-github-actions/deploy-cloudrun@",
    "google-github-actions/get-gke-credentials@",
    "gcloud run services update-traffic",
    "gcloud run services update ",
    "gcloud run deploy ",
    "gcloud run jobs deploy ",
    "gcloud run jobs update ",
)


class PolicyError(ValueError):
    pass


def parse_top_level_concurrency(text: str) -> dict[str, str] | None:
    """Return scalar fields from a workflow-level concurrency mapping."""

    lines = text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line == "concurrency:")
    except StopIteration:
        return None

    fields: dict[str, str] = {}
    for line in lines[start + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break
        if not line.startswith("  ") or line.startswith("    ") or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        fields[key] = value.strip()
    return fields


def validate_lock(name: str, text: str, contract: LockContract) -> list[str]:
    errors: list[str] = []
    concurrency = parse_top_level_concurrency(text)
    if concurrency is None:
        return [f"{name}: missing workflow-level concurrency block"]

    actual_group = concurrency.get("group")
    if actual_group != contract.group:
        errors.append(f"{name}: concurrency group must be {contract.group!r}, got {actual_group!r}")
    if concurrency.get("cancel-in-progress") != "false":
        errors.append(f"{name}: deploy locks must use cancel-in-progress: false")
    return errors


def is_persistent_writer(text: str) -> bool:
    return any(marker in text for marker in WRITER_MARKERS)


def resolve_environment(group: str, environment: str) -> str:
    return group.replace(
        "${{ github.event.inputs.environment || 'development' }}", environment
    ).replace("${{ github.event.inputs.environment }}", environment)


def development_group(name: str, group: str) -> str:
    return DEVELOPMENT_GROUP_OVERRIDES.get(name, resolve_environment(group, "development"))


def validate_shared_families(groups: dict[str, str]) -> list[str]:
    errors: list[str] = []

    family_pairs = (
        ("gcp_backend.yml", "gcp_backend_auto_dev.yml"),
        ("gcp_backend_listen_helm.yml", "gcp_backend_auto_dev.yml"),
        ("gcp_llm_gateway.yml", "gcp_llm_gateway_auto_dev.yml"),
        ("gcp_llm_gateway.yml", "gcp_backend_auto_dev.yml"),
        ("gcp_memory_maintenance_job.yml", "gcp_memory_maintenance_job_auto_dev.yml"),
        ("gcp_backend_agent_proxy.yml", "gcp_backend_agent_proxy_auto_deploy.yml"),
        ("gcp_backend_pusher.yml", "gcp_backend_pusher_auto_deploy.yml"),
    )
    for manual, automatic in family_pairs:
        manual_dev = development_group(manual, groups[manual])
        if manual_dev != groups[automatic]:
            errors.append(
                f"{manual} development lock {manual_dev!r} does not match {automatic} lock {groups[automatic]!r}"
            )

    environment_scoped = (
        "gcp_backend.yml",
        "gcp_backend_agent_proxy.yml",
        "gcp_backend_listen_helm.yml",
        "gcp_diarizer.yml",
        "gcp_llm_gateway.yml",
        "gcp_memory_maintenance_job.yml",
        "gcp_models.yml",
        "gcp_nllb_translation.yml",
        "gcp_notifications_job.yml",
        "gcp_parakeet.yml",
        "gcp_plugins.yml",
    )
    for name in environment_scoped:
        if resolve_environment(groups[name], "development") == resolve_environment(groups[name], "prod"):
            errors.append(f"{name}: development and prod must resolve to different lock groups")

    return errors


def check_repository() -> list[str]:
    errors: list[str] = []
    workflow_text = {
        path.name: path.read_text()
        for pattern in ("*.yml", "*.yaml")
        for path in WORKFLOWS.glob(pattern)
    }

    detected = {name for name, text in workflow_text.items() if is_persistent_writer(text)}
    expected = set(LOCK_CONTRACTS) | set(RUN_SCOPED_EXEMPTIONS)
    for name in sorted(detected - expected):
        errors.append(f"{name}: persistent Cloud Run/GKE writer is missing from the lock policy")
    for name in sorted(expected - detected):
        errors.append(f"{name}: lock policy entry no longer contains a recognized deploy writer")

    groups: dict[str, str] = {}
    for name, contract in LOCK_CONTRACTS.items():
        text = workflow_text.get(name)
        if text is None:
            errors.append(f"{name}: audited deploy workflow is missing")
            continue
        errors.extend(validate_lock(name, text, contract))
        concurrency = parse_top_level_concurrency(text)
        if concurrency and concurrency.get("group"):
            groups[name] = concurrency["group"]

    if set(groups) == set(LOCK_CONTRACTS):
        errors.extend(validate_shared_families(groups))

    for name, marker in RUN_SCOPED_EXEMPTIONS.items():
        text = workflow_text.get(name, "")
        if marker not in text:
            errors.append(f"{name}: run-scoped deploy-lock exemption lost required marker {marker!r}")

    identity_markers = (
        'SHORT_SHA="$(git rev-parse --short=7 HEAD)"',
        'revision_suffix=${SHORT_SHA}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}',
    )
    for name in ("gcp_backend.yml", "gcp_backend_auto_dev.yml"):
        text = workflow_text.get(name, "")
        for marker in identity_markers:
            if marker not in text:
                errors.append(f"{name}: backend revision identity must include {marker!r}")

    return errors


def run_self_test() -> None:
    good = """name: fixture
concurrency:
  group: deploy-fixture-development
  cancel-in-progress: false
jobs:
  deploy:
    runs-on: ubuntu-latest
"""
    contract = LockContract("deploy-fixture-development")
    if validate_lock("fixture.yml", good, contract):
        raise PolicyError("valid workflow-level lock was rejected")

    job_only = """name: fixture
jobs:
  deploy:
    concurrency:
      group: deploy-fixture-development
      cancel-in-progress: false
"""
    if not any("workflow-level" in error for error in validate_lock("fixture.yml", job_only, contract)):
        raise PolicyError("job-level-only lock satisfied the workflow-level contract")

    wrong_group = good.replace("deploy-fixture-development", "deploy-other-development")
    if not any("group must be" in error for error in validate_lock("fixture.yml", wrong_group, contract)):
        raise PolicyError("mismatched group satisfied the contract")

    canceling = good.replace("cancel-in-progress: false", "cancel-in-progress: true")
    if not any("cancel-in-progress" in error for error in validate_lock("fixture.yml", canceling, contract)):
        raise PolicyError("cancel-in-progress: true satisfied the deploy contract")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        print("deployment concurrency policy self-test OK")
        return 0

    errors = check_repository()
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1

    print(
        f"deployment concurrency policy OK ({len(LOCK_CONTRACTS)} persistent writers, "
        f"{len(RUN_SCOPED_EXEMPTIONS)} run-scoped exemption)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
