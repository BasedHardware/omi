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

# Only a build that reached a decision may become the baseline. A failed, cancelled or timed-out
# build leaves its commit unbuilt, so advancing past it would strand a broken merge until the next
# app change happened along. `skipped` counts: Codemagic decided there was nothing to build.
BASELINE_STATUSES = frozenset({"finished", "success", "succeeded", "skipped"})


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


def build_sha(build: dict[str, Any]) -> Optional[str]:
    for key in ("commit", "commitId", "commitHash"):
        value = build.get(key)
        if isinstance(value, dict):
            value = value.get("hash") or value.get("sha")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def newest_built_sha(builds: Iterable[dict[str, Any]]) -> Optional[str]:
    """Commit of the most recent build that settled, by createdAt rather than list position.

    The API's ordering is not part of any contract we rely on elsewhere, and reading the wrong
    build here would compare against an old commit and dispatch on every scheduled run.
    """
    candidates = [
        (str(b.get("createdAt") or ""), sha)
        for b in builds
        if str(b.get("status") or "").lower() in BASELINE_STATUSES and (sha := build_sha(b))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def last_built_sha(app_id: str, workflow_id: str, token: str) -> Optional[str]:
    payload = _api_get(f"{BUILDS_API}?appId={app_id}&workflowId={workflow_id}", token)
    return newest_built_sha(payload.get("builds") or [])


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

    # Per workflow: iOS and Android drift apart whenever one is built on its own, and a shared
    # baseline would let the newer platform suppress the other's build.
    pending_by_workflow: dict[str, list[str]] = {}
    if args.event == "schedule":
        if not token:
            raise DispatchError("CODEMAGIC_API_TOKEN is required to read the last built commit")
        for workflow_id in MOBILE_WORKFLOWS:
            pending_by_workflow[workflow_id] = app_commits_since(
                last_built_sha(args.app_id, workflow_id, token)
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
    for workflow_id in targets:
        print(f"dispatched {workflow_id} build={dispatch(args.app_id, workflow_id, token, args.branch)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DispatchError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
