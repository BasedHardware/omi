#!/usr/bin/env python3
"""Automated writes to `main` must be checkable and revertible.

A workflow that opens a PR against `main` and merges it itself is the one path
into `main` with no human in the loop. Two properties keep that path honest, and
`sync-docs.yml` lost both (#10535):

1. **The PR must be able to run checks.** GitHub deliberately does not fire
   `pull_request` workflows for events authored by `GITHUB_TOKEN`, so a PR
   opened with that token arrives with an empty check list — it *looks*
   reviewed because it is a PR, while nothing verified it. Opening it with an
   app token (`actions/create-github-app-token`) makes CI run.
2. **The merge must stay revertible.** AGENTS.md ("Merge, never squash") keeps
   merge commits so a bad automated commit on `main` can be undone with
   `git revert -m 1`. A squashed automated merge removes that recovery.

Real instances this would have caught: #8325 (created and merged 4 seconds
later, check list `skipping`/`skipping`, single-parent merge commit), plus
#7543, #3680 and #3675 in the same shape.

Scope: only workflows that BOTH open a PR via `peter-evans/create-pull-request`
and merge one via `gh pr merge`. A workflow that merely opens a PR for humans is
untouched — a human reviewing it is the check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"

CREATE_PR_ACTION = "peter-evans/create-pull-request"
GH_PR_MERGE = "gh pr merge"
APP_TOKEN_ACTION = "actions/create-github-app-token"

# `token: ${{ secrets.GITHUB_TOKEN }}` on the create-pull-request step, in any
# spacing GitHub Actions accepts.
GITHUB_TOKEN_INPUT = re.compile(r"token:\s*\$\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}")
GITHUB_CONTEXT_TOKEN_INPUT = re.compile(r"token:\s*\$\{\{\s*github\.token\s*\}\}")


def _self_merging_workflows() -> list[Path]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if CREATE_PR_ACTION in text and GH_PR_MERGE in text:
            found.append(path)
    return found


def _create_pr_token(step: str) -> str | None:
    with_indent: int | None = None
    for line in step.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped == "with:":
            with_indent = indent
        elif with_indent is not None:
            if stripped and indent <= with_indent:
                break
            if stripped.startswith("token:"):
                return stripped.partition(":")[2].strip()
    return None


def check_workflow(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT)
    errors: list[str] = []

    create_pr_tokens = [
        _create_pr_token(step) for step in re.split(r"(?m)^(?=\s*-\s)", text) if CREATE_PR_ACTION in step
    ]

    if any(
        token is not None
        and (GITHUB_TOKEN_INPUT.search(f"token: {token}") or GITHUB_CONTEXT_TOKEN_INPUT.search(f"token: {token}"))
        for token in create_pr_tokens
    ):
        errors.append(
            f"{rel}: opens its own auto-merged PR with secrets.GITHUB_TOKEN or github.token, so no "
            f"pull_request checks fire on it. Mint an app token with "
            f"{APP_TOKEN_ACTION} and pass that to {CREATE_PR_ACTION} instead (#10535)."
        )
    elif any(token is None for token in create_pr_tokens):
        errors.append(
            f"{rel}: opens its own auto-merged PR without an explicit non-default token, "
            f"so {CREATE_PR_ACTION} falls back to GitHub's default token and no "
            f"pull_request checks fire (#10535)."
        )
    if APP_TOKEN_ACTION not in text:
        errors.append(
            f"{rel}: opens its own auto-merged PR without an {APP_TOKEN_ACTION} step, "
            f"so the PR cannot run pull_request checks (#10535)."
        )

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or GH_PR_MERGE not in stripped:
            continue
        if "--squash" in stripped:
            errors.append(
                f"{rel}: merges an automated PR with --squash. AGENTS.md requires "
                f"'Merge, never squash' so main stays revertible with "
                f"git revert -m 1; use --merge (#10535)."
            )

    return errors


def main() -> int:
    workflows = _self_merging_workflows()
    if not workflows:
        # No self-merging workflow left. The guard is vacuous rather than passing
        # silently on a bad glob, so say which directory was searched.
        print(f"automated main-write admission: no self-merging workflows in {WORKFLOWS.relative_to(ROOT)}")
        return 0

    errors: list[str] = []
    for path in workflows:
        errors.extend(check_workflow(path))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    names = ", ".join(str(p.relative_to(ROOT)) for p in workflows)
    print(f"automated main-write admission: {len(workflows)} self-merging workflow(s) OK ({names})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
