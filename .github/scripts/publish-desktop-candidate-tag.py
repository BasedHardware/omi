#!/usr/bin/env python3
"""Publish an immutable timestamped macOS candidate from a merged release source."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SOURCE_IDENTITY_SCHEMA = "desktop-release-planner-source-identity/v3"
SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(bearer\s+)\S+"),
    re.compile(r"\b(?:gh[oprsu]_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+)\b"),
    re.compile(r"(?i)((?:access_)?token=)[^&\s]+"),
    re.compile(r"(?i)(https?://[^:/\s]+:)[^@/\s]+(@)"),
)


class GitHubApiError(RuntimeError):
    """A bounded, credential-safe GitHub CLI failure."""


class GitTransportError(RuntimeError):
    """A bounded, credential-safe native Git publication failure."""


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


def run_git(args: list[str], *, stdin: str | None = None, environment: dict[str, str] | None = None) -> str:
    """Run the native Git transport without exposing credentials in failures."""
    if environment is None:
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    result = subprocess.run(
        ["git", *args],
        check=False,
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    if result.returncode:
        detail = sanitize_api_diagnostic(result.stderr or result.stdout)
        raise GitTransportError(f"Git tag publication failed (exit {result.returncode}): {detail}")
    return result.stdout


def validate_inputs(repository: str, release_tag: str, candidate_sha: str) -> None:
    owner, separator, name = repository.partition("/")
    if not owner or not separator or not name or "/" in name:
        raise ValueError("repository must be in owner/name form")
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        raise ValueError("release_tag must be an exact v<version>+<build>-macos tag")
    if not SHA_RE.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be a 40-character lowercase SHA")


def validate_planner_evidence(*, evidence: str, release_tag: str, candidate_sha: str) -> str:
    """Bind the separately retained planner artifact to this exact candidate tag."""
    try:
        decoded = json.loads(evidence)
    except json.JSONDecodeError as error:
        raise ValueError("planner source identity evidence must be valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("planner source identity evidence must be a JSON object")

    expected = {
        "schema": SOURCE_IDENTITY_SCHEMA,
        "release_tag": release_tag,
        "candidate_source_sha": candidate_sha,
    }
    for field, value in expected.items():
        if decoded.get(field) != value:
            raise ValueError(f"planner source identity evidence {field} does not bind this candidate")
    origin_main_sha = decoded.get("origin_main_sha")
    if not isinstance(origin_main_sha, str) or not SHA_RE.fullmatch(origin_main_sha):
        raise ValueError("planner source identity evidence origin_main_sha must be an exact commit SHA")
    return origin_main_sha


def create_local_candidate_tag(*, release_tag: str, candidate_sha: str) -> None:
    """Create a timestamped immutable tag; it is not a candidate until pushed."""
    run_git(["tag", "--annotate", "--message", f"Omi Desktop candidate {release_tag}", release_tag, candidate_sha])


def require_candidate_merged_on_main(repository: str, candidate_sha: str) -> None:
    """Use GitHub's authoritative comparison so later main merges are valid."""
    response = run_gh_json(["api", "--method", "GET", f"repos/{repository}/compare/{candidate_sha}...main"])
    merge_base = response.get("merge_base_commit")
    merge_base_sha = merge_base.get("sha") if isinstance(merge_base, dict) else None
    if merge_base_sha != candidate_sha:
        raise ValueError("candidate source is not reachable from current GitHub main; tag was not pushed")


def publish_immutable_tag_ref(release_tag: str) -> None:
    """Publish the immutable ref before the workflow dispatches its exact-tag build."""
    tag_ref = f"refs/tags/{release_tag}"
    # No force refspec: an existing remote candidate makes Git fail rather
    # than rewriting immutable tag evidence or retrying a stale candidate.
    run_git(["push", "origin", tag_ref])


def publish_candidate_tag(
    *,
    repository: str,
    release_tag: str,
    candidate_sha: str,
    evidence: str,
) -> None:
    validate_inputs(repository, release_tag, candidate_sha)
    validate_planner_evidence(evidence=evidence, release_tag=release_tag, candidate_sha=candidate_sha)
    # Main may advance after planning. That is safe because the exact green
    # candidate remains immutable and later macOS changes belong to the next
    # hourly train. A candidate that is not merged on main still fails closed.
    require_candidate_merged_on_main(repository, candidate_sha)
    # A local tag is not a candidate. It becomes one only through the native
    # Git tag push below, which is the provider-visible Codemagic boundary.
    create_local_candidate_tag(release_tag=release_tag, candidate_sha=candidate_sha)
    publish_immutable_tag_ref(release_tag)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    evidence = args.evidence.read_text(encoding="utf-8")
    publish_candidate_tag(
        repository=args.repository,
        release_tag=args.release_tag,
        candidate_sha=args.candidate_sha,
        evidence=evidence,
    )
    print(f"Published immutable candidate tag {args.release_tag} at {args.candidate_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
