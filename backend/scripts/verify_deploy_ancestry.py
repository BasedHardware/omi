#!/usr/bin/env python3
"""Reusable deploy ancestry guard for backend deployments (chip task_53b2277f).

Verifies mechanically whether a candidate/merge commit SHA is contained within
a deployed release SHA using the GitHub commits compare API (or local git fallback).
Eliminates ad-hoc manual verification so post-deploy verification scripts and
workflows can prove: 'is the intended change actually live?'

Exit Codes:
  0: <contains> is an ancestor of <release> (intended change is present).
  1: <contains> is NOT an ancestor of <release> (change is missing).
  2: Resolution / network / argument error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
DEFAULT_REPO = "BasedHardware/omi"


class AncestryError(Exception):
    """Raised when ancestry cannot be resolved due to invalid inputs or network failure."""


@dataclass(frozen=True)
class AncestryResult:
    is_ancestor: bool
    status: str
    ahead_by: int
    behind_by: int
    release: str
    contains: str
    method: str  # "github_api", "git_merge_base", or "identity"
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_ancestor": self.is_ancestor,
            "status": self.status,
            "ahead_by": self.ahead_by,
            "behind_by": self.behind_by,
            "release": self.release,
            "contains": self.contains,
            "method": self.method,
            "detail": self.detail,
        }


def validate_sha(sha: str, name: str) -> str:
    """Validate and normalize a 40-character hex commit SHA."""
    cleaned = (sha or "").strip().lower()
    if not SHA_RE.match(cleaned):
        raise AncestryError(f"Invalid {name} SHA: '{sha}'. Must be a 40-character hexadecimal SHA.")
    if cleaned == "0" * 40:
        raise AncestryError(f"Invalid {name} SHA: cannot be all-zero sentinel.")
    return cleaned


def query_github_compare(
    *,
    repository: str,
    base: str,
    head: str,
    token: str | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Query GitHub commits compare API: compare base...head."""
    base_encoded = urllib.parse.quote(base)
    head_encoded = urllib.parse.quote(head)
    url = f"https://api.github.com/repos/{repository}/compare/{base_encoded}...{head_encoded}"

    headers = {
        "User-Agent": "BasedHardware-Omi-DeployAncestryGuard/1.0",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if exc.code == 404:
            raise AncestryError(
                f"GitHub compare API 404: commit {base} or {head} was not found in {repository}."
            ) from exc
        if exc.code == 403:
            raise AncestryError(
                f"GitHub compare API rate limit or permissions error (HTTP 403): {body[:200]}"
            ) from exc
        raise AncestryError(f"GitHub compare API HTTP {exc.code}: {body[:200]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AncestryError(f"Network error querying GitHub compare API: {exc}") from exc


def check_ancestry_via_git(contains: str, release: str) -> bool:
    """Fallback to local git merge-base --is-ancestor."""
    cmd = ["git", "merge-base", "--is-ancestor", contains, release]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise AncestryError(f"git merge-base failed (exit {proc.returncode}): {proc.stderr.strip()}")


def verify_deploy_ancestry(
    *,
    release_sha: str,
    contains_sha: str,
    repository: str = DEFAULT_REPO,
    token: str | None = None,
    allow_git_fallback: bool = True,
) -> AncestryResult:
    """Determine whether contains_sha is an ancestor of release_sha."""
    release = validate_sha(release_sha, "release")
    contains = validate_sha(contains_sha, "contains")

    # 1. Identity case: commit is an ancestor of itself
    if release == contains:
        return AncestryResult(
            is_ancestor=True,
            status="identical",
            ahead_by=0,
            behind_by=0,
            release=release,
            contains=contains,
            method="identity",
            detail="Release SHA matches target commit exactly.",
        )

    # 2. Query GitHub Commits Compare API (base=contains, head=release)
    api_error: Exception | None = None
    try:
        payload = query_github_compare(
            repository=repository,
            base=contains,
            head=release,
            token=token,
        )
        status = payload.get("status", "unknown")
        ahead_by = int(payload.get("ahead_by", 0))
        behind_by = int(payload.get("behind_by", 0))

        # contains is an ancestor of release iff release has all commits of contains,
        # meaning release is ahead of contains and behind by 0.
        is_ancestor = status in ("ahead", "identical") and behind_by == 0
        detail = (
            f"Release {release[:8]} contains {contains[:8]} (status={status}, ahead_by={ahead_by}, behind_by={behind_by})"
            if is_ancestor
            else f"Release {release[:8]} lacks {contains[:8]} (status={status}, ahead_by={ahead_by}, behind_by={behind_by})"
        )

        return AncestryResult(
            is_ancestor=is_ancestor,
            status=status,
            ahead_by=ahead_by,
            behind_by=behind_by,
            release=release,
            contains=contains,
            method="github_api",
            detail=detail,
        )
    except Exception as exc:
        api_error = exc

    # 3. Local Git Fallback (if API was unavailable or errored)
    if allow_git_fallback:
        try:
            is_ancestor = check_ancestry_via_git(contains, release)
            detail = (
                f"Resolved via git merge-base: {contains[:8]} is ancestor of {release[:8]}"
                if is_ancestor
                else f"Resolved via git merge-base: {contains[:8]} is NOT an ancestor of {release[:8]}"
            )
            return AncestryResult(
                is_ancestor=is_ancestor,
                status="ahead" if is_ancestor else "diverged",
                ahead_by=1 if is_ancestor else 0,
                behind_by=0 if is_ancestor else 1,
                release=release,
                contains=contains,
                method="git_merge_base",
                detail=detail,
            )
        except Exception as git_exc:
            raise AncestryError(
                f"Failed to check ancestry via GitHub API ({api_error}) and local git ({git_exc})."
            ) from git_exc

    raise AncestryError(f"GitHub API ancestry check failed: {api_error}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--release",
        required=True,
        help="Deployed release SHA (the prospective descendant commit).",
    )
    parser.add_argument(
        "--contains",
        required=True,
        help="Target commit / PR merge SHA to verify (the prospective ancestor commit).",
    )
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO),
        help=f"Target GitHub owner/repo (default: GITHUB_REPOSITORY or '{DEFAULT_REPO}').",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"),
        help="GitHub personal access token (default: GH_TOKEN or GITHUB_TOKEN).",
    )
    parser.add_argument(
        "--no-git-fallback",
        action="store_true",
        help="Disable local git merge-base fallback if GitHub API fails.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON result to stdout.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress human-readable status outputs (rely on exit code).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = verify_deploy_ancestry(
            release_sha=args.release,
            contains_sha=args.contains,
            repository=args.repository,
            token=args.token,
            allow_git_fallback=not args.no_git_fallback,
        )

        if args.json:
            print(json.dumps(result.as_dict(), indent=2))
        elif not args.quiet:
            if result.is_ancestor:
                print(f"[OK] Ancestry verified via {result.method}: {result.detail}")
            else:
                print(f"[FAIL] Ancestry check failed via {result.method}: {result.detail}", file=sys.stderr)

        return 0 if result.is_ancestor else 1

    except AncestryError as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "is_ancestor": False}, indent=2), file=sys.stderr)
        elif not args.quiet:
            print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
