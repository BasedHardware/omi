#!/usr/bin/env python3
"""Decide whether the desktop auto-release workflow should create a new tag."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path

CODEMAGIC_CHECK_NAME = "Release OMI Desktop (Swift)"
RELEASE_ELIGIBILITY_CHECK_NAME = "Release Eligibility"
REQUIRED_SOURCE_CHECK_NAMES = (
    RELEASE_ELIGIBILITY_CHECK_NAME,
    "Desktop Swift Build & Tests",
    "Desktop Swift Release Compile",
)
RECENT_TAG_WITHOUT_CHECK_SECONDS = 10 * 60
AUTO_RELEASE_QUIET_SECONDS = 10 * 60


def run(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(args, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.strip()


def git(args: list[str], *, check: bool = True) -> str:
    return run(["git", *args], check=check)


def version_sort_key(tag: str) -> tuple[int, ...]:
    version = tag.removeprefix("v").split("+", 1)[0]
    return tuple(int(part) for part in version.split("."))


def latest_desktop_tag() -> str | None:
    tags = git(["tag", "-l", "v*-macos"]).splitlines()
    if not tags:
        return None
    return sorted(tags, key=version_sort_key)[-1]


def releasable_desktop_changes_since(ref: str | None) -> list[str]:
    if ref is None:
        output = git(["ls-files", "desktop/macos"])
    else:
        output = git(["diff", "--name-only", "--diff-filter=ACDMR", f"{ref}..HEAD", "--", "desktop/macos"])

    changes = []
    for path in output.splitlines():
        if not path:
            continue
        if path == "desktop/macos/CHANGELOG.json":
            continue
        if path == "desktop/macos/AGENTS.md":
            continue
        if path.startswith("desktop/macos/changelog/"):
            continue
        if path.startswith("desktop/macos/Backend-Rust/"):
            continue
        changes.append(path)
    return changes


def tag_sha(tag: str) -> str | None:
    try:
        return git(["rev-list", "-n", "1", tag])
    except subprocess.CalledProcessError:
        return None


def tag_age_seconds(tag: str) -> int | None:
    try:
        raw = git(["log", "-1", "--format=%ct", tag])
        return int(time.time()) - int(raw)
    except (subprocess.CalledProcessError, ValueError):
        return None


def latest_change_age_seconds(paths: list[str]) -> int | None:
    if not paths:
        return None

    try:
        raw = git(["log", "-1", "--format=%ct", "HEAD", "--", *paths])
        return int(time.time()) - int(raw)
    except (subprocess.CalledProcessError, ValueError):
        return None


def github_check_status(repository: str, sha: str, check_name: str) -> tuple[str | None, str | None, str | None]:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/commits/{sha}/check-runs?filter=latest",
            "--jq",
            f'.check_runs[] | select(.name=="{check_name}") | [.status, (.conclusion // "")] | @tsv',
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "unknown gh api error"
        return None, None, error

    output = result.stdout.strip()
    first = next((line for line in output.splitlines() if line.strip()), "")
    if not first:
        return None, None, None
    parts = first.split("\t", 1)
    status = parts[0] if parts else None
    conclusion = parts[1] if len(parts) > 1 else None
    return status, conclusion, None


def codemagic_check_status(repository: str, sha: str) -> tuple[str | None, str | None, str | None]:
    return github_check_status(repository, sha, CODEMAGIC_CHECK_NAME)


def required_source_checks_reason(repository: str, sha: str) -> str | None:
    for check_name in REQUIRED_SOURCE_CHECK_NAMES:
        status, conclusion, error = github_check_status(repository, sha, check_name)
        if error:
            return f"could not read required check {check_name} for source SHA {sha}: {error}"
        if status is None:
            return f"required check {check_name} is missing for exact main SHA {sha}"
        if status != "completed":
            return f"required check {check_name} for exact main SHA {sha} is {status}"
        if conclusion != "success":
            return (
                f"required check {check_name} for exact main SHA {sha} "
                f"completed with {conclusion or 'no conclusion'}"
            )
    return None


def active_release_reason(repository: str, latest_tag: str | None) -> str | None:
    if latest_tag is None:
        return None

    sha = tag_sha(latest_tag)
    if not sha:
        return None

    status, conclusion, error = codemagic_check_status(repository, sha)
    if error:
        return f"could not read GitHub check runs for {latest_tag}: {error}"

    if status and status != "completed":
        return f"{CODEMAGIC_CHECK_NAME} for {latest_tag} is {status}"

    if status is None:
        age = tag_age_seconds(latest_tag)
        if age is not None and age < RECENT_TAG_WITHOUT_CHECK_SECONDS:
            return f"{latest_tag} is recent and has no Codemagic check yet"

    if status == "completed":
        print(f"Latest Codemagic release check: {latest_tag} completed ({conclusion or 'n/a'}).")
    return None


def set_output(name: str, value: str) -> None:
    print(f"{name}={value}")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()

    latest_tag = latest_desktop_tag()
    changes = releasable_desktop_changes_since(latest_tag)
    # The tag is created from this checkout (plus its deterministic changelog
    # commit), so exact current main is the release source authority. Gating an
    # older path-touching commit strands the queue when a later metadata-only
    # repair makes current main eligible without rerunning component CI.
    source_sha = git(["rev-parse", "HEAD"])
    set_output("latest_tag", latest_tag or "")
    set_output("source_sha", source_sha)

    if not changes:
        set_output("should_release", "false")
        set_output("reason", "No releasable desktop app changes since the latest desktop tag.")
        return 0

    if changes:
        print("Releasable desktop app changes since latest tag:")
        for path in changes:
            print(f"  - {path}")

    latest_change_age = latest_change_age_seconds(changes)
    if latest_change_age is None:
        set_output("should_release", "false")
        set_output("reason", "Waiting for desktop release quiet window: could not determine latest releasable change age.")
        return 0
    if latest_change_age < AUTO_RELEASE_QUIET_SECONDS:
        wait_seconds = AUTO_RELEASE_QUIET_SECONDS - latest_change_age
        set_output("should_release", "false")
        set_output(
            "reason",
            f"Waiting for desktop release quiet window: latest releasable change is "
            f"{latest_change_age}s old; need {AUTO_RELEASE_QUIET_SECONDS}s ({wait_seconds}s remaining).",
        )
        return 0

    source_check_reason = required_source_checks_reason(args.repository, source_sha)
    if source_check_reason:
        set_output("should_release", "false")
        set_output("reason", f"Desktop candidate source gate blocked: {source_check_reason}.")
        return 0

    active_reason = active_release_reason(args.repository, latest_tag)
    if active_reason:
        set_output("should_release", "false")
        set_output("reason", f"Release already active: {active_reason}.")
        return 0

    set_output("should_release", "true")
    set_output("reason", f"Ready to release {len(changes)} changed desktop app file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
