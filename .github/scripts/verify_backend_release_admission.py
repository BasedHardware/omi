#!/usr/bin/env python3
"""Fail closed unless a successful Release Eligibility run proves one source SHA."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MAIN_BRANCH = "main"
RELEASE_WORKFLOW_NAME = "Release Eligibility"
RELEASE_WORKFLOW_PATH = ".github/workflows/release-eligibility.yml"
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ZERO_SHA = "0" * 40


class ReleaseAdmissionError(ValueError):
    """The requested manual deployment source lacks an immutable release proof."""


def require_full_sha(value: str) -> None:
    if not SHA_RE.fullmatch(value):
        raise ReleaseAdmissionError("release SHA must be a full 40-character lowercase hexadecimal SHA")
    if value == ZERO_SHA:
        raise ReleaseAdmissionError("release SHA must not be the all-zero initial-push sentinel")


def _head_repository_name(run: dict[str, Any]) -> str | None:
    repository = run.get("head_repository")
    if not isinstance(repository, dict):
        return None
    full_name = repository.get("full_name")
    return full_name if isinstance(full_name, str) else None


def is_admitted_run(
    run: object, *, sha: str, repository: str, branch: str = MAIN_BRANCH, require_first_attempt: bool = False
) -> bool:
    """Return whether one REST workflow-run record proves the requested SHA."""

    if not isinstance(run, dict):
        return False
    return (
        run.get("name") == RELEASE_WORKFLOW_NAME
        and run.get("path") in (RELEASE_WORKFLOW_PATH, f"{RELEASE_WORKFLOW_PATH}@{branch}")
        and run.get("event") == ("push" if branch == MAIN_BRANCH else "workflow_dispatch")
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and (not require_first_attempt or run.get("run_attempt") == 1)
        and run.get("head_branch") == branch
        and run.get("head_sha") == sha
        and _head_repository_name(run) == repository
    )


def validate_admission(
    payload: object,
    *,
    sha: str,
    repository: str,
    release_branch: str | None = None,
    require_first_attempt: bool = False,
) -> None:
    """Require an exact successful proof from the selected branch and canonical workflow."""

    require_full_sha(sha)
    branch = MAIN_BRANCH if release_branch is None else release_branch
    if release_branch is not None and not re.fullmatch(r"release/\S+", release_branch):
        raise ReleaseAdmissionError("release branch must match release/*")
    if not repository or "/" not in repository:
        raise ReleaseAdmissionError("repository must be an owner/name identifier")
    if not isinstance(payload, dict):
        raise ReleaseAdmissionError("workflow-run response must be a JSON object")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ReleaseAdmissionError("workflow-run response is missing workflow_runs")
    if not any(
        is_admitted_run(run, sha=sha, repository=repository, branch=branch, require_first_attempt=require_first_attempt)
        for run in runs
    ):
        raise ReleaseAdmissionError(
            f"release SHA has no successful {branch} Release Eligibility workflow run from this repository"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-branch", help="release/* source branch for build-only admission")
    parser.add_argument("--workflow-runs", type=Path, required=True)
    parser.add_argument("--require-first-attempt", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.workflow_runs.read_text(encoding="utf-8"))
        validate_admission(
            payload,
            sha=args.sha,
            repository=args.repository,
            release_branch=args.release_branch,
            require_first_attempt=args.require_first_attempt,
        )
    except (OSError, json.JSONDecodeError, ReleaseAdmissionError) as exc:
        print(f"backend release admission failed: {exc}", file=sys.stderr)
        return 1
    print(f"backend release source admitted: sha={args.sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
