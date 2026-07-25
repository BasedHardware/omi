#!/usr/bin/env python3
"""Publish a macOS candidate tag only when it is bound to merged origin/main."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

PLANNER_PATH = Path(__file__).with_name("plan-desktop-release.py")
PLANNER_SPEC = importlib.util.spec_from_file_location("plan_desktop_release", PLANNER_PATH)
assert PLANNER_SPEC and PLANNER_SPEC.loader
planner = importlib.util.module_from_spec(PLANNER_SPEC)
PLANNER_SPEC.loader.exec_module(planner)

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
TAG_PATTERN = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+[0-9]+-macos$")


class CandidatePublicationError(RuntimeError):
    """Raised when the immutable candidate cannot be published safely."""


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def run_command(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise CandidatePublicationError(f"{' '.join(args)} failed: {detail}")
    return result


def command_output(runner: CommandRunner, args: list[str]) -> str:
    return runner(args, check=True).stdout.strip()


def validate_sha(label: str, value: str) -> str:
    normalized = value.strip().lower()
    if not SHA_PATTERN.fullmatch(normalized):
        raise CandidatePublicationError(f"{label} must be a full lowercase 40-character commit SHA")
    return normalized


def read_pr_state(
    repository: str,
    pr_number: int,
    *,
    runner: CommandRunner,
) -> tuple[str, str | None]:
    raw = command_output(
        runner,
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repository,
            "--json",
            "state,mergeCommit",
        ],
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CandidatePublicationError("gh pr view returned invalid JSON") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("state"), str):
        raise CandidatePublicationError("gh pr view returned an invalid PR state")

    merge_commit = payload.get("mergeCommit")
    merge_sha = merge_commit.get("oid") if isinstance(merge_commit, dict) else None
    if merge_sha is not None and not isinstance(merge_sha, str):
        raise CandidatePublicationError("gh pr view returned an invalid merge commit")
    return payload["state"].upper(), merge_sha


def wait_for_merged_pr(
    repository: str,
    pr_number: int,
    *,
    wait_seconds: int,
    poll_seconds: int,
    runner: CommandRunner,
    sleeper: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> str:
    deadline = monotonic() + wait_seconds
    while True:
        state, merge_sha = read_pr_state(repository, pr_number, runner=runner)
        if state == "MERGED":
            if merge_sha is None:
                raise CandidatePublicationError("merged changelog PR has no merge commit")
            return validate_sha("merged changelog PR commit", merge_sha)
        if state != "OPEN":
            raise CandidatePublicationError(f"changelog PR #{pr_number} is {state.lower()}, not merged")
        if wait_seconds == 0:
            raise CandidatePublicationError(f"changelog PR #{pr_number} is still open")

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CandidatePublicationError(
                f"timed out after {wait_seconds}s waiting for changelog PR #{pr_number} to merge"
            )
        sleeper(min(poll_seconds, remaining))


def fetch_origin_main(*, runner: CommandRunner) -> str:
    runner(
        [
            "git",
            "fetch",
            "--force",
            "origin",
            "refs/heads/main:refs/remotes/origin/main",
        ],
        check=True,
    )
    return validate_sha(
        "freshly fetched origin/main",
        command_output(runner, ["git", "rev-parse", "origin/main"]),
    )


def newest_releasable_source_at(ref: str) -> str | None:
    latest_tag = planner.latest_desktop_tag()
    changes = planner.releasable_desktop_changes_since(latest_tag, head_ref=ref)
    return planner.latest_releasable_desktop_sha(changes, head_ref=ref)


def publish_candidate_tag(
    *,
    repository: str,
    pr_number: int,
    release_tag: str,
    approved_source_sha: str,
    wait_seconds: int = 0,
    poll_seconds: int = 15,
    runner: CommandRunner = run_command,
    source_gate: Callable[[str, str], object] = planner.required_source_checks_gate,
    newest_source: Callable[[str], str | None] = newest_releasable_source_at,
) -> str:
    if not TAG_PATTERN.fullmatch(release_tag):
        raise CandidatePublicationError("release tag must be an exact v<version>+<build>-macos candidate tag")
    approved_source_sha = validate_sha("approved release source", approved_source_sha)
    merged_main_sha = wait_for_merged_pr(
        repository,
        pr_number,
        wait_seconds=wait_seconds,
        poll_seconds=poll_seconds,
        runner=runner,
    )

    observed_main_sha = fetch_origin_main(runner=runner)
    if observed_main_sha != merged_main_sha:
        raise CandidatePublicationError(
            "origin/main changed after the changelog merge: "
            f"expected {merged_main_sha}, freshly fetched {observed_main_sha}"
        )

    merge_base = validate_sha(
        "release source merge base",
        command_output(runner, ["git", "merge-base", approved_source_sha, merged_main_sha]),
    )
    if merge_base != approved_source_sha:
        raise CandidatePublicationError(
            f"approved release source {approved_source_sha} is not an ancestor of merged main {merged_main_sha}"
        )

    current_source_sha = newest_source("origin/main")
    if current_source_sha != approved_source_sha:
        raise CandidatePublicationError(
            "newest releasable desktop source on merged origin/main changed: "
            f"approved {approved_source_sha}, found {current_source_sha or 'none'}"
        )

    gate = source_gate(repository, approved_source_sha)
    if getattr(gate, "state", None) != "ready":
        reason = getattr(gate, "reason", None) or "unknown exact-SHA source-check state"
        raise CandidatePublicationError(f"approved release source checks are not ready: {reason}")

    # Re-fetch immediately before creating and pushing the immutable ref. This is
    # deliberately after every potentially slow API/check operation.
    final_main_sha = fetch_origin_main(runner=runner)
    if final_main_sha != merged_main_sha:
        raise CandidatePublicationError(
            "origin/main changed before tag push: "
            f"intended {merged_main_sha}, freshly fetched {final_main_sha}"
        )

    remote_tag = runner(
        ["git", "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{release_tag}"],
        check=False,
    )
    if remote_tag.returncode == 0:
        raise CandidatePublicationError(f"immutable candidate tag {release_tag} already exists; refusing reuse")
    if remote_tag.returncode != 2:
        detail = remote_tag.stderr.strip() or remote_tag.stdout.strip() or f"exit {remote_tag.returncode}"
        raise CandidatePublicationError(f"could not verify candidate tag absence: {detail}")

    runner(["git", "tag", release_tag, merged_main_sha], check=True)
    runner(
        ["git", "push", "origin", f"refs/tags/{release_tag}:refs/tags/{release_tag}"],
        check=True,
    )
    return merged_main_sha


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", required=True, type=int)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--approved-source-sha", required=True)
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=15)
    args = parser.parse_args()

    if args.pr_number <= 0:
        parser.error("--pr-number must be positive")
    if args.wait_seconds < 0:
        parser.error("--wait-seconds cannot be negative")
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")

    try:
        target_sha = publish_candidate_tag(
            repository=args.repository,
            pr_number=args.pr_number,
            release_tag=args.release_tag,
            approved_source_sha=args.approved_source_sha,
            wait_seconds=args.wait_seconds,
            poll_seconds=args.poll_seconds,
        )
    except CandidatePublicationError as error:
        parser.exit(1, f"ERROR: {error}\n")

    print(f"Published {args.release_tag} at merged origin/main commit {target_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
