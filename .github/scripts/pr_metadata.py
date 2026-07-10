#!/usr/bin/env python3
"""Load current pull-request metadata without trusting a stale event payload."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PullRequestMetadata:
    number: int
    body: str
    updated_at: str
    labels: tuple[str, ...]
    source: str


def _parse_metadata(data: dict, source: str) -> PullRequestMetadata:
    labels = data.get("labels") or []
    label_names = tuple(
        sorted(
            label["name"] if isinstance(label, dict) else str(label)
            for label in labels
            if (isinstance(label, str) and label) or (isinstance(label, dict) and label.get("name"))
        )
    )
    number = data.get("number")
    if not isinstance(number, int):
        raise RuntimeError(f"PR metadata from {source} did not include a numeric PR number")
    return PullRequestMetadata(
        number=number,
        body=str(data.get("body") or ""),
        updated_at=str(data.get("updated_at") or data.get("updatedAt") or "unknown"),
        labels=label_names,
        source=source,
    )


def load_from_api(
    repository: str,
    number: int,
    token: str,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> PullRequestMetadata:
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required to read current PR metadata")
    url = f"https://api.github.com/repos/{repository}/pulls/{number}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "omi-pr-preflight",
        },
    )
    try:
        with opener(request, timeout=15) as response:  # type: ignore[attr-defined]
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub API returned HTTP {exc.code} while reading PR #{number}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API request failed while reading PR #{number}: {exc.reason}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"GitHub API returned invalid metadata for PR #{number}")
    return _parse_metadata(payload, f"GitHub API PR #{number}")


def load_from_gh(root: Path) -> PullRequestMetadata:
    try:
        result = subprocess.run(
            ["gh", "pr", "view", "--json", "number,body,updatedAt,labels"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gh is not installed; pass --pr-body-file before the first push") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "no pull request is associated with this branch"
        raise RuntimeError(f"could not discover the current PR with gh: {detail}") from exc
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("gh returned invalid PR metadata")
    return _parse_metadata(payload, "gh current PR")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub repository as owner/name")
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path, help="File to receive the current PR body")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        metadata = load_from_api(args.repository, args.pr_number, os.getenv("GITHUB_TOKEN", ""))
    except RuntimeError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    args.output.write_text(metadata.body, encoding="utf-8")
    print(f"Loaded {metadata.source}, updated_at={metadata.updated_at}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
