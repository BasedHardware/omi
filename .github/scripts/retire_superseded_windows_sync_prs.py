#!/usr/bin/env python3
"""Close Windows version-sync PRs superseded by a newer release."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TextIO

WINDOWS_SYNC_BRANCH_RE = re.compile(r"^release/windows-v(\d+)\.(\d+)\.(\d+)$")
Version = tuple[int, int, int]
Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SyncPullRequest:
    number: int
    branch: str
    version: Version


def parse_version(value: str) -> Version:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    if match is None:
        raise argparse.ArgumentTypeError("version must use MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in match.groups())


def format_version(version: Version) -> str:
    return ".".join(str(part) for part in version)


def decode_sync_pr(raw: object) -> SyncPullRequest | None:
    if not isinstance(raw, dict):
        return None
    number = raw.get("number")
    branch = raw.get("headRefName")
    if (
        not isinstance(number, int)
        or isinstance(number, bool)
        or not isinstance(branch, str)
        or raw.get("baseRefName") != "main"
        or raw.get("isCrossRepository") is not False
    ):
        return None
    match = WINDOWS_SYNC_BRANCH_RE.fullmatch(branch)
    if match is None:
        return None
    return SyncPullRequest(
        number=number,
        branch=branch,
        version=tuple(int(part) for part in match.groups()),
    )


def select_superseded_prs(
    raw_prs: object,
    *,
    current_pr: int,
    current_version: Version,
) -> list[SyncPullRequest] | None:
    if not isinstance(raw_prs, list):
        return None

    sync_prs = [decoded for raw in raw_prs if (decoded := decode_sync_pr(raw)) is not None]
    current = next((pr for pr in sync_prs if pr.number == current_pr), None)
    if current is None or current.version != current_version:
        return None

    return sorted(
        (pr for pr in sync_prs if pr.number != current_pr and pr.version < current_version),
        key=lambda pr: (pr.version, pr.number),
    )


def retire_superseded_prs(
    *,
    repository: str,
    current_pr: int,
    current_version: Version,
    runner: Runner = subprocess.run,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    listing = runner(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repository,
            "--base",
            "main",
            "--state",
            "open",
            "--limit",
            "200",
            "--json",
            "number,headRefName,baseRefName,isCrossRepository",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        print("Warning: could not list Windows sync PRs; cleanup skipped.", file=stderr)
        return 0

    try:
        raw_prs = json.loads(listing.stdout)
    except json.JSONDecodeError:
        print("Warning: gh returned invalid Windows sync PR JSON; cleanup skipped.", file=stderr)
        return 0

    superseded = select_superseded_prs(
        raw_prs,
        current_pr=current_pr,
        current_version=current_version,
    )
    if superseded is None:
        print(
            f"Warning: current Windows sync PR #{current_pr} was not confirmed; cleanup skipped.",
            file=stderr,
        )
        return 0

    current_version_text = format_version(current_version)
    closed = 0
    for pull_request in superseded:
        comment = (
            f"Superseded by Windows release sync PR #{current_pr} "
            f"(v{current_version_text}). The release tag remains authoritative; "
            "no tag, release, or branch was deleted."
        )
        result = runner(
            [
                "gh",
                "pr",
                "close",
                str(pull_request.number),
                "--repo",
                repository,
                "--comment",
                comment,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"Warning: could not close superseded Windows sync PR #{pull_request.number}.",
                file=stderr,
            )
            continue
        closed += 1
        message = (
            f"Closed superseded Windows sync PR #{pull_request.number} " f"(v{format_version(pull_request.version)})."
        )
        print(
            message,
            file=stdout,
        )

    print(f"Retired {closed} superseded Windows sync PR(s).", file=stdout)
    return closed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Close older same-repository Windows version-sync PRs.")
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="GitHub repository in owner/name form (defaults to GITHUB_REPOSITORY).",
    )
    parser.add_argument("--current-pr", type=int, required=True)
    parser.add_argument("--current-version", type=parse_version, required=True)
    args = parser.parse_args(argv)
    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    if args.current_pr <= 0:
        parser.error("--current-pr must be positive")

    retire_superseded_prs(
        repository=args.repository,
        current_pr=args.current_pr,
        current_version=args.current_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
