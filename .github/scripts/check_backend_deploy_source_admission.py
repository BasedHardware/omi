#!/usr/bin/env python3
"""Keep backend deployment source selection bound to Release Eligibility."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / ".github" / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from workflow_composite_contract import backend_deploy_contract_text

AUTO_WORKFLOW_PATH = Path(".github/workflows/gcp_backend_auto_dev.yml")
MANUAL_WORKFLOW_PATH = Path(".github/workflows/gcp_backend.yml")
DEPLOY_BACKEND_STACK_ACTION = Path(".github/actions/deploy-backend-stack/action.yml")
FIRESTORE_READINESS_ACTION = Path(".github/actions/firestore-readiness/action.yml")
ADMISSION_VERIFIER_PATH = Path(".github/scripts/verify_backend_release_admission.py")
AUTO_ADMISSION_VERIFIER_PATH = Path(".github/scripts/verify_auto_backend_release_admission.py")
FIRESTORE_CONTROL_CHECKOUT_STEP = "Checkout immutable Firestore gate controls"
FIRESTORE_GATE_STEP = "Verify serving Firestore indexes"
FIRESTORE_GATE_USES = "./.github/firestore-workflow/.github/actions/firestore-readiness"
AUTO_PROOF_SHA = "${{ github.event.workflow_run.head_sha }}"
AUTO_PROOF_RUN_ATTEMPT = "${{ github.event.workflow_run.run_attempt }}"
AUTO_ADMITTED_SHA = "${{ needs.admit_source.outputs.admitted_sha }}"
AUTO_DEPLOY_ADMITTED_SHA = "${{ needs.firestore_readiness.outputs.admitted_sha }}"
MANUAL_ADMITTED_SHA = "${{ needs.firestore_readiness.outputs.admitted_sha }}"
AUTO_SOURCE_ADMISSION_CONDITION = "\n".join(
    (
        "(needs.scope.outputs.applies == 'true' || needs.scope.outputs.workerd == 'true') &&",
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
        "(github.event.inputs.mode == 'deploy' || github.event.inputs.mode == 'build-only' || github.event.inputs.mode == 'workerd-image-only' || github.event.inputs.mode == 'workerd-install' || github.event.inputs.mode == 'workerd-rollback')",
    )
)
MANUAL_TRAFFIC_REPAIR_CONDITION = "\n".join(
    (
        "github.ref == 'refs/heads/main' &&",
        "github.event.inputs.mode == 'repair-traffic-only'",
    )
)
MANUAL_DEPLOY_JOB_NEEDS = "needs: [validate-production-boundary, firestore_readiness, record_break_glass]"
_MANUAL_ADMITTED_JOB_CONDITION = "\n".join(
    (
        "always() &&",
        "github.ref == 'refs/heads/main' &&",
        "github.event.inputs.mode == 'deploy' &&",
        "needs.validate-production-boundary.result == 'success' &&",
        "needs.firestore_readiness.result == 'success' &&",
        "(needs.record_break_glass.result == 'success' || needs.record_break_glass.result == 'skipped')",
    )
)
# SCA-3120: the stack deploy job never runs for the explicit projection pump selection;
# deploy-projection-pump owns that singleton under the same admission jobs.
MANUAL_DEPLOY_JOB_CONDITION = _MANUAL_ADMITTED_JOB_CONDITION.replace(
    "github.event.inputs.mode == 'deploy' &&",
    "github.event.inputs.mode == 'deploy' &&\ngithub.event.inputs.cloud_run_service != 'backend-projection-pump' &&",
)
MANUAL_PROJECTION_PUMP_JOB_CONDITION = _MANUAL_ADMITTED_JOB_CONDITION.replace(
    "github.event.inputs.mode == 'deploy' &&",
    "github.event.inputs.mode == 'deploy' &&\n"
    "github.event.inputs.environment == 'prod' &&\n"
    "github.event.inputs.cloud_run_service == 'backend-projection-pump' &&",
)
MANUAL_BUILD_ONLY_JOB_CONDITION = _MANUAL_ADMITTED_JOB_CONDITION.replace(
    "github.event.inputs.mode == 'deploy' &&", "github.event.inputs.mode == 'build-only' &&"
).replace("always() &&", "always() && !cancelled() &&", 1)
MANUAL_BUILD_ONLY_HEAD_CHECK = '"$head_sha" != "$ADMITTED_SHA"'
MANUAL_BUILD_ONLY_SMOKE = "runtime_image_contracts.py smoke"
MANUAL_BUILD_ONLY_PUSH = 'docker push "$IMAGE"'
MANUAL_BUILD_ONLY_ADMITTED_CHECKOUT = "ref: ${{ needs.firestore_readiness.outputs.admitted_sha }}"
# build-only publishes an image and must never reach a serving surface.
MANUAL_BUILD_ONLY_FORBIDDEN = (
    "deploy-backend-stack",
    "deploy-cloudrun",
    "gcloud run",
    "gcloud container clusters",
    "get-gke-credentials",
    "kubectl",
    "setup-helm",
    "helm upgrade",
    "helm install",
    "helm rollback",
    "update-traffic",
    "repair_cloud_run_traffic",
    "set-env-vars",
    "update-env-vars",
    ":latest",
    "push: true",
    "cache-to:",
    "ensure_",
)


def deploy_backend_stack_action_text(root: Path = ROOT) -> str:
    return (root / DEPLOY_BACKEND_STACK_ACTION).read_text(encoding="utf-8")


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


def validate_firestore_gate_steps(
    errors: list[str],
    readiness_steps: str,
    *,
    source_sha_binding: str,
    verify_credential_project: str | None,
    label: str,
) -> None:
    """Pin the Firestore readiness gate to the shared immutable composite."""

    control_checkout = require_step(
        errors,
        readiness_steps,
        FIRESTORE_CONTROL_CHECKOUT_STEP,
        f"{label} immutable gate-control checkout",
    )
    for fragment, message in (
        ("uses: actions/checkout@v7", f"{label} must stage gate controls with actions/checkout"),
        ("ref: ${{ github.workflow_sha }}", f"{label} must stage gate controls from the workflow's immutable commit"),
        ("path: .github/firestore-workflow", f"{label} must stage gate controls under .github/firestore-workflow"),
        ("persist-credentials: false", f"{label} gate-control checkout must not persist credentials"),
    ):
        require_fragment(errors, control_checkout, fragment, message)
    if re.search(r"(?m)^        [\"']?(?:if|continue-on-error)[\"']?:", control_checkout):
        errors.append(f"{label} immutable gate-control checkout must not be conditionally skipped or tolerated")

    gate = require_step(
        errors,
        readiness_steps,
        FIRESTORE_GATE_STEP,
        f"{label} Firestore readiness gate",
    )
    for fragment, message in (
        (f"uses: {FIRESTORE_GATE_USES}", f"{label} must run the shared Firestore readiness composite"),
        (f"source_sha: {source_sha_binding}", f"{label} must bind the gate to the admitted source SHA"),
        ("project_id: ${{ vars.RUNTIME_GCP_PROJECT_ID }}", f"{label} must target the runtime project"),
        (
            "service_account: omi-ci-index-check@based-hardware.iam.gserviceaccount.com",
            f"{label} must pass the keyless index-check identity to the gate",
        ),
        (
            "workloadIdentityPools/omi-gha-deploy-",
            f"{label} must authenticate the gate through a deploy workload identity pool",
        ),
    ):
        require_fragment(errors, gate, fragment, message)
    if verify_credential_project is None:
        if "verify_credential_project" in gate:
            errors.append(f"{label} must leave credential-project verification at its default")
    else:
        require_fragment(
            errors,
            gate,
            f"verify_credential_project: '{verify_credential_project}'",
            f"{label} must verify the read-only credential project",
        )
    if re.search(r"(?m)^        [\"']?(?:if|continue-on-error)[\"']?:", gate):
        errors.append(f"{label} Firestore readiness gate must not be conditionally skipped or tolerated")

    control_index = named_step_index(readiness_steps, FIRESTORE_CONTROL_CHECKOUT_STEP)
    gate_index = named_step_index(readiness_steps, FIRESTORE_GATE_STEP)
    admitted_index = named_step_index(readiness_steps, "Checkout admitted Firestore source")
    if control_index is not None and admitted_index is not None and control_index < admitted_index:
        errors.append(f"{label} immutable gate controls must be staged after the admitted-source checkout")
    if control_index is not None and gate_index is not None and control_index > gate_index:
        errors.append(f"{label} must stage immutable gate controls before invoking the readiness composite")
    for forbidden, message in (
        ("FIRESTORE_SOURCE_COMMIT", f"{label} must not retain an inline Firestore source binding"),
        ("reconcile_firestore_indexes.py", f"{label} must not invoke the reconciler outside the composite"),
        ("google-github-actions/auth", f"{label} must not retain inline Firestore authentication"),
        ("--check-only", f"{label} must not retain an inline readiness check"),
        ("upload-artifact", f"{label} must not retain an inline proposal upload"),
    ):
        if forbidden in readiness_steps:
            errors.append(message)


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


def validate_auto_workflow(text: str, root: Path = ROOT) -> list[str]:
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

    admit_job = mapping_block(text, "admit_source", 2)
    admission_steps = None if admit_job is None else mapping_block(admit_job, "steps", 4)
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
        require_fragment(
            errors,
            scope_job,
            "outputs:\n      applies: ${{ steps.scope.outputs.applies }}\n      workerd: ${{ steps.scope.outputs.workerd }}",
            "auto backend scope decision must publish backend and workerd decisions",
        )
        scope_decision = require_step(
            errors,
            scope_steps,
            "Decide backend and workerd build scope",
            "backend and workerd build scope decision",
        )
        for fragment, message in (
            (f"RELEASE_SHA: {AUTO_PROOF_SHA}", "auto backend scope decision must bind the triggering SHA"),
            ("git rev-parse \"${RELEASE_SHA}^\"", "auto backend scope decision must inspect the triggering parent"),
            (
                "git diff --name-only \"$parent_sha\" \"$RELEASE_SHA\"",
                "auto backend scope decision must diff the triggering SHA against its parent",
            ),
            (
                "echo \"applies=true\" >> \"$GITHUB_OUTPUT\"",
                "auto backend scope decision must publish an in-scope result",
            ),
            ("echo \"applies=false\" >> \"$GITHUB_OUTPUT\"", "auto backend scope decision must publish a no-op result"),
            ("grep -Eq '^backend-go/' <<<\"$changed_files\"", "auto backend scope decision must select workerd source changes"),
            ("echo \"workerd=true\" >> \"$GITHUB_OUTPUT\"", "auto backend scope decision must publish workerd source changes"),
            ("echo \"workerd=false\" >> \"$GITHUB_OUTPUT\"", "auto backend scope decision must publish workerd no-ops"),
            ("Green no-op", "auto backend scope decision must summarize green no-ops"),
        ):
            require_fragment(errors, scope_decision, fragment, message)
        # Supersession must NOT be decided here. Skipping a triggering SHA for
        # being behind main strands a backend change whenever an unrelated
        # commit merges first: the backend commit no-ops for being behind and
        # the newer commit no-ops because its own diff is unrelated. Admission
        # resolves the newest proven commit instead, which subsumes
        # supersession without that hole.
        for forbidden, message in (
            ('"$comparison" == "behind"', "auto backend scope decision must not strand a behind triggering SHA"),
            ("/compare/$RELEASE_SHA...$main_sha", "auto backend scope decision must not decide supersession"),
            ("superseded no-op", "auto backend scope decision must not publish a superseded no-op"),
            ("git fetch --no-tags", "auto backend scope decision must not fetch local main history"),
            ("git merge-base", "auto backend scope decision must not compute local ancestry"),
            ("origin/main", "auto backend scope decision must not resolve local origin/main"),
        ):
            if forbidden in scope_decision:
                errors.append(message)
    if admit_job is None:
        errors.append("auto backend deploy is missing its source-admission job")
    else:
        require_fragment(
            errors,
            admit_job,
            "needs: scope",
            "auto source-admission job must depend on the scope decision",
        )
        require_fragment(
            errors,
            admit_job,
            "permissions:\n      actions: 'read'\n      contents: 'read'",
            "auto source-admission job must have only GitHub read permissions",
        )
        if any(fragment in admit_job for fragment in ("environment:", "id-token:", "google-github-actions/auth", "gcloud")):
            errors.append("auto source-admission job must not have cloud access")
        condition = folded_job_condition(admit_job)
        if condition != AUTO_SOURCE_ADMISSION_CONDITION:
            errors.append("auto source-admission job must use exactly the fail-closed Release Eligibility predicate")
        require_fragment(
            errors,
            admit_job,
            "outputs:\n      admitted_sha: ${{ steps.admitted_source.outputs.admitted_sha }}",
            "auto source-admission job must publish one admitted SHA",
        )
    if admission_steps is None:
        errors.append("auto backend deploy source-admission job must contain its steps")
    else:
        main_checkout = require_step(
            errors,
            admission_steps,
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
            admission_steps,
            "Resolve and verify the newest proven main source",
            "automatic release-proof freshness validation",
        )
        validate_fail_closed_step(errors, admission, "automatic release-proof freshness validation")
        main_index = named_step_index(admission_steps, "Checkout current main for automatic source admission")
        admission_index = named_step_index(admission_steps, "Resolve and verify the newest proven main source")
        if main_index is not None and admission_index is not None and admission_index < main_index:
            errors.append("automatic source admission must check out current main before verifying the proof")
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
                "actions/workflows/release-eligibility.yml/runs?event=push&branch=main&status=success",
                "automatic source admission must resolve the newest successful main Release Eligibility proof",
            ),
            (
                "curl --silent --show-error --fail",
                "automatic source admission must refuse to deploy on an unreadable proof listing",
            ),
            (
                'git merge-base --is-ancestor "$candidate_sha" "$main_sha"',
                "automatic source admission must only admit a candidate reachable from current main",
            ),
            (
                'git merge-base --is-ancestor "$RELEASE_SHA" "$admitted_sha"',
                "automatic source admission must prove the admitted SHA is not older than its trigger",
            ),
            (
                ".github/scripts/verify_auto_backend_release_admission.py",
                "automatic source admission must verify proof freshness and current main identity",
            ),
            ('--sha "$admitted_sha"', "automatic source admission must verify the resolved SHA"),
            ('--trigger-sha "$RELEASE_SHA"', "automatic source admission must verify the triggering proof SHA"),
            ('--main-sha "$main_sha"', "automatic source admission must verify current main"),
            (
                '--run-attempt "$RELEASE_RUN_ATTEMPT"',
                "automatic source admission must reject proof reruns",
            ),
            (
                '--sha-is-ancestor-of-main "$sha_is_ancestor_of_main"',
                "automatic source admission must verify merged-into-main ancestry",
            ),
            (
                '--trigger-is-ancestor-of-sha "$trigger_is_ancestor_of_sha"',
                "automatic source admission must refuse a target older than its trigger",
            ),
            (
                "printf 'admitted_sha=%s\\n' \"$admitted_sha\" >> \"$GITHUB_OUTPUT\"",
                "automatic source admission must publish the resolved SHA",
            ),
        ):
            require_fragment(errors, admission, fragment, message)
    if firestore_job is None or readiness_steps is None:
        errors.append("auto backend deploy is missing its Firestore readiness job")
    else:
        for fragment, message in (
            ("needs: [scope, admit_source]", "Firestore readiness must wait for source admission"),
            ("if: needs.scope.outputs.applies == 'true'\n", "Firestore readiness must run only for backend deployment"),
            (f"admitted_sha: {AUTO_ADMITTED_SHA}", "Firestore readiness must forward the checked SHA"),
        ):
            require_fragment(errors, firestore_job, fragment, message)
        checkout = require_step(
            errors, readiness_steps, "Checkout admitted Firestore source", "admitted Firestore source checkout"
        )
        require_fragment(errors, checkout, f"ref: {AUTO_ADMITTED_SHA}", "Firestore must check the admitted SHA")
        checkout_index = named_step_index(readiness_steps, "Checkout admitted Firestore source")
        gate_index = named_step_index(readiness_steps, FIRESTORE_GATE_STEP)
        if checkout_index is not None and gate_index is not None and checkout_index > gate_index:
            errors.append("admitted-source checkout must run before the Firestore readiness gate")
        validate_firestore_gate_steps(
            errors,
            readiness_steps,
            source_sha_binding=AUTO_ADMITTED_SHA,
            verify_credential_project="true",
            label="automatic backend source admission",
        )

    deploy_job = mapping_block(text, "deploy", 2)
    if deploy_job is None:
        errors.append("auto backend deploy is missing its deployment job")
    else:
        require_fragment(
            errors,
            deploy_job,
            "needs: [scope, firestore_readiness]",
            "auto backend deploy must depend on both scope and source admission",
        )
        require_fragment(
            errors,
            deploy_job,
            "if: needs.scope.outputs.applies == 'true'",
            "auto backend deploy must run only for backend changes",
        )
        if "needs.scope.outputs.workerd" in deploy_job:
            errors.append("auto backend deployment must not be triggered by workerd-only changes")

    publish_job = mapping_block(text, "publish_workerd", 2)
    if publish_job is None:
        errors.append("auto backend deploy is missing its workerd image publishing job")
    else:
        for fragment, message in (
            ("needs: [scope, admit_source]", "workerd publishing must depend on scope and source admission"),
            ("if: needs.scope.outputs.workerd == 'true'", "workerd publishing must run only for workerd changes"),
            (
                "outputs:\n      image_digest: ${{ steps.publish.outputs.digest }}",
                "workerd publishing must expose the pushed image digest",
            ),
            (
                f"ref: {AUTO_ADMITTED_SHA}",
                "workerd publishing must check out the admitted source SHA",
            ),
            (
                "workload_identity_provider: projects/1031333818730/locations/global/workloadIdentityPools/omi-gha-deploy-dev/providers/github",
                "workerd publishing must use the development workload identity provider",
            ),
            (
                "service_account: omi-ci-deployer-dev@based-hardware-dev.iam.gserviceaccount.com",
                "workerd publishing must use the development deployer identity",
            ),
            (
                "docker build --platform linux/amd64 --tag \"$image\" --file backend-go/Dockerfile backend-go",
                "workerd publishing must build the admitted backend-go image",
            ),
            ('docker push "$image"', "workerd publishing must push the image to the development registry"),
            (
                "gcloud container images describe \"$image\" --format='value(image_summary.digest)'",
                "workerd publishing must resolve the registry image digest",
            ),
            ('echo "digest=$digest" >> "$GITHUB_OUTPUT"', "workerd publishing must publish the resolved digest"),
            (
                "Deployment: none; dev services were not changed.",
                "workerd publishing must state that it does not deploy development services",
            ),
        ):
            require_fragment(errors, publish_job, fragment, message)
        if re.search(r"(?m)^        [\"']?(?:if|continue-on-error)[\"']?:", publish_job):
            errors.append("workerd publishing steps must not be conditionally skipped or tolerated")
        for fragment in (
            "deploy-backend-stack",
            "deploy-cloudrun",
            "gcloud run",
            "kubectl",
            "helm upgrade",
            "helm install",
            "update-traffic",
        ):
            if fragment in publish_job:
                errors.append(f"workerd image publishing must not deploy development services ({fragment})")

    if text.count(AUTO_PROOF_SHA) != 3:
        errors.append(
            "auto backend deploy must use workflow_run.head_sha only in scope decision and current-main admission guard"
        )
    if text.count(AUTO_PROOF_RUN_ATTEMPT) != 1:
        errors.append("auto backend deploy must use workflow_run.run_attempt only in the source-admission guard")
    contract = backend_deploy_contract_text(text, root, DEPLOY_BACKEND_STACK_ACTION)
    allowed_github_sha = "ref: ${{ github.sha }}\n        path: .workflow-source"
    if "github.sha" in contract.replace(allowed_github_sha, ""):
        errors.append("auto backend deploy must not use github.sha after workflow_run admission")
    if text.count(f"ref: {AUTO_ADMITTED_SHA}") != 2:
        errors.append("auto backend deploy must check out the verified SHA before Firestore readiness")
    if "FIRESTORE_SOURCE_COMMIT" in text:
        errors.append("auto backend deploy must bind Firestore readiness through the composite, not inline env")
    if text.count(f"uses: {FIRESTORE_GATE_USES}") != 1:
        errors.append("auto backend deploy must invoke the shared Firestore readiness composite exactly once")
    if contract.count('ref: ${{ inputs.admitted_sha }}') != 1:
        errors.append("auto backend deploy must check out the verified SHA before deployment")
    if contract.count('--commit-sha "${{ inputs.admitted_sha }}"') != 3:
        errors.append("auto backend deploy must bind every release vector to the verified SHA")
    return errors


def validate_manual_workflow(text: str, root: Path = ROOT) -> list[str]:
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
        "      release_sha:\n        description: 'Exact main SHA with a successful Release Eligibility proof (deploy and build-only modes)'\n        required: false",
        "manual backend deploy must keep release_sha optional for traffic-only repair",
    )
    if "github.event.inputs.branch" in text or re.search(r"(?m)^      branch:\n", text):
        errors.append("manual backend deploy must not accept an arbitrary branch or ref")
    contract = backend_deploy_contract_text(text, root, DEPLOY_BACKEND_STACK_ACTION)
    control_source_ref = "ref: ${{ github.sha }}"
    if contract.count(control_source_ref) != 1 or "Checkout workflow-owned deploy-control source" not in contract:
        errors.append("manual backend deploy must stage workflow-owned control scripts from github.sha")

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
        (
            '[ "$(git cat-file -t "${DEPLOY_SHA}" 2>/dev/null)" = "commit" ]',
            "manual source admission must require a commit object",
        ),
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
        (
            "printf 'admitted_sha=%s\\n' \"$DEPLOY_SHA\" >> \"$GITHUB_OUTPUT\"",
            "manual source admission must publish the checked SHA",
        ),
    ):
        require_fragment(errors, admission, fragment, message)

    admitted_checkout = require_step(errors, text, "Checkout admitted Firestore source", "admitted-source checkout")
    require_fragment(
        errors,
        admitted_checkout,
        "ref: ${{ steps.admitted_source.outputs.admitted_sha }}",
        "manual backend deploy must check out the admitted SHA",
    )
    readiness_steps = mapping_block(firestore_job, "steps", 4)
    if readiness_steps is None:
        errors.append("manual source admission must contain its steps")
    else:
        validate_firestore_gate_steps(
            errors,
            readiness_steps,
            source_sha_binding="${{ steps.admitted_source.outputs.admitted_sha }}",
            verify_credential_project=None,
            label="manual backend source admission",
        )
        if "FIRESTORE_SOURCE_COMMIT" in readiness_steps:
            errors.append("manual backend deploy must bind Firestore readiness through the composite, not inline env")

    deploy_job = mapping_block(text, "deploy", 2)
    contract = backend_deploy_contract_text(text, root, DEPLOY_BACKEND_STACK_ACTION)
    if deploy_job is None:
        errors.append("manual backend deploy is missing its deployment job")
    else:
        require_fragment(
            errors,
            deploy_job,
            MANUAL_DEPLOY_JOB_NEEDS,
            "manual deployment must depend on production-boundary validation, source admission, and break-glass audit",
        )
        if folded_job_condition(deploy_job) != MANUAL_DEPLOY_JOB_CONDITION:
            errors.append("manual deployment must gate break-glass deploys on a successful audit record")
        # Scoped to the deploy job: the projection pump job carries the same line (SCA-3120).
        require_fragment(
            errors,
            deploy_job,
            f"admitted_sha: {MANUAL_ADMITTED_SHA}",
            "manual deployment must pass the admitted SHA to the deploy composite action",
        )
        if contract.count('--commit-sha "${{ inputs.admitted_sha }}"') != 3:
            errors.append("manual deployment must bind every release vector to the admitted SHA")
    pump_job = mapping_block(text, "deploy-projection-pump", 2)
    if pump_job is None:
        errors.append("manual backend deploy is missing its projection pump deployment job")
    else:
        require_fragment(
            errors,
            pump_job,
            MANUAL_DEPLOY_JOB_NEEDS,
            "projection pump deployment must depend on production-boundary validation, source admission, and break-glass audit",
        )
        if folded_job_condition(pump_job) != MANUAL_PROJECTION_PUMP_JOB_CONDITION:
            errors.append(
                "projection pump deployment must run only for an admitted prod backend-projection-pump selection"
            )
        require_fragment(
            errors,
            pump_job,
            f"admitted_sha: {MANUAL_ADMITTED_SHA}",
            "projection pump deployment must pass the admitted SHA to its composite action",
        )
    errors.extend(validate_manual_build_only_job(text))
    errors.extend(validate_workerd_publish_job(text))
    errors.extend(validate_workerd_helm_job(text))
    return errors


WORKERD_HELM_CONDITION = "\n".join((
    "github.ref == 'refs/heads/main' &&",
    "(inputs.mode == 'workerd-install' || inputs.mode == 'workerd-rollback') &&",
    "inputs.environment == 'prod' &&",
    "needs.firestore_readiness.outputs.break_glass == 'false'",
))
# SCA-3883: the only route that installs the workerd chart. Each fragment is a refusal or an
# ordering the release go-ahead relies on.
WORKERD_HELM_FRAGMENTS = (
    "needs: [validate-production-boundary, firestore_readiness]",
    MANUAL_BUILD_ONLY_ADMITTED_CHECKOUT,
    "environment: prod",
    "RELEASE: prod-omi-workerd",
    "REPOSITORY: gcr.io/based-hardware/workerd",
    "version: v4.2.4",
    '--ref "$ADMITTED_SHA" --verify-image "$REPOSITORY" --check-worktree)"',
    'if [[ "$identity" != "$EXPECTED_IDENTITY" ]]; then',
    "Release identity differs from workerd_identity; refusing to install.",
    "--set migration.enabled=true",
    'kubectl -n "$NAMESPACE" wait --for=condition=complete "job/$job" --timeout=150s',
    "Workerd migration did not complete; the Deployment is unchanged.",
    'kubectl -n "$NAMESPACE" rollout status "deployment/$RELEASE" --timeout=5m',
    "curl -fsS -m 5 http://127.0.0.1:18080/ready",
    "if: failure() && inputs.mode == 'workerd-install' && steps.install.outcome != 'skipped'",
    'helm -n "$NAMESPACE" rollback "$RELEASE" "$REVISION" --wait --timeout 5m',
    "refusing a rollback that would enable private intake.",
    "refusing ${{ inputs.mode }} while private intake is live.",
    "not restoring it automatically.",
    'if [[ "$REVISION" == 0 ]]; then',
    'if [[ "${{ inputs.mode }}" == workerd-install && "$image" != "$REPOSITORY@$WORKERD_DIGEST" ]]; then',
    '[[ "${ready%/*}" == "${ready#*/}" ]]',
    '--revision "$REVISION" --all -o json | jq -r \'.intake.enabled // false\')"',
)


def validate_workerd_helm_job(text: str) -> list[str]:
    job = mapping_block(text, "workerd-helm", 2)
    if job is None:
        return ["manual backend workflow is missing its workerd install/rollback job"]
    errors: list[str] = []
    if folded_job_condition(job) != WORKERD_HELM_CONDITION:
        errors.append("workerd helm must run only for normal admitted main-ref production install or rollback")
    for fragment in WORKERD_HELM_FRAGMENTS:
        require_fragment(errors, job, fragment, f"workerd helm must retain {fragment}")
    migrate = job.find("name: Run migration Job")
    install = job.find("name: Install chart")
    identity = job.find("name: Verify release identity")
    if not 0 <= identity < migrate < install:
        errors.append("workerd helm must verify the identity, then migrate, then install")
    for fragment in ("gcloud run", "--to-revisions", "update-traffic"):
        if fragment in job:
            errors.append(f"workerd helm must not touch Cloud Run: {fragment}")
    return errors


def validate_workerd_publish_job(text: str) -> list[str]:
    job = mapping_block(text, "publish-workerd", 2)
    if job is None:
        return ["manual backend workflow is missing its workerd image-only job"]

    errors: list[str] = []
    condition = "\n".join((
        "github.ref == 'refs/heads/main' &&",
        "inputs.mode == 'workerd-image-only' &&",
        "inputs.environment == 'prod' &&",
        "needs.firestore_readiness.outputs.break_glass == 'false'",
    ))
    if folded_job_condition(job) != condition:
        errors.append("workerd publish must run only for the normal admitted main-ref production image-only mode")
    for fragment in (
        "needs: [validate-production-boundary, firestore_readiness]",
        MANUAL_BUILD_ONLY_ADMITTED_CHECKOUT,
        f"ADMITTED_SHA: {MANUAL_ADMITTED_SHA}",
        "environment: prod",
        'repository="gcr.io/based-hardware/workerd"',
        "--file backend-go/Dockerfile backend-go",
        # SCA-3883: images are keyed by the backend-go tree and carry it as a label.
        'tree="$(git rev-parse "$ADMITTED_SHA:backend-go")"',
        '--label "omi.workerd.backend-go-tree=$tree"',
        "Existing workerd tree tag has a different backend-go tree.",
        'tree_image="$repository:tree-$recipe-${tree:0:20}"',
        "outcome=reused",
        "Existing workerd SHA tag has a different backend-go tree.",
    ):
        require_fragment(errors, job, fragment, f"workerd publish must retain {fragment}")
    for fragment in MANUAL_BUILD_ONLY_FORBIDDEN:
        if fragment in job:
            errors.append(f"workerd publish must not touch a serving surface: {fragment}")
    return errors


def validate_manual_build_only_job(text: str) -> list[str]:
    errors: list[str] = []
    build_job = mapping_block(text, "build-image", 2)
    if build_job is None:
        return ["manual backend deploy is missing its build-only image job"]
    require_fragment(
        errors,
        build_job,
        MANUAL_DEPLOY_JOB_NEEDS,
        "build-only must depend on production-boundary validation, source admission, and break-glass audit",
    )
    if folded_job_condition(build_job) != MANUAL_BUILD_ONLY_JOB_CONDITION:
        errors.append("build-only must use exactly the admitted, audited main-ref build condition")
    require_fragment(
        errors,
        build_job,
        "environment: ${{ github.event.inputs.environment == 'prod' && 'prod' || 'development' }}",
        "build-only must push from the same Environment protection as deploy",
    )
    if build_job.count(MANUAL_BUILD_ONLY_ADMITTED_CHECKOUT) != 1:
        errors.append("build-only must check out exactly the admitted SHA")
    if "github.event.inputs.release_sha" in build_job:
        errors.append("build-only must build the admitted SHA, never the raw release_sha input")
    smoke_at = build_job.find(MANUAL_BUILD_ONLY_SMOKE)
    push_at = build_job.find(MANUAL_BUILD_ONLY_PUSH)
    if smoke_at < 0 or push_at < 0 or smoke_at > push_at or build_job.count(MANUAL_BUILD_ONLY_PUSH) != 1:
        errors.append("build-only must smoke the built image before pushing its exact tag")
    if MANUAL_BUILD_ONLY_HEAD_CHECK not in build_job:
        errors.append("build-only must verify the checked-out HEAD is the admitted SHA")
    root_checkouts = [
        step
        for step in re.split(r"(?m)^      - ", build_job)
        if "uses: actions/checkout@" in step
        and not re.search(r"(?m)^          path: (?!['\"]?\.?/?['\"]?\s*$)\S", step)
    ]
    if len(root_checkouts) != 1:
        errors.append("build-only must check out exactly one root source tree")
    for forbidden in MANUAL_BUILD_ONLY_FORBIDDEN:
        if forbidden in build_job:
            errors.append(f"build-only must not touch a serving surface or mutable tag ({forbidden!r})")
    return errors


def validate(root: Path = ROOT) -> list[str]:
    paths = (
        AUTO_WORKFLOW_PATH,
        MANUAL_WORKFLOW_PATH,
        ADMISSION_VERIFIER_PATH,
        AUTO_ADMISSION_VERIFIER_PATH,
        DEPLOY_BACKEND_STACK_ACTION,
        FIRESTORE_READINESS_ACTION,
    )
    missing = [str(path) for path in paths if not (root / path).is_file()]
    if missing:
        return [f"backend source-admission contract is missing: {path}" for path in missing]
    errors = validate_auto_workflow((root / AUTO_WORKFLOW_PATH).read_text(encoding="utf-8"), root)
    errors.extend(validate_manual_workflow((root / MANUAL_WORKFLOW_PATH).read_text(encoding="utf-8"), root))
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
