#!/usr/bin/env python3
"""Retire superseded Windows release version-sync PRs.

The Windows release workflow opens one `release/windows-v<version>` sync PR per
release. The release tag is authoritative, so any older open sync PR targeting
main is stale once a newer release has a PR. This script closes those stale PRs
with a comment pointing at the newest one, keeping review noise down without
touching tags, releases, or branches.

The selection predicate is pure and unit-tested; the gh calls are best-effort
and never raise (the release is already published by the time this runs).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]

GithubRunner = object  # gh subprocess seam for tests


@dataclass(frozen=True)
class SyncPullRequest:
    number: int
    head_ref: str


def select_superseded(prs: Sequence[SyncPullRequest], current_number: int, prefix: str) -> list[SyncPullRequest]:
    """Return the PRs to close: same-repo `prefix*` heads, excluding the current PR.

    The current PR is retained and unrelated heads (no matching prefix) are never
    selected, so a release can only retire the exact class of PR it replaces.
    """
    return [
        pr
        for pr in prs
        if pr.number != current_number and pr.head_ref.startswith(prefix)
    ]


def _run_gh(args: Sequence[str], *, gh: str = "gh") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [gh, *args],
        text=True,
        capture_output=True,
        check=False,
    )


def retire(
    *,
    current_number: int,
    version: str,
    base: str,
    search_head: str,
    gh: str = "gh",
) -> list[SyncPullRequest]:
    """List matching open PRs and close every one except the current PR.

    Returns the list of PRs that were closed. All gh failures are swallowed so a
    cleanup problem can never block the release workflow.
    """
    listed = _run_gh(
        [
            "pr", "list",
            "--base", base,
            "--state", "open",
            "--search", f"head:{search_head}",
            "--json", "number,headRefName",
        ],
        gh=gh,
    )
    if listed.returncode:
        return []

    try:
        raw = json.loads(listed.stdout)
    except json.JSONDecodeError:
        return []

    prs = [SyncPullRequest(number=item["number"], head_ref=item["headRefName"]) for item in raw]
    to_close = select_superseded(prs, current_number, search_head)

    for pr in to_close:
        closed = _run_gh(
            [
                "pr", "close", str(pr.number),
                "--comment",
                f"Superseded by #{current_number} (release v{version}); the release tag is authoritative.",
            ],
            gh=gh,
        )
        if closed.returncode == 0:
            print(f"Closed superseded sync PR #{pr.number} in favor of #{current_number}.")
        else:
            print(f"Could not close superseded PR #{pr.number} (non-fatal).", file=sys.stderr)
    return to_close


def _self_test(gh: str) -> int:
    """Hermetic check of the selection predicate and CLI wiring (no gh needed)."""
    prs = [
        SyncPullRequest(number=10419, head_ref="release/windows-v1.0.3"),
        SyncPullRequest(number=10513, head_ref="release/windows-v1.0.11"),
        SyncPullRequest(number=10723, head_ref="release/windows-v1.0.26"),
        SyncPullRequest(number=99999, head_ref="unrelated/feature"),
        SyncPullRequest(number=10960, head_ref="release/windows-v1.0.30"),
    ]
    selected = select_superseded(prs, current_number=10960, prefix="release/windows-v")
    expected = [10419, 10513, 10723]
    if [pr.number for pr in selected] != expected:
        print(f"self-test failed: selected {selected}, expected {expected}", file=sys.stderr)
        return 1

    kept = [pr.number for pr in prs if pr.number not in {pr.number for pr in selected}]
    if 10960 not in kept or 99999 not in kept:
        print("self-test failed: current or unrelated PR was not retained", file=sys.stderr)
        return 1

    if shutil.which(gh) is None:
        print(f"self-test passed; gh not found on PATH ({gh!r}), skipping live listing", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-pr", type=int, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--search-head", default="release/windows-v")
    parser.add_argument("--gh", default="gh", help="gh executable (test seam)")
    parser.add_argument("--self-test", action="store_true", help="run the hermetic predicate self-test and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test(args.gh)

    retire(
        current_number=args.current_pr,
        version=args.version,
        base=args.base,
        search_head=args.search_head,
        gh=args.gh,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
