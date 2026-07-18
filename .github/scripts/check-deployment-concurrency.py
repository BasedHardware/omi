#!/usr/bin/env python3
"""Enforce target-scoped serialization for persistent deployment writers.

This is intentionally a narrow, stdlib-only structural policy check. Actionlint
validates workflow syntax, but it cannot prove that separate workflow entry
points which mutate the same remote resource resolve to the same concurrency
group.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.firestore_workflow_policy import (  # noqa: E402
    has_direct_firestore_mutation,
    reconciliation_invocations,
)

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
    "gcp_backend.yml": LockContract("deploy-backend-stack-${{ github.event.inputs.environment }}"),
    "gcp_firestore_indexes.yml": LockContract("deploy-backend-stack-${{ github.event.inputs.environment }}"),
    "gcp_backend_agent_proxy.yml": LockContract("deploy-gke-agent-proxy-${{ github.event.inputs.environment }}"),
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
    "gcp_memory_maintenance_job_auto_dev.yml": LockContract("deploy-cloud-run-memory-maintenance-job-development"),
    "gcp_models.yml": LockContract("deploy-gke-vad-${{ github.event.inputs.environment }}"),
    "gcp_nllb_translation.yml": LockContract("deploy-gke-nllb-translation-${{ github.event.inputs.environment }}"),
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

# Firestore index creation is a schema migration, not ordinary deploy work.
# Keep a single auditable writer so backend readiness can stay read-only.
FIRESTORE_SCHEMA_WRITERS = frozenset({"gcp_firestore_indexes.yml"})

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
PUBLIC_BUILD_DEPLOY_ACTION = "uses: ./.github/actions/deploy-public-build"

PUSHER_CHART_MARKER = "backend/charts/pusher"
PUSHER_CONFIGMAP_PREFLIGHT = (
    "kubectl -n ${{ vars.ENV }}-omi-backend get configmap " "${{ vars.ENV }}-omi-backend-config >/dev/null"
)
PUSHER_REFERENCE_PREFLIGHT = "backend/scripts/verify_pusher_config_references.py"


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


def job_block(text: str, job: str) -> list[str] | None:
    """Return one top-level job's YAML lines using its fixed indentation."""

    lines = text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line == f"  {job}:")
    except StopIteration:
        return None

    block: list[str] = []
    for line in lines[start + 1 :]:
        if line and not line.startswith("    "):
            break
        block.append(line)
    return block


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


def validate_auto_deploy_acceptance(text: str) -> list[str]:
    """Keep exact candidate acceptance in the locked deploy job before promotion."""

    block = job_block(text, "deploy")
    if block is None:
        return ["gcp_backend_auto_dev.yml: missing deploy job"]
    required_markers = (
        "Capture exact no-traffic candidate URLs",
        "backend/scripts/verify_backend_release_vector.py",
        "backend/scripts/run_dev_candidate_acceptance.py",
        "--candidate",
        '--commit-sha "${{ github.sha }}"',
        '--deploy-run-id "${{ github.run_id }}"',
        '--deploy-run-attempt "${{ github.run_attempt }}"',
        "--environment dev",
        "Shift Cloud Run traffic to validated revisions",
    )
    errors = [
        f"gcp_backend_auto_dev.yml: candidate acceptance missing {marker!r}"
        for marker in required_markers
        if not any(marker in line for line in block)
    ]
    smoke_index = next((index for index, line in enumerate(block) if "run_dev_candidate_acceptance.py" in line), -1)
    promotion_index = next((index for index, line in enumerate(block) if "Shift Cloud Run traffic" in line), -1)
    if smoke_index >= promotion_index:
        errors.append("gcp_backend_auto_dev.yml: candidate acceptance must run before traffic promotion")
    if job_block(text, "verify") is not None:
        errors.append("gcp_backend_auto_dev.yml: candidate acceptance must not run in a post-promotion verify job")
    return errors


def validate_serving_release_vector(name: str, text: str) -> list[str]:
    """Require a post-promotion, all-tier vector check in each full backend deploy."""

    block = job_block(text, "deploy")
    if block is None:
        return [f"{name}: missing deploy job"]
    promotion_index = next((index for index, line in enumerate(block) if "Shift Cloud Run traffic" in line), -1)
    verifier_index = next(
        (index for index, line in enumerate(block) if "Verify serving backend release vector" in line), -1
    )
    errors: list[str] = []
    if promotion_index < 0:
        errors.append(f"{name}: missing Cloud Run traffic promotion")
    if verifier_index < 0:
        errors.append(f"{name}: missing post-promotion release-vector verification")
    elif verifier_index <= promotion_index:
        errors.append(f"{name}: release-vector verification must run after traffic promotion")

    verifier_step = next(
        (step for step in deploy_job_steps(block) if "Verify serving backend release vector" in "\n".join(step)),
        [],
    )
    verifier_text = "\n".join(verifier_step)
    if "backend/scripts/verify_backend_release_vector.py" not in verifier_text:
        errors.append(f"{name}: release-vector verification must use the canonical verifier")
    if "--environment" not in verifier_text:
        errors.append(f"{name}: release-vector verification must bind an environment")
    if name == "gcp_backend.yml" and "github.event.inputs.deploy_targets == 'all'" not in verifier_text:
        errors.append(f"{name}: all-tier release-vector verification must not run for cloud-run-only deploys")
    return errors


def validate_phase_aware_backend_promotion(name: str, text: str) -> list[str]:
    """Keep the Cloud Run candidate boundary ahead of GKE and traffic mutations."""

    block = job_block(text, "deploy")
    if block is None:
        return [f"{name}: missing deploy job"]
    steps = deploy_job_steps(block)

    def step_index(marker: str) -> int:
        return next((index for index, step in enumerate(steps) if marker in "\n".join(step)), -1)

    errors: list[str] = []
    candidate_index = step_index("Accept no-traffic Cloud Run candidate")
    snapshot_index = step_index("Capture Cloud Run pre-promotion traffic snapshot")
    promotion_index = step_index("Shift Cloud Run traffic to validated revisions")
    serving_vector_index = step_index("Verify serving backend release vector")
    restore_index = step_index("Restore Cloud Run traffic snapshot after failed promotion")
    required_steps = {
        "candidate acceptance": candidate_index,
        "pre-promotion traffic snapshot": snapshot_index,
        "traffic promotion": promotion_index,
        "serving release-vector verification": serving_vector_index,
        "traffic snapshot restoration": restore_index,
    }
    errors.extend(f"{name}: missing {description}" for description, index in required_steps.items() if index < 0)

    candidate_step = steps[candidate_index] if candidate_index >= 0 else []
    candidate_text = "\n".join(candidate_step)
    for marker in ("backend/scripts/verify_backend_release_vector.py", "--candidate", "--cloud-run-only"):
        if marker not in candidate_text:
            errors.append(f"{name}: candidate acceptance must include {marker!r}")

    for marker in (
        "Apply non-secret backend runtime config",
        "Deploy backend-secrets",
        "Deploy ${{ env.SERVICE }}-listen to GKE",
    ):
        mutation_index = step_index(marker)
        if mutation_index < 0:
            errors.append(f"{name}: missing deferred GKE mutation {marker!r}")
        elif candidate_index >= mutation_index:
            errors.append(f"{name}: candidate acceptance must precede {marker!r}")

    if snapshot_index >= promotion_index:
        errors.append(f"{name}: pre-promotion traffic snapshot must precede traffic promotion")
    if serving_vector_index <= promotion_index:
        errors.append(f"{name}: serving release-vector verification must follow traffic promotion")
    if restore_index <= serving_vector_index:
        errors.append(f"{name}: traffic snapshot restoration must follow serving release-vector verification")

    snapshot_step = "\n".join(steps[snapshot_index]) if snapshot_index >= 0 else ""
    if "backend/scripts/cloud_run_traffic_snapshot.py capture" not in snapshot_step:
        errors.append(f"{name}: pre-promotion snapshot must use the canonical Cloud Run snapshot helper")
    for service in ("backend", "backend-sync", "backend-sync-backfill", "backend-integration"):
        if f"--service {service}" not in snapshot_step:
            errors.append(f"{name}: pre-promotion snapshot must include {service}")

    restore_step = "\n".join(steps[restore_index]) if restore_index >= 0 else ""
    restore_condition = (
        "if: ${{ failure() && steps.cloud-run-traffic-snapshot.outcome == 'success' "
        "&& (steps.shift-cloud-run-traffic.outcome == 'failure' "
        "|| steps.verify-serving-release-vector.outcome == 'failure') }}"
    )
    if restore_condition not in restore_step:
        errors.append(f"{name}: traffic restoration must run after a failed promotion when its snapshot exists")
    if "backend/scripts/cloud_run_traffic_snapshot.py restore" not in restore_step:
        errors.append(f"{name}: traffic restoration must use the canonical Cloud Run snapshot helper")
    for artifact in ("cloud-run-pre-promotion-traffic-snapshot.json", "cloud-run-traffic-restore.json"):
        if artifact not in text:
            errors.append(f"{name}: must retain {artifact!r} as deployment evidence")
    return errors


def deploy_job_steps(block: list[str]) -> list[list[str]]:
    """Return deploy-job step blocks in workflow order."""

    steps: list[list[str]] = []
    index = 0
    while index < len(block):
        if block[index].startswith("      - "):
            start = index
            index += 1
            while index < len(block) and not block[index].startswith("      - "):
                index += 1
            steps.append(block[start:index])
        else:
            index += 1
    return steps


def workflow_steps(text: str) -> list[list[str]]:
    """Return top-level job step blocks from a workflow."""

    steps: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("      - "):
            if current is not None:
                steps.append(current)
            current = [line]
            continue
        if current is None:
            continue
        if line and len(line) - len(line.lstrip()) < 6:
            steps.append(current)
            current = None
            continue
        current.append(line)
    if current is not None:
        steps.append(current)
    return steps


def has_firestore_index_writer(text: str) -> bool:
    """Detect Firestore schema mutations by command semantics, not step names."""

    for step in workflow_steps(text):
        active = "\n".join(line for line in step if not line.lstrip().startswith("#"))
        if has_direct_firestore_mutation(active):
            return True
        if any(invocation.mutates_schema for invocation in reconciliation_invocations(active)):
            return True
    return False


def validate_firestore_schema_writers(workflow_text: dict[str, str]) -> list[str]:
    """Require every detected Firestore schema writer to be explicitly owned."""

    detected = {name for name, text in workflow_text.items() if has_firestore_index_writer(text)}
    owner = ", ".join(sorted(FIRESTORE_SCHEMA_WRITERS))
    return [
        *(
            f"{name}: Firestore schema writes are owned only by {owner}"
            for name in sorted(detected - FIRESTORE_SCHEMA_WRITERS)
        ),
        *(
            f"{name}: canonical Firestore schema writer is missing"
            for name in sorted(FIRESTORE_SCHEMA_WRITERS - detected)
        ),
    ]


def pusher_preflight_step_is_valid(name: str, step: list[str]) -> bool:
    """Return whether a deploy step performs an allowed pusher preflight."""

    if step[0].lstrip().startswith("#"):
        return False

    conditions = [candidate.strip() for candidate in step if candidate.strip().startswith("if:")]
    nonfatal = any(
        candidate.strip().startswith("continue-on-error:") or candidate.strip() == "set +e" for candidate in step
    )
    allowed_conditions = ["if: env.SERVICE == 'pusher'"] if name == "gcp_backend_pusher.yml" else []
    if nonfatal or conditions != allowed_conditions:
        return False

    step_text = "\n".join(step)
    if "|| true" in step_text:
        return False
    if PUSHER_REFERENCE_PREFLIGHT in step_text:
        return True

    for line in step:
        stripped = line.strip()
        command = stripped.removeprefix("- run: ").removeprefix("run: ")
        if command == PUSHER_CONFIGMAP_PREFLIGHT:
            return True
    return False


def validate_pusher_config_preflight(name: str, text: str) -> list[str]:
    """Require an active ConfigMap check in the pusher deploy job before Helm."""

    if PUSHER_CHART_MARKER not in text:
        return []
    block = job_block(text, "deploy")
    if block is None:
        return [f"{name}: pusher deploy must verify the backend runtime ConfigMap before Helm"]

    chart_indexes = [
        index for index, line in enumerate(block) if PUSHER_CHART_MARKER in line and not line.lstrip().startswith("#")
    ]
    if not chart_indexes:
        return []
    chart_index = min(chart_indexes)

    for step in deploy_job_steps(block[:chart_index]):
        if pusher_preflight_step_is_valid(name, step):
            return []

    return [f"{name}: pusher deploy must verify the backend runtime ConfigMap before Helm"]


def is_persistent_writer(text: str) -> bool:
    return (
        any(marker in text for marker in WRITER_MARKERS)
        or any(
            any(PUBLIC_BUILD_DEPLOY_ACTION in line and not line.lstrip().startswith("#") for line in step)
            for step in workflow_steps(text)
        )
        or has_firestore_index_writer(text)
    )


def resolve_environment(group: str, environment: str) -> str:
    return group.replace("${{ github.event.inputs.environment || 'development' }}", environment).replace(
        "${{ github.event.inputs.environment }}", environment
    )


def development_group(name: str, group: str) -> str:
    return DEVELOPMENT_GROUP_OVERRIDES.get(name, resolve_environment(group, "development"))


def validate_shared_families(groups: dict[str, str]) -> list[str]:
    errors: list[str] = []

    family_pairs = (
        ("gcp_backend.yml", "gcp_backend_auto_dev.yml"),
        ("gcp_firestore_indexes.yml", "gcp_backend_auto_dev.yml"),
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
        "gcp_firestore_indexes.yml",
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
        path.name: path.read_text(encoding="utf-8")
        for pattern in ("*.yml", "*.yaml")
        for path in WORKFLOWS.glob(pattern)
    }
    errors.extend(validate_firestore_schema_writers(workflow_text))

    detected = {name for name, text in workflow_text.items() if is_persistent_writer(text)}
    expected = set(LOCK_CONTRACTS) | set(RUN_SCOPED_EXEMPTIONS)
    for name in sorted(detected - expected):
        errors.append(f"{name}: persistent deployment writer is missing from the lock policy")
    for name in sorted(expected - detected):
        errors.append(f"{name}: lock policy entry no longer contains a recognized deployment writer")

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
        "revision_suffix=${SHORT_SHA}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}",
    )
    for name in ("gcp_backend.yml", "gcp_backend_auto_dev.yml"):
        text = workflow_text.get(name, "")
        for marker in identity_markers:
            if marker not in text:
                errors.append(f"{name}: backend revision identity must include {marker!r}")

    auto_deploy = workflow_text.get("gcp_backend_auto_dev.yml", "")
    errors.extend(validate_auto_deploy_acceptance(auto_deploy))
    for name in ("gcp_backend.yml", "gcp_backend_auto_dev.yml"):
        errors.extend(validate_serving_release_vector(name, workflow_text.get(name, "")))
        errors.extend(validate_phase_aware_backend_promotion(name, workflow_text.get(name, "")))
    for name, text in workflow_text.items():
        errors.extend(validate_pusher_config_preflight(name, text))
    release_vector_workflows = sorted(
        name for name, text in workflow_text.items() if "backend/scripts/verify_backend_release_vector.py" in text
    )
    allowed_release_vector_workflows = {"gcp_backend.yml", "gcp_backend_auto_dev.yml"}
    for name in release_vector_workflows:
        if name not in allowed_release_vector_workflows:
            errors.append(f"{name}: release-vector verification may run only in a source backend deploy workflow")

    return errors


def _self_test_firestore_schema_ownership() -> None:
    firestore_read_only = """name: fixture
jobs:
  verify:
    steps:
      - run: |
          python3 backend/scripts/reconcile_firestore_indexes.py \\
            --project runtime-project \\
            --check-only
"""
    if is_persistent_writer(firestore_read_only):
        raise PolicyError("read-only Firestore readiness was classified as a persistent writer")
    default_reconciliation = firestore_read_only.replace(" \\" + "\n            --check-only\n", "\n")
    if not is_persistent_writer(default_reconciliation):
        raise PolicyError("default Firestore reconciliation bypassed persistent-writer detection")
    if not is_persistent_writer(firestore_read_only.replace("--check-only", "--provision-missing")):
        raise PolicyError("explicit Firestore provisioning bypassed persistent-writer detection")
    mixed_firestore_step = firestore_read_only.replace(
        "            --check-only\n",
        "            --check-only\n          python3 backend/scripts/reconcile_firestore_indexes.py --project runtime-project\n",
    )
    if not is_persistent_writer(mixed_firestore_step):
        raise PolicyError("a read-only token masked a second Firestore writer in the same step")
    leading_comment = firestore_read_only.replace(
        "          python3",
        "          # readiness check\n          python3",
    )
    if is_persistent_writer(leading_comment):
        raise PolicyError("a leading shell comment changed read-only Firestore classification")
    comment_separated_writer = firestore_read_only.replace(
        "            --check-only\n",
        "            --check-only\n          # writer follows\n"
        "          python3 backend/scripts/reconcile_firestore_indexes.py --project runtime-project\n",
    )
    if not is_persistent_writer(comment_separated_writer):
        raise PolicyError("an inter-command comment masked a Firestore writer")
    direct_firebase_writer = """name: fixture
jobs:
  deploy:
    steps:
      - run: npx firebase deploy --only firestore:indexes
"""
    if not is_persistent_writer(direct_firebase_writer):
        raise PolicyError("direct Firebase index deployment bypassed persistent-writer detection")
    commented_firebase_writer = direct_firebase_writer.replace(
        "      - run: npx firebase",
        "      - run: |\n          # npx firebase",
    )
    if is_persistent_writer(commented_firebase_writer):
        raise PolicyError("a commented Firebase example was classified as a writer")
    direct_writer_commands = (
        "npx firebase deploy",
        "npx firebase deploy --project prod --only=firestore:indexes",
        "gcloud --project=prod firestore indexes composite create --collection-group=memories",
    )
    for command in direct_writer_commands:
        fixture = direct_firebase_writer.replace(
            "npx firebase deploy --only firestore:indexes",
            command,
        )
        if not is_persistent_writer(fixture):
            raise PolicyError(f"direct Firestore writer bypassed detection: {command}")
    non_firestore_firebase_deploy = direct_firebase_writer.replace(
        "--only firestore:indexes",
        "--only functions",
    )
    if is_persistent_writer(non_firestore_firebase_deploy):
        raise PolicyError("a functions-only Firebase deploy was classified as a Firestore writer")
    centralized_public_build_writer = """name: fixture
jobs:
  deploy:
    steps:
      - uses: ./.github/actions/deploy-public-build
"""
    if not is_persistent_writer(centralized_public_build_writer):
        raise PolicyError("centralized public-build deployment bypassed persistent-writer detection")
    if is_persistent_writer(centralized_public_build_writer.replace("      - uses:", "      # - uses:")):
        raise PolicyError("a commented centralized public-build deployment was classified as a writer")
    gcloud_list = direct_firebase_writer.replace(
        "npx firebase deploy --only firestore:indexes",
        "gcloud firestore indexes composite list",
    )
    if is_persistent_writer(gcloud_list):
        raise PolicyError("a read-only gcloud index list was classified as a writer")

    canonical_firestore_writer = {"gcp_firestore_indexes.yml": direct_firebase_writer}
    if validate_firestore_schema_writers(canonical_firestore_writer):
        raise PolicyError("the canonical Firestore schema writer was rejected")
    duplicate_firestore_writer = {
        **canonical_firestore_writer,
        "gcp_backend_auto_dev.yml": direct_firebase_writer,
    }
    if not any(
        "gcp_backend_auto_dev.yml" in error for error in validate_firestore_schema_writers(duplicate_firestore_writer)
    ):
        raise PolicyError("an unapproved Firestore schema writer bypassed ownership enforcement")
    if not any(
        "canonical Firestore schema writer is missing" in error for error in validate_firestore_schema_writers({})
    ):
        raise PolicyError("a missing canonical Firestore schema writer bypassed ownership enforcement")


def _self_test_workflow_lock() -> None:
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


def _self_test_deploy_guards() -> None:
    in_deploy_acceptance = """name: fixture
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: >-
          python3 backend/scripts/verify_backend_release_vector.py
          --candidate
          --commit-sha "${{ github.sha }}"
          --deploy-run-id "${{ github.run_id }}"
          --deploy-run-attempt "${{ github.run_attempt }}"
          --environment dev
      - name: Capture exact no-traffic candidate URLs
      - run: python3 backend/scripts/run_dev_candidate_acceptance.py
      - name: Shift Cloud Run traffic to validated revisions
"""
    if validate_auto_deploy_acceptance(in_deploy_acceptance):
        raise PolicyError("valid in-deploy candidate acceptance was rejected")

    serving_vector = """name: fixture
jobs:
  deploy:
    steps:
      - name: Shift Cloud Run traffic to validated revisions
      - name: Verify serving backend release vector
        run: python3 backend/scripts/verify_backend_release_vector.py --environment dev
"""
    if validate_serving_release_vector("gcp_backend_auto_dev.yml", serving_vector):
        raise PolicyError("valid post-promotion release-vector verification was rejected")

    phase_aware_promotion = """name: fixture
jobs:
  deploy:
    steps:
      - name: Accept no-traffic Cloud Run candidate
        run: python3 backend/scripts/verify_backend_release_vector.py --candidate --cloud-run-only
      - name: Apply non-secret backend runtime config
      - name: Deploy backend-secrets to GKE
      - name: Deploy ${{ env.SERVICE }}-listen to GKE
      - name: Capture Cloud Run pre-promotion traffic snapshot
        run: |-
          python3 backend/scripts/cloud_run_traffic_snapshot.py capture \\
            --service backend \\
            --service backend-sync \\
            --service backend-sync-backfill \\
            --service backend-integration \\
            --output cloud-run-pre-promotion-traffic-snapshot.json
      - name: Shift Cloud Run traffic to validated revisions
        id: shift-cloud-run-traffic
      - name: Verify serving backend release vector
        id: verify-serving-release-vector
      - name: Restore Cloud Run traffic snapshot after failed promotion
        if: ${{ failure() && steps.cloud-run-traffic-snapshot.outcome == 'success' && (steps.shift-cloud-run-traffic.outcome == 'failure' || steps.verify-serving-release-vector.outcome == 'failure') }}
        run: |-
          python3 backend/scripts/cloud_run_traffic_snapshot.py restore \\
            --evidence-path cloud-run-traffic-restore.json
"""
    if validate_phase_aware_backend_promotion("fixture.yml", phase_aware_promotion):
        raise PolicyError("valid phase-aware backend promotion was rejected")
    without_restore = phase_aware_promotion.replace(
        "Restore Cloud Run traffic snapshot after failed promotion", "Report"
    )
    if not any(
        "traffic snapshot restoration" in error
        for error in validate_phase_aware_backend_promotion("fixture.yml", without_restore)
    ):
        raise PolicyError("missing traffic restoration satisfied the phase-aware deploy contract")

    pusher_deploy = """name: fixture
jobs:
  deploy:
    steps:
      - run: kubectl -n ${{ vars.ENV }}-omi-backend get configmap ${{ vars.ENV }}-omi-backend-config >/dev/null
      - run: helm upgrade ./backend/charts/pusher
"""
    if validate_pusher_config_preflight("fixture.yml", pusher_deploy):
        raise PolicyError("valid pusher ConfigMap preflight was rejected")
    reference_preflight = """name: fixture
jobs:
  deploy:
    steps:
      - name: Preflight pusher ConfigMap and Secret references
        run: |
          python3 -m pip install -q pyyaml
          python3 backend/scripts/verify_pusher_config_references.py \\
            --environment ${{ vars.ENV }} --namespace ${{ vars.ENV }}-omi-backend
      - run: helm upgrade ./backend/charts/pusher
"""
    if validate_pusher_config_preflight("fixture.yml", reference_preflight):
        raise PolicyError("valid pusher reference preflight was rejected")
    missing_preflight = pusher_deploy.replace(
        "kubectl -n ${{ vars.ENV }}-omi-backend get configmap ${{ vars.ENV }}-omi-backend-config >/dev/null\n",
        "",
    )
    if not any("before Helm" in error for error in validate_pusher_config_preflight("fixture.yml", missing_preflight)):
        raise PolicyError("missing pusher ConfigMap preflight satisfied the deploy contract")

    equivalent_chart_path = """name: fixture
jobs:
  deploy:
    steps:
      - run: helm upgrade backend/charts/pusher
"""
    if not validate_pusher_config_preflight("fixture.yml", equivalent_chart_path):
        raise PolicyError("equivalent pusher chart path bypassed the deploy contract")

    late_preflight = """name: fixture
jobs:
  deploy:
    steps:
      - run: helm upgrade ./backend/charts/pusher
      - run: kubectl -n ${{ vars.ENV }}-omi-backend get configmap ${{ vars.ENV }}-omi-backend-config >/dev/null
"""
    if not any("before Helm" in error for error in validate_pusher_config_preflight("fixture.yml", late_preflight)):
        raise PolicyError("late pusher ConfigMap preflight satisfied the deploy contract")

    cross_job_preflight = """name: fixture
jobs:
  prepare:
    steps:
      - run: kubectl -n ${{ vars.ENV }}-omi-backend get configmap ${{ vars.ENV }}-omi-backend-config >/dev/null
  deploy:
    steps:
      - run: helm upgrade ./backend/charts/pusher
"""
    if not validate_pusher_config_preflight("fixture.yml", cross_job_preflight):
        raise PolicyError("cross-job pusher ConfigMap preflight satisfied the deploy contract")

    disabled_preflight = """name: fixture
jobs:
  deploy:
    steps:
      - name: Disabled preflight
        if: false
        run: kubectl -n ${{ vars.ENV }}-omi-backend get configmap ${{ vars.ENV }}-omi-backend-config >/dev/null
      - run: helm upgrade ./backend/charts/pusher
"""
    if not validate_pusher_config_preflight("fixture.yml", disabled_preflight):
        raise PolicyError("disabled pusher ConfigMap preflight satisfied the deploy contract")

    nonfatal_preflight = """name: fixture
jobs:
  deploy:
    steps:
      - name: Nonfatal preflight
        continue-on-error: true
        run: kubectl -n ${{ vars.ENV }}-omi-backend get configmap ${{ vars.ENV }}-omi-backend-config >/dev/null
      - run: helm upgrade ./backend/charts/pusher
"""
    if not validate_pusher_config_preflight("fixture.yml", nonfatal_preflight):
        raise PolicyError("nonfatal pusher ConfigMap preflight satisfied the deploy contract")

    masked_preflight = """name: fixture
jobs:
  deploy:
    steps:
      - run: kubectl -n ${{ vars.ENV }}-omi-backend get configmap ${{ vars.ENV }}-omi-backend-config >/dev/null || true
      - run: helm upgrade ./backend/charts/pusher
"""
    if not validate_pusher_config_preflight("fixture.yml", masked_preflight):
        raise PolicyError("masked pusher ConfigMap preflight satisfied the deploy contract")


def run_self_test() -> None:
    """Exercise independent policy fixtures without creating a monolithic test body."""

    _self_test_firestore_schema_ownership()
    _self_test_workflow_lock()
    _self_test_deploy_guards()


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
