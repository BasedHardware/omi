#!/usr/bin/env python3
"""Build fail-closed evidence for a macOS candidate tag's source identity."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SCHEMA = "desktop-release-planner-source-identity/v3"
RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")


def require_sha(name: str, value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 40-character lowercase SHA")
    return value


def require_release_tag(value: str) -> str:
    if not RELEASE_TAG_RE.fullmatch(value):
        raise ValueError("release_tag must be an exact v<version>+<build>-macos tag")
    return value


def git(repository_root: Path, args: list[str], *, check: bool = True) -> str:
    # The caller can be a Git hook or another repository-scoped tool. Do not
    # inherit its GIT_DIR/index/worktree state when proving a different,
    # explicit repository root.
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    result = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    return result.stdout.strip()


def ensure_candidate_history_is_safe(
    *,
    repository_root: Path,
    planned_source_sha: str,
    candidate_source_sha: str,
    origin_main_sha: str,
    changelog_commit: str = "",
    changelog_parent_sha: str = "",
) -> None:
    """Bind a candidate to the checked source without requiring a quiet main.

    A direct candidate is exactly the green planner source. A changelog
    candidate is exactly one child of that source and may change only desktop
    changelog files. Either candidate must already be reachable from the fresh
    main tip, but later main commits are intentionally outside the candidate.
    """
    try:
        git(
            repository_root,
            ["merge-base", "--is-ancestor", candidate_source_sha, origin_main_sha],
        )
    except subprocess.CalledProcessError as error:
        raise ValueError("candidate source must be reachable from fresh origin/main") from error

    if changelog_commit:
        if candidate_source_sha != changelog_commit:
            raise ValueError("changelog candidate must exactly equal the consolidated changelog commit")
        actual_parent = git(repository_root, ["rev-parse", f"{changelog_commit}^1"])
        if actual_parent != changelog_parent_sha:
            raise ValueError("changelog commit parent does not match its recorded source SHA")
        if changelog_parent_sha != planned_source_sha:
            raise ValueError("changelog commit must be based directly on the green planner source")
        changed_paths = git(
            repository_root,
            ["diff-tree", "--no-commit-id", "--name-only", "--diff-filter=ACDMR", "-r", changelog_commit],
        ).splitlines()
        invalid_paths = [
            path
            for path in changed_paths
            if path != "desktop/macos/CHANGELOG.json" and not path.startswith("desktop/macos/changelog/")
        ]
        if not changed_paths:
            raise ValueError("changelog candidate must contain a changelog-only change")
        if invalid_paths:
            raise ValueError("changelog candidate contains non-changelog paths: " + ", ".join(invalid_paths))
    elif candidate_source_sha != planned_source_sha:
        raise ValueError("direct candidate must exactly equal the green planner source")


def build_evidence(
    *,
    release_tag: str,
    planned_source_sha: str,
    candidate_source_sha: str,
    origin_main_sha: str,
    changelog_parent_sha: str = "",
    changelog_commit: str = "",
    changelog_pr: str = "",
) -> dict[str, object]:
    """Record the exact checked source and its optional changelog-only child."""
    release_tag = require_release_tag(release_tag)
    planned_source_sha = require_sha("planned_source_sha", planned_source_sha)
    candidate_source_sha = require_sha("candidate_source_sha", candidate_source_sha)
    origin_main_sha = require_sha("origin_main_sha", origin_main_sha)

    if changelog_commit or changelog_pr or changelog_parent_sha:
        if not (changelog_commit and changelog_pr and changelog_parent_sha):
            raise ValueError("merged changelog evidence requires commit, PR URL, and first parent")
        changelog_commit = require_sha("changelog_commit", changelog_commit)
        changelog_parent_sha = require_sha("changelog_parent_sha", changelog_parent_sha)
        if candidate_source_sha != changelog_commit:
            raise ValueError("changelog candidate must exactly equal the consolidated changelog commit")
        if changelog_parent_sha != planned_source_sha:
            raise ValueError("changelog commit must be based directly on the green planner source")
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/[1-9][0-9]*", changelog_pr):
            raise ValueError("changelog_pr must be a canonical GitHub pull request URL")
        evidence = {
            "schema": SCHEMA,
            "release_tag": release_tag,
            "mode": "changelog-only",
            "planned_source_sha": planned_source_sha,
            "candidate_source_sha": candidate_source_sha,
            "origin_main_sha": origin_main_sha,
            "changelog_commit": changelog_commit,
            "changelog_pr": changelog_pr,
            "changelog_parent_sha": changelog_parent_sha,
        }
        return evidence

    if candidate_source_sha != planned_source_sha:
        raise ValueError("direct candidate must exactly equal the green planner source")
    return {
        "schema": SCHEMA,
        "release_tag": release_tag,
        "mode": "direct",
        "planned_source_sha": planned_source_sha,
        "candidate_source_sha": candidate_source_sha,
        "origin_main_sha": origin_main_sha,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--planned-source-sha", required=True)
    parser.add_argument("--candidate-source-sha", required=True)
    parser.add_argument("--origin-main-sha", required=True)
    parser.add_argument("--changelog-parent-sha", default="")
    parser.add_argument("--changelog-commit", default="")
    parser.add_argument("--changelog-pr", default="")
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        planned_source_sha = require_sha("planned_source_sha", args.planned_source_sha)
        candidate_source_sha = require_sha("candidate_source_sha", args.candidate_source_sha)
        changelog_parent_sha = args.changelog_parent_sha
        if args.changelog_commit or args.changelog_pr or changelog_parent_sha:
            changelog_parent_sha = require_sha("changelog_parent_sha", changelog_parent_sha)
        ensure_candidate_history_is_safe(
            repository_root=Path(args.repository_root),
            planned_source_sha=planned_source_sha,
            candidate_source_sha=candidate_source_sha,
            origin_main_sha=require_sha("origin_main_sha", args.origin_main_sha),
            changelog_commit=args.changelog_commit,
            changelog_parent_sha=changelog_parent_sha,
        )
        evidence = build_evidence(
            release_tag=args.release_tag,
            planned_source_sha=planned_source_sha,
            candidate_source_sha=candidate_source_sha,
            origin_main_sha=args.origin_main_sha,
            changelog_parent_sha=changelog_parent_sha,
            changelog_commit=args.changelog_commit,
            changelog_pr=args.changelog_pr,
        )
    except ValueError as error:
        parser.error(str(error))

    Path(args.output).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"desktop release source identity verified for {evidence['candidate_source_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
