#!/usr/bin/env python3
"""Run the Codemagic qualification lane for a desktop beta candidate.

Starts the omi-desktop-qualification Codemagic workflow for an immutable
v*-macos tag, polls the build to a terminal state, then verifies the build's
qualification-result artifact binds to the exact requested tag and source SHA.
Exit code 0 means the Codemagic lane actually qualified this candidate; any
other outcome (build failure, timeout, artifact missing, tag/SHA mismatch,
transient API death) exits non-zero so the workflow falls back to the
self-hosted qualification lane.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.codemagic.io"
SUCCESS_STATUSES = {"finished"}
FAILURE_STATUSES = {"failed", "canceled", "cancelled", "timeout", "skipped", "warning"}
RESULT_ARTIFACT_NAME = "qualification-result.json"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _request(url: str, token: str, payload: dict | None = None) -> dict:
    data = None
    headers = {"x-auth-token": token}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def start_build(
    token: str, app_id: str, workflow_id: str, branch: str, release_tag: str, gh_token: str
) -> str:
    variables = {"OMI_QUALIFY_TAG": release_tag}
    if gh_token:
        # Short-lived Omi Bot app token for the build's read-only gh calls; the
        # Codemagic workflow deliberately imports no standing credential group.
        variables["OMI_QUALIFY_GH_TOKEN"] = gh_token
    payload = {
        "appId": app_id,
        "workflowId": workflow_id,
        # The workflow configuration is trusted from the mainline branch; the
        # candidate source is materialized from the immutable tag inside the
        # build via OMI_QUALIFY_TAG.
        "branch": branch,
        "environment": {"variables": variables},
    }
    response = _request(f"{API_BASE}/builds", token, payload)
    build_id = response.get("buildId")
    if not build_id:
        fail(f"Codemagic did not return a buildId: {json.dumps(response)[:500]}")
    return str(build_id)


def get_build(token: str, build_id: str) -> dict:
    response = _request(f"{API_BASE}/builds/{build_id}", token)
    build = response.get("build")
    if not isinstance(build, dict):
        fail(f"Codemagic build lookup returned no build object: {json.dumps(response)[:500]}")
    return build


def poll_build(token: str, build_id: str, poll_seconds: int, timeout_minutes: int) -> dict:
    deadline = time.monotonic() + timeout_minutes * 60
    consecutive_errors = 0
    last_status = ""
    while time.monotonic() < deadline:
        try:
            build = get_build(token, build_id)
            consecutive_errors = 0
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            consecutive_errors += 1
            if consecutive_errors >= 10:
                fail(f"Codemagic API unreachable while polling build {build_id}: {exc}")
            time.sleep(poll_seconds)
            continue
        status = str(build.get("status", ""))
        if status != last_status:
            print(f"codemagic build {build_id}: {status}", flush=True)
            last_status = status
        if status in SUCCESS_STATUSES or status in FAILURE_STATUSES:
            return build
        time.sleep(poll_seconds)
    fail(f"Codemagic build {build_id} did not reach a terminal state within {timeout_minutes} minutes")
    raise AssertionError("unreachable")


def verify_result_payload(payload: dict, release_tag: str, target_sha: str) -> None:
    if payload.get("ok") is not True:
        fail(f"qualification result does not report ok=true: {json.dumps(payload)[:500]}")
    if payload.get("release_tag") != release_tag:
        fail(
            "qualification result is bound to a different tag: "
            f"{payload.get('release_tag')!r} != {release_tag!r}"
        )
    if payload.get("source_sha") != target_sha:
        fail(
            "qualification result is bound to a different source SHA: "
            f"{payload.get('source_sha')!r} != {target_sha!r}"
        )


def fetch_result_artifact(token: str, build: dict) -> dict:
    artefacts = build.get("artefacts") or []
    url = ""
    for artefact in artefacts:
        if isinstance(artefact, dict) and artefact.get("name") == RESULT_ARTIFACT_NAME:
            url = str(artefact.get("url", ""))
            break
    if not url:
        names = [a.get("name") for a in artefacts if isinstance(a, dict)]
        fail(f"finished Codemagic build has no {RESULT_ARTIFACT_NAME} artifact (found: {names})")
    request = urllib.request.Request(url, headers={"x-auth-token": token})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--timeout-minutes", type=int, default=150)
    args = parser.parse_args()

    token = os.environ.get("CODEMAGIC_API_TOKEN", "")
    if not token:
        fail("CODEMAGIC_API_TOKEN environment variable is required")
    gh_token = os.environ.get("QUALIFY_GH_TOKEN", "")
    if not gh_token:
        fail("QUALIFY_GH_TOKEN environment variable is required for the build's read-only gh calls")

    build_id = start_build(token, args.app_id, args.workflow_id, args.branch, args.release_tag, gh_token)
    print(f"dispatched Codemagic qualification build {build_id} for {args.release_tag}")
    print(f"build page: https://codemagic.io/app/{args.app_id}/build/{build_id}")

    build = poll_build(token, build_id, args.poll_seconds, args.timeout_minutes)
    status = str(build.get("status", ""))
    if status not in SUCCESS_STATUSES:
        fail(f"Codemagic qualification build {build_id} ended {status}")

    payload = fetch_result_artifact(token, build)
    verify_result_payload(payload, args.release_tag, args.target_sha)
    print(f"Codemagic lane qualified {args.release_tag} at {args.target_sha} (build {build_id})")


if __name__ == "__main__":
    main()
