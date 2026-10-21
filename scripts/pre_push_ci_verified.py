#!/usr/bin/env python3
"""Decide whether every pushed commit already passed terminal-green GitHub CI.

Fast-forwarding a branch to a SHA that CI has already certified re-runs the
whole local pre-push suite against a tree nothing has changed: about 55 minutes
per rollout sync. scripts/pre-push calls this before selecting checks and skips
only that duplicated local suite when, for every pushed SHA:

- GitHub knows the exact commit and its tree equals the local tree;
- at least one CI workflow run (push / pull_request / merge_group) on that SHA
  concluded success, and every CI workflow run on it is terminal and green
  (success, skipped or neutral);
- if it carries any legacy commit statuses, their combined state is success.

Deployment writers (the LOCK_CONTRACTS registry in
.github/scripts/check-deployment-concurrency.py, read at the base ref the hook
passes, never from the working tree) are not CI and neither certify nor block:
on main they sit parked behind their concurrency lock or are cancelled by a
newer push, which says nothing about the commit. If the registry cannot be
read, deploys are judged like CI, which only fails closed.

This is not a skip hatch. Nothing here reads the environment; the only way to
skip is for GitHub to report green CI on the exact SHA. Every error, timeout,
unknown SHA, non-GitHub remote or unparseable answer fails closed: exit 1, and
the hook runs its full suite. Each verdict is printed and appended to a JSON
lines log.

Exit 0: verified, skip the local suite. Exit 1: run the local suite.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

CI_EVENTS = frozenset({"push", "pull_request", "pull_request_target", "merge_group"})
GREEN_CONCLUSIONS = frozenset({"success", "skipped", "neutral"})
GH_TIMEOUT_SECONDS = 30
DEPLOY_REGISTRY = Path(".github/scripts/check-deployment-concurrency.py")

_GITHUB_REMOTE = re.compile(
    r"^(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
_SHA = re.compile(r"^[0-9a-f]{40}$")

GhApi = Callable[[str], Any]


class NotVerified(Exception):
    """The push is not provably CI-green; run the local suite."""


def github_repo(remote_url: str) -> str | None:
    match = _GITHUB_REMOTE.match(remote_url.strip())
    return match.group("repo") if match else None


def deploy_workflow_files(registry_source: str) -> frozenset[str]:
    """Workflow file names keyed in the deployment-concurrency LOCK_CONTRACTS."""
    for node in ast.parse(registry_source).body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "LOCK_CONTRACTS" for t in node.targets)
            and isinstance(node.value, ast.Dict)
        ):
            return frozenset(
                key.value
                for key in node.value.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )
    return frozenset()


def verify_commit(
    repo: str,
    sha: str,
    local_tree: str,
    gh_api: GhApi,
    deploy_files: frozenset[str],
) -> str:
    """Return a one-line proof for a CI-green SHA, or raise NotVerified."""
    commit = gh_api(f"repos/{repo}/commits/{sha}")
    remote_tree = (commit.get("commit") or {}).get("tree", {}).get("sha") if isinstance(commit, dict) else None
    if remote_tree != local_tree:
        raise NotVerified(f"{sha[:12]}: GitHub tree {remote_tree!s:.12} differs from local tree {local_tree:.12}")

    pages = gh_api(f"repos/{repo}/actions/runs?head_sha={sha}&per_page=100")
    if not isinstance(pages, list):
        pages = [pages]
    runs = [run for page in pages for run in (page or {}).get("workflow_runs", [])]
    green: list[str] = []
    for run in runs:
        if run.get("head_sha") != sha or run.get("event") not in CI_EVENTS:
            continue
        if Path(run.get("path") or "").name in deploy_files:
            continue
        name = run.get("name") or run.get("path") or "?"
        status = run.get("status")
        conclusion = run.get("conclusion")
        if status != "completed":
            raise NotVerified(f"{sha[:12]}: CI run {name!r} is {status}, not terminal")
        if conclusion not in GREEN_CONCLUSIONS:
            raise NotVerified(f"{sha[:12]}: CI run {name!r} concluded {conclusion}")
        if conclusion == "success":
            green.append(name)
    if not green:
        raise NotVerified(f"{sha[:12]}: no successful CI workflow run on this exact SHA")

    # GitHub reports "pending" for a commit with no statuses at all; only that case is neutral.
    combined = gh_api(f"repos/{repo}/commits/{sha}/status")
    if not isinstance(combined, dict):
        raise NotVerified(f"{sha[:12]}: combined commit status is unreadable")
    state = combined.get("state")
    if combined.get("total_count", 0) and state != "success":
        raise NotVerified(f"{sha[:12]}: combined commit status is {state}")

    return f"{sha[:12]}: {len(green)} successful CI run(s), tree {local_tree[:12]} matches"


def gh_api_subprocess(endpoint: str) -> Any:
    command = ["gh", "api", "--paginate", "--slurp", endpoint] if "actions/runs" in endpoint else ["gh", "api", endpoint]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT_SECONDS,
            env={**os.environ, "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NotVerified(f"GitHub unreachable: {error}") from error
    if result.returncode != 0:
        first = (result.stderr.strip().splitlines() or ["no output"])[0]
        raise NotVerified(f"GitHub unreachable: gh api {endpoint} exited {result.returncode}: {first}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise NotVerified(f"GitHub answer for {endpoint} is not JSON") from error


def _local_tree(sha: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{sha}^{{tree}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    tree = result.stdout.strip()
    if result.returncode != 0 or not _SHA.match(tree):
        raise NotVerified(f"{sha[:12]}: cannot resolve the local tree")
    return tree


def decide(
    remote_url: str,
    shas: list[str],
    gh_api: GhApi,
    local_tree: Callable[[str], str],
    deploy_files: frozenset[str],
) -> tuple[bool, list[str]]:
    repo = github_repo(remote_url)
    if repo is None:
        return False, [f"remote {remote_url!r} is not a GitHub repository"]
    if not shas:
        return False, ["no pushed commits to verify"]
    proofs: list[str] = []
    try:
        for sha in shas:
            if not _SHA.match(sha):
                raise NotVerified(f"{sha!r} is not a full commit SHA")
            proofs.append(verify_commit(repo, sha, local_tree(sha), gh_api, deploy_files))
    except NotVerified as reason:
        return False, [*proofs, str(reason)]
    except Exception as error:  # fail closed on anything unexpected
        return False, [*proofs, f"verification error: {type(error).__name__}: {error}"]
    return True, proofs


def _deploy_files_at(ref: str) -> frozenset[str]:
    """The registry as the base branch has it, so a local edit cannot widen what is ignored."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{DEPLOY_REGISTRY.as_posix()}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return frozenset()
    try:
        return deploy_workflow_files(result.stdout)
    except (SyntaxError, ValueError):
        return frozenset()


def _append_log(log_file: Path, record: dict[str, Any]) -> None:
    try:
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as error:
        print(f"  (could not append to {log_file}: {error})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remote-url", required=True)
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--registry-ref", required=True, help="trusted ref to read the deploy-writer registry from")
    parser.add_argument("shas", nargs="*")
    args = parser.parse_args(argv)

    deploy_files = _deploy_files_at(args.registry_ref)

    verified, lines = decide(args.remote_url, args.shas, gh_api_subprocess, _local_tree, deploy_files)
    verdict = "ci-green: skipping the duplicated local suite" if verified else "not CI-verified: running the local suite"
    print(f"CI-verified push check: {verdict}")
    for line in lines:
        print(f"  {line}")
    _append_log(
        args.log_file,
        {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "remote": args.remote_url,
            "shas": args.shas,
            "verified": verified,
            "detail": lines,
        },
    )
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())
