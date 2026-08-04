#!/usr/bin/env python3
"""Prove native Codemagic tag intake or dispatch one fenced fallback build."""

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BUILDS_API = "https://api.codemagic.io/builds"
EVIDENCE_SCHEMA = "codemagic-native-tag-intake/v2"
RELEASE_TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ProviderApiError(RuntimeError):
    """A credential-safe Codemagic API failure."""

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


def build_id(build: dict[str, Any]) -> str:
    for value in (build.get("_id"), build.get("id"), build.get("buildId")):
        if isinstance(value, str):
            return value
    return ""


def build_tag(build: dict[str, Any]) -> str:
    for value in (build.get("tag"), _nested_mapping(build, "config").get("tag")):
        if isinstance(value, str):
            return value
    return ""


def build_workflow_id(build: dict[str, Any]) -> str:
    config = _nested_mapping(build, "config")
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
    return {
        "build_id": build_id(build),
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
    """Classify every reported same-tag build regardless of provider state."""
    exact_tag = [build for build in builds if build_tag(build) == release_tag]
    exact_workflow = [build for build in exact_tag if build_workflow_id(build) == workflow_id]
    observed_workflows = sorted({build_workflow_id(build) or "<unreported>" for build in exact_tag})

    status = "native_intake_absent"
    message = (
        f"Codemagic returned no build for exact tag {release_tag}; the immutable tag is intact and "
        "may be eligible for one fenced fallback dispatch."
    )
    if len(exact_tag) > 1:
        status = "duplicate_same_tag_build"
        message = (
            f"Codemagic has {len(exact_tag)} builds for exact tag {release_tag} across workflows "
            f"{', '.join(observed_workflows)}; a fallback would violate the single-build fence."
        )
    elif exact_tag and not exact_workflow:
        status = "workflow_selector_mismatch"
        message = (
            f"Codemagic has a build record for {release_tag}, but it does not use workflow {workflow_id}; "
            f"observed workflow: {', '.join(observed_workflows)}."
        )
    elif exact_workflow:
        reported_shas = set().union(*(build_commit_shas(build) for build in exact_workflow))
        if reported_shas and source_sha not in reported_shas:
            status = "source_identity_mismatch"
            message = (
                f"Codemagic workflow {workflow_id} selected {release_tag}, but its reported source does not "
                f"match {source_sha}; observed: {', '.join(sorted(reported_shas))}."
            )
        else:
            status = "canonical_build_observed"
            source_note = (
                f" and reported exact source {source_sha}"
                if source_sha in reported_shas
                else "; the immutable tag remains the source identity because this API response omitted commit SHA"
            )
            message = f"Codemagic has one canonical {workflow_id} build for {release_tag}{source_note}."

    return {
        "status": status,
        "message": message,
        "total_builds_returned": len(builds),
        "exact_tag_build_count": len(exact_tag),
        "exact_workflow_build_count": len(exact_workflow),
        "observed_workflows": observed_workflows,
        "matching_builds": [summarize_build(build) for build in exact_tag[:100]],
    }


def _request_json(
    request: urllib.request.Request,
    *,
    opener: Callable[..., Any],
    error_context: str,
) -> dict[str, Any]:
    try:
        with opener(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        retryable = error.code == 429 or error.code >= 500
        raise ProviderApiError(f"{error_context} returned HTTP {error.code}", retryable=retryable) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise ProviderApiError(f"{error_context} was unavailable: {type(error).__name__}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderApiError(f"{error_context} returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ProviderApiError(f"{error_context} returned an unexpected payload")
    return payload


def fetch_builds(
    *,
    app_id: str,
    release_tag: str,
    api_token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    if not api_token:
        raise ProviderApiError("CODEMAGIC_API_TOKEN is not configured", retryable=False)
    # Follow every pagination cursor before classifying, because every state of
    # every same-tag build participates in the duplicate/active-build fence.
    next_url = f"{BUILDS_API}?{urllib.parse.urlencode({'appId': app_id, 'tag': release_tag, 'limit': 100})}"
    builds: list[dict[str, Any]] = []
    visited_urls: set[str] = set()
    while next_url:
        if next_url in visited_urls or len(visited_urls) >= 20:
            raise ProviderApiError("Codemagic builds query returned an invalid pagination cursor", retryable=False)
        visited_urls.add(next_url)
        parsed = urllib.parse.urlparse(next_url)
        if parsed.scheme != "https" or parsed.netloc != "api.codemagic.io" or parsed.path != "/builds":
            raise ProviderApiError("Codemagic builds query returned an unsafe pagination cursor", retryable=False)
        request = urllib.request.Request(
            next_url,
            headers={"Accept": "application/json", "x-auth-token": api_token},
            method="GET",
        )
        payload = _request_json(request, opener=opener, error_context="Codemagic builds query")
        page_builds = payload.get("builds")
        if not isinstance(page_builds, list) or not all(isinstance(build, dict) for build in page_builds):
            raise ProviderApiError("Codemagic builds query returned an unexpected payload")
        builds.extend(page_builds)
        cursor = payload.get("nextPageUrl")
        if cursor is None:
            next_url = ""
        elif isinstance(cursor, str):
            next_url = urllib.parse.urljoin(BUILDS_API, cursor)
        else:
            raise ProviderApiError("Codemagic builds query returned an invalid pagination cursor", retryable=False)
    return builds


def fetch_build(
    *,
    build_id_value: str,
    api_token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    if not build_id_value:
        raise ValueError("build_id_value is required")
    if not api_token:
        raise ProviderApiError("CODEMAGIC_API_TOKEN is not configured", retryable=False)
    request = urllib.request.Request(
        f"{BUILDS_API}/{urllib.parse.quote(build_id_value, safe='')}",
        headers={"Accept": "application/json", "x-auth-token": api_token},
        method="GET",
    )
    payload = _request_json(request, opener=opener, error_context="Codemagic build query")
    build = payload.get("build", payload)
    if not isinstance(build, dict):
        raise ProviderApiError("Codemagic build query returned an unexpected payload")
    return build


def request_fallback_build(
    *,
    app_id: str,
    workflow_id: str,
    release_tag: str,
    api_token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> str:
    """Make the sole authorized POST; callers must have already fenced absence."""
    if not api_token:
        raise ProviderApiError("CODEMAGIC_API_TOKEN is not configured", retryable=False)
    payload = json.dumps({"appId": app_id, "workflowId": workflow_id, "tag": release_tag}).encode("utf-8")
    request = urllib.request.Request(
        BUILDS_API,
        data=payload,
        headers={"Accept": "application/json", "Content-Type": "application/json", "x-auth-token": api_token},
        method="POST",
    )
    response = _request_json(request, opener=opener, error_context="Codemagic fallback build dispatch")
    returned_build_id = response.get("buildId") or response.get("_id") or response.get("id")
    if not isinstance(returned_build_id, str) or not returned_build_id:
        raise ProviderApiError("Codemagic fallback build dispatch did not return a build ID", retryable=False)
    return returned_build_id


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
    """Observe native intake for the complete bounded window before fallback."""
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
            # One canonical build, or an unacceptable same-tag state, settles the
            # decision immediately. Only total absence consumes the full window.
            if decision["status"] != "native_intake_absent":
                break
        except ProviderApiError as error:
            consecutive_errors += 1
            api_errors.append({"attempt": attempts, "message": str(error), "retryable": error.retryable})
            api_errors = api_errors[-10:]
            if not error.retryable:
                break

        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(float(poll_seconds), remaining))

    if decision["status"] == "native_intake_absent" and (successful_queries == 0 or consecutive_errors > 0):
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


def verify_build_identity(
    build: dict[str, Any], *, release_tag: str, workflow_id: str, source_sha: str) -> dict[str, object]:
    errors: list[str] = []
    if build_tag(build) != release_tag:
        errors.append(f"returned build tag {build_tag(build)!r} does not equal {release_tag!r}")
    if build_workflow_id(build) != workflow_id:
        errors.append(f"returned build workflow {build_workflow_id(build)!r} does not equal {workflow_id!r}")
    reported_shas = build_commit_shas(build)
    if reported_shas and source_sha not in reported_shas:
        errors.append(f"returned build source does not equal {source_sha}; observed {sorted(reported_shas)}")
    return {"valid": not errors, "errors": errors, "build": summarize_build(build)}


def dispatch_fallback_after_absence(
    *,
    fetch: Callable[[], list[dict[str, Any]]],
    dispatch: Callable[[], str],
    fetch_one: Callable[[str], dict[str, Any]],
    release_tag: str,
    workflow_id: str,
    source_sha: str,
    visibility_timeout_seconds: int = 120,
    visibility_poll_seconds: int = 5,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Re-fence, POST once, then wait briefly for provider build visibility."""
    final_fence_builds = fetch()
    final_fence = classify_builds(
        final_fence_builds,
        release_tag=release_tag,
        workflow_id=workflow_id,
        source_sha=source_sha,
    )
    if final_fence["status"] == "canonical_build_observed":
        return {"outcome": "canonical_build_observed_before_fallback", "final_fence": final_fence, "dispatch_count": 0}
    if final_fence["status"] != "native_intake_absent":
        return {"outcome": "fallback_fence_rejected", "final_fence": final_fence, "dispatch_count": 0}

    # No retry around this POST: an ambiguous transport result is resolved only by
    # reading the all-state same-tag build set, never by issuing a second request.
    returned_build_id = ""
    dispatch_error = ""
    try:
        returned_build_id = dispatch()
    except ProviderApiError as error:
        dispatch_error = str(error)

    # Codemagic can acknowledge a POST before /builds indexes the new record.
    # Keep the one-build fence intact while allowing bounded visibility lag.
    post_dispatch_visibility = poll_for_intake(
        fetch=fetch,
        release_tag=release_tag,
        workflow_id=workflow_id,
        source_sha=source_sha,
        timeout_seconds=visibility_timeout_seconds,
        poll_seconds=visibility_poll_seconds,
        monotonic=monotonic,
        sleep=sleep,
    )
    final_query = post_dispatch_visibility["decision"]
    assert isinstance(final_query, dict)
    result: dict[str, object] = {
        "final_fence": final_fence,
        "dispatch_count": 1,
        "returned_build_id": returned_build_id,
        "dispatch_error": dispatch_error,
        "post_dispatch_visibility": post_dispatch_visibility,
        "final_query": final_query,
    }
    if final_query["status"] != "canonical_build_observed":
        result["outcome"] = "fallback_final_query_rejected"
        return result

    canonical = final_query["matching_builds"]
    assert isinstance(canonical, list)
    canonical_ids = {item.get("build_id") for item in canonical if isinstance(item, dict)}
    if dispatch_error:
        result["outcome"] = "fallback_dispatch_ambiguous_but_canonical_build_observed"
        return result
    if returned_build_id not in canonical_ids:
        result["outcome"] = "fallback_returned_build_not_canonical"
        return result

    returned_build = fetch_one(returned_build_id)
    returned_identity = verify_build_identity(
        returned_build,
        release_tag=release_tag,
        workflow_id=workflow_id,
        source_sha=source_sha,
    )
    result["returned_build"] = returned_identity
    result["outcome"] = "fallback_dispatched_and_verified" if returned_identity["valid"] else "fallback_returned_build_identity_mismatch"
    return result


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
    parser.add_argument("--dispatch-fallback-on-absence", action="store_true")
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
    api_token = os.environ.get("CODEMAGIC_API_TOKEN", "")
    fetch = lambda: fetch_builds(app_id=args.app_id, release_tag=args.release_tag, api_token=api_token)
    intake = poll_for_intake(
        fetch=fetch,
        release_tag=args.release_tag,
        workflow_id=args.workflow_id,
        source_sha=args.source_sha,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    decision = intake["decision"]
    assert isinstance(decision, dict)
    fallback: dict[str, object] | None = None
    outcome = str(decision["status"])
    success = outcome == "canonical_build_observed"

    if outcome == "native_intake_absent" and args.dispatch_fallback_on_absence:
        fallback = dispatch_fallback_after_absence(
            fetch=fetch,
            dispatch=lambda: request_fallback_build(
                app_id=args.app_id,
                workflow_id=args.workflow_id,
                release_tag=args.release_tag,
                api_token=api_token,
            ),
            fetch_one=lambda build_id_value: fetch_build(build_id_value=build_id_value, api_token=api_token),
            release_tag=args.release_tag,
            workflow_id=args.workflow_id,
            source_sha=args.source_sha,
        )
        outcome = str(fallback["outcome"])
        success = outcome in {
            "canonical_build_observed_before_fallback",
            "fallback_dispatch_ambiguous_but_canonical_build_observed",
            "fallback_dispatched_and_verified",
        }

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "app_id": args.app_id,
        "workflow_id": args.workflow_id,
        "release_tag": args.release_tag,
        "source_sha": args.source_sha,
        "timeout_seconds": args.timeout_seconds,
        "poll_seconds": args.poll_seconds,
        "dispatch_fallback_on_absence": args.dispatch_fallback_on_absence,
        "intake": intake,
        "fallback": fallback,
        "outcome": outcome,
    }
    write_evidence(args.evidence, evidence)

    if success:
        print(f"Codemagic candidate intake complete: {outcome}.")
        return 0
    print(f"ERROR: {decision['message']}", file=sys.stderr)
    print(f"Codemagic intake/fallback evidence: {args.evidence}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
