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
3. **The app token must exist before the PR opens, in the same job.** A
   create-pull-request step that references `steps.<app-token>.outputs.token`
   proves nothing if that token step is declared later in the job — `steps` is
   populated top to bottom — or if the token step lives in a different job,
   where that expression is out of scope.

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
APP_TOKEN_OUTPUT = re.compile(r"\$\{\{\s*steps\.([A-Za-z0-9_-]+)\.outputs\.token\s*\}\}")


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


def _step_blocks(text: str) -> list[tuple[str, int]]:
    """Split a YAML fragment into its `- ` list-entry blocks.

    Returns (block text, block index) pairs. Indices order the blocks exactly as
    GitHub Actions runs the steps within that list.
    """
    matches = list(re.finditer(r"(?m)^(?=\s*-\s)", text))
    blocks: list[tuple[str, int]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((text[start:end], index))
    return blocks


def _job_steps_lists(text: str) -> list[list[tuple[str, int]]]:
    """Group step blocks by the job that owns them.

    GitHub Actions `steps.<id>.outputs` is job-scoped. A token minted in job A
    is not available to create-pull-request in job B, even when the expression
    literally says `steps.app-token.outputs.token`.
    """
    lists: list[list[tuple[str, int]]] = []
    for steps_match in re.finditer(r"(?m)^(?P<indent>[ \t]*)steps:\s*(?:#.*)?$", text):
        indent = steps_match.group("indent")
        start = steps_match.end()
        rest = text[start:]
        end_rel = len(rest)
        for line_match in re.finditer(r"(?m)^([ \t]*)\S", rest):
            if line_match.start() == 0:
                continue
            line_indent = line_match.group(1)
            if len(line_indent) <= len(indent):
                end_rel = line_match.start()
                break
        section = rest[:end_rel]
        blocks: list[tuple[str, int]] = []
        for block, index in _step_blocks(section):
            first_line = next((line for line in block.splitlines() if line.strip()), "")
            first_indent = len(first_line) - len(first_line.lstrip())
            # Direct children of `steps:` are more indented than `steps:` itself.
            if first_indent <= len(indent):
                continue
            blocks.append((block, index))
        if blocks:
            lists.append(blocks)
    return lists


def _app_token_step_ids(step_blocks: list[tuple[str, int]]) -> set[str]:
    step_ids: set[str] = set()
    for step, _ in step_blocks:
        if APP_TOKEN_ACTION not in step:
            continue
        match = re.search(r"(?m)^\s*id:\s*([A-Za-z0-9_-]+)\s*$", step)
        if match:
            step_ids.add(match.group(1))
    return step_ids


def _app_token_step_offsets(step_blocks: list[tuple[str, int]]) -> dict[str, int]:
    """Map app-token step id -> index within the same job's steps list."""
    offsets: dict[str, int] = {}
    for index, (step, _) in enumerate(step_blocks):
        if APP_TOKEN_ACTION not in step:
            continue
        match = re.search(r"(?m)^\s*id:\s*([A-Za-z0-9_-]+)\s*$", step)
        if match:
            offsets[match.group(1)] = index
    return offsets


def _check_create_pr_job(rel: Path, step_blocks: list[tuple[str, int]]) -> list[str]:
    """Validate app-token admission for one job that opens a self-merged PR."""
    create_pr_steps = [(step, index) for index, (step, _) in enumerate(step_blocks) if CREATE_PR_ACTION in step]
    if not create_pr_steps:
        return []

    errors: list[str] = []
    create_pr_tokens = [_create_pr_token(step) for step, _ in create_pr_steps]
    app_token_step_ids = _app_token_step_ids(step_blocks)
    app_token_offsets = _app_token_step_offsets(step_blocks)

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
    elif any(
        not (match := APP_TOKEN_OUTPUT.fullmatch(token or "")) or match.group(1) not in app_token_step_ids
        for token in create_pr_tokens
    ):
        errors.append(
            f"{rel}: opens its own auto-merged PR with a token that is not an output of an "
            f"{APP_TOKEN_ACTION} step in the same job as {CREATE_PR_ACTION}, so the checkable "
            f"app-identity contract is not proven (#10535)."
        )
    elif any(
        not (match := APP_TOKEN_OUTPUT.fullmatch(token or ""))
        or app_token_offsets.get(match.group(1), -1) > pr_offset
        for token, (_, pr_offset) in zip(create_pr_tokens, create_pr_steps)
    ):
        errors.append(
            f"{rel}: references an {APP_TOKEN_ACTION} step that is declared after the "
            f"{CREATE_PR_ACTION} step in the same job, so the app token is not yet available "
            f"when the PR is opened and the checkable app-identity contract is not proven (#10535)."
        )
    if not app_token_step_ids:
        errors.append(
            f"{rel}: opens its own auto-merged PR without an {APP_TOKEN_ACTION} step in the "
            f"same job as {CREATE_PR_ACTION}, so the PR cannot run pull_request checks (#10535)."
        )

    return errors


def check_workflow(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(ROOT)
    errors: list[str] = []

    for step_blocks in _job_steps_lists(text):
        errors.extend(_check_create_pr_job(rel, step_blocks))

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or GH_PR_MERGE not in stripped:
            continue
        if "--merge" not in stripped:
            errors.append(
                f"{rel}: merges an automated PR without --merge ({stripped}). AGENTS.md requires "
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
