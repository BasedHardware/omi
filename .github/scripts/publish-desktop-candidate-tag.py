#!/usr/bin/env python3
"""Publish an immutable lightweight macOS candidate tag from exact live main."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SOURCE_IDENTITY_SCHEMA = "desktop-release-planner-source-identity/v2"
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


def run_git(
    args: list[str], *, stdin: str | None = None, environment: dict[str, str] | None = None
) -> str:
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


def validate_planner_evidence(*, evidence: str, release_tag: str, candidate_sha: str) -> None:
    """Bind the separately retained planner artifact to this exact lightweight tag."""
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
        "origin_main_sha": candidate_sha,
    }
    for field, value in expected.items():
        if decoded.get(field) != value:
            raise ValueError(f"planner source identity evidence {field} does not bind this candidate")


def create_local_lightweight_tag(*, release_tag: str, candidate_sha: str) -> None:
    """Create a direct commit tag; it is not a candidate until pushed."""
    # No --annotate/--message flag: Codemagic's native tag trigger requires a
    # lightweight ref, while source provenance is retained as a workflow artifact.
    run_git(["tag", release_tag, candidate_sha])


def live_main_sha(repository: str) -> str:
    response = run_gh_json(["api", "--method", "GET", f"repos/{repository}/git/ref/heads/main"])
    target = response.get("object")
    if not isinstance(target, dict):
        raise ValueError("GitHub did not return the live main ref target")
    sha = target.get("sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ValueError("GitHub did not return the live main commit SHA")
    return sha


def publish_immutable_tag_ref(release_tag: str) -> None:
    """Publish through Git's tag push so Codemagic sees its native tag trigger."""
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
    # A local tag is not a candidate. It becomes one only through the native
    # Git tag push below, which is the provider-visible Codemagic boundary.
    create_local_lightweight_tag(release_tag=release_tag, candidate_sha=candidate_sha)
    observed_main_sha = live_main_sha(repository)
    if observed_main_sha != candidate_sha:
        raise ValueError(
            "GitHub main moved before candidate publication; "
            f"expected {candidate_sha}, observed {observed_main_sha}; tag was not pushed"
        )
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
