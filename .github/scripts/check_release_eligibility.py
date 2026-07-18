#!/usr/bin/env python3
"""Keep the automatic main-SHA release proof bound to canonical CI checks."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = Path(".github/workflows/release-eligibility.yml")
ACTION_PATH = Path(".github/actions/release-eligibility/action.yml")


def require_fragment(errors: list[str], text: str, fragment: str, message: str) -> None:
    if fragment not in text:
        errors.append(message)


def mapping_block(text: str, key: str, indent: int) -> str | None:
    """Return a YAML mapping block with the repository's fixed indentation."""

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
    """Return one named step block, stopping at the next peer step."""

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


def validate_required_step(errors: list[str], text: str, name: str, indent: int, label: str) -> str:
    """Require a critical step to run normally and fail closed."""

    step = named_step_block(text, name, indent)
    if step is None:
        errors.append(f"release eligibility is missing its {label} step")
        return ""
    field_indent = " " * (indent + 2)
    if re.search(rf"(?m)^{re.escape(field_indent)}[\"']?(?:if|continue-on-error)[\"']?:", step):
        errors.append(f"release eligibility {label} step must not be conditionally skipped or tolerated")
    script_indent = f"{field_indent}  "
    if not re.search(rf"(?m)^{re.escape(script_indent)}set -euo pipefail$", step):
        errors.append(f"release eligibility {label} step must enable strict shell failure handling")
    if re.search(r"\|\|\s*(?:true\b|:|exit\s+0\b)|\bset\s+\+(?:e|o\s+(?:errexit|pipefail))\b", step):
        errors.append(f"release eligibility {label} step must not contain a shell fail-open path")
    return step


def validate_workflow(text: str) -> list[str]:
    errors: list[str] = []
    push = re.search(r"(?ms)^  push:\n(?P<body>(?:    .*\n?)*)", text)
    if push is None or "    branches: [main]" not in push.group("body"):
        errors.append("release eligibility must trigger only on pushes to main")
    elif re.search(r"(?m)^    (?:paths|paths-ignore|tags|tags-ignore|branches-ignore):", push.group("body")):
        errors.append("release eligibility must not path-filter or otherwise narrow main pushes")
    on_block = mapping_block(text, "on", 0)
    trigger_keys = (
        []
        if on_block is None
        else [
            match.group("key").strip("\"'")
            for match in re.finditer(r"(?m)^  (?P<key>[\"']?[A-Za-z_]+[\"']?):", on_block)
        ]
    )
    if trigger_keys != ["push"]:
        errors.append("release eligibility must declare only the automatic push trigger")
    require_fragment(errors, text, "name: Release Eligibility", "release eligibility workflow is missing its unique check name")
    require_fragment(
        errors,
        text,
        "  release-eligibility:\n    name: Release Eligibility",
        "release eligibility workflow is missing its uniquely named result job",
    )
    job = mapping_block(text, "release-eligibility", 2)
    if job is None:
        errors.append("release eligibility workflow is missing its result job")
    elif re.search(r"(?m)^    [\"']?(?:if|continue-on-error)[\"']?:", job):
        errors.append("release eligibility result job must not be conditionally skipped or tolerated")
    require_fragment(
        errors,
        text,
        "uses: actions/checkout@v7\n        with:\n          ref: ${{ github.sha }}\n          fetch-depth: 0",
        "release eligibility must check out the exact GitHub SHA with complete history",
    )
    require_fragment(
        errors,
        text,
        "uses: ./.github/actions/release-eligibility",
        "release eligibility workflow must use the canonical release-eligibility action",
    )
    for name, expression in {
        "ref": "${{ github.ref }}",
        "sha": "${{ github.sha }}",
        "before": "${{ github.event.before }}",
        "after": "${{ github.event.after }}",
    }.items():
        require_fragment(
            errors,
            text,
            f"          {name}: {expression}",
            f"release eligibility must pass {name} as {expression}",
        )
    invocation = named_step_block(text, "Verify release eligibility", 6)
    if invocation is None:
        errors.append("release eligibility workflow is missing its action invocation step")
    elif re.search(r"(?m)^        [\"']?(?:if|continue-on-error)[\"']?:", invocation):
        errors.append("release eligibility action invocation must not be conditionally skipped or tolerated")
    permissions = mapping_block(text, "permissions", 0)
    if permissions is None or [line.strip() for line in permissions.splitlines() if line.strip()] != ["contents: read"]:
        errors.append("release eligibility must use only repository contents: read permissions")
    if re.search(r"(?m)^    permissions:", job or ""):
        errors.append("release eligibility result job must not override least-privilege workflow permissions")
    return errors


def validate_action(text: str) -> list[str]:
    errors: list[str] = []
    for name in ("ref", "sha", "before", "after"):
        require_fragment(
            errors,
            text,
            f"  {name}:\n",
            f"release eligibility action is missing required {name} input",
        )
    for env_name, expression in {
        "RELEASE_REF": "${{ inputs.ref }}",
        "RELEASE_SHA": "${{ inputs.sha }}",
        "RELEASE_BEFORE": "${{ inputs.before }}",
        "RELEASE_AFTER": "${{ inputs.after }}",
    }.items():
        require_fragment(
            errors,
            text,
            f"        {env_name}: {expression}",
            f"release eligibility action must bind {env_name} from {expression}",
        )
    identity_step = validate_required_step(
        errors,
        text,
        "Verify exact main release identity",
        4,
        "identity validation",
    )
    preflight_step = validate_required_step(
        errors,
        text,
        "Run canonical deterministic CI preflight",
        4,
        "canonical preflight",
    )
    for fragment, message in (
        ("RELEASE_CHECKOUT_SHA=\"$(git rev-parse --verify HEAD)\"", "release eligibility must resolve checkout SHA"),
        (".github/scripts/verify_release_eligibility.py", "release eligibility must validate immutable release identity"),
        ("--ref \"$RELEASE_REF\"", "release identity validator must receive the triggering ref"),
        ("--sha \"$RELEASE_SHA\"", "release identity validator must receive the immutable release SHA"),
        ("--before \"$RELEASE_BEFORE\"", "release identity validator must receive the deterministic-check base SHA"),
        ("--after \"$RELEASE_AFTER\"", "release identity validator must receive the push event SHA"),
        ("--checkout-sha \"$RELEASE_CHECKOUT_SHA\"", "release identity validator must receive the checkout SHA"),
        ("git cat-file -e \"${RELEASE_BEFORE}^{commit}\"", "release eligibility must verify the base identity is a commit"),
        ("git cat-file -e \"${RELEASE_SHA}^{commit}\"", "release eligibility must verify the release identity is a commit"),
        ("git merge-base --is-ancestor \"$RELEASE_BEFORE\" \"$RELEASE_SHA\"", "release eligibility must require the base SHA to be an ancestor"),
        (".github/scripts/run_checks.py", "release eligibility must call the canonical deterministic check runner"),
        ("--lane ci", "release eligibility must use the CI check lane"),
        ("--base \"$RELEASE_BEFORE\"", "release eligibility must use the event base SHA"),
        ("--head \"$RELEASE_SHA\"", "release eligibility must use the immutable release SHA as check head"),
        ("--skip-pr-body-checks", "release eligibility must use the canonical post-merge preflight mode"),
    ):
        require_fragment(errors, text, fragment, message)
    for step, fragment, message in (
        (identity_step, ".github/scripts/verify_release_eligibility.py", "identity validation step must run the immutable identity verifier"),
        (identity_step, "git merge-base --is-ancestor", "identity validation step must enforce main ancestry"),
        (preflight_step, ".github/scripts/run_checks.py", "canonical preflight step must run the deterministic check runner"),
    ):
        require_fragment(errors, step, fragment, message)
    return errors


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    workflow = root / WORKFLOW_PATH
    action = root / ACTION_PATH
    if not workflow.is_file():
        return [f"release eligibility workflow is missing: {WORKFLOW_PATH}"]
    if not action.is_file():
        return [f"release eligibility action is missing: {ACTION_PATH}"]
    errors.extend(validate_workflow(workflow.read_text(encoding="utf-8")))
    errors.extend(validate_action(action.read_text(encoding="utf-8")))
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("release eligibility contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
