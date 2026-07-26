#!/usr/bin/env python3
"""Fail closed when Codemagic does not intake a native macOS candidate tag."""

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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUILDS_API = "https://api.codemagic.io/builds"
EVIDENCE_SCHEMA = "codemagic-native-tag-intake/v1"
RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ProviderApiError(RuntimeError):
    """A credential-safe Codemagic visibility failure."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def validate_inputs(
    *,
    app_id: str,
    workflow_id: str,
    release_tag: str,
    source_sha: str,
    timeout_seconds: int,
    poll_seconds: int,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{24}", app_id):
        raise ValueError("app_id must be a 24-character lowercase hexadecimal Codemagic app ID")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", workflow_id):
        raise ValueError("workflow_id must be a codemagic.yaml workflow key")
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        raise ValueError("release_tag must be an exact v<version>+<build>-macos tag")
    if not SHA_RE.fullmatch(source_sha):
        raise ValueError("source_sha must be a 40-character lowercase commit SHA")
    if timeout_seconds < 0 or timeout_seconds > 1200:
        raise ValueError("timeout_seconds must be between 0 and 1200")
    if poll_seconds < 1 or poll_seconds > 120:
        raise ValueError("poll_seconds must be between 1 and 120")


def _nested_mapping(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def build_tag(build: dict[str, Any]) -> str:
    for value in (build.get("tag"), _nested_mapping(build, "config").get("tag")):
        if isinstance(value, str):
            return value
    return ""


def build_workflow_id(build: dict[str, Any]) -> str:
    config = _nested_mapping(build, "config")
    for value in (
        build.get("workflowId"),
        build.get("workflow_id"),
        config.get("workflowId"),
        config.get("workflow_id"),
    ):
        if isinstance(value, str):
            return value
    return ""


def build_commit_shas(build: dict[str, Any]) -> set[str]:
    candidates: list[object] = [
        build.get("commit"),
        build.get("commitId"),
        build.get("commitHash"),
        build.get("commitSha"),
        _nested_mapping(build, "config").get("commit"),
    ]
    shas: set[str] = set()
    for candidate in candidates:
        if isinstance(candidate, str) and SHA_RE.fullmatch(candidate):
            shas.add(candidate)
        elif isinstance(candidate, dict):
            for key in ("hash", "sha", "id"):
                value = candidate.get(key)
                if isinstance(value, str) and SHA_RE.fullmatch(value):
                    shas.add(value)
    return shas


def summarize_build(build: dict[str, Any]) -> dict[str, object]:
    build_id = build.get("_id") or build.get("id") or build.get("buildId") or ""
    return {
        "build_id": build_id if isinstance(build_id, str) else "",
        "tag": build_tag(build),
        "workflow_id": build_workflow_id(build),
        "commit_shas": sorted(build_commit_shas(build)),
        "status": build.get("status") if isinstance(build.get("status"), str) else "",
        "created_at": build.get("createdAt") if isinstance(build.get("createdAt"), str) else "",
    }


def classify_builds(
    builds: list[dict[str, Any]],
    *,
    release_tag: str,
    workflow_id: str,
    source_sha: str,
) -> dict[str, object]:
    exact_tag = [build for build in builds if build_tag(build) == release_tag]
    exact_workflow = [build for build in exact_tag if build_workflow_id(build) == workflow_id]
    observed_workflows = sorted({build_workflow_id(build) or "<unreported>" for build in exact_tag})

    status = "native_intake_absent"
    message = (
        f"Codemagic returned no build for exact tag {release_tag}; inspect the app Webhooks view "
        "and do not recreate or rewrite the immutable tag."
    )
    if exact_tag and not exact_workflow:
        status = "workflow_selector_mismatch"
        message = (
            f"Codemagic has build records for {release_tag}, but none use workflow {workflow_id}; "
            f"observed workflows: {', '.join(observed_workflows)}."
        )
    elif len(exact_workflow) > 1:
        status = "duplicate_native_intake"
        message = (
            f"Codemagic created {len(exact_workflow)} builds for exact tag {release_tag} and workflow "
            f"{workflow_id}; preserve the immutable tag and inspect provider webhook deduplication."
        )
    elif exact_workflow:
        reported_shas = set().union(*(build_commit_shas(build) for build in exact_workflow))
        if reported_shas and source_sha not in reported_shas:
            status = "source_identity_mismatch"
            message = (
                f"Codemagic workflow {workflow_id} intook {release_tag}, but its reported source "
                f"does not match {source_sha}; observed: {', '.join(sorted(reported_shas))}."
            )
        else:
            status = "intake_confirmed"
            source_note = (
                f" and reported exact source {source_sha}"
                if source_sha in reported_shas
                else "; the immutable tag remains the source identity because this API response omitted commit SHA"
            )
            message = f"Codemagic intook {release_tag} with workflow {workflow_id}{source_note}."

    return {
        "status": status,
        "message": message,
        "total_builds_returned": len(builds),
        "exact_tag_build_count": len(exact_tag),
        "exact_workflow_build_count": len(exact_workflow),
        "observed_workflows": observed_workflows,
        "matching_builds": [summarize_build(build) for build in exact_tag[:10]],
    }


def fetch_builds(
    *,
    app_id: str,
    release_tag: str,
    api_token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    if not api_token:
        raise ProviderApiError("CODEMAGIC_API_TOKEN is not configured", retryable=False)
    query = urllib.parse.urlencode({"appId": app_id, "tag": release_tag, "limit": 100})
    request = urllib.request.Request(
        f"{BUILDS_API}?{query}",
        headers={"Accept": "application/json", "x-auth-token": api_token},
        method="GET",
    )
    try:
        with opener(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        retryable = error.code == 429 or error.code >= 500
        raise ProviderApiError(
            f"Codemagic builds query returned HTTP {error.code}",
            retryable=retryable,
        ) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ProviderApiError(f"Codemagic builds query was unavailable: {type(error).__name__}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderApiError("Codemagic builds query returned invalid JSON") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("builds"), list):
        raise ProviderApiError("Codemagic builds query returned an unexpected payload")
    builds = payload["builds"]
    if not all(isinstance(build, dict) for build in builds):
        raise ProviderApiError("Codemagic builds query returned a non-object build record")
    return builds


def poll_for_intake(
    *,
    fetch: Callable[[], list[dict[str, Any]]],
    release_tag: str,
    workflow_id: str,
    source_sha: str,
    timeout_seconds: int,
    poll_seconds: int,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    started = monotonic()
    deadline = started + timeout_seconds
    attempts = 0
    successful_queries = 0
    consecutive_errors = 0
    api_errors: list[dict[str, object]] = []
    decision = classify_builds([], release_tag=release_tag, workflow_id=workflow_id, source_sha=source_sha)

    while True:
        attempts += 1
        try:
            builds = fetch()
            successful_queries += 1
            consecutive_errors = 0
            decision = classify_builds(
                builds,
                release_tag=release_tag,
                workflow_id=workflow_id,
                source_sha=source_sha,
            )
            if decision["status"] == "intake_confirmed":
                break
        except ProviderApiError as error:
            consecutive_errors += 1
            api_errors.append(
                {
                    "attempt": attempts,
                    "message": str(error),
                    "retryable": error.retryable,
                }
            )
            api_errors = api_errors[-10:]
            if not error.retryable:
                break

        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(float(poll_seconds), remaining))

    if decision["status"] != "intake_confirmed" and (successful_queries == 0 or consecutive_errors > 0):
        latest_error = api_errors[-1]["message"] if api_errors else "no successful query"
        decision = {
            **decision,
            "status": "provider_api_unavailable",
            "message": (
                "Codemagic build visibility was unavailable at the intake deadline "
                f"({latest_error}); native intake cannot be distinguished from an API-query failure."
            ),
        }

    return {
        "attempts": attempts,
        "successful_queries": successful_queries,
        "elapsed_seconds": round(monotonic() - started, 3),
        "api_errors": api_errors,
        "decision": decision,
    }


def write_evidence(path: Path, evidence: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    validate_inputs(
        app_id=args.app_id,
        workflow_id=args.workflow_id,
        release_tag=args.release_tag,
        source_sha=args.source_sha,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    result = poll_for_intake(
        fetch=lambda: fetch_builds(
            app_id=args.app_id,
            release_tag=args.release_tag,
            api_token=os.environ.get("CODEMAGIC_API_TOKEN", ""),
        ),
        release_tag=args.release_tag,
        workflow_id=args.workflow_id,
        source_sha=args.source_sha,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "observed_at": datetime.now(UTC).isoformat(),
        "app_id": args.app_id,
        "workflow_id": args.workflow_id,
        "release_tag": args.release_tag,
        "source_sha": args.source_sha,
        "timeout_seconds": args.timeout_seconds,
        "poll_seconds": args.poll_seconds,
        **result,
    }
    write_evidence(args.evidence, evidence)

    decision = result["decision"]
    assert isinstance(decision, dict)
    message = str(decision["message"])
    if decision["status"] == "intake_confirmed":
        print(message)
        return 0
    print(f"ERROR: {message}", file=sys.stderr)
    print(f"Codemagic intake evidence: {args.evidence}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
