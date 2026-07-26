#!/usr/bin/env python3
"""Publish an immutable annotated macOS candidate tag from exact live main."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

TAGGER_NAME = "github-actions[bot]"
TAGGER_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(bearer\s+)\S+"),
    re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+)\b"),
    re.compile(r"(?i)((?:access_)?token=)[^&\s]+"),
)


class GitHubApiError(RuntimeError):
    """A bounded, credential-safe GitHub CLI failure."""


def sanitize_api_diagnostic(value: str) -> str:
    """Retain actionable API context without echoing credentials."""
    sanitized = " ".join(value.split())
    for pattern in SECRET_PATTERNS:
        replacement = r"\1<redacted>" if pattern.groups else "<redacted>"
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized[:1000] or "no diagnostic text returned"


def run_gh_json(args: list[str], payload: dict[str, object] | None = None) -> dict[str, object]:
    """Call the authenticated GitHub CLI without exposing input to a shell."""
    command = ["gh", *args]
    stdin = None
    if payload is not None:
        command.extend(["--input", "-"])
        stdin = json.dumps(payload)
    result = subprocess.run(
        command,
        check=False,
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = sanitize_api_diagnostic(result.stderr or result.stdout)
        raise GitHubApiError(f"GitHub API request failed (exit {result.returncode}): {detail}")
    try:
        decoded = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = sanitize_api_diagnostic(result.stdout)
        raise GitHubApiError(f"GitHub API returned invalid JSON: {detail}") from error
    if not isinstance(decoded, dict):
        raise ValueError("GitHub API returned an unexpected JSON payload")
    if decoded.get("errors"):
        detail = sanitize_api_diagnostic(json.dumps(decoded["errors"], sort_keys=True))
        raise GitHubApiError(f"GitHub API rejected the request: {detail}")
    return decoded


def validate_inputs(repository: str, release_tag: str, candidate_sha: str) -> None:
    owner, separator, name = repository.partition("/")
    if not owner or not separator or not name or "/" in name:
        raise ValueError("repository must be in owner/name form")
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        raise ValueError("release_tag must be an exact v<version>+<build>-macos tag")
    if not SHA_RE.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be a 40-character lowercase SHA")


def create_annotated_tag_object(
    *, repository: str, release_tag: str, candidate_sha: str, evidence: str, timestamp: str
) -> str:
    response = run_gh_json(
        ["api", "--method", "POST", f"repos/{repository}/git/tags"],
        {
            "tag": release_tag,
            "message": evidence,
            "object": candidate_sha,
            "type": "commit",
            "tagger": {"name": TAGGER_NAME, "email": TAGGER_EMAIL, "date": timestamp},
        },
    )
    tag_object_sha = response.get("sha")
    if not isinstance(tag_object_sha, str) or not SHA_RE.fullmatch(tag_object_sha):
        raise ValueError("GitHub did not return the annotated tag object SHA")
    return tag_object_sha


def live_main_sha(repository: str) -> str:
    response = run_gh_json(["api", "--method", "GET", f"repos/{repository}/git/ref/heads/main"])
    target = response.get("object")
    if not isinstance(target, dict):
        raise ValueError("GitHub did not return the live main ref target")
    sha = target.get("sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ValueError("GitHub did not return the live main commit SHA")
    return sha


def create_immutable_tag_ref(*, repository: str, release_tag: str, tag_object_sha: str) -> None:
    """Create the candidate ref once; conflicts fail without rewriting a tag."""
    expected_ref = f"refs/tags/{release_tag}"
    response = run_gh_json(
        ["api", "--method", "POST", f"repos/{repository}/git/refs"],
        {
            "ref": expected_ref,
            "sha": tag_object_sha,
        },
    )
    target = response.get("object")
    if response.get("ref") != expected_ref or not isinstance(target, dict):
        raise ValueError("GitHub returned an unexpected candidate tag ref")
    if target.get("sha") != tag_object_sha:
        raise ValueError("GitHub candidate tag ref does not target the annotated tag object")


def publish_candidate_tag(
    *,
    repository: str,
    release_tag: str,
    candidate_sha: str,
    evidence: str,
    timestamp: str,
) -> None:
    validate_inputs(repository, release_tag, candidate_sha)
    # A tag object alone is unreachable and is not a candidate. The only
    # candidate-creating action is the create-only ref request below.
    tag_object_sha = create_annotated_tag_object(
        repository=repository,
        release_tag=release_tag,
        candidate_sha=candidate_sha,
        evidence=evidence,
        timestamp=timestamp,
    )
    observed_main_sha = live_main_sha(repository)
    if observed_main_sha != candidate_sha:
        raise ValueError(
            "GitHub main moved before candidate publication; "
            f"expected {candidate_sha}, observed {observed_main_sha}; tag ref was not created"
        )
    create_immutable_tag_ref(
        repository=repository,
        release_tag=release_tag,
        tag_object_sha=tag_object_sha,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    evidence = args.evidence.read_text(encoding="utf-8")
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    publish_candidate_tag(
        repository=args.repository,
        release_tag=args.release_tag,
        candidate_sha=args.candidate_sha,
        evidence=evidence,
        timestamp=timestamp,
    )
    print(f"Published immutable candidate tag {args.release_tag} at {args.candidate_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
