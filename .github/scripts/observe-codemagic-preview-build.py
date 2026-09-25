#!/usr/bin/env python3
"""Fail closed unless the dispatched Codemagic preview build reaches a terminal success."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CODEMAGIC_BUILDS_URL = "https://api.codemagic.io/builds"
CANONICAL_WORKFLOW = "omi-desktop-swift-preview"
SCHEMA = "codemagic-preview-build-observation/v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,47}$")
SECRET_RE = re.compile(r"(?i)(bearer\s+|x-auth-token[:=]\s*)\S+")

SUCCESS_STATUSES = frozenset({"finished", "success", "succeeded"})
FAILURE_STATUSES = frozenset({"failed", "canceled", "cancelled", "timeout", "timed_out", "skipped"})


class ObservationError(RuntimeError):
    """A Codemagic preview observation could not be completed."""


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


def nested_mapping(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def build_workflow_id(build: dict[str, Any]) -> str:
    config = nested_mapping(build, "config")
    for value in (
        build.get("fileWorkflowId"),
        build.get("workflowId"),
        build.get("workflow_id"),
        config.get("fileWorkflowId"),
        config.get("workflowId"),
        config.get("workflow_id"),
    ):
        if isinstance(value, str):
            return value
    return ""


def build_env_variables(build: dict[str, Any]) -> dict[str, str]:
    variables: dict[str, str] = {}
    for container in (
        nested_mapping(build, "environment").get("variables"),
        nested_mapping(nested_mapping(build, "config"), "environment").get("variables"),
        build.get("environmentVariables"),
        nested_mapping(build, "config").get("environmentVariables"),
    ):
        if not isinstance(container, dict):
            continue
        for key, value in container.items():
            if isinstance(key, str) and isinstance(value, str):
                variables[key] = value
    return variables


def public_build(build: dict[str, Any]) -> dict[str, Any]:
    return {
        key: build.get(key)
        for key in ("_id", "buildId", "workflowId", "fileWorkflowId", "branch", "status", "startedAt", "finishedAt")
        if build.get(key) is not None
    }


def fetch_build(*, build_id: str, api_token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{CODEMAGIC_BUILDS_URL}/{urllib.parse.quote(build_id, safe='')}",
        headers={"Accept": "application/json", "x-auth-token": api_token},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, json.JSONDecodeError) as error:
        raise ObservationError(f"Codemagic preview build query failed: {sanitized_error(error)}") from error
    build = payload.get("build", payload) if isinstance(payload, dict) else None
    if not isinstance(build, dict):
        raise ObservationError("Codemagic preview build query returned an unexpected payload")
    return build


def validate_inputs(
    *,
    app_id: str,
    build_id: str,
    preview_slug: str,
    source_sha: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{24}", app_id):
        raise ValueError("app_id must be a 24-character lowercase hexadecimal Codemagic app ID")
    if not build_id or not re.fullmatch(r"[A-Za-z0-9_-]+", build_id):
        raise ValueError("build_id must be a non-empty Codemagic build identifier")
    if not SLUG_RE.fullmatch(preview_slug):
        raise ValueError("preview_slug must be a lowercase preview slug")
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be a 40-character lowercase commit SHA")
    if timeout_seconds < 0 or timeout_seconds > 14400:
        raise ValueError("timeout_seconds must be between 0 and 14400")
    if poll_seconds < 1 or poll_seconds > 120:
        raise ValueError("poll_seconds must be between 1 and 120")


def identity_errors(build: dict[str, Any], *, preview_slug: str, source_sha: str) -> list[str]:
    errors: list[str] = []
    workflow = build_workflow_id(build)
    if workflow and workflow != CANONICAL_WORKFLOW:
        errors.append(f"workflow {workflow!r} is not {CANONICAL_WORKFLOW!r}")
    variables = build_env_variables(build)
    reported_slug = variables.get("PREVIEW_SLUG")
    if reported_slug is not None and reported_slug != preview_slug:
        errors.append(f"PREVIEW_SLUG {reported_slug!r} does not equal {preview_slug!r}")
    reported_sha = variables.get("PREVIEW_SOURCE_SHA")
    if reported_sha is not None and reported_sha != source_sha:
        errors.append(f"PREVIEW_SOURCE_SHA {reported_sha!r} does not equal {source_sha!r}")
    return errors


def observe(
    *,
    app_id: str,
    build_id: str,
    preview_slug: str,
    source_sha: str,
    api_token: str,
    timeout_seconds: int,
    poll_seconds: int,
    output: Path,
    fetch: Callable[..., dict[str, Any]] = fetch_build,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    validate_inputs(
        app_id=app_id,
        build_id=build_id,
        preview_slug=preview_slug,
        source_sha=source_sha,
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
        "build_id": build_id,
        "preview_slug": preview_slug,
        "source_sha": source_sha,
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
            build = fetch(build_id=build_id, api_token=api_token)
        except ObservationError as error:
            evidence["last_error"] = sanitized_error(error)
            build = None
        else:
            evidence.pop("last_error", None)
            evidence["build"] = public_build(build)
            evidence["workflow_observed"] = build_workflow_id(build)
            status = build.get("status") if isinstance(build.get("status"), str) else ""
            evidence["codemagic_status"] = status
            mismatches = identity_errors(build, preview_slug=preview_slug, source_sha=source_sha)
            if mismatches:
                evidence.update(
                    status="identity_mismatch",
                    observed_at=utc_now(),
                    error="; ".join(mismatches),
                )
                atomic_write_json(output, evidence)
                return 1
            if status in SUCCESS_STATUSES:
                evidence.update(status="finished", observed_at=utc_now())
                atomic_write_json(output, evidence)
                return 0
            if status in FAILURE_STATUSES:
                evidence.update(
                    status="failed",
                    observed_at=utc_now(),
                    error=f"Codemagic preview build reached terminal status {status!r}",
                )
                atomic_write_json(output, evidence)
                return 1

        if monotonic() >= deadline:
            evidence.update(status="timeout", observed_at=utc_now())
            if "last_error" in evidence:
                evidence["status"] = "unobservable"
            else:
                evidence["error"] = (
                    "Codemagic preview build did not reach a terminal status before the observation deadline"
                )
            atomic_write_json(output, evidence)
            return 1
        sleeper(min(float(poll_seconds), max(0.0, deadline - monotonic())))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--preview-slug", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    return observe(
        app_id=args.app_id,
        build_id=args.build_id,
        preview_slug=args.preview_slug,
        source_sha=args.source_sha,
        api_token=os.environ.get("CODEMAGIC_API_TOKEN", ""),
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        output=args.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
