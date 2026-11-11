#!/usr/bin/env python3
"""Resolve a main-reachable desktop changelog consolidate commit for tag-release.

When a prior tag-release failed before publishing the immutable tag, retries can
see:

- a source-qualified remote branch tip that is *not* an ancestor of origin/main
  after a manual squash merge;
- consolidate dirt left in the worktree that blocks ``git checkout -B`` reuse;
- an exact-parent consolidate already merged on main.

This helper reuses only a main-reachable consolidate whose first parent is the
exact planned source. An orphan returns a recoverable mode so the workflow can
publish a run-qualified branch instead of wedging every later train.

Never scan every commit on main (rev-list + per-sha rev-parse): that path is
O(history) and hung M1 tag-release for 15+ minutes while v0.12.143 was blocked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def require_sha(name: str, value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ValueError(f"{name} must be a 40-character lowercase SHA")
    return value


def git(repository_root: Path, args: list[str], *, check: bool = True) -> str:
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


def is_ancestor(repository_root: Path, maybe_ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "merge-base", "--is-ancestor", maybe_ancestor, descendant],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={name: value for name, value in os.environ.items() if not name.startswith("GIT_")},
    )
    return result.returncode == 0


def consolidate_subject_re(version: str) -> re.Pattern[str]:
    return re.compile(rf"^chore: consolidate changelog for v{re.escape(version)}(?: \(#([1-9][0-9]*)\))?$")


def merge_subject_re(version: str) -> re.Pattern[str]:
    return re.compile(rf"^Update desktop changelog for v{re.escape(version)}\b.*\(#([1-9][0-9]*)\)\s*$")


def find_main_reachable_consolidate(
    repository_root: Path,
    *,
    planned_source_sha: str,
    version: str,
    main_ref: str = "origin/main",
) -> str | None:
    """Return consolidate commit on main for this version.

    Only a consolidate whose first parent is the exact green planner source is
    reusable. A later planned source simply consolidates again (or finds no
    diff), which avoids binding a candidate to stale release notes.
    """
    planned_source_sha = require_sha("planned_source_sha", planned_source_sha)
    subject_pattern = consolidate_subject_re(version)
    log = git(
        repository_root,
        ["log", main_ref, "--format=%H%x00%P%x00%s", "--grep", f"consolidate changelog for v{version}"],
    )
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, parents, subject = line.split("\x00", 2)
        parent_list = parents.split()
        if not parent_list:
            continue
        if subject_pattern.fullmatch(subject.strip()) is None:
            continue
        if not is_ancestor(repository_root, sha, main_ref):
            continue
        if parent_list[0] == planned_source_sha:
            return sha
    return None


def find_changelog_merge_on_main(
    repository_root: Path,
    *,
    version: str,
    consolidate_commit: str,
    main_ref: str = "origin/main",
    repository_slug: str = "",
) -> tuple[str, str] | None:
    """Return (merge_commit_sha, pr_url) for the changelog merge on main."""
    consolidate_commit = require_sha("consolidate_commit", consolidate_commit)
    pattern = merge_subject_re(version)
    log = git(
        repository_root,
        ["log", main_ref, "--merges", "--format=%H%x00%s", f"--grep=Update desktop changelog for v{version}"],
    )
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, subject = line.split("\x00", 1)
        match = pattern.match(subject.strip())
        if not match:
            continue
        parents = git(repository_root, ["rev-parse", f"{sha}^@"]).splitlines()
        if consolidate_commit not in parents and not is_ancestor(repository_root, consolidate_commit, sha):
            continue
        pr_number = match.group(1)
        if repository_slug:
            pr_url = f"https://github.com/{repository_slug}/pull/{pr_number}"
        else:
            pr_url = f"pull/{pr_number}"
        return sha, pr_url
    # GitHub squash merges append the PR number to the consolidate subject. If
    # the squash commit is itself the exact parent-bound consolidate, it is a
    # valid changelog-only candidate and carries its own PR evidence.
    squash_log = git(
        repository_root,
        ["log", main_ref, "--format=%H%x00%s", "--grep", f"consolidate changelog for v{version}"],
    )
    subject_pattern = consolidate_subject_re(version)
    for line in squash_log.splitlines():
        if not line.strip():
            continue
        sha, subject = line.split("\x00", 1)
        match = subject_pattern.fullmatch(subject.strip())
        if sha != consolidate_commit or match is None or match.group(1) is None:
            continue
        pr_number = match.group(1)
        pr_url = f"https://github.com/{repository_slug}/pull/{pr_number}" if repository_slug else f"pull/{pr_number}"
        return sha, pr_url
    return None


def resolve_changelog_sync(
    repository_root: Path,
    *,
    planned_source_sha: str,
    version: str,
    branch_tip: str = "",
    main_ref: str = "origin/main",
    repository_slug: str = "",
) -> dict[str, object]:
    """Resolve commit + optional PR evidence for tag-release changelog sync."""
    planned_source_sha = require_sha("planned_source_sha", planned_source_sha)
    main_tip = git(repository_root, ["rev-parse", f"{main_ref}^{{commit}}"])

    main_commit = find_main_reachable_consolidate(
        repository_root,
        planned_source_sha=planned_source_sha,
        version=version,
        main_ref=main_ref,
    )

    preferred = ""
    orphaned_branch = False
    if branch_tip:
        branch_tip = require_sha("branch_tip", branch_tip)
        parent = git(repository_root, ["rev-parse", f"{branch_tip}^1"])
        if parent == planned_source_sha and is_ancestor(repository_root, branch_tip, main_ref):
            preferred = branch_tip
        elif main_commit is None:
            orphaned_branch = True

    commit = preferred or main_commit or ""
    if not commit:
        return {
            "mode": "stale-orphan" if orphaned_branch else "missing",
            "commit": "",
            "pr_url": "",
            "merged_main_sha": "",
            "already_on_main": False,
            "main_tip": main_tip,
        }

    already_on_main = is_ancestor(repository_root, commit, main_ref)
    pr_url = ""
    merged_main_sha = ""
    if already_on_main:
        found = find_changelog_merge_on_main(
            repository_root,
            version=version,
            consolidate_commit=commit,
            main_ref=main_ref,
            repository_slug=repository_slug,
        )
        if found:
            merged_main_sha, pr_url = found
        mode = "already-on-main"
    else:
        mode = "branch-tip"

    return {
        "mode": mode,
        "commit": commit,
        "pr_url": pr_url,
        "merged_main_sha": merged_main_sha,
        "already_on_main": already_on_main,
        "main_tip": main_tip,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--planned-source-sha", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--branch-tip", default="")
    parser.add_argument("--main-ref", default="origin/main")
    parser.add_argument("--repository", default="")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = resolve_changelog_sync(
            args.repository_root.resolve(),
            planned_source_sha=args.planned_source_sha.lower(),
            version=args.version,
            branch_tip=args.branch_tip.lower() if args.branch_tip else "",
            main_ref=args.main_ref,
            repository_slug=args.repository,
        )
    except ValueError as error:
        print(f"resolve-desktop-changelog-sync.py: error: {error}", file=sys.stderr)
        return 2

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        args.output_json.write_text(payload, encoding="utf-8")
    if args.github_output:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if not gh_out:
            print("GITHUB_OUTPUT is not set", file=sys.stderr)
            return 2
        with open(gh_out, "a", encoding="utf-8") as handle:
            for key in ("mode", "commit", "pr_url", "merged_main_sha"):
                handle.write(f"{key}={result[key]}\n")
            handle.write(f"already_on_main={'true' if result['already_on_main'] else 'false'}\n")
    if not args.output_json and not args.github_output:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
