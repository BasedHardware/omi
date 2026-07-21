#!/usr/bin/env python3
"""Fail closed if the production-only backend release vector regains a beta ring."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_RELEASE_SOURCES = (
    Path("backend/deploy/release_rings.yaml"),
    Path("backend/scripts/render_release_ring_config.py"),
    Path(".github/workflows/release-record.yml"),
    Path(".github/workflows/deploy-release-ring.yml"),
)


def require(text: str, path: Path, fragments: tuple[str, ...]) -> list[str]:
    return [
        f"{path}: missing required release-vector guard {fragment!r}" for fragment in fragments if fragment not in text
    ]


def check() -> list[str]:
    paths = {relative: ROOT / relative for relative in BACKEND_RELEASE_SOURCES}
    errors = [f"{path}: release-vector source is missing" for path in paths.values() if not path.exists()]
    if errors:
        return errors

    record = paths[Path(".github/workflows/release-record.yml")].read_text(encoding="utf-8")
    deploy = paths[Path(".github/workflows/deploy-release-ring.yml")].read_text(encoding="utf-8")
    errors.extend(
        require(
            record,
            paths[Path(".github/workflows/release-record.yml")],
            (
                "workflow_run:",
                'workflows: ["Release Eligibility"]',
                "github.event.workflow_run.head_sha",
                "docker/build-push-action@v7",
                "backend/scripts/release_rings.py create-record",
                "backend/scripts/release_rings.py materialize-runtime",
                "gcloud storage cp --if-generation-match=0",
                "workload_identity_provider:",
            ),
        )
    )
    errors.extend(
        require(
            deploy,
            paths[Path(".github/workflows/deploy-release-ring.yml")],
            (
                "group: deploy-backend-stack-prod",
                "environment: prod",
                "github.ref == 'refs/heads/main'",
                "RELEASE_RING: prod",
                "RELEASE_ID: ${{ inputs.release_id }}",
                'test "$PROD_CONFIRM" = "deploy-prod"',
                "backend/scripts/release_rings.py validate-record",
                "Checkout immutable release source inputs",
                "ref: ${{ steps.record.outputs.git_sha }}",
                "Preflight all recorded GKE configuration before mutation",
                "--dry-run=server",
                "DRY_RUN=true",
                "backend/scripts/deploy-backend-secrets.sh",
                "cloud_run_traffic_snapshot.py capture",
                "release_ring_gke_snapshot.py capture",
                "--no-traffic",
                "cloud_run_traffic_snapshot.py restore",
                "release_ring_gke_snapshot.py restore",
                "wait_external_secret_refresh.py",
                "Verify serving release vector",
                "backend/scripts/verify_backend_release_vector.py",
                '--commit-sha "${{ steps.record.outputs.git_sha }}"',
                '--deploy-run-id "$GITHUB_RUN_ID"',
                '--deploy-run-attempt "$GITHUB_RUN_ATTEMPT"',
                '--expected-image "${{ steps.record.outputs.backend_image }}"',
                "--hold",
                "workload_identity_provider:",
            ),
        )
    )
    promotion = deploy.find("Shift validated Cloud Run revisions to serving traffic")
    verification = deploy.find("Verify serving release vector")
    if promotion < 0 or verification < 0 or verification <= promotion:
        errors.append("release-ring serving release-vector verification must follow traffic promotion")
    if "credentials_json:" in record or "credentials_json:" in deploy:
        errors.append("release-vector workflows must use OIDC, not JSON credentials")
    if deploy.count("${{ inputs.release_id }}") != 1 or deploy.count("${{ inputs.confirm }}") != 1:
        errors.append("deploy dispatch inputs must enter shell only through the job environment")
    for relative, path in paths.items():
        if "beta" in path.read_text(encoding="utf-8").lower():
            errors.append(f"{relative}: backend beta-ring logic is forbidden")
    return errors


if __name__ == "__main__":
    problems = check()
    for problem in problems:
        print(f"ERROR: {problem}", file=sys.stderr)
    raise SystemExit(bool(problems))
