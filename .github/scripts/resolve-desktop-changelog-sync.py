#!/usr/bin/env python3
"""Resolve a main-reachable desktop changelog consolidate commit for tag-release.

When a prior tag-release merged the changelog PR but failed before publishing the
immutable tag, retries can see:

- a source-qualified remote branch tip that is *not* an ancestor of origin/main
  (orphan rewrite of the consolidate commit), while the merge's second parent
  *is* on main;
- consolidate dirt left in the worktree that blocks ``git checkout -B`` reuse;
- a newer planned source SHA (tip-bumps) that is a descendant of the already
  merged changelog, so consolidate^1 != planned source.

This helper prefers any consolidate commit that is reachable from origin/main
for the exact version subject. When the planned source still matches the
consolidate parent that binding is preferred; otherwise a version-matched
main-reachable consolidate is accepted for already-on-main recovery.

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


def consolidate_subject(version: str) -> str:
    return f"chore: consolidate changelog for v{version}"


def merge_subject_re(version: str) -> re.Pattern[str]:
    return re.compile(
        rf"^Update desktop changelog for v{re.escape(version)}\b.*\(#([1-9][0-9]*)\)\s*$"
    )


def changelog_inputs_changed_since(
    repository_root: Path,
    *,
    base_sha: str,
    planned_source_sha: str,
) -> bool:
    """True when planned source carries newer changelog inputs than base.

    Parent-mismatch already-on-main recovery is only safe when tip-bumps (or
    other non-changelog commits) advanced the planned source. New unreleased
    fragments or release notes after the consolidate must force a fresh
    consolidation so they are not silently attributed to a later version.
    """

    base_sha = require_sha("base_sha", base_sha)
    planned_source_sha = require_sha("planned_source_sha", planned_source_sha)
    changed = git(
        repository_root,
        [
            "diff",
            "--name-only",
            "--diff-filter=ACDMR",
            f"{base_sha}..{planned_source_sha}",
            "--",
            "desktop/macos/changelog/unreleased",
            "desktop/macos/changelog/releases",
            "desktop/macos/CHANGELOG.json",
        ],
    )
    if changed.strip():
        return True
    # Also treat any unreleased fragment present on the planned tree as pending
    # input even if the path was unchanged (empty tree edge cases).
    unreleased = git(
        repository_root,
        [
            "ls-tree",
            "-r",
            "--name-only",
            planned_source_sha,
            "--",
            "desktop/macos/changelog/unreleased",
        ],
        check=False,
    )
    return any(path.endswith(".json") for path in unreleased.splitlines())


def find_main_reachable_consolidate(
    repository_root: Path,
    *,
    planned_source_sha: str,
    version: str,
    main_ref: str = "origin/main",
) -> str | None:
    """Return consolidate commit on main for this version.

    Prefer parent == planned source. Fall back to a main-reachable consolidate
    with the exact version subject only when changelog inputs did not advance
    after that consolidate (tip-bump / partial tag recovery).
    """
    planned_source_sha = require_sha("planned_source_sha", planned_source_sha)
    want = consolidate_subject(version)
    log = git(
        repository_root,
        ["log", main_ref, "--format=%H%x00%P%x00%s", "--grep", f"consolidate changelog for v{version}"],
    )
    parent_match: str | None = None
    version_match: str | None = None
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, parents, subject = line.split("\x00", 2)
        parent_list = parents.split()
        if not parent_list:
            continue
        if subject.strip() != want:
            continue
        if not is_ancestor(repository_root, sha, main_ref):
            continue
        if parent_list[0] == planned_source_sha:
            parent_match = sha
            break
        if version_match is None:
            version_match = sha
    if parent_match is not None:
        return parent_match
    if version_match is None:
        return None
    if changelog_inputs_changed_since(
        repository_root,
        base_sha=version_match,
        planned_source_sha=planned_source_sha,
    ):
        return None
    return version_match


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

    preferred = ""
    if branch_tip:
        branch_tip = require_sha("branch_tip", branch_tip)
        parent = git(repository_root, ["rev-parse", f"{branch_tip}^1"])
        if parent != planned_source_sha:
            raise ValueError(
                "changelog branch tip first parent must equal the planned source SHA "
                f"(got {parent}, want {planned_source_sha})"
            )
        if is_ancestor(repository_root, branch_tip, main_ref):
            preferred = branch_tip

    main_commit = find_main_reachable_consolidate(
        repository_root,
        planned_source_sha=planned_source_sha,
        version=version,
        main_ref=main_ref,
    )

    commit = preferred or main_commit or ""
    if not commit and branch_tip and preferred == "":
        if main_commit:
            commit = main_commit
        else:
            raise ValueError(
                "changelog branch tip is not reachable from main and no main-reachable "
                f"consolidate commit exists for v{version}"
            )

    if not commit:
        return {
            "mode": "missing",
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
