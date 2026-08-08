#!/usr/bin/env python3
"""Retire superseded Windows release version-sync PRs.

The Windows release workflow opens one `release/windows-v<version>` sync PR per
release. The release tag is authoritative, so any older open sync PR targeting
main is stale once a newer release has a PR. This script closes those stale PRs
with a comment pointing at the newest one, keeping review noise down without
touching tags, releases, or branches.

The selection predicate is pure and unit-tested; the gh calls are best-effort
and never raise (the release is already published by the time this runs).

Listing intentionally does **not** use `gh pr list --search 'head:…'`. That
qualifier does not match same-repo `release/windows-v*` heads as a prefix (live
queries return zero results). It also does **not** use a single-page
`gh pr list --limit 100`: this repo routinely has more than 100 open PRs against
`main`, so a truncated first page would silently miss older superseded sync PRs.
Candidates are fetched exhaustively via `gh api --paginate --slurp` and filtered
locally with `head_ref.startswith(prefix)`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]

LIST_PAGE_SIZE = 100

GithubRunner = object  # gh subprocess seam for tests


@dataclass(frozen=True)
class SyncPullRequest:
    number: int
    head_ref: str
    is_cross_repository: bool = False


def select_superseded(prs: Sequence[SyncPullRequest], current_number: int, prefix: str) -> list[SyncPullRequest]:
    """Return the PRs to close: same-repo `prefix*` heads, excluding the current PR.

    The current PR is retained, unrelated heads (no matching prefix) are never
    selected, and fork-origin PRs (is_cross_repository) are never closed — this
    workflow manages only the repository's own release sync PRs, so a release
    can only retire the exact class of PR it replaces.
    """
    return [
        pr
        for pr in prs
        if pr.number != current_number and not pr.is_cross_repository and pr.head_ref.startswith(prefix)
    ]


def list_open_prs_args(*, repository: str, base: str, per_page: int = LIST_PAGE_SIZE) -> list[str]:
    """Build exhaustive `gh api` args for open PRs targeting ``base``.

    Do not add `gh pr list --search head:…` — GitHub's `head:` search qualifier
    does not treat the value as a branch-name prefix for same-repo PRs.
    Do not use a single-page `gh pr list --limit 100` — open PR volume against
    ``main`` can exceed one page, and a truncated list would miss older sync PRs.
    """
    return [
        "api",
        "--paginate",
        "--slurp",
        f"repos/{repository}/pulls?state=open&base={base}&per_page={per_page}",
    ]


def parse_listed_prs(stdout: str) -> list[SyncPullRequest]:
    """Parse `gh api --paginate --slurp` output (array of pages of pulls)."""
    pages = json.loads(stdout)
    if not isinstance(pages, list):
        raise TypeError("expected a JSON array of pull pages")

    prs: list[SyncPullRequest] = []
    for page in pages:
        if not isinstance(page, list):
            raise TypeError("expected each page to be a JSON array of pulls")
        for item in page:
            if not isinstance(item, dict):
                raise TypeError("expected each pull to be a JSON object")
            head = item.get("head") or {}
            base = item.get("base") or {}
            if not isinstance(head, dict) or not isinstance(base, dict):
                raise TypeError("expected pull head/base objects")
            head_repo = head.get("repo") if isinstance(head.get("repo"), dict) else None
            base_repo = base.get("repo") if isinstance(base.get("repo"), dict) else None
            head_full = head_repo.get("full_name") if head_repo else None
            base_full = base_repo.get("full_name") if base_repo else None
            # Missing head repo (deleted fork) is treated as cross-repo so we never close it.
            is_cross = head_full is None or base_full is None or head_full != base_full
            prs.append(
                SyncPullRequest(
                    number=int(item["number"]),
                    head_ref=str(head["ref"]),
                    is_cross_repository=is_cross,
                )
            )
    return prs


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
    repository: str,
    gh: str = "gh",
) -> list[SyncPullRequest]:
    """List all open PRs against ``base`` and close superseded sync PRs.

    Returns the list of PRs that were closed. All gh failures are swallowed so a
    cleanup problem can never block the release workflow.
    """
    listed = _run_gh(list_open_prs_args(repository=repository, base=base), gh=gh)
    if listed.returncode:
        return []

    try:
        prs = parse_listed_prs(listed.stdout)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return []

    to_close = select_superseded(prs, current_number, search_head)

    for pr in to_close:
        closed = _run_gh(
            [
                "pr",
                "close",
                str(pr.number),
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
    """Hermetic check of the selection predicate and listing args (no gh needed)."""
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

    list_args = list_open_prs_args(repository="BasedHardware/omi", base="main")
    if "--search" in list_args or any(a.startswith("head:") for a in list_args):
        print(f"self-test failed: listing still uses head-search: {list_args}", file=sys.stderr)
        return 1
    if "--paginate" not in list_args or "--slurp" not in list_args:
        print(f"self-test failed: listing is not exhaustive: {list_args}", file=sys.stderr)
        return 1
    if not any("per_page=" in a for a in list_args):
        print(f"self-test failed: listing missing per_page: {list_args}", file=sys.stderr)
        return 1

    # Truncation guard: a single full page must not be treated as the complete set.
    page = [
        {
            "number": i,
            "head": {"ref": f"release/windows-v1.0.{i}", "repo": {"full_name": "BasedHardware/omi"}},
            "base": {"repo": {"full_name": "BasedHardware/omi"}},
        }
        for i in range(1, LIST_PAGE_SIZE + 1)
    ]
    if len(parse_listed_prs(json.dumps([page]))) != LIST_PAGE_SIZE:
        print("self-test failed: single-page parse length mismatch", file=sys.stderr)
        return 1
    two_pages = parse_listed_prs(
        json.dumps(
            [
                page,
                [
                    {
                        "number": 999,
                        "head": {"ref": "feat/x", "repo": {"full_name": "BasedHardware/omi"}},
                        "base": {"repo": {"full_name": "BasedHardware/omi"}},
                    }
                ],
            ]
        )
    )
    if len(two_pages) != LIST_PAGE_SIZE + 1:
        print("self-test failed: multi-page parse did not flatten pages", file=sys.stderr)
        return 1

    if shutil.which(gh) is None:
        print(f"self-test passed; gh not found on PATH ({gh!r}), skipping live listing", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-pr", type=int)
    parser.add_argument("--version")
    parser.add_argument("--base", default="main")
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="owner/name for gh api pulls listing (defaults to GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--search-head",
        default="release/windows-v",
        help="local headRefName prefix used after listing open PRs (not a gh --search qualifier)",
    )
    parser.add_argument("--gh", default="gh", help="gh executable (test seam)")
    parser.add_argument("--self-test", action="store_true", help="run the hermetic predicate self-test and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test(args.gh)

    if args.current_pr is None or args.version is None:
        parser.error("--current-pr and --version are required unless --self-test is used")
    if not args.repository:
        parser.error("--repository is required (or set GITHUB_REPOSITORY)")

    retire(
        current_number=args.current_pr,
        version=args.version,
        base=args.base,
        search_head=args.search_head,
        repository=args.repository,
        gh=args.gh,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
