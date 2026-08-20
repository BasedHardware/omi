#!/usr/bin/env python3
"""Load Line-Count-Exception text from PRs associated with a merged commit.

Release Eligibility runs on a push SHA, where the original PR body is not in
the event payload. Body-declared line-count exceptions therefore disappear and
the ratchet fails the same diff that the PR lane already approved (#11564).

This helper concatenates the bodies of pull requests associated with a commit
so the post-merge ratchet can honor those declarations.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_VERSION = "2022-11-28"


def associated_pr_bodies(
    repository: str,
    sha: str,
    token: str,
    *,
    opener=urllib.request.urlopen,
) -> str:
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to read associated pull requests")
    if "/" not in repository:
        raise RuntimeError(f"repository must be owner/name, got {repository!r}")
    url = f"https://api.github.com/repos/{repository}/commits/{sha}/pulls"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "omi-release-eligibility",
        },
    )
    try:
        with opener(request, timeout=15) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise RuntimeError(f"GitHub API returned HTTP {code} while listing PRs for {sha}") from None
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"GitHub API request failed while listing PRs for {sha}: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"GitHub API returned invalid associated-PR payload for {sha}")
    bodies: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        body = item.get("body")
        if isinstance(body, str) and body.strip():
            bodies.append(body)
    return "\n\n".join(bodies)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub repository as owner/name")
    parser.add_argument("--sha", required=True, help="Commit SHA whose associated PRs should be read")
    parser.add_argument("--output", required=True, type=Path, help="File to receive concatenated PR bodies")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        body = associated_pr_bodies(args.repository, args.sha, os.getenv("GITHUB_TOKEN", ""))
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    args.output.write_text(body, encoding="utf-8")
    print(f"OK: wrote associated PR body ({len(body)} bytes) for {args.sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
