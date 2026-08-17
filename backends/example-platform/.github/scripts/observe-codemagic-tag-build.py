#!/usr/bin/env python3
"""Fail closed unless one native Codemagic build observes an immutable tag."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

CODEMAGIC_BUILDS_URL = "https://api.codemagic.io/builds"
CANONICAL_WORKFLOW = "omi-desktop-swift-release"
SCHEMA = "codemagic-tag-build-observation/v1"
TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_RE = re.compile(r"(?i)(bearer\s+|x-auth-token[:=]\s*)\S+")


class ObservationError(RuntimeError):
    """A read-only Codemagic observation could not be completed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def sanitized_error(error: BaseException) -> str:
    detail = " ".join(str(error).split()) or error.__class__.__name__
    return SECRET_RE.sub(r"\1<redacted>", detail)[:1000]


def fetch_builds(*, app_id: str, api_token: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"appId": app_id, "limit": "100"})
    request = urllib.request.Request(
        f"{CODEMAGIC_BUILDS_URL}?{query}",
        headers={"x-auth-token": api_token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise ObservationError(f"Codemagic build observation request failed: {sanitized_error(error)}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("builds"), list):
        raise ObservationError("Codemagic build observation returned no builds list")
    return [build for build in payload["builds"] if isinstance(build, dict)]


def matching_builds(builds: list[dict[str, Any]], release_tag: str) -> list[dict[str, Any]]:
    """Return only canonical release-workflow builds for the exact tag identity."""
    return [
        build
        for build in builds
        if build.get("workflowId") == CANONICAL_WORKFLOW
        and (build.get("tag") == release_tag or build.get("branch") == release_tag)
    ]


def public_build(build: dict[str, Any]) -> dict[str, Any]:
    """Keep durable evidence useful without copying response metadata wholesale."""
    return {
        key: build.get(key)
        for key in ("_id", "buildId", "workflowId", "tag", "branch", "status", "startedAt", "finishedAt")
        if build.get(key) is not None
    }


def validate_inputs(*, app_id: str, release_tag: str, candidate_sha: str, timeout_seconds: int, poll_seconds: int) -> None:
    if not app_id:
        raise ValueError("app_id must not be empty")
    if not TAG_RE.fullmatch(release_tag):
        raise ValueError("release_tag must be an exact v<version>+<build>-macos tag")
    if not SHA_RE.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be a 40-character lowercase SHA")
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must not be negative")
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")


def observe(
    *,
    app_id: str,
    release_tag: str,
    candidate_sha: str,
    api_token: str,
    timeout_seconds: int,
    poll_seconds: int,
    output: Path,
    fetch: Callable[..., list[dict[str, Any]]] = fetch_builds,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    validate_inputs(
        app_id=app_id,
        release_tag=release_tag,
        candidate_sha=candidate_sha,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
    started = monotonic()
    deadline = started + timeout_seconds
    evidence: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "observing",
        "app_id": app_id,
        "workflow_id": CANONICAL_WORKFLOW,
        "release_tag": release_tag,
        "candidate_sha": candidate_sha,
        "started_at": utc_now(),
        "timeout_seconds": timeout_seconds,
        "poll_seconds": poll_seconds,
        "attempts": 0,
    }
    atomic_write_json(output, evidence)

    if not api_token:
        evidence.update(status="unobservable", observed_at=utc_now(), error="CODEMAGIC_API_TOKEN is required")
        atomic_write_json(output, evidence)
        return 1

    while True:
        evidence["attempts"] = int(evidence["attempts"]) + 1
        try:
            builds = fetch(app_id=app_id, api_token=api_token)
        except ObservationError as error:
            evidence["last_error"] = sanitized_error(error)
            builds = []
        else:
            matches = matching_builds(builds, release_tag)
            evidence["matching_builds"] = [public_build(build) for build in matches]
            if len(matches) == 1:
                evidence.update(status="observed", observed_at=utc_now())
                evidence.pop("last_error", None)
                atomic_write_json(output, evidence)
                return 0
            if len(matches) > 1:
                evidence.update(
                    status="duplicate",
                    observed_at=utc_now(),
                    error="multiple Codemagic release builds match the immutable candidate tag",
                )
                atomic_write_json(output, evidence)
                return 1

        if monotonic() >= deadline:
            evidence.update(status="missing", observed_at=utc_now())
            if "last_error" in evidence:
                evidence["status"] = "unobservable"
            else:
                evidence["error"] = "no Codemagic release build observed for the immutable candidate tag"
            atomic_write_json(output, evidence)
            return 1
        sleeper(min(float(poll_seconds), max(0.0, deadline - monotonic())))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    return observe(
        app_id=args.app_id,
        release_tag=args.release_tag,
        candidate_sha=args.candidate_sha,
        api_token=os.environ.get("CODEMAGIC_API_TOKEN", ""),
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        output=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
