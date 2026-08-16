#!/usr/bin/env python3
"""Keep the admin deploy scope gate ahead of environment: prod."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = Path(".github/workflows/gcp_admin.yml")
CLASSIFIER_PATH = Path(".github/scripts/check_admin_deploy_scope.py")
LOCK_GROUP = (
    "deploy-cloud-run-omi-admin-dashboard-${{ github.event_name == 'workflow_dispatch' && "
    "github.event.inputs.environment || github.ref == 'refs/heads/development' && 'development' || "
    "github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id) }}"
)
DEPLOY_ENVIRONMENT = (
    "environment: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || "
    "(github.ref == 'refs/heads/development' && 'development') || 'prod' }}"
)
SCOPE_CONDITION = "needs.scope.outputs.applies == 'true'"


def mapping_block(text: str, key: str, indent: int) -> str | None:
    lines = text.splitlines()
    marker = f"{' ' * indent}{key}:"
    try:
        start = lines.index(marker)
    except ValueError:
        return None
    body: list[str] = []
    for line in lines[start + 1 :]:
        if line and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return "\n".join(body)


def named_step_block(text: str, name: str, indent: int) -> str | None:
    lines = text.splitlines()
    marker = f"{' ' * indent}- name: {name}"
    try:
        start = lines.index(marker)
    except ValueError:
        return None
    body = [lines[start]]
    peer = f"{' ' * indent}- "
    for line in lines[start + 1 :]:
        if line.startswith(peer):
            break
        body.append(line)
    return "\n".join(body)


def require_fragment(errors: list[str], text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        errors.append(message)


def validate_workflow(text: str) -> list[str]:
    errors: list[str] = []
    concurrency = mapping_block(text, "concurrency", 0)
    if concurrency is None:
        errors.append("admin deploy is missing its workflow-level concurrency block")
    else:
        require_fragment(errors, concurrency, f"group: {LOCK_GROUP}", "admin deploy must keep the existing lock group")
        require_fragment(
            errors,
            concurrency,
            "cancel-in-progress: false",
            "admin deploy must keep cancel-in-progress: false",
        )

    require_fragment(
        errors,
        text,
        "      - '.github/workflows/gcp_admin.yml'",
        "admin deploy path filter must include this workflow",
    )

    scope_job = mapping_block(text, "scope", 2)
    if scope_job is None:
        errors.append("admin deploy is missing its unprivileged scope decision job")
        return errors

    require_fragment(
        errors,
        scope_job,
        "permissions:\n      contents: read",
        "admin scope decision must remain contents-read-only",
    )
    if re.search(r"(?m)^    environment:", scope_job):
        errors.append("admin scope decision must not receive a deployment environment")
    if "google-github-actions/auth" in scope_job or "gcloud" in scope_job or "id-token: write" in scope_job:
        errors.append("admin scope decision must not authenticate to cloud services")

    checkout = named_step_block(scope_job, "Checkout triggering commit for scope decision", 6)
    if checkout is None:
        errors.append("admin scope decision is missing its triggering-commit checkout")
    else:
        require_fragment(
            errors,
            checkout,
            "fetch-depth: 2",
            "admin scope decision must shallow-fetch only the triggering parent diff",
        )
        if "fetch-depth: 0" in checkout:
            errors.append("admin scope decision must not fetch full history")

    decision = named_step_block(
        scope_job,
        "Decide whether the triggering commit can affect the admin deployment",
        6,
    )
    if decision is None:
        errors.append("admin scope decision is missing its classifier step")
    else:
        require_fragment(
            errors,
            decision,
            ".github/scripts/check_admin_deploy_scope.py --github-output",
            "admin scope decision must use the shared admin deploy classifier",
        )
        require_fragment(
            errors,
            decision,
            "EVENT_NAME: ${{ github.event_name }}",
            "admin scope decision must bind the GitHub event name",
        )
        if re.search(r"(?m)^        [\"']?(?:if|continue-on-error)[\"']?:", decision):
            errors.append("admin scope decision must not be conditionally skipped or tolerated")

    deploy_job = mapping_block(text, "deploy", 2)
    if deploy_job is None:
        errors.append("admin deploy is missing its deployment job")
        return errors

    require_fragment(errors, deploy_job, "needs: scope", "admin deploy job must depend on the scope decision")
    require_fragment(
        errors,
        deploy_job,
        f"if: {SCOPE_CONDITION}",
        "admin deploy job must take the environment slot only when scope applies",
    )
    require_fragment(
        errors,
        deploy_job,
        DEPLOY_ENVIRONMENT,
        "admin deploy job must keep the existing environment: prod expression",
    )
    if deploy_job.find("needs: scope") > deploy_job.find(DEPLOY_ENVIRONMENT):
        errors.append("admin deploy job must decide scope before receiving a deployment environment")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    missing = [str(path) for path in (WORKFLOW_PATH, CLASSIFIER_PATH) if not (root / path).is_file()]
    if missing:
        return [f"admin deploy scope contract is missing: {path}" for path in missing]
    return validate_workflow((root / WORKFLOW_PATH).read_text(encoding="utf-8"))


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("admin deploy scope-admission contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
