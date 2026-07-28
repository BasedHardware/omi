#!/usr/bin/env python3
"""Decide whether the desktop auto-release workflow should create a new tag."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

CODEMAGIC_CHECK_NAME = "Release OMI Desktop (Swift)"
RELEASE_ELIGIBILITY_CHECK_NAME = "Release Eligibility"
REQUIRED_SOURCE_CHECK_NAMES = (
    RELEASE_ELIGIBILITY_CHECK_NAME,
    "Desktop Swift Build & Tests",
    "Desktop Swift Release Compile",
)
RECENT_TAG_WITHOUT_CHECK_SECONDS = 10 * 60
# The exact-SHA aggregate can complete after the former 12-minute boundary on
# a healthy run. Give the normal 20-minute CI budget time to settle while
# retaining a bounded, fail-closed source-check gate.
SOURCE_CHECK_WAIT_SECONDS = 20 * 60
SOURCE_CHECK_POLL_SECONDS = 30
MAX_SOURCE_STATUS_POLLS = 20
# Short debounce so a merge is tagged within ~a minute instead of waiting ten.
# The one-active-release fence (Codemagic build status on the latest tag) already
# collapses rapid bursts to the newest SHA while a build runs, so this window only
# needs to coalesce near-simultaneous merges, not batch a whole feature.
AUTO_RELEASE_QUIET_SECONDS = 60
DESKTOP_RELEASE_PATHS = (
    "desktop/macos",
    "codemagic.yaml",
    # The M1 qualification job checks out the immutable candidate tag and
    # imports this exact lifecycle module. Keep the scope to that tag-bound
    # runtime surface; other dev-harness and backend changes are not releases.
    "scripts/dev-harness/dev_harness/qualification.py",
    ".github/scripts/plan-desktop-release.py",
    ".github/scripts/desktop-release-source-identity.py",
    ".github/scripts/publish-desktop-candidate-tag.py",
    ".github/scripts/verify-pre-tag-readiness.py",
    ".github/workflows/desktop_auto_release.yml",
    ".github/workflows/desktop_qualify_beta.yml",
    ".github/workflows/desktop-swift-ci.yml",
)


class SourceCheckGate:
    def __init__(self, state: str, reason: str | None = None) -> None:
        self.state = state
        self.reason = reason


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
        output = git(["ls-files", *DESKTOP_RELEASE_PATHS])
    else:
        output = git(["diff", "--name-only", "--diff-filter=ACDMR", f"{ref}..HEAD", "--", *DESKTOP_RELEASE_PATHS])

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
        raw = git(["log", "--first-parent", "-1", "--format=%ct", "HEAD", "--", *paths])
        return int(time.time()) - int(raw)
    except (subprocess.CalledProcessError, ValueError):
        return None


def latest_releasable_desktop_sha(paths: list[str]) -> str | None:
    if not paths:
        return None

    try:
        return git(["log", "--first-parent", "-1", "--format=%H", "HEAD", "--", *paths]) or None
    except subprocess.CalledProcessError:
        return None


def check_run_sort_key(check_run: dict[str, object]) -> tuple[tuple[datetime, datetime, int] | None, str | None]:
    """Return a validated, deterministic ordering key for one GitHub check run."""
    check_run_id = check_run.get("id")
    if type(check_run_id) is not int or check_run_id <= 0:
        return None, "gh api returned a check run with an invalid id"

    timestamps: list[datetime] = []
    for field_name, allow_none in (("started_at", False), ("completed_at", True)):
        value = check_run.get(field_name)
        if value is None and allow_none:
            timestamps.append(datetime.min.replace(tzinfo=timezone.utc))
            continue
        if not isinstance(value, str):
            return None, f"gh api returned a check run with an invalid {field_name}"
        try:
            timestamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError:
            return None, f"gh api returned a check run with an invalid {field_name}"
        if timestamp.tzinfo is None:
            return None, f"gh api returned a check run with an invalid {field_name}"
        timestamps.append(timestamp.astimezone(timezone.utc))

    return (timestamps[0], timestamps[1], check_run_id), None


def github_check_status(repository: str, sha: str, check_name: str) -> tuple[str | None, str | None, str | None]:
    result = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repository}/commits/{sha}/check-runs?filter=all&per_page=100",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "unknown gh api error"
        return None, None, error

    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, None, "gh api returned invalid check-runs JSON"

    if not isinstance(pages, list):
        return None, None, "gh api returned invalid check-runs pages"

    matching_runs: list[tuple[tuple[datetime, datetime, int], dict[str, object]]] = []
    for page in pages:
        if not isinstance(page, dict):
            return None, None, "gh api returned an invalid check-runs page"
        check_runs = page.get("check_runs")
        if not isinstance(check_runs, list):
            return None, None, "gh api returned an invalid check-runs payload"
        for check_run in check_runs:
            if not isinstance(check_run, dict):
                return None, None, "gh api returned an invalid check run"
            if check_run.get("name") == check_name:
                sort_key, sort_key_error = check_run_sort_key(check_run)
                if sort_key_error:
                    return None, None, sort_key_error
                assert sort_key is not None
                matching_runs.append((sort_key, check_run))

    if not matching_runs:
        return None, None, None

    # `filter=latest` can omit an exact-SHA check run. Request every page and
    # choose the newest matching run ourselves so a later rerun cannot be
    # hidden by the API filter. `started_at` is primary so a newer in-progress
    # rerun is never masked by an older completed success; the remaining fields
    # make ordering deterministic when timestamps collide or are unavailable.
    latest = max(matching_runs, key=lambda run: run[0])[1]
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    if status is not None and not isinstance(status, str):
        return None, None, "gh api returned a check run with an invalid status"
    if conclusion is not None and not isinstance(conclusion, str):
        return None, None, "gh api returned a check run with an invalid conclusion"
    return status, conclusion, None


def codemagic_check_status(repository: str, sha: str) -> tuple[str | None, str | None, str | None]:
    return github_check_status(repository, sha, CODEMAGIC_CHECK_NAME)


def required_source_checks_gate(repository: str, sha: str) -> SourceCheckGate:
    for check_name in REQUIRED_SOURCE_CHECK_NAMES:
        status, conclusion, error = github_check_status(repository, sha, check_name)
        if error:
            return SourceCheckGate(
                "waiting", f"could not read required check {check_name} for source SHA {sha}: {error}"
            )
        if status is None:
            return SourceCheckGate("waiting", f"required check {check_name} is missing for exact source SHA {sha}")
        if status != "completed":
            return SourceCheckGate("waiting", f"required check {check_name} for exact source SHA {sha} is {status}")
        if conclusion != "success":
            return SourceCheckGate(
                "blocked",
                f"required check {check_name} for exact source SHA {sha} "
                f"completed with {conclusion or 'no conclusion'}",
            )
    return SourceCheckGate("ready")


def wait_for_required_source_checks(
    repository: str, sha: str, *, wait_seconds: int, poll_seconds: int
) -> SourceCheckGate:
    """Re-evaluate only transient exact-SHA source-check states for a bounded time."""
    gate = required_source_checks_gate(repository, sha)
    if gate.state != "waiting" or wait_seconds == 0:
        return gate

    deadline = time.monotonic() + wait_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return SourceCheckGate(
                "blocked",
                f"timed out after {wait_seconds}s waiting for required exact-SHA checks: {gate.reason}",
            )
        time.sleep(min(poll_seconds, remaining))
        gate = required_source_checks_gate(repository, sha)
        if gate.state != "waiting":
            return gate


def candidate_tags_for_source(sha: str) -> list[str]:
    tags = git(["tag", "-l", "v*-macos", "--points-at", sha]).splitlines()
    return sorted((tag for tag in tags if tag), key=version_sort_key, reverse=True)


def github_candidate_release_published(repository: str, tag: str) -> tuple[bool | None, str | None]:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository, "--json", "tagName,isDraft,publishedAt"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "unknown gh release view error"
        if "not found" in error.lower():
            return False, None
        return None, error
    try:
        release = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "gh release view returned invalid JSON"
    if not isinstance(release, dict) or release.get("tagName") != tag:
        return None, "gh release view did not return the requested tag"
    return release.get("isDraft") is False and isinstance(release.get("publishedAt"), str), None


def normal_candidate_lifecycle(repository: str, source_sha: str, tag: str) -> tuple[str, str]:
    """Return the tag-triggered candidate lifecycle without mutating it."""
    status, conclusion, error = codemagic_check_status(repository, source_sha)
    if error:
        return "unknown", f"could not read normal candidate check for {tag}: {error}"
    if status and status != "completed":
        return "active", f"{CODEMAGIC_CHECK_NAME} for {tag} is {status}"

    published, release_error = github_candidate_release_published(repository, tag)
    if release_error:
        return "unknown", f"could not read candidate release for {tag}: {release_error}"
    if published:
        return "published", f"immutable candidate release {tag} is published"
    if status is None:
        return "waiting", f"immutable tag {tag} is awaiting the normal tag-triggered Codemagic check"
    return (
        "blocked",
        f"{CODEMAGIC_CHECK_NAME} for {tag} completed ({conclusion or 'no conclusion'}) without a published candidate",
    )


def existing_source_candidate_reason(repository: str, source_sha: str) -> str | None:
    tags = candidate_tags_for_source(source_sha)
    if not tags:
        return None

    tag = tags[0]
    lifecycle, detail = normal_candidate_lifecycle(repository, source_sha, tag)
    if lifecycle in {"active", "published"}:
        return (
            f"immutable candidate tag {tag} already owns exact source SHA {source_sha}; "
            f"normal candidate lifecycle is {lifecycle} ({detail})."
        )
    return (
        f"immutable candidate tag {tag} already owns exact source SHA {source_sha}; "
        f"refusing a duplicate candidate while its normal lifecycle is {lifecycle} ({detail})."
    )


def source_candidate_status(repository: str, source_sha: str) -> tuple[str, str, str]:
    """Return one bounded, read-only candidate lifecycle observation for a source SHA."""
    tags = candidate_tags_for_source(source_sha)
    if not tags:
        return "waiting", "", "no immutable v*-macos candidate tag exists for this source SHA"
    tag = tags[0]
    lifecycle, detail = normal_candidate_lifecycle(repository, source_sha, tag)
    return lifecycle, tag, detail


def watch_source_candidate(repository: str, source_sha: str, *, max_polls: int, poll_seconds: int) -> int:
    """Print only candidate lifecycle transitions using bounded read-only calls."""
    previous: tuple[str, str, str] | None = None
    for poll in range(max_polls):
        observation = source_candidate_status(repository, source_sha)
        if observation != previous:
            lifecycle, tag, detail = observation
            print(
                "Desktop candidate status changed: "
                f"source_sha={source_sha} tag={tag or 'none'} lifecycle={lifecycle}; {detail}"
            )
            previous = observation
        if poll + 1 < max_polls:
            time.sleep(poll_seconds)
    return 0


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
    parser.add_argument("--source-check-wait-seconds", type=int, default=SOURCE_CHECK_WAIT_SECONDS)
    parser.add_argument("--source-check-poll-seconds", type=int, default=SOURCE_CHECK_POLL_SECONDS)
    parser.add_argument("--watch-source-sha")
    parser.add_argument("--watch-max-polls", type=int, default=1)
    parser.add_argument("--watch-poll-seconds", type=int, default=SOURCE_CHECK_POLL_SECONDS)
    args = parser.parse_args()

    if args.source_check_wait_seconds < 0:
        parser.error("--source-check-wait-seconds must be non-negative")
    if args.source_check_poll_seconds <= 0:
        parser.error("--source-check-poll-seconds must be positive")
    if args.watch_source_sha:
        if not re.fullmatch(r"[0-9a-f]{40}", args.watch_source_sha):
            parser.error("--watch-source-sha must be a full lowercase SHA")
        if not 1 <= args.watch_max_polls <= MAX_SOURCE_STATUS_POLLS:
            parser.error(f"--watch-max-polls must be between 1 and {MAX_SOURCE_STATUS_POLLS}")
        if args.watch_poll_seconds < 0:
            parser.error("--watch-poll-seconds must be non-negative")
        return watch_source_candidate(
            args.repository,
            args.watch_source_sha,
            max_polls=args.watch_max_polls,
            poll_seconds=args.watch_poll_seconds,
        )

    latest_tag = latest_desktop_tag()
    changes = releasable_desktop_changes_since(latest_tag)
    set_output("latest_tag", latest_tag or "")

    if not changes:
        set_output("source_sha", "")
        set_output("should_release", "false")
        set_output("reason", "No releasable desktop app changes since the latest desktop tag.")
        return 0

    # Component CI is produced on the immutable commit that last changed the
    # queued desktop paths. Later backend/docs-only main commits intentionally
    # do not become desktop candidates because the producer skips its expensive
    # release compile on those SHAs.
    source_sha = latest_releasable_desktop_sha(changes)
    set_output("source_sha", source_sha or "")
    if source_sha is None:
        set_output("should_release", "false")
        set_output("reason", "Could not resolve the newest releasable desktop source SHA.")
        return 0

    if changes:
        print("Releasable desktop app changes since latest tag:")
        for path in changes:
            print(f"  - {path}")

    existing_candidate = existing_source_candidate_reason(args.repository, source_sha)
    if existing_candidate:
        set_output("should_release", "false")
        set_output("reason", f"Desktop candidate already exists: {existing_candidate}")
        return 0

    latest_change_age = latest_change_age_seconds(changes)
    if latest_change_age is None:
        set_output("should_release", "false")
        set_output(
            "reason", "Waiting for desktop release quiet window: could not determine latest releasable change age."
        )
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

    source_check_gate = wait_for_required_source_checks(
        args.repository,
        source_sha,
        wait_seconds=args.source_check_wait_seconds,
        poll_seconds=args.source_check_poll_seconds,
    )
    if source_check_gate.state == "waiting":
        set_output("should_release", "false")
        set_output("reason", f"Waiting for required exact-SHA checks: {source_check_gate.reason}.")
        return 0
    if source_check_gate.state == "blocked":
        set_output("should_release", "false")
        set_output("reason", f"Desktop candidate source gate blocked: {source_check_gate.reason}.")
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
