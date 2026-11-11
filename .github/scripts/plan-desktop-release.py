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
REQUIRED_SOURCE_CHECKS: dict[str, str] = {
    RELEASE_ELIGIBILITY_CHECK_NAME: ".github/workflows/release-eligibility.yml",
    "Desktop Swift Build & Tests": ".github/workflows/desktop-swift-ci.yml",
    "Desktop Swift Release Compile": ".github/workflows/desktop-swift-ci.yml",
}
REQUIRED_SOURCE_CHECK_NAMES = tuple(REQUIRED_SOURCE_CHECKS)
EVENT_DELIVERY_GRACE_SECONDS = 10 * 60
RECENT_TAG_WITHOUT_CHECK_SECONDS = 10 * 60
# The planner never sleeps on a source gate. It used to poll for up to 90
# minutes, which outlived the GitHub App installation token minted at job start
# (those expire after 60 minutes): every poll past expiry failed with "gh: Bad
# credentials (401)", killing the fallback scan and reporting a credentials
# error instead of the real gate state (Aug 14 2026, issue #11574). #11575
# clamped the wait to 45 minutes; evaluating once and deferring to the next
# hourly tick removes the wait — and the token-lifetime constraint — entirely.
WATCH_POLL_SECONDS = 30
MAX_SOURCE_STATUS_POLLS = 20
# Short debounce so a merge is tagged within ~a minute instead of waiting ten.
# The one-active-release fence (Codemagic build status on the latest tag) already
# collapses rapid bursts to the newest SHA while a build runs, so this window only
# needs to coalesce near-simultaneous merges, not batch a whole feature.
AUTO_RELEASE_QUIET_SECONDS = 60
DESKTOP_RELEASE_PATHS = (
    "desktop/macos",
    "codemagic.yaml",
    ".github/scripts/plan-desktop-release.py",
    ".github/scripts/desktop-release-source-identity.py",
    ".github/scripts/publish-desktop-candidate-tag.py",
    ".github/workflows/desktop_auto_release.yml",
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


def tag_creation_age_seconds(tag: str) -> int | None:
    """Read an annotated tag's creation clock, falling back for legacy tags."""
    try:
        raw = git(["for-each-ref", "--format=%(taggerdate:unix)", f"refs/tags/{tag}"])
        if raw:
            return max(0, int(time.time()) - int(raw))
    except (subprocess.CalledProcessError, ValueError):
        pass
    return tag_age_seconds(tag)


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


# A blocked newest SHA must not wedge the train indefinitely: fall back to the
# newest older releasable SHA whose exact-SHA checks already succeeded, so the
# last green tree keeps shipping while the tip is being fixed. Bounded so a
# long-red history cannot turn the planner into a full-history scan.
FALLBACK_SOURCE_CANDIDATES = 20


def releasable_desktop_shas_since(ref: str | None) -> list[str]:
    """First-parent commits (newest first) that touched releasable desktop paths."""
    range_arg = "HEAD" if ref is None else f"{ref}..HEAD"
    try:
        output = git(
            [
                "log",
                "--first-parent",
                f"--max-count={FALLBACK_SOURCE_CANDIDATES}",
                "--format=%H",
                range_arg,
                "--",
                *DESKTOP_RELEASE_PATHS,
            ]
        )
    except subprocess.CalledProcessError:
        return []
    return [line for line in output.splitlines() if line]


def first_parent_shas_after(blocked_sha: str) -> list[str]:
    """First-parent commits newer than `blocked_sha` on main, newest first."""
    try:
        output = git(
            [
                "log",
                "--first-parent",
                f"--max-count={FALLBACK_SOURCE_CANDIDATES}",
                "--format=%H",
                f"{blocked_sha}..HEAD",
            ]
        )
    except subprocess.CalledProcessError:
        return []
    return [line for line in output.splitlines() if line]


def newest_green_source_ahead(repository: str, blocked_sha: str) -> tuple[str, str] | None:
    """Newest commit ABOVE the blocked SHA whose own required checks are green.

    A commit newer than `blocked_sha` on first-parent main contains everything
    `blocked_sha` contains, so its own exact-SHA checks tested a superset of
    that tree. When those checks are green, the desktop code in the blocked
    commit has been proven green by a later run, and the train may ship from
    that newer SHA. This is what makes a green tip unblock the train, and what
    stops a single flaky red commit from wedging shipping: the next commit that
    actually runs desktop CI carries the train forward.

    Only a genuine `ready` gate qualifies — skipped and absent checks are not
    success, so a non-desktop commit (whose desktop jobs skip) never qualifies.
    Preferred over `newest_green_fallback_source` because it ships newer, not
    older, code.
    """
    for sha in first_parent_shas_after(blocked_sha):
        gate = required_source_checks_gate(repository, sha)
        if gate.state == "ready":
            return sha, f"newest green SHA ahead of blocked {blocked_sha[:12]}"
    return None


def newest_green_fallback_source(repository: str, latest_tag: str | None, blocked_sha: str) -> tuple[str, str] | None:
    """Newest older releasable SHA whose required checks all succeeded, if any."""
    for sha in releasable_desktop_shas_since(latest_tag):
        if sha == blocked_sha:
            continue
        gate = required_source_checks_gate(repository, sha)
        if gate.state == "ready":
            return sha, f"newest green releasable SHA behind blocked {blocked_sha[:12]}"
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


def github_check_status(
    repository: str, sha: str, check_name: str
) -> tuple[str | None, str | None, str | None, str | None]:
    """Return status, conclusion, html_url, error for the newest matching check run."""
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
        return None, None, None, error

    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, None, None, "gh api returned invalid check-runs JSON"

    if not isinstance(pages, list):
        return None, None, None, "gh api returned invalid check-runs pages"

    matching_runs: list[tuple[tuple[datetime, datetime, int], dict[str, object]]] = []
    for page in pages:
        if not isinstance(page, dict):
            return None, None, None, "gh api returned an invalid check-runs page"
        check_runs = page.get("check_runs")
        if not isinstance(check_runs, list):
            return None, None, None, "gh api returned an invalid check-runs payload"
        for check_run in check_runs:
            if not isinstance(check_run, dict):
                return None, None, None, "gh api returned an invalid check run"
            if check_run.get("name") == check_name:
                sort_key, sort_key_error = check_run_sort_key(check_run)
                if sort_key_error:
                    return None, None, None, sort_key_error
                assert sort_key is not None
                matching_runs.append((sort_key, check_run))

    if not matching_runs:
        return None, None, None, None

    # `filter=latest` can omit an exact-SHA check run. Request every page and
    # choose the newest matching run ourselves so a later rerun cannot be
    # hidden by the API filter. `started_at` is primary so a newer in-progress
    # rerun is never masked by an older completed success; the remaining fields
    # make ordering deterministic when timestamps collide or are unavailable.
    latest = max(matching_runs, key=lambda run: run[0])[1]
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    html_url = latest.get("html_url")
    if status is not None and not isinstance(status, str):
        return None, None, None, "gh api returned a check run with an invalid status"
    if conclusion is not None and not isinstance(conclusion, str):
        return None, None, None, "gh api returned a check run with an invalid conclusion"
    if html_url is not None and not isinstance(html_url, str):
        html_url = None
    return status, conclusion, html_url if isinstance(html_url, str) else None, None


def github_workflow_state(repository: str, workflow_file: str) -> tuple[str | None, str | None]:
    """Return (state, error) for a producing workflow file."""
    result = subprocess.run(
        ["gh", "api", f"repos/{repository}/actions/workflows/{Path(workflow_file).name}"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "unknown gh api error"
        return None, error
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "gh api returned invalid workflow JSON"
    if not isinstance(payload, dict):
        return None, "gh api returned an invalid workflow payload"
    state = payload.get("state")
    if not isinstance(state, str):
        return None, "gh api returned a workflow with an invalid state"
    return state, None


def github_workflow_runs_for_sha(
    repository: str, workflow_file: str, sha: str
) -> tuple[list[dict[str, object]] | None, str | None]:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/actions/workflows/{Path(workflow_file).name}/runs?head_sha={sha}",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "unknown gh api error"
        return None, error
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "gh api returned invalid workflow-runs JSON"
    if not isinstance(payload, dict):
        return None, "gh api returned an invalid workflow-runs payload"
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return None, "gh api returned an invalid workflow-runs list"
    parsed: list[dict[str, object]] = []
    for run in runs:
        if isinstance(run, dict):
            parsed.append(run)
    return parsed, None


def commit_age_seconds(sha: str) -> int | None:
    try:
        raw = git(["log", "-1", "--format=%ct", sha])
        return int(time.time()) - int(raw)
    except (subprocess.CalledProcessError, ValueError):
        return None


def ci_evidence_recipe(repository: str, sha: str, workflow_file: str) -> str:
    return (
        f"gh api repos/{repository}/git/refs -f ref=refs/heads/ci-evidence/{sha} -f sha={sha} "
        f"&& gh workflow run {workflow_file} --ref ci-evidence/{sha} "
        f"(delete the branch after the run completes)"
    )


def _newest_workflow_run(runs: list[dict[str, object]]) -> dict[str, object] | None:
    if not runs:
        return None

    def sort_key(run: dict[str, object]) -> tuple[int, int]:
        run_id = run.get("id")
        numeric_id = run_id if type(run_id) is int else 0
        created = run.get("created_at")
        stamp = 0
        if isinstance(created, str):
            try:
                stamp = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp())
            except ValueError:
                stamp = 0
        return stamp, numeric_id

    return max(runs, key=sort_key)


def _diagnose_missing_check(repository: str, sha: str, check_name: str, workflow_file: str) -> SourceCheckGate:
    runs, error = github_workflow_runs_for_sha(repository, workflow_file, sha)
    if error:
        return SourceCheckGate(
            "blocked",
            f"could not read producing runs for {check_name} ({workflow_file}) " f"on source SHA {sha}: {error}",
        )
    assert runs is not None
    run = _newest_workflow_run(runs)
    if run is not None:
        status = run.get("status") if isinstance(run.get("status"), str) else "unknown"
        html_url = run.get("html_url") if isinstance(run.get("html_url"), str) else ""
        run_id = run.get("id")
        if status in {"queued", "in_progress", "waiting", "pending", "requested"}:
            detail = f"producing run is {status}"
            if html_url:
                detail += f": {html_url}"
            return SourceCheckGate(
                "defer",
                f"required check {check_name} is missing for exact source SHA {sha}; {detail}",
            )
        rerun = f"gh run rerun {run_id}" if type(run_id) is int else "gh run rerun <run-id>"
        return SourceCheckGate(
            "blocked",
            f"required check {check_name} is missing for exact source SHA {sha} after "
            f"producing workflow {workflow_file} completed"
            + (f" ({html_url})" if html_url else "")
            + f"; fix: {rerun}",
        )

    age = commit_age_seconds(sha)
    if age is None or age <= EVENT_DELIVERY_GRACE_SECONDS:
        return SourceCheckGate(
            "defer",
            f"required check {check_name} is missing for exact source SHA {sha}; "
            f"commit age {age if age is not None else 'unknown'}s is within the "
            f"{EVENT_DELIVERY_GRACE_SECONDS}s event-delivery grace",
        )
    recipe = ci_evidence_recipe(repository, sha, workflow_file)
    return SourceCheckGate(
        "blocked",
        f"required check {check_name} cannot exist for exact source SHA {sha}: "
        f"push events do not replay. Mint evidence with: {recipe}",
    )


def evaluate_source_checks(repository: str, sha: str) -> SourceCheckGate:
    """Single-pass source gate: ready, defer, or blocked. Never sleeps."""
    seen_workflows: list[str] = []
    for workflow_file in REQUIRED_SOURCE_CHECKS.values():
        if workflow_file in seen_workflows:
            continue
        seen_workflows.append(workflow_file)
        state, error = github_workflow_state(repository, workflow_file)
        if error:
            return SourceCheckGate(
                "blocked",
                f"could not read producer workflow {workflow_file}: {error}",
            )
        if state != "active":
            recipe = ci_evidence_recipe(repository, sha, workflow_file)
            return SourceCheckGate(
                "blocked",
                f"producer workflow {workflow_file} is {state}; "
                f"fix with `gh workflow enable {workflow_file}` then re-mint evidence: {recipe}",
            )

    observations: dict[str, tuple[str | None, str | None, str | None, str | None]] = {}
    for check_name in REQUIRED_SOURCE_CHECK_NAMES:
        observations[check_name] = github_check_status(repository, sha, check_name)

    missing: list[str] = []
    for check_name, (status, conclusion, html_url, error) in observations.items():
        if error:
            return SourceCheckGate(
                "blocked",
                f"could not read required check {check_name} for source SHA {sha}: {error}",
            )
        if status is None:
            missing.append(check_name)
            continue
        if status in {"queued", "in_progress", "waiting", "pending", "requested"}:
            return SourceCheckGate(
                "defer",
                f"required check {check_name} for exact source SHA {sha} is {status}",
            )
        if status == "completed" and conclusion != "success":
            url_suffix = f": {html_url}" if html_url else ""
            return SourceCheckGate(
                "blocked",
                f"required check {check_name} for exact source SHA {sha} "
                f"completed with {conclusion or 'no conclusion'}{url_suffix}",
            )
        if status == "completed" and conclusion == "success":
            continue
        return SourceCheckGate(
            "defer",
            f"required check {check_name} for exact source SHA {sha} is {status}",
        )

    for check_name in missing:
        gate = _diagnose_missing_check(repository, sha, check_name, REQUIRED_SOURCE_CHECKS[check_name])
        if gate.state != "ready":
            return gate
    return SourceCheckGate("ready")


def required_source_checks_gate(repository: str, sha: str) -> SourceCheckGate:
    return evaluate_source_checks(repository, sha)


def codemagic_check_status(repository: str, sha: str) -> tuple[str | None, str | None, str | None]:
    status, conclusion, _html_url, error = github_check_status(repository, sha, CODEMAGIC_CHECK_NAME)
    return status, conclusion, error


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


def candidate_publication_age_seconds(repository: str, tag: str) -> int | None:
    """Age of the candidate tag or release, the hourly train's throttle clock.

    New candidate tags are annotated and carry their own creation timestamp.
    A GitHub release's createdAt remains authoritative after publication. For
    legacy lightweight tags without a release, use the tagged commit time as a
    conservative transition fallback.
    """
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository, "--json", "tagName,createdAt"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        try:
            release = json.loads(result.stdout)
        except json.JSONDecodeError:
            release = None
        if isinstance(release, dict) and release.get("tagName") == tag:
            created_at = release.get("createdAt")
            if isinstance(created_at, str):
                try:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                except ValueError:
                    pass
                else:
                    return max(0, int(time.time() - created.timestamp()))
    return tag_creation_age_seconds(tag)


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
    parser.add_argument(
        "--min-tag-interval-seconds",
        type=int,
        default=0,
        help=(
            "Defer tagging while the latest desktop tag is younger than this "
            "(the hourly release train's throttle; 0 disables it)"
        ),
    )
    parser.add_argument(
        "--codemagic-source-gate",
        action="store_true",
        help="Let the tag-bound Codemagic compile, signing, and smoke workflow gate the candidate",
    )
    parser.add_argument("--watch-source-sha")
    parser.add_argument("--watch-max-polls", type=int, default=1)
    parser.add_argument("--watch-poll-seconds", type=int, default=WATCH_POLL_SECONDS)
    args = parser.parse_args()

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
    set_output("latest_tag", latest_tag or "")

    if args.min_tag_interval_seconds > 0 and latest_tag is not None:
        latest_candidate_age = candidate_publication_age_seconds(args.repository, latest_tag)
        if latest_candidate_age is not None and latest_candidate_age < args.min_tag_interval_seconds:
            remaining = args.min_tag_interval_seconds - latest_candidate_age
            set_output("source_sha", "")
            set_output("should_release", "false")
            set_output(
                "reason",
                f"Hourly release train: candidate {latest_tag} created {latest_candidate_age}s ago; "
                f"next candidate in {remaining}s.",
            )
            return 0

    changes = releasable_desktop_changes_since(latest_tag)

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

    if args.codemagic_source_gate:
        print("Codemagic owns candidate compile, signing, notarization, and signed-smoke admission.")
    else:
        source_check_gate = evaluate_source_checks(args.repository, source_sha)
        if source_check_gate.state == "defer":
            print(f"::warning::{source_check_gate.reason}")
            set_output("should_release", "false")
            set_output("reason", f"Waiting for required exact-SHA checks: {source_check_gate.reason}.")
            return 0
        if source_check_gate.state == "blocked":
            # Prefer a green SHA ABOVE the blocked one — it proves the same desktop
            # tree and ships newer code — before falling back to an older green SHA.
            fallback = newest_green_source_ahead(args.repository, source_sha) or newest_green_fallback_source(
                args.repository, latest_tag, source_sha
            )
            if fallback is None:
                print(f"::error::{source_check_gate.reason}")
                set_output("should_release", "false")
                set_output("reason", f"Desktop candidate source gate blocked: {source_check_gate.reason}.")
                return 1
            fallback_sha, fallback_note = fallback
            print(
                f"::warning::Newest releasable SHA {source_sha} is blocked "
                f"({source_check_gate.reason}); falling back to {fallback_note}."
            )
            source_sha = fallback_sha
            set_output("source_sha", source_sha)
            existing_candidate = existing_source_candidate_reason(args.repository, source_sha)
            if existing_candidate:
                set_output("should_release", "false")
                set_output("reason", f"Desktop candidate already exists for fallback source: {existing_candidate}")
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
