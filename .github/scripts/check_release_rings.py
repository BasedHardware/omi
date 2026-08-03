#!/usr/bin/env python3
"""Guard the one-action, production backend release path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".github" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from workflow_composite_contract import backend_deploy_contract_text
BACKEND_RELEASE_SOURCES = (
    Path(".github/workflows/gcp_backend.yml"),
)
DEPLOY_BACKEND_STACK_ACTION = Path(".github/actions/deploy-backend-stack/action.yml")

OBSOLETE_RELEASE_RING_SOURCES = (
    Path("backend/deploy/release_rings.yaml"),
    Path("backend/scripts/release_rings.py"),
    Path("backend/scripts/render_release_ring_config.py"),
    Path("backend/scripts/release_ring_gke_snapshot.py"),
    Path(".github/workflows/release-record.yml"),
    Path(".github/workflows/deploy-release-ring.yml"),
)

OBSOLETE_RELEASE_BINDINGS = (
    "RELEASE_ARTIFACT_PROJECT_ID",
    "RELEASE_RUNTIME_PROJECT_ID",
    "RELEASE_GKE_CLUSTER",
    "RELEASE_RECORDS_BUCKET",
    "RELEASE_RECORDS_WRITER_SERVICE_ACCOUNT",
    "RELEASE_RING_DEPLOYER_SERVICE_ACCOUNT",
    "RELEASE_RINGS_WIF_PROVIDER",
    "BACKEND_SECRETS_GSA",
)


def require(text: str, path: Path, fragments: tuple[str, ...]) -> list[str]:
    return [
        f"{path}: missing required release-vector guard {fragment!r}" for fragment in fragments if fragment not in text
    ]


def require_one(text: str, path: Path, description: str, alternatives: tuple[str, ...]) -> list[str]:
    if any(fragment in text for fragment in alternatives):
        return []
    return [f"{path}: missing required release-vector guard {description!r}"]


def check() -> list[str]:
    paths = {relative: ROOT / relative for relative in BACKEND_RELEASE_SOURCES}
    errors = [f"{path}: canonical production deploy source is missing" for path in paths.values() if not path.exists()]
    if errors:
        return errors

    workflow_path = paths[Path(".github/workflows/gcp_backend.yml")]
    workflow = workflow_path.read_text(encoding="utf-8")
    contract = backend_deploy_contract_text(workflow, ROOT, DEPLOY_BACKEND_STACK_ACTION)
    errors.extend(
        require(
            contract,
            workflow_path,
            (
                "release_sha:",
                "default: 'cloud-run-only'",
                "github.ref == 'refs/heads/main'",
                "firestore_readiness:",
                "GCP_FIRESTORE_READONLY_CREDENTIALS",
                "needs.firestore_readiness.outputs.admitted_sha",
                "--check-only",
                "no_traffic: true",
                "Verify serving backend release vector",
                "github.event.inputs.environment == 'prod'",
                "environment=prod, deploy_targets=all is unsupported",
                "Smoke promoted production serving API",
            ),
        )
    )
    errors.extend(
        require_one(
            contract,
            workflow_path,
            "canonical deploy-backend-secrets helper",
            ("backend/scripts/deploy-backend-secrets.sh", "$DEPLOY_CONTROL_SCRIPTS/deploy-backend-secrets.sh"),
        )
    )
    errors.extend(
        require_one(
            contract,
            workflow_path,
            "canonical Cloud Run snapshot helper capture",
            ("cloud_run_traffic_snapshot.py capture", 'cloud_run_traffic_snapshot.py" capture'),
        )
    )
    errors.extend(
        require_one(
            contract,
            workflow_path,
            "canonical Cloud Run snapshot helper restore",
            ("cloud_run_traffic_snapshot.py restore", 'cloud_run_traffic_snapshot.py" restore'),
        )
    )
    errors.extend(
        require_one(
            contract,
            workflow_path,
            "canonical release-vector verifier",
            ("backend/scripts/verify_backend_release_vector.py", "$DEPLOY_CONTROL_SCRIPTS/verify_backend_release_vector.py"),
        )
    )
    promotion = contract.find("Shift Cloud Run traffic to validated revisions")
    verification = contract.find("Verify serving backend release vector")
    if promotion < 0 or verification < 0 or verification <= promotion:
        errors.append("canonical serving release-vector verification must follow traffic promotion")
    if "probe-transcription-candidate-from-cloud-run.sh" in contract:
        errors.append("canonical production deploy must not create an ephemeral Cloud Run candidate probe")
    for binding in OBSOLETE_RELEASE_BINDINGS:
        if binding in contract:
            errors.append(f"gcp_backend.yml: obsolete release binding {binding!r} must not be required")
    for relative in OBSOLETE_RELEASE_RING_SOURCES:
        if (ROOT / relative).exists():
            errors.append(f"{relative}: obsolete release-ring authority must be deleted")
    for relative, path in paths.items():
        if "release-ring deployment control plane" in path.read_text(encoding="utf-8").lower():
            errors.append(f"{relative}: backend release-ring deployment control plane is forbidden")
    return errors


if __name__ == "__main__":
    problems = check()
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    raise SystemExit(bool(problems))
