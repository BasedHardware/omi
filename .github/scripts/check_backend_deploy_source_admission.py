#!/usr/bin/env python3
"""Keep backend deployment source selection bound to Release Eligibility."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTO_WORKFLOW_PATH = Path(".github/workflows/gcp_backend_auto_dev.yml")
MANUAL_WORKFLOW_PATH = Path(".github/workflows/gcp_backend.yml")
ADMISSION_VERIFIER_PATH = Path(".github/scripts/verify_backend_release_admission.py")
ADMITTED_SHA = "${{ github.event.workflow_run.head_sha }}"
MANUAL_ADMITTED_SHA = "${{ needs.firestore_readiness.outputs.admitted_sha }}"
AUTO_SOURCE_ADMISSION_CONDITION = "\n".join(
    (
        "github.event.workflow_run.conclusion == 'success' &&",
        "github.event.workflow_run.event == 'push' &&",
        "github.event.workflow_run.head_branch == 'main' &&",
        "github.event.workflow_run.head_repository.full_name == github.repository",
    )
)
MANUAL_DEPLOY_CONDITION = "\n".join(
    (
        "github.ref == 'refs/heads/main' &&",
        "github.event.inputs.mode == 'deploy'",
    )
)
MANUAL_TRAFFIC_REPAIR_CONDITION = "\n".join(
    (
        "github.ref == 'refs/heads/main' &&",
        "github.event.inputs.mode == 'repair-traffic-only'",
    )
)


def require_fragment(errors: list[str], text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        errors.append(message)


def mapping_block(text: str, key: str, indent: int) -> str | None:
    """Return a fixed-indentation YAML mapping block without a YAML dependency."""

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
    """Return one named workflow step, stopping before the next peer step."""

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


def require_step(errors: list[str], text: str, name: str, label: str) -> str:
    step = named_step_block(text, name, 6)
    if step is None:
        errors.append(f"backend source admission is missing its {label} step")
        return ""
    return step


def folded_job_condition(job: str) -> str | None:
    """Return an exact folded job-level ``if: >-`` condition.

    Deployment job guards are intentionally fail-closed. Checking individual
    substrings would allow a future ``|| true`` to retain every predicate while
    making a source or ref guard permissive.
    """

    match = re.search(r"(?m)^    if: >-\n(?P<condition>(?:      [^\n]*(?:\n|$))*)", job)
    if match is None:
        return None
    return "\n".join(line[6:] for line in match.group("condition").splitlines()).strip()


def validate_auto_workflow(text: str) -> list[str]:
    errors: list[str] = []
    on_block = mapping_block(text, "on", 0)
    trigger_keys = (
        []
        if on_block is None
        else [
            match.group("key").strip("\"'")
            for match in re.finditer(r"(?m)^  (?P<key>[\"']?[A-Za-z_]+[\"']?):", on_block)
        ]
    )
    if trigger_keys != ["workflow_run"]:
        errors.append("auto backend deploy must trigger only from workflow_run")
    for fragment, message in (
        (
            '  workflow_run:\n    workflows: ["Release Eligibility"]\n    branches: [main]\n    types: [completed]',
            "auto backend deploy must consume completed Release Eligibility runs on main",
        ),
    ):
        require_fragment(errors, text, fragment, message)

    firestore_job = mapping_block(text, "firestore_readiness", 2)
    if firestore_job is None:
        errors.append("auto backend deploy is missing its source-admission job")
    else:
        condition = folded_job_condition(firestore_job)
        if condition != AUTO_SOURCE_ADMISSION_CONDITION:
            errors.append(
                "auto source-admission job must use exactly the fail-closed Release Eligibility predicate"
            )

    deploy_job = mapping_block(text, "deploy", 2)
    if deploy_job is None or "    needs: firestore_readiness" not in (deploy_job or ""):
        errors.append("auto backend deploy must depend on the source-admission job")
    elif re.search(r"(?m)^    if:", deploy_job):
        errors.append("auto backend deploy must not override source-admission dependency")

    if "github.sha" in text:
        errors.append("auto backend deploy must not use github.sha after workflow_run admission")
    if text.count(f"ref: {ADMITTED_SHA}") != 2:
        errors.append("auto backend deploy must check out workflow_run.head_sha in both source jobs")
    if text.count(f"FIRESTORE_SOURCE_COMMIT: {ADMITTED_SHA}") != 2:
        errors.append("auto backend deploy must bind Firestore readiness to workflow_run.head_sha")
    if text.count(f'--commit-sha "{ADMITTED_SHA}"') != 3:
        errors.append("auto backend deploy must bind every release vector to workflow_run.head_sha")
    return errors


def validate_manual_workflow(text: str) -> list[str]:
    errors: list[str] = []
    on_block = mapping_block(text, "on", 0)
    trigger_keys = (
        []
        if on_block is None
        else [
            match.group("key").strip("\"'")
            for match in re.finditer(r"(?m)^  (?P<key>[\"']?[A-Za-z_]+[\"']?):", on_block)
        ]
    )
    if trigger_keys != ["workflow_dispatch"]:
        errors.append("manual backend deploy must retain only the explicit workflow_dispatch entrypoint")
    require_fragment(
        errors,
        text,
        "      release_sha:\n        description: 'Exact main SHA with a successful Release Eligibility proof (deploy mode only)'\n        required: false",
        "manual backend deploy must keep release_sha optional for traffic-only repair",
    )
    if "github.event.inputs.branch" in text or re.search(r"(?m)^      branch:\n", text):
        errors.append("manual backend deploy must not accept an arbitrary branch or ref")
    if "github.sha" in text:
        errors.append("manual backend deploy must not substitute the dispatch default SHA for admitted source")

    repair_job = mapping_block(text, "repair-traffic", 2)
    if repair_job is None:
        errors.append("manual backend deploy is missing the traffic-only repair path")
    else:
        if folded_job_condition(repair_job) != MANUAL_TRAFFIC_REPAIR_CONDITION:
            errors.append("traffic-only repair must use exactly the main-ref recovery condition")
        require_fragment(
            errors,
            repair_job,
            "ref: main",
            "traffic-only repair must check out the repository recovery script from main",
        )
        if "release_sha" in repair_job or "admitted_source" in repair_job:
            errors.append("traffic-only repair must not require a release-source admission")

    firestore_job = mapping_block(text, "firestore_readiness", 2)
    if firestore_job is None:
        errors.append("manual backend deploy is missing its source-admission job")
        return errors
    if folded_job_condition(firestore_job) != MANUAL_DEPLOY_CONDITION:
        errors.append("manual source admission must use exactly the main-ref deploy condition")
    for fragment, message in (
        ("actions: 'read'", "manual source admission must read the Release Eligibility workflow result"),
        (
            "admitted_sha: ${{ steps.admitted_source.outputs.admitted_sha }}",
            "manual source admission must publish one admitted SHA",
        ),
    ):
        require_fragment(errors, firestore_job, fragment, message)

    main_checkout = require_step(errors, text, "Checkout current main for source admission", "current-main checkout")
    for fragment, message in (
        ("ref: main", "manual source admission must inspect main"),
        ("fetch-depth: 0", "manual source admission must fetch main ancestry"),
    ):
        require_fragment(errors, main_checkout, fragment, message)

    admission = require_step(errors, text, "Verify exact admitted main source", "release-proof validation")
    for fragment, message in (
        ("DEPLOY_SHA: ${{ github.event.inputs.release_sha }}", "manual source admission must bind release_sha"),
        ("GH_TOKEN: ${{ github.token }}", "manual source admission must authenticate the proof query"),
        ("set -euo pipefail", "manual source admission must fail closed"),
        (
            '[[ ! "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ || "$DEPLOY_SHA" == "0000000000000000000000000000000000000000" ]]',
            "manual source admission must reject non-exact SHA inputs before querying GitHub",
        ),
        ("git fetch --no-tags origin main", "manual source admission must fetch the current main ancestry"),
        ("git cat-file -e \"${DEPLOY_SHA}^{commit}\"", "manual source admission must require a commit object"),
        (
            "git merge-base --is-ancestor \"$DEPLOY_SHA\" \"$main_sha\"",
            "manual source admission must require the requested SHA to be on main",
        ),
        (
            "actions/workflows/release-eligibility.yml/runs?event=push&branch=main&status=completed&head_sha=${DEPLOY_SHA}",
            "manual source admission must query the canonical main Release Eligibility workflow for the exact SHA",
        ),
        (
            ".github/scripts/verify_backend_release_admission.py",
            "manual source admission must verify the returned Release Eligibility proof",
        ),
        ("--sha \"$DEPLOY_SHA\"", "manual source admission must verify the requested SHA"),
        ("--repository \"$GITHUB_REPOSITORY\"", "manual source admission must verify the source repository"),
        ("--workflow-runs \"$proof_path\"", "manual source admission must verify the queried workflow runs"),
        ("printf 'admitted_sha=%s\\n' \"$DEPLOY_SHA\" >> \"$GITHUB_OUTPUT\"", "manual source admission must publish the checked SHA"),
    ):
        require_fragment(errors, admission, fragment, message)

    admitted_checkout = require_step(errors, text, "Checkout admitted Firestore source", "admitted-source checkout")
    require_fragment(
        errors,
        admitted_checkout,
        "ref: ${{ steps.admitted_source.outputs.admitted_sha }}",
        "manual backend deploy must check out the admitted SHA",
    )

    deploy_job = mapping_block(text, "deploy", 2)
    if deploy_job is None:
        errors.append("manual backend deploy is missing its deployment job")
    else:
        require_fragment(
            errors,
            deploy_job,
            "needs: firestore_readiness",
            "manual deployment must depend on source admission",
        )
        if folded_job_condition(deploy_job) != MANUAL_DEPLOY_CONDITION:
            errors.append("manual deployment must use exactly the main-ref deploy condition")
        require_fragment(
            errors,
            deploy_job,
            f"ref: {MANUAL_ADMITTED_SHA}",
            "manual deployment must check out the admitted SHA",
        )
        if deploy_job.count(f'--commit-sha "{MANUAL_ADMITTED_SHA}"') != 3:
            errors.append("manual deployment must bind every release vector to the admitted SHA")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    paths = (AUTO_WORKFLOW_PATH, MANUAL_WORKFLOW_PATH, ADMISSION_VERIFIER_PATH)
    missing = [str(path) for path in paths if not (root / path).is_file()]
    if missing:
        return [f"backend source-admission contract is missing: {path}" for path in missing]
    errors = validate_auto_workflow((root / AUTO_WORKFLOW_PATH).read_text(encoding="utf-8"))
    errors.extend(validate_manual_workflow((root / MANUAL_WORKFLOW_PATH).read_text(encoding="utf-8")))
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("backend deploy source-admission contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
