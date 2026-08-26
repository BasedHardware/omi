#!/usr/bin/env python3
"""Hourly alarm: desktop beta is stale versus the candidate train.

Uses GH_TOKEN (default repo token) and unauthenticated HTTPS. Diagnoses from
one command's output. Idempotent: healthy runs print recovered and exit 0.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PLANNER_PATH = Path(__file__).with_name("plan-desktop-release.py")
SPEC = importlib.util.spec_from_file_location("plan_desktop_release", PLANNER_PATH)
assert SPEC and SPEC.loader
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)

BETA_APPCAST_URL = "https://api.omi.me/v2/desktop/appcast.xml?identity=beta"
CODEMAGIC_CHECK_NAME = planner.CODEMAGIC_CHECK_NAME
PROMOTION_LAG_SECONDS = 3 * 60 * 60
WEDGED_TRAIN_SECONDS = 6 * 60 * 60
AUTO_RELEASE_WORKFLOW = "desktop_auto_release.yml"
TAG_BUILD_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+\+(\d+)-macos$")
SPARKLE_VERSION_RE = re.compile(r"<sparkle:version>(\d+)</sparkle:version>|sparkle:version=\"(\d+)\"")


class FreshnessError(RuntimeError):
    pass


def parse_tag_build(tag: str) -> int | None:
    match = TAG_BUILD_RE.fullmatch(tag)
    if match is None:
        return None
    return int(match.group(1))


def live_beta_build(appcast: str) -> int | None:
    builds = [int(a or b) for a, b in SPARKLE_VERSION_RE.findall(appcast)]
    return max(builds) if builds else None


def fetch_beta_appcast() -> str:
    request = urllib.request.Request(BETA_APPCAST_URL, headers={"Accept": "application/xml, text/xml, */*"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise FreshnessError(f"could not fetch beta appcast {BETA_APPCAST_URL}: {error}") from error


def is_releasable_path(path: str) -> bool:
    if path == "desktop/macos/CHANGELOG.json":
        return False
    if path == "desktop/macos/AGENTS.md":
        return False
    if path.startswith("desktop/macos/changelog/"):
        return False
    return True


def oldest_unreleased_releasable_main_commit(latest_tag: str) -> tuple[str, int] | None:
    """Return the oldest unshipped macOS update so merge churn cannot reset age."""
    try:
        output = planner.git(
            [
                "log",
                "--first-parent",
                "--reverse",
                "--format=%H",
                f"{latest_tag}..HEAD",
                "--",
                *planner.DESKTOP_RELEASE_PATHS,
            ]
        )
    except subprocess.CalledProcessError:
        return None
    for sha in output.splitlines():
        if not sha:
            continue
        try:
            files = planner.git(
                [
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "--diff-filter=ACDMR",
                    "-r",
                    f"{sha}^1",
                    sha,
                    "--",
                    *planner.DESKTOP_RELEASE_PATHS,
                ]
            )
        except subprocess.CalledProcessError:
            continue
        if any(is_releasable_path(path) for path in files.splitlines() if path):
            age = planner.commit_age_seconds(sha)
            if age is None:
                return None
            return sha, age
    return None


def is_ancestor(commit: str, ref: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, ref],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.returncode == 0


def latest_auto_release_run_url(repository: str) -> str:
    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repository}/actions/workflows/{AUTO_RELEASE_WORKFLOW}/runs?per_page=1",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return f"(could not read latest {AUTO_RELEASE_WORKFLOW} run: {result.stderr.strip() or result.stdout.strip()})"
    try:
        payload = json.loads(result.stdout)
        runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
        if isinstance(runs, list) and runs and isinstance(runs[0], dict):
            url = runs[0].get("html_url")
            if isinstance(url, str) and url:
                return url
    except json.JSONDecodeError:
        pass
    return f"(no {AUTO_RELEASE_WORKFLOW} runs found)"


def diagnose_promotion_lag(repository: str, tag: str, tag_sha: str) -> str:
    status, conclusion, html_url, error = planner.github_check_status(repository, tag_sha, CODEMAGIC_CHECK_NAME)
    check_url = html_url or f"(no {CODEMAGIC_CHECK_NAME} URL)"
    if error:
        return f"could not read {CODEMAGIC_CHECK_NAME} on {tag} ({tag_sha}): {error}. " f"Inspect {check_url}."
    if status is None:
        return (
            f"{CODEMAGIC_CHECK_NAME} is absent on {tag} ({tag_sha}): no Codemagic intake. "
            f"Dispatch workflow \"Build Desktop Release Candidate\" "
            f"(.github/workflows/{AUTO_RELEASE_WORKFLOW})."
        )
    if status == "completed" and conclusion == "failure":
        return (
            f"{CODEMAGIC_CHECK_NAME} failed on {tag}: {check_url}. "
            f"Re-run that Codemagic build or dispatch \"Desktop Release Recovery Required\"."
        )
    if status == "completed" and conclusion == "success":
        return (
            f"{CODEMAGIC_CHECK_NAME} succeeded on {tag}: {check_url}. "
            f"The build published but promotion did not land. "
            f"Dispatch \"Retry Desktop Beta Promotion\" "
            f"(.github/workflows/desktop_recover_beta.yml) with release_tag={tag}."
        )
    return (
        f"{CODEMAGIC_CHECK_NAME} on {tag} is {status}"
        + (f"/{conclusion}" if conclusion else "")
        + f": {check_url}. Wait for Codemagic, or dispatch \"Build Desktop Release Candidate\"."
    )


def evaluate(*, repository: str) -> tuple[int, list[str]]:
    lines: list[str] = ["Desktop beta freshness"]
    alarms: list[str] = []

    tag = planner.latest_desktop_tag()
    if tag is None:
        lines.append("No v*-macos candidate tag exists yet.")
        return 0, lines

    candidate_build = parse_tag_build(tag)
    if candidate_build is None:
        raise FreshnessError(f"newest desktop tag is not a canonical v*-macos tag: {tag}")

    appcast = fetch_beta_appcast()
    live_build = live_beta_build(appcast)
    tag_sha = planner.tag_sha(tag) or ""
    tag_age = planner.tag_age_seconds(tag)
    lines.append(f"candidate_tag={tag}")
    lines.append(f"candidate_build={candidate_build}")
    lines.append(f"live_beta_build={live_build if live_build is not None else 'missing'}")
    lines.append(f"candidate_tag_age_seconds={tag_age if tag_age is not None else 'unknown'}")

    if live_build is None:
        alarms.append(f"beta appcast {BETA_APPCAST_URL} has no sparkle:version")
    elif candidate_build > live_build and tag_age is not None and tag_age > PROMOTION_LAG_SECONDS:
        diagnosis = diagnose_promotion_lag(repository, tag, tag_sha)
        alarms.append(
            f"Promotion lag: candidate_build {candidate_build} > live_beta_build {live_build} "
            f"and {tag} is {tag_age}s old (>{PROMOTION_LAG_SECONDS}s). {diagnosis}"
        )

    oldest_unreleased = oldest_unreleased_releasable_main_commit(tag)
    if oldest_unreleased is not None:
        sha, age = oldest_unreleased
        lines.append(f"oldest_unreleased_main_sha={sha}")
        lines.append(f"oldest_unreleased_main_age_seconds={age}")
        if age > WEDGED_TRAIN_SECONDS and not is_ancestor(sha, tag):
            run_url = latest_auto_release_run_url(repository)
            alarms.append(
                f"Wedged train: oldest unshipped releasable first-parent main commit {sha} is {age}s old "
                f"(>{WEDGED_TRAIN_SECONDS}s) and is not an ancestor of {tag}. "
                f"Inspect the latest \"Build Desktop Release Candidate\" run: {run_url}. "
                f"Dispatch .github/workflows/{AUTO_RELEASE_WORKFLOW} to retry tagging."
            )
    else:
        lines.append("oldest_unreleased_main_sha=none")

    if alarms:
        lines.append("status=unhealthy")
        lines.extend(alarms)
        return 1, lines

    lines.append("status=healthy")
    return 0, lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "BasedHardware/omi"))
    parser.add_argument("--summary", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        exit_code, lines = evaluate(repository=args.repository)
    except FreshnessError as error:
        lines = [f"Desktop beta freshness failed: {error}"]
        exit_code = 1
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)
    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(text, encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
