#!/usr/bin/env python3
"""Keep stateless release-ring workflow invariants structural and fail-closed."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def require(text: str, path: Path, fragments: tuple[str, ...]) -> list[str]:
    return [f"{path}: missing required release-ring guard {fragment!r}" for fragment in fragments if fragment not in text]


def check() -> list[str]:
    record_path = ROOT / ".github/workflows/release-record.yml"
    deploy_path = ROOT / ".github/workflows/deploy-release-ring.yml"
    errors: list[str] = []
    for path in (record_path, deploy_path):
        if not path.exists():
            errors.append(f"{path}: release-ring workflow is missing")
            continue
    if errors:
        return errors

    record = record_path.read_text(encoding="utf-8")
    deploy = deploy_path.read_text(encoding="utf-8")
    errors.extend(
        require(
            record,
            record_path,
            (
                "workflow_run:",
                'workflows: ["Release Eligibility"]',
                "github.event.workflow_run.head_sha",
                "github.event.workflow_run.head_branch == 'main'",
                "docker/build-push-action@v7",
                "backend/scripts/release_rings.py create-record",
                "backend/scripts/release_rings.py resolve-secrets",
                "backend/scripts/release_rings.py materialize-runtime",
                "backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml",
                "get-gke-credentials@v3",
                "gcloud storage cp --if-generation-match=0",
                "gh workflow run deploy-release-ring.yml --ref main",
                "workload_identity_provider:",
            ),
        )
    )
    errors.extend(
        require(
            deploy,
            deploy_path,
            (
                "group: deploy-release-ring-${{ inputs.ring }}",
                "environment: ${{ inputs.ring }}",
                "github.ref == 'refs/heads/main'",
                "test \"${{ inputs.confirm }}\" = \"deploy-prod\"",
                "backend/scripts/release_rings.py validate-record",
                "Require a non-held beta-soaked record before prod promotion",
                "Checkout the immutable record source for deployment rendering",
                "ref: ${{ steps.record.outputs.git_sha }}",
                "render_backend_runtime_env.py",
                "--update-secrets",
                "backend/scripts/deploy-backend-secrets.sh",
                "Verify beta endpoint prerequisites before mutation",
                "cloud_run_traffic_snapshot.py capture",
                "--no-traffic",
                "cloud_run_traffic_snapshot.py restore",
                "gcloud run services delete",
                "state=partial_mutation",
                "--hold",
                "--if-generation-match=\"$generation\"",
                "workload_identity_provider:",
                "PAGER_WEBHOOK",
                "smoke_cloud_run_health.py",
                "transcription-release-candidate-probe",
                "Gate beta candidate on authenticated known-audio transcription",
            ),
        )
    )
    for path, text in ((record_path, record), (deploy_path, deploy)):
        if "credentials_json:" in text:
            errors.append(f"{path}: release-ring workflows must use ring-bound OIDC, not JSON credentials")
    if "release_sha:" in deploy or "branch:" in deploy or "image:" in deploy:
        errors.append(f"{deploy_path}: deploy accepts free-form source or image input")
    topology_path = ROOT / "backend/deploy/release_rings.yaml"
    if not topology_path.exists() or "backend: backend-beta" not in topology_path.read_text(encoding="utf-8"):
        errors.append("backend/deploy/release_rings.yaml: beta must use distinct Cloud Run service identities")
    return errors


if __name__ == "__main__":
    problems = check()
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    raise SystemExit(bool(problems))
