#!/usr/bin/env python3
"""Decide and dispatch the Codemagic internal mobile builds.

App changes land on main in bursts, and a build per merge is mostly wasted: the earlier one is
superseded minutes later. Codemagic's own triggering has no rate limit, so the push trigger is
replaced by this: a three-hourly batch that builds only when app code actually changed, plus an
immediate build for an allowlisted author who needs their own change on a device now.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Iterable, Optional

from mobile_distribution import is_baseline_eligible, normalize_codemagic_build

BUILDS_API = "https://api.codemagic.io/builds"
MOBILE_WORKFLOWS = ("ios-internal-auto", "android-internal-auto")
WORKFLOW_PLATFORMS = {"ios-internal-auto": "ios", "android-internal-auto": "android"}
APP_PATHS = ("app/",)


class DispatchError(Exception):
    pass


def normalized_actors(raw: Optional[str]) -> set[str]:
    return {actor.strip().lower() for actor in (raw or "").split(",") if actor.strip()}


def decide_dispatch(
    *,
    event: str,
    actor: str,
    commit_authors: Iterable[str],
    instant_actors: set[str],
    has_pending_app_commits: bool,
) -> tuple[bool, str]:
    """Return whether to dispatch now, and the reason recorded in the run summary."""
    if event == "workflow_dispatch":
        return True, "manual"

    if event == "push":
        who = {actor.lower()} | {author.lower() for author in commit_authors}
        if who & instant_actors:
            return True, "instant-actor"
        return False, "batched: the three-hourly run picks this up"

    if event == "schedule":
        if has_pending_app_commits:
            return True, "batch: app changes since the last build"
        return False, "no app changes since the last build"

    return False, f"unsupported event {event}"


def _api_get(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"x-auth-token": token})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise DispatchError(f"Codemagic API read failed: {error}") from error
    if not isinstance(payload, dict):
        raise DispatchError("Codemagic API read returned a malformed object")
    return payload


def _api_post(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-auth-token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise DispatchError(f"Codemagic API dispatch failed: {error}") from error
    if not isinstance(result, dict):
        raise DispatchError("Codemagic API dispatch returned a malformed object")
    return result


def build_sha(build: dict[str, Any]) -> Optional[str]:
    """Return one validated source SHA, ignoring provider display labels."""
    for key in ("commit", "commitId", "commitHash"):
        value = build.get(key)
        if isinstance(value, dict):
            value = value.get("hash") or value.get("sha")
        if isinstance(value, str) and valid_source_sha(value.strip()):
            return value.strip()
    return None


def newest_built_sha(builds: Iterable[dict[str, Any]], *, platform: str = "ios") -> Optional[str]:
    """Commit of the newest build with verified platform distribution.

    The API's ordering is not part of any contract we rely on elsewhere, and reading the wrong
    build here would compare against an old commit and dispatch on every scheduled run.  Platform
    evidence is required because a provider can report a finished build after a store task fails.
    ``is_baseline_eligible`` consumes the Omi-normalized evidence contract; raw provider records
    without that adapter output remain ineligible rather than being interpreted heuristically.
    """
    candidates = [
        (str(b.get("createdAt") or ""), sha)
        for b in builds
        if isinstance(b, dict)
        and (sha := build_sha(b))
        and is_baseline_eligible(b, platform=platform)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def last_built_sha(
    app_id: str, workflow_id: str, token: str, *, platform: Optional[str] = None
) -> Optional[str]:
    payload = _api_get(f"{BUILDS_API}?appId={app_id}&workflowId={workflow_id}", token)
    selected_platform = platform or WORKFLOW_PLATFORMS.get(workflow_id)
    if selected_platform is None:
        raise DispatchError(f"unknown mobile workflow {workflow_id}")
    detailed_builds: list[dict[str, Any]] = []
    for build in payload.get("builds") or []:
        if not isinstance(build, dict):
            continue
        detail = build
        build_id = build.get("_id") or build.get("id")
        if isinstance(build_id, str) and "buildActions" not in build:
            detail_payload = _api_get(f"{BUILDS_API}/{build_id}", token)
            candidate = detail_payload.get("build", detail_payload)
            if isinstance(candidate, dict):
                detail = candidate
        detailed_builds.append(
            normalize_codemagic_build(detail, platform=selected_platform, workflow_id=workflow_id)
        )
    return newest_built_sha(detailed_builds, platform=selected_platform)


def is_ancestor(sha: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "HEAD"], capture_output=True, check=False
    )
    return result.returncode == 0


def app_commits_since(sha: Optional[str]) -> list[str]:
    """App-path commits between ``sha`` and HEAD. No usable baseline means treat HEAD as pending."""
    if not sha:
        return ["HEAD"]
    if not is_ancestor(sha):
        # A rewritten or rewound main leaves a baseline off this history; the range would read
        # empty and skip a batch that is genuinely pending.
        return ["HEAD"]
    revision_range = f"{sha}..HEAD"
    result = subprocess.run(
        ["git", "log", "--format=%H", revision_range, "--", *APP_PATHS],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # An unknown SHA (force-push, pruned history) must not silently stop builds.
        return ["HEAD"]
    return [line for line in result.stdout.split() if line]


def valid_source_sha(source_sha: str) -> bool:
    return bool(source_sha and len(source_sha) == 40 and all(c in "0123456789abcdef" for c in source_sha))


def source_identity_matches(evaluated_sha: str, checkout_sha: str) -> bool:
    """Require the workflow's evaluated commit to be the checked-out commit."""
    return valid_source_sha(evaluated_sha) and valid_source_sha(checkout_sha) and evaluated_sha == checkout_sha


def dispatch(app_id: str, workflow_id: str, token: str, branch: str, source_sha: str) -> str:
    """Dispatch a branch build carrying a checked-out source pin.

    Codemagic accepts a branch plus custom environment variables, but not a commit
    parameter. The workflow checks this pin against its own HEAD before any build
    work, so branch movement fails closed instead of silently building a newer tip.
    """
    if not valid_source_sha(source_sha):
        raise DispatchError("evaluated source SHA must be 40 lowercase hexadecimal characters")
    result = _api_post(
        BUILDS_API,
        token,
        {
            "appId": app_id,
            "workflowId": workflow_id,
            "branch": branch,
            "environment": {
                "variables": {
                    "OMI_RELEASE_SOURCE_SHA": source_sha,
                    "OMI_RELEASE_PLATFORM": WORKFLOW_PLATFORMS.get(workflow_id, ""),
                }
            },
        },
    )
    build_id = result.get("buildId")
    if not isinstance(build_id, str) or not build_id:
        raise DispatchError("Codemagic API dispatch did not return a buildId")
    return build_id


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--actor", default="")
    parser.add_argument("--commit-authors", default="")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--source-sha", required=True, help="exact commit evaluated by this workflow")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    token = os.environ.get("CODEMAGIC_API_TOKEN", "")
    instant_actors = normalized_actors(os.environ.get("MOBILE_INSTANT_BUILD_ACTORS"))

    # Per workflow: iOS and Android drift apart whenever one is built on its own, and a shared
    # baseline would let the newer platform suppress the other's build.
    pending_by_workflow: dict[str, list[str]] = {}
    if args.event == "schedule":
        if not token:
            raise DispatchError("CODEMAGIC_API_TOKEN is required to read the last built commit")
        for workflow_id in MOBILE_WORKFLOWS:
            pending_by_workflow[workflow_id] = app_commits_since(
                last_built_sha(
                    args.app_id,
                    workflow_id,
                    token,
                    platform=WORKFLOW_PLATFORMS[workflow_id],
                )
            )

    should, reason = decide_dispatch(
        event=args.event,
        actor=args.actor,
        commit_authors=[a for a in args.commit_authors.split(",") if a.strip()],
        instant_actors=instant_actors,
        has_pending_app_commits=any(pending_by_workflow.values()),
    )

    summary = [f"event={args.event}", f"actor={args.actor}", f"dispatch={should}", f"reason={reason}"]
    for workflow_id, commits in pending_by_workflow.items():
        summary.append(f"{workflow_id}_pending={len(commits)}")
    print(" ".join(summary))

    if not should or args.dry_run:
        return 0

    if not token:
        raise DispatchError("CODEMAGIC_API_TOKEN is required to dispatch")
    targets = [w for w, commits in pending_by_workflow.items() if commits] or list(MOBILE_WORKFLOWS)
    checkout_sha_result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], capture_output=True, text=True, check=False
    )
    checkout_sha = checkout_sha_result.stdout.strip()
    if not source_identity_matches(args.source_sha, checkout_sha):
        raise DispatchError("evaluated source SHA does not match the checked-out commit")
    for workflow_id in targets:
        build_id = dispatch(args.app_id, workflow_id, token, args.branch, args.source_sha)
        print(f"dispatched workflow={workflow_id} build_id={build_id} source={args.source_sha}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DispatchError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
