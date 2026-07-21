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
AUTO_ADMISSION_VERIFIER_PATH = Path(".github/scripts/verify_auto_backend_release_admission.py")
AUTO_PROOF_SHA = "${{ github.event.workflow_run.head_sha }}"
AUTO_PROOF_RUN_ATTEMPT = "${{ github.event.workflow_run.run_attempt }}"
AUTO_FIRESTORE_ADMITTED_SHA = "${{ steps.admitted_source.outputs.admitted_sha }}"
AUTO_DEPLOY_ADMITTED_SHA = "${{ needs.firestore_readiness.outputs.admitted_sha }}"
MANUAL_ADMITTED_SHA = "${{ needs.firestore_readiness.outputs.admitted_sha }}"
AUTO_SOURCE_ADMISSION_CONDITION = "\n".join(
    (
        "needs.scope.outputs.applies == 'true' &&",
        "github.event.workflow_run.conclusion == 'success' &&",
        "github.event.workflow_run.event == 'push' &&",
        "github.event.workflow_run.run_attempt == 1 &&",
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
MANUAL_DEPLOY_NEEDS = "needs: [validate-production-boundary, firestore_readiness]"


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
    indices = named_step_indices(text, name)
    if not indices:
        errors.append(f"backend source admission is missing its {label} step")
        return ""
    if len(indices) != 1:
        errors.append(f"backend source admission must contain exactly one {label} step")
        return ""
    return named_step_block(text, name, 6) or ""


def named_step_indices(text: str, name: str, indent: int = 6) -> list[int]:
    marker = f"{' ' * indent}- name: {name}"
    return [match.start() for match in re.finditer(rf"(?m)^{re.escape(marker)}$", text)]


def named_step_index(text: str, name: str, indent: int = 6) -> int | None:
    indices = named_step_indices(text, name, indent)
    return indices[0] if len(indices) == 1 else None


def validate_fail_closed_step(errors: list[str], step: str, label: str) -> None:
    """Reject conditions and shell fallbacks on an automatic source guard."""

    if re.search(r"(?m)^        [\"']?(?:if|continue-on-error)[\"']?:", step):
        errors.append(f"{label} must not be conditionally skipped or tolerated")
    if "        set -euo pipefail" not in step:
        errors.append(f"{label} must enable strict shell failure handling")
    if re.search(r"\|\|\s*(?:true\b|:|exit\s+0\b)|\bset\s+\+(?:e|o\s+(?:errexit|pipefail))\b", step):
        errors.append(f"{label} must not contain a shell fail-open path")


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
    readiness_steps = None if firestore_job is None else mapping_block(firestore_job, "steps", 4)
    scope_job = mapping_block(text, "scope", 2)
    scope_steps = None if scope_job is None else mapping_block(scope_job, "steps", 4)
    if scope_job is None:
        errors.append("auto backend deploy is missing its unprivileged scope decision job")
    else:
        require_fragment(
            errors,
            scope_job,
            "permissions:\n      contents: 'read'",
            "auto backend scope decision must remain contents-read-only",
        )
        if "environment:" in scope_job:
            errors.append("auto backend scope decision must not receive a deployment environment")
        if "google-github-actions/auth" in scope_job or "gcloud" in scope_job:
            errors.append("auto backend scope decision must not authenticate to cloud services")
    if scope_steps is None:
        errors.append("auto backend deploy scope decision must contain its steps")
    else:
        scope_checkout = require_step(
            errors,
            scope_steps,
            "Checkout triggering main commit for scope decision",
            "triggering-commit scope checkout",
        )
        for fragment, message in (
            (f"ref: {AUTO_PROOF_SHA}", "auto backend scope decision must inspect the triggering SHA"),
            ("fetch-depth: 2", "auto backend scope decision must shallow-fetch only the triggering parent diff"),
        ):
            require_fragment(errors, scope_checkout, fragment, message)
        if "fetch-depth: 0" in scope_checkout:
            errors.append("auto backend scope decision must not fetch full history")
        scope_decision = require_step(
            errors,
            scope_steps,
            "Decide whether the triggering commit can affect the backend deployment",
            "backend deployment scope decision",
        )
        for fragment, message in (
            (f"GH_TOKEN: ${{{{ github.token }}}}", "auto backend scope decision must use its read-only GitHub token"),
            (f"RELEASE_SHA: {AUTO_PROOF_SHA}", "auto backend scope decision must bind the triggering SHA"),
            (
                '"$api_base/repos/$GITHUB_REPOSITORY/git/ref/heads/main"',
                "auto backend scope decision must resolve current main through the bounded GitHub ref API",
            ),
            (
                '"$api_base/repos/$GITHUB_REPOSITORY/compare/$RELEASE_SHA...$main_sha"',
                "auto backend scope decision must compare the immutable triggering SHA to the resolved main SHA through GitHub",
            ),
            (
                'if .ref == "refs/heads/main" and .object.type == "commit"',
                "auto backend scope decision must bind the current-main ref response identity",
            ),
            (
                '.base_commit.sha == $release_sha and .head_commit.sha == $main_sha',
                "auto backend scope decision must bind compare base and head identities",
            ),
            (
                '.status == "behind"',
                "auto backend scope decision must require GitHub's behind status for a superseded no-op",
            ),
            (
                'if [[ "$comparison" == "behind" ]]; then',
                "auto backend scope decision must only no-op after confirmed supersession",
            ),
            (
                "supersession API proof was unavailable or ambiguous; preserving fail-closed source admission",
                "auto backend scope decision must treat API or identity ambiguity as guarded admission",
            ),
            ("echo \"applies=true\" >> \"$GITHUB_OUTPUT\"", "auto backend scope decision must continue to guarded admission when supersession is uncertain"),
            ("echo \"applies=false\" >> \"$GITHUB_OUTPUT\"", "auto backend scope decision must publish a no-op result"),
            (
                "Backend development deploy superseded no-op",
                "auto backend scope decision must summarize superseded candidates as green no-ops",
            ),
            (
                "GitHub compare confirmed triggering SHA $RELEASE_SHA is behind current main $main_sha",
                "auto backend scope decision must name both bound SHAs in a superseded summary",
            ),
            ("git rev-parse \"${RELEASE_SHA}^\"", "auto backend scope decision must inspect the triggering parent"),
            (
                "git diff --name-only \"$parent_sha\" \"$RELEASE_SHA\"",
                "auto backend scope decision must diff the triggering SHA against its parent",
            ),
            ("Green no-op", "auto backend scope decision must summarize green no-ops"),
        ):
            require_fragment(errors, scope_decision, fragment, message)
        fallback_summary = "supersession API proof was unavailable or ambiguous; preserving fail-closed source admission"
        if scope_decision.count(fallback_summary) != 2:
            errors.append("auto backend scope decision must treat API or identity ambiguity as guarded admission")
        for forbidden, message in (
            ("git fetch --no-tags", "auto backend scope decision must not fetch local main history for supersession"),
            ("git merge-base", "auto backend scope decision must not use local merge-base supersession proof"),
            ("origin/main", "auto backend scope decision must not resolve local origin/main for supersession"),
        ):
            if forbidden in scope_decision:
                errors.append(message)
    if firestore_job is None:
        errors.append("auto backend deploy is missing its source-admission job")
    else:
        require_fragment(
            errors,
            firestore_job,
            "needs: scope",
            "auto source-admission job must depend on the scope decision",
        )
        condition = folded_job_condition(firestore_job)
        if condition != AUTO_SOURCE_ADMISSION_CONDITION:
            errors.append(
                "auto source-admission job must use exactly the fail-closed Release Eligibility predicate"
            )
        require_fragment(
            errors,
            firestore_job,
            "outputs:\n      admitted_sha: ${{ steps.admitted_source.outputs.admitted_sha }}",
            "auto source-admission job must publish one admitted SHA",
        )
    if readiness_steps is None:
        errors.append("auto backend deploy source-admission job must contain its steps")
    else:
        main_checkout = require_step(
            errors,
            readiness_steps,
            "Checkout current main for automatic source admission",
            "current-main automatic admission checkout",
        )
        for fragment, message in (
            ("ref: main", "automatic source admission must check out current main"),
            ("fetch-depth: 0", "automatic source admission must fetch current main ancestry"),
        ):
            require_fragment(errors, main_checkout, fragment, message)

        admission = require_step(
            errors,
            readiness_steps,
            "Verify Release Eligibility proof is current main",
            "automatic release-proof freshness validation",
        )
        validate_fail_closed_step(errors, admission, "automatic release-proof freshness validation")
        for fragment, message in (
            (f"RELEASE_SHA: {AUTO_PROOF_SHA}", "automatic source admission must bind the proof SHA"),
            (
                f"RELEASE_RUN_ATTEMPT: {AUTO_PROOF_RUN_ATTEMPT}",
                "automatic source admission must bind the proof run attempt",
            ),
            (
                "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main",
                "automatic source admission must refresh current main",
            ),
            (
                "main_sha=\"$(git rev-parse --verify 'origin/main^{commit}')\"",
                "automatic source admission must resolve current main's immutable SHA",
            ),
            (
                "checkout_sha=\"$(git rev-parse --verify HEAD)\"",
                "automatic source admission must resolve the current-main guard checkout SHA",
            ),
            (
                ".github/scripts/verify_auto_backend_release_admission.py",
                "automatic source admission must verify proof freshness and current main identity",
            ),
            ("--sha \"$RELEASE_SHA\"", "automatic source admission must verify the proof SHA"),
            ("--main-sha \"$main_sha\"", "automatic source admission must verify current main"),
            (
                "--checkout-sha \"$checkout_sha\"",
                "automatic source admission must verify the current-main guard checkout",
            ),
            (
                "--run-attempt \"$RELEASE_RUN_ATTEMPT\"",
                "automatic source admission must reject proof reruns",
            ),
            (
                "printf 'admitted_sha=%s\\n' \"$RELEASE_SHA\" >> \"$GITHUB_OUTPUT\"",
                "automatic source admission must publish the verified SHA",
            ),
        ):
            require_fragment(errors, admission, fragment, message)

        require_step(
            errors,
            readiness_steps,
            "Require read-only Firestore credentials",
            "read-only Firestore credential boundary",
        )
        require_step(
            errors,
            readiness_steps,
            "Checkout admitted Firestore source",
            "admitted-source checkout",
        )
        require_step(
            errors,
            readiness_steps,
            "Google Auth for read-only Firestore inventory",
            "read-only Firestore inventory authentication",
        )
        admission_index = named_step_index(readiness_steps, "Verify Release Eligibility proof is current main")
        credential_index = named_step_index(readiness_steps, "Require read-only Firestore credentials")
        checkout_index = named_step_index(readiness_steps, "Checkout admitted Firestore source")
        auth_index = named_step_index(readiness_steps, "Google Auth for read-only Firestore inventory")
        if admission_index is not None and credential_index is not None and admission_index > credential_index:
            errors.append("automatic release-proof freshness validation must run before read-only credential use")
        if admission_index is not None and checkout_index is not None and admission_index > checkout_index:
            errors.append("automatic release-proof freshness validation must run before admitted-source checkout or execution")
        if admission_index is not None and auth_index is not None and admission_index > auth_index:
            errors.append("automatic release-proof freshness validation must run before read-only Firestore authentication")
        if credential_index is not None and checkout_index is not None and credential_index > checkout_index:
            errors.append("read-only credential use must run before admitted-source checkout")
        if checkout_index is not None and auth_index is not None and checkout_index > auth_index:
            errors.append("admitted-source checkout must run before read-only Firestore authentication")

    deploy_job = mapping_block(text, "deploy", 2)
    if deploy_job is None or "    needs: firestore_readiness" not in (deploy_job or ""):
        errors.append("auto backend deploy must depend on the source-admission job")
    elif re.search(r"(?m)^    if:", deploy_job):
        errors.append("auto backend deploy must not override source-admission dependency")

    if "github.sha" in text:
        errors.append("auto backend deploy must not use github.sha after workflow_run admission")
    if text.count(AUTO_PROOF_SHA) != 3:
        errors.append("auto backend deploy must use workflow_run.head_sha only in scope decision and current-main admission guard")
    if text.count(AUTO_PROOF_RUN_ATTEMPT) != 1:
        errors.append("auto backend deploy must use workflow_run.run_attempt only in the source-admission guard")
    if text.count(f"ref: {AUTO_FIRESTORE_ADMITTED_SHA}") != 1:
        errors.append("auto backend deploy must check out the verified SHA before Firestore readiness")
    if text.count(f"FIRESTORE_SOURCE_COMMIT: {AUTO_FIRESTORE_ADMITTED_SHA}") != 2:
        errors.append("auto backend deploy must bind Firestore readiness to the verified SHA")
    if text.count(f"ref: {AUTO_DEPLOY_ADMITTED_SHA}") != 1:
        errors.append("auto backend deploy must check out the verified SHA before deployment")
    if text.count(f'--commit-sha "{AUTO_DEPLOY_ADMITTED_SHA}"') != 3:
        errors.append("auto backend deploy must bind every release vector to the verified SHA")
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
    require_fragment(
        errors,
        firestore_job,
        "needs: validate-production-boundary",
        "manual source admission must wait for production-boundary validation",
    )
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
        (
            "git fetch --no-tags origin +refs/heads/main:refs/remotes/origin/main",
            "manual source admission must fetch the current main ancestry",
        ),
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
            MANUAL_DEPLOY_NEEDS,
            "manual deployment must depend on production-boundary validation and source admission",
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
    paths = (AUTO_WORKFLOW_PATH, MANUAL_WORKFLOW_PATH, ADMISSION_VERIFIER_PATH, AUTO_ADMISSION_VERIFIER_PATH)
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
