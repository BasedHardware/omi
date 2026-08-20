#!/usr/bin/env python3
"""Load current pull-request metadata, preferring the API over event payloads."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
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


class TransientPRMetadataError(RuntimeError):
    """The current metadata API was unavailable after bounded retries."""


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


# A single flaky GitHub API response must not fail an unrelated PR's required
# preflight, so transient failures receive bounded deterministic retries.
_API_ATTEMPTS = 3
_TRANSIENT_HTTP_STATUSES = frozenset({500, 502, 503, 504})


def load_from_event_file(event_path: Path, expected_number: int) -> PullRequestMetadata:
    """Read the PR snapshot that triggered this workflow after an API outage."""
    try:
        event = json.loads(event_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"could not read GitHub event payload: {exc}") from exc
    if not isinstance(event, dict) or not isinstance(event.get("pull_request"), dict):
        raise RuntimeError("GitHub event payload did not include a pull_request object")
    pull_request = {**event["pull_request"], "number": event.get("number")}
    metadata = _parse_metadata(pull_request, f"GitHub event payload {event_path}")
    if metadata.number != expected_number:
        raise RuntimeError(
            f"GitHub event payload PR number {metadata.number} did not match expected PR #{expected_number}"
        )
    return metadata


def load_from_api(
    repository: str,
    number: int,
    token: str,
    *,
    opener: Callable[..., object] = urllib.request.urlopen,
    sleeper: Callable[[float], None] = time.sleep,
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
    for attempt in range(1, _API_ATTEMPTS + 1):
        retryable: RuntimeError
        try:
            with opener(request, timeout=15) as response:  # type: ignore[attr-defined]
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            error = RuntimeError(f"GitHub API returned HTTP {exc.code} while reading PR #{number}")
            exc.close()
            if exc.code not in _TRANSIENT_HTTP_STATUSES:
                raise error from exc
            retryable = error
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            reason = getattr(exc, "reason", exc)
            retryable = RuntimeError(f"GitHub API request failed while reading PR #{number}: {reason}")
        else:
            if not isinstance(payload, dict):
                raise RuntimeError(f"GitHub API returned invalid metadata for PR #{number}")
            return _parse_metadata(payload, f"GitHub API PR #{number}")
        if attempt == _API_ATTEMPTS:
            raise TransientPRMetadataError(str(retryable)) from retryable
        sleeper(2.0 * attempt)
    raise AssertionError("unreachable")


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


# GitHub squash-merge subjects end with `(#1234)`. A merge commit starts with
# `Merge pull request #1234`. Either form is enough to recover the PR that
# already passed Hygiene with INV-* / Failure-Class citations in its body.
_SUBJECT_PR_RE = re.compile(r"\(#(\d+)\)")
_MERGE_PR_RE = re.compile(r"^Merge pull request #(\d+)\b")


def extract_merged_pr_number(commit_body: str) -> int | None:
    """Return the merged PR number from a squash/merge commit subject, if any."""
    first_line = commit_body.splitlines()[0].strip() if commit_body else ""
    merge = _MERGE_PR_RE.match(first_line)
    if merge:
        return int(merge.group(1))
    matches = list(_SUBJECT_PR_RE.finditer(first_line))
    if not matches:
        return None
    return int(matches[-1].group(1))


def resolve_main_push_body(
    commit_body: str,
    *,
    repository: str,
    token: str,
    loader: Callable[..., PullRequestMetadata] = load_from_api,
) -> str:
    """Commit message plus the merged PR body when HEAD is a squash/merge.

    #10965 passed only `git log -1` through --pr-body-file, assuming GitHub
    folds the PR description into the squash message. This repo's squash
    default is the commit list, so INV-* citations that made PR Hygiene
    green (see #11835) vanish on the main push. Append the live PR body
    when the subject carries (#NNNN). API failures keep the commit
    message — fail-closed for direct pushes, no new flake on API outage
    when the commit already cites the IDs.
    """
    number = extract_merged_pr_number(commit_body)
    if number is None or not repository or not token:
        return commit_body
    try:
        metadata = loader(repository, number, token)
    except RuntimeError as exc:
        print(f"WARN: could not load merged PR #{number} body: {exc}", file=sys.stderr)
        return commit_body
    pr_body = (metadata.body or "").strip()
    if not pr_body or pr_body in commit_body:
        return commit_body
    return commit_body.rstrip() + "\n\n" + metadata.body


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub repository as owner/name")
    parser.add_argument("--pr-number", type=int, help="PR number when loading a live PR body")
    parser.add_argument(
        "--from-commit-body-file",
        type=Path,
        help="Main-push commit message; resolve (#NNNN) and append that PR body",
    )
    parser.add_argument("--output", required=True, type=Path, help="File to receive the current PR body")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.from_commit_body_file is not None:
        try:
            commit_body = args.from_commit_body_file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"FAIL: could not read commit body: {exc}", file=sys.stderr)
            return 1
        body = resolve_main_push_body(
            commit_body,
            repository=args.repository,
            token=os.getenv("GITHUB_TOKEN", ""),
        )
        args.output.write_text(body, encoding="utf-8")
        number = extract_merged_pr_number(commit_body)
        if number is not None and body != commit_body:
            print(f"Loaded merged PR #{number} body and appended it to the commit message.")
        else:
            print("Using commit message as the main-push PR body.")
        return 0
    if args.pr_number is None:
        print("FAIL: --pr-number or --from-commit-body-file is required", file=sys.stderr)
        return 2
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
