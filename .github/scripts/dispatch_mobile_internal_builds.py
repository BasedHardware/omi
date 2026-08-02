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

BUILDS_API = "https://api.codemagic.io/builds"
MOBILE_WORKFLOWS = ("ios-internal-auto", "android-internal-auto")
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
            return json.loads(response.read().decode())
    except urllib.error.URLError as error:
        raise DispatchError(f"Codemagic API read failed: {error}") from error


def last_built_sha(app_id: str, workflow_id: str, token: str) -> Optional[str]:
    """Newest commit Codemagic has already built for this workflow, if any."""
    payload = _api_get(f"{BUILDS_API}?appId={app_id}&workflowId={workflow_id}", token)
    builds = payload.get("builds") or []
    for build in builds:
        for key in ("commit", "commitId", "commitHash"):
            value = build.get(key)
            if isinstance(value, dict):
                value = value.get("hash") or value.get("sha")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def app_commits_since(sha: Optional[str]) -> list[str]:
    """App-path commits between ``sha`` and HEAD. No known baseline means treat HEAD as pending."""
    if not sha:
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


def dispatch(app_id: str, workflow_id: str, token: str, branch: str) -> str:
    payload = json.dumps({"appId": app_id, "workflowId": workflow_id, "branch": branch}).encode()
    request = urllib.request.Request(
        BUILDS_API,
        data=payload,
        headers={"Content-Type": "application/json", "x-auth-token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except urllib.error.URLError as error:
        raise DispatchError(f"Codemagic dispatch failed for {workflow_id}: {error}") from error
    build_id = body.get("buildId")
    if not build_id:
        raise DispatchError(f"Codemagic returned no build id for {workflow_id}")
    return str(build_id)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--actor", default="")
    parser.add_argument("--commit-authors", default="")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    token = os.environ.get("CODEMAGIC_API_TOKEN", "")
    instant_actors = normalized_actors(os.environ.get("MOBILE_INSTANT_BUILD_ACTORS"))

    pending: list[str] = []
    if args.event == "schedule":
        if not token:
            raise DispatchError("CODEMAGIC_API_TOKEN is required to read the last built commit")
        pending = app_commits_since(last_built_sha(args.app_id, MOBILE_WORKFLOWS[0], token))

    should, reason = decide_dispatch(
        event=args.event,
        actor=args.actor,
        commit_authors=[a for a in args.commit_authors.split(",") if a.strip()],
        instant_actors=instant_actors,
        has_pending_app_commits=bool(pending),
    )

    summary = [f"event={args.event}", f"actor={args.actor}", f"dispatch={should}", f"reason={reason}"]
    if args.event == "schedule":
        summary.append(f"pending_app_commits={len(pending)}")
    print(" ".join(summary))

    if not should or args.dry_run:
        return 0

    if not token:
        raise DispatchError("CODEMAGIC_API_TOKEN is required to dispatch")
    for workflow_id in MOBILE_WORKFLOWS:
        print(f"dispatched {workflow_id} build={dispatch(args.app_id, workflow_id, token, args.branch)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DispatchError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
