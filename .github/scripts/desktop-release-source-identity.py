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
SCHEMA = "desktop-release-planner-source-identity/v2"
RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
DESKTOP_RELEASE_PATHS = (
    "desktop/macos",
    "codemagic.yaml",
    "scripts/dev-harness/dev_harness/qualification.py",
    ".github/scripts/plan-desktop-release.py",
    ".github/scripts/desktop-release-source-identity.py",
    ".github/scripts/publish-desktop-candidate-tag.py",
    ".github/scripts/verify-pre-tag-readiness.py",
    ".github/workflows/desktop_auto_release.yml",
    ".github/workflows/desktop_qualify_beta.yml",
    ".github/workflows/desktop-swift-ci.yml",
)
def require_sha(name: str, value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 40-character lowercase SHA")
    return value


def require_release_tag(value: str) -> str:
    if not RELEASE_TAG_RE.fullmatch(value):
        raise ValueError("release_tag must be an exact v<version>+<build>-macos tag")
    return value


def releasable_desktop_paths(paths: list[str]) -> list[str]:
    """Filter a Git path list with the planner's release-input policy."""
    releasable = []
    for path in paths:
        if not path:
            continue
        if path == "desktop/macos/CHANGELOG.json":
            continue
        if path == "desktop/macos/AGENTS.md":
            continue
        if path.startswith("desktop/macos/changelog/"):
            continue
        releasable.append(path)
    return releasable


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
    changelog_commit: str = "",
    changelog_parent_sha: str = "",
) -> None:
    """Reject a current-main candidate that contains a newer releasable change.

    The planner deliberately gates the latest desktop-changing source rather
    than every later main commit. A candidate may therefore include later
    backend/docs-only commits, but it must still descend from the gated source
    and contain no newer releasable desktop input.
    """
    try:
        git(
            repository_root,
            ["merge-base", "--is-ancestor", planned_source_sha, candidate_source_sha],
        )
    except subprocess.CalledProcessError as error:
        raise ValueError("candidate main must descend from the planner source SHA") from error

    # A range endpoint diff hides a desktop change that a later commit reverts.
    # The planner selects sources from first-parent history, so examine every
    # first-parent commit after the planned source with the same release-input
    # policy. Any newer releasable change must force a new exact-SHA gate even
    # when its net tree effect is later undone.
    commits_after_planned_source = git(
        repository_root,
        ["rev-list", "--first-parent", f"{planned_source_sha}..{candidate_source_sha}"],
    ).splitlines()
    newer_releasable_changes: list[str] = []
    for commit_sha in commits_after_planned_source:
        changed_paths = git(
            repository_root,
            [
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "--diff-filter=ACDMR",
                "-r",
                f"{commit_sha}^1",
                commit_sha,
                "--",
                *DESKTOP_RELEASE_PATHS,
            ],
        ).splitlines()
        newer_releasable_changes.extend(f"{commit_sha}:{path}" for path in releasable_desktop_paths(changed_paths))
    if newer_releasable_changes:
        raise ValueError(
            "candidate main contains newer releasable desktop changes after the planner source: "
            + ", ".join(newer_releasable_changes)
        )

    if changelog_commit:
        try:
            git(
                repository_root,
                ["merge-base", "--is-ancestor", changelog_commit, candidate_source_sha],
            )
        except subprocess.CalledProcessError as error:
            raise ValueError("merged changelog commit must be reachable from the candidate main") from error
        actual_parent = git(repository_root, ["rev-parse", f"{changelog_commit}^1"])
        if actual_parent != changelog_parent_sha:
            raise ValueError("merged changelog parent does not match its recorded source SHA")
        if changelog_parent_sha != planned_source_sha:
            # A changelog merge may race a newer releasable desktop merge. The
            # workflow is allowed to replan in that narrow case, but only from
            # a source descended from the immutable changelog parent. This
            # keeps the original source evidence intact without allowing an
            # unrelated or stale changelog branch to be repurposed.
            try:
                git(
                    repository_root,
                    ["merge-base", "--is-ancestor", changelog_parent_sha, planned_source_sha],
                )
            except subprocess.CalledProcessError as error:
                raise ValueError("replanned source must descend from the changelog parent SHA") from error


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
    """Prove the candidate tag targets the source currently merged on main.

    A candidate always resolves to fresh main. The current main may contain
    later non-desktop commits, which are admitted only after the caller proves
    ancestry and confirms there is no newer releasable desktop input. A
    consolidated changelog records its own parent, not the merge commit's first
    parent: concurrent non-desktop main commits are valid merge parents. If a
    newer releasable desktop change races that merge, the workflow replans from
    the newer checked source and preserves the changelog's original parent in
    a distinct evidence mode.
    """
    release_tag = require_release_tag(release_tag)
    planned_source_sha = require_sha("planned_source_sha", planned_source_sha)
    candidate_source_sha = require_sha("candidate_source_sha", candidate_source_sha)
    origin_main_sha = require_sha("origin_main_sha", origin_main_sha)

    if candidate_source_sha != origin_main_sha:
        raise ValueError("candidate_source_sha must exactly match fresh origin/main")

    if changelog_commit or changelog_pr or changelog_parent_sha:
        if not (changelog_commit and changelog_pr and changelog_parent_sha):
            raise ValueError("merged changelog evidence requires commit, PR URL, and first parent")
        changelog_commit = require_sha("changelog_commit", changelog_commit)
        changelog_parent_sha = require_sha("changelog_parent_sha", changelog_parent_sha)
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/[1-9][0-9]*", changelog_pr):
            raise ValueError("changelog_pr must be a canonical GitHub pull request URL")
        evidence = {
            "schema": SCHEMA,
            "release_tag": release_tag,
            "mode": "merged-changelog" if changelog_parent_sha == planned_source_sha else "replanned-changelog",
            "planned_source_sha": planned_source_sha,
            "candidate_source_sha": candidate_source_sha,
            "origin_main_sha": origin_main_sha,
            "changelog_commit": changelog_commit,
            "changelog_pr": changelog_pr,
            "changelog_parent_sha": changelog_parent_sha,
        }
        if changelog_parent_sha != planned_source_sha:
            evidence["replanned_from_source_sha"] = changelog_parent_sha
        return evidence

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
