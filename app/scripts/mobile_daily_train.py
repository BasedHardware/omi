#!/usr/bin/env python3
"""Daily mobile release train: queue the newest internal build for a human to release.

iOS: the newest processed TestFlight build whose marketing version is newer than the live
App Store version is submitted for review with release type MANUAL. One submission is in
flight at a time: anything WAITING_FOR_REVIEW / IN_REVIEW is left alone. An approved version
nobody released (PENDING_DEVELOPER_RELEASE) is cancelled and replaced when a newer build
exists; when it already carries the newest build it stays, so a human can still release it.

Android: the newest build on the Play internal/alpha tracks that is newer than the live
production release is written to production as a *draft* release. Each run overwrites the
draft with the newer build; a human presses Release in Play Console.

Nothing here releases to users. Exit 0 when there is nothing to do; exit 1 on a real failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Callable, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mobile_store_promote as promote  # noqa: E402

APP_ID = promote.APP_ID
PACKAGE_NAME = promote.PACKAGE_NAME
VERSION_RE = promote.VERSION_RE
IN_FLIGHT_STATES = (
    "WAITING_FOR_REVIEW",
    "IN_REVIEW",
    "WAITING_FOR_EXPORT_COMPLIANCE",
    "PENDING_APPLE_RELEASE",
    "PROCESSING_FOR_APP_STORE",
)
PENDING_STATE = "PENDING_DEVELOPER_RELEASE"
LIVE_STATE = "READY_FOR_SALE"
REJECTED_STATE = "DEVELOPER_REJECTED"
PLAY_SOURCE_TRACKS = ("internal", "alpha")
ACTIVE_PLAY_STATUSES = ("completed", "inProgress")
STATE_POLL_SECONDS = 5
STATE_POLL_ATTEMPTS = 24


class TrainError(Exception):
    pass


def log(message: str) -> None:
    print(f"[mobile-daily-train] {message}", flush=True)


def strict_version(value: object) -> str | None:
    return value if isinstance(value, str) and VERSION_RE.fullmatch(value) else None


def newest_version(versions: Iterable[str]) -> str | None:
    strict = [version for version in versions if strict_version(version)]
    return max(strict, key=promote.version_parts) if strict else None


# --------------------------------------------------------------------------- iOS


@dataclass(frozen=True)
class IOSVersion:
    id: str
    version: str
    state: str


@dataclass(frozen=True)
class IOSCandidate:
    build_id: str
    version: str
    build_number: int


@dataclass(frozen=True)
class IOSState:
    live_version: str
    in_flight: tuple[IOSVersion, ...]
    pending: tuple[IOSVersion, ...]
    candidate: IOSCandidate | None
    # App Store version id the candidate build is already attached to, if any.
    candidate_version_id: str | None


@dataclass(frozen=True)
class IOSPlan:
    action: str  # hold | nothing | leave | replace | submit
    reason: str
    reject: IOSVersion | None = None
    submit: IOSCandidate | None = None


def plan_ios(state: IOSState) -> IOSPlan:
    """Pure decision over the fetched App Store Connect state."""
    if state.in_flight:
        inflight = ", ".join(f"{v.version} {v.state}" for v in state.in_flight)
        return IOSPlan("hold", f"a submission is already in flight ({inflight}); only one at a time")
    if len(state.pending) > 1:
        raise TrainError("more than one App Store version is pending developer release; resolve by hand")
    pending = state.pending[0] if state.pending else None
    candidate = state.candidate
    if candidate is None:
        return IOSPlan("nothing", f"no processed TestFlight build is newer than live {state.live_version}")
    if pending is not None:
        if state.candidate_version_id == pending.id:
            return IOSPlan(
                "leave",
                f"{pending.version} is approved and waiting for a human release with the newest build "
                f"{candidate.build_number}",
            )
        if promote.version_parts(pending.version) > promote.version_parts(candidate.version):
            raise TrainError(
                f"pending version {pending.version} is newer than the newest TestFlight build "
                f"{candidate.version} ({candidate.build_number}); refusing to reject it"
            )
        return IOSPlan(
            "replace",
            f"{pending.version} was approved but never released; replacing it with build "
            f"{candidate.build_number} ({candidate.version})",
            reject=pending,
            submit=candidate,
        )
    return IOSPlan(
        "submit", f"submitting build {candidate.build_number} ({candidate.version}) for review", submit=candidate
    )


def asc_json(*args: str, timeout: int = 180) -> object:
    command = ["app-store-connect", *args, "--json"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        raise TrainError(f"App Store Connect command failed: {' '.join(args[:3])}\n{exc.stderr[-2000:]}") from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise TrainError(f"App Store Connect command did not complete: {' '.join(args[:3])}: {exc}") from exc
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise TrainError(f"App Store Connect returned invalid JSON for {' '.join(args[:3])}") from exc


def _attributes(resource: object) -> dict[str, object]:
    if not isinstance(resource, dict) or not isinstance(resource.get("attributes"), dict):
        raise TrainError("App Store Connect returned an invalid resource")
    return resource["attributes"]


def _resource_id(resource: object) -> str:
    if not isinstance(resource, dict) or not isinstance(resource.get("id"), str) or not resource["id"]:
        raise TrainError("App Store Connect resource has no id")
    return resource["id"]


def _resource_list(payload: object) -> list[object]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise TrainError("App Store Connect returned a non-list result")
    return payload


def ios_versions_in_state(asc: Callable[..., object], state: str) -> list[IOSVersion]:
    payload = asc("apps", "app-store-versions", APP_ID, "--platform", "IOS", "--state", state)
    versions = []
    for resource in _resource_list(payload):
        attrs = _attributes(resource)
        version = attrs.get("versionString")
        if not isinstance(version, str):
            raise TrainError("App Store version has no version string")
        versions.append(IOSVersion(_resource_id(resource), version, str(attrs.get("appStoreState"))))
    return versions


def ios_prerelease_versions(asc: Callable[..., object]) -> list[str]:
    payload = asc("apps", "pre-release-versions", APP_ID)
    versions = []
    for resource in _resource_list(payload):
        attrs = _attributes(resource)
        if attrs.get("platform") not in (None, "IOS"):
            continue
        version = strict_version(attrs.get("version"))
        if version:
            versions.append(version)
    return versions


def ios_valid_builds(asc: Callable[..., object], version: str) -> list[tuple[int, str]]:
    payload = asc(
        "builds",
        "list",
        "--app-id",
        APP_ID,
        "--platform",
        "IOS",
        "--pre-release-version",
        version,
        "--processing-state",
        "VALID",
        "--not-expired",
    )
    builds = []
    for resource in _resource_list(payload):
        attrs = _attributes(resource)
        number = attrs.get("version")
        if not isinstance(number, str) or not promote.BUILD_RE.fullmatch(number):
            raise TrainError(f"TestFlight build for {version} has an invalid build number")
        if attrs.get("processingState") != "VALID" or attrs.get("expired", False):
            continue
        builds.append((int(number), _resource_id(resource)))
    return builds


def ios_candidate(asc: Callable[..., object], live_version: str) -> IOSCandidate | None:
    """Newest valid TestFlight build of the highest marketing version newer than the live one."""
    live = promote.version_parts(live_version)
    newer = sorted(
        {v for v in ios_prerelease_versions(asc) if promote.version_parts(v) > live},
        key=promote.version_parts,
        reverse=True,
    )
    for version in newer:
        builds = ios_valid_builds(asc, version)
        if builds:
            number, build_id = max(builds)
            return IOSCandidate(build_id, version, number)
        log(f"TestFlight {version} has no processed build yet; looking at the next version")
    return None


def ios_build_version_id(asc: Callable[..., object], build_id: str) -> str | None:
    """App Store version the build is attached to, or None when it was never submitted."""
    try:
        payload = asc("builds", "app-store-version", build_id)
    except TrainError:
        return None
    if payload is None:
        return None
    return _resource_id(payload)


def fetch_ios_state(asc: Callable[..., object]) -> IOSState:
    live_version = newest_version(v.version for v in ios_versions_in_state(asc, LIVE_STATE))
    if live_version is None:
        raise TrainError("App Store Connect reports no live (READY_FOR_SALE) iOS version")
    in_flight = tuple(v for state in IN_FLIGHT_STATES for v in ios_versions_in_state(asc, state))
    pending = tuple(ios_versions_in_state(asc, PENDING_STATE))
    candidate = ios_candidate(asc, live_version)
    candidate_version_id = ios_build_version_id(asc, candidate.build_id) if candidate and pending else None
    return IOSState(live_version, in_flight, pending, candidate, candidate_version_id)


def ios_live_locales(asc: Callable[..., object], live_version_id: str) -> list[str]:
    payload = asc("app-store-versions", "localizations", live_version_id)
    locales = []
    for resource in _resource_list(payload):
        locale = _attributes(resource).get("locale")
        if not isinstance(locale, str) or not locale:
            raise TrainError("App Store localization has no locale")
        locales.append(locale)
    if not locales:
        raise TrainError("the live App Store version has no localizations")
    return sorted(set(locales))


def review_submission_for_version(asc: Callable[..., object], version_id: str) -> str:
    payload = asc("apps", "list-review-submissions", APP_ID, "--platform", "IOS", "--review-submission-state", "COMPLETE")
    submissions = sorted(
        _resource_list(payload), key=lambda r: str(_attributes(r).get("submittedDate") or ""), reverse=True
    )
    for submission in submissions:
        submission_id = _resource_id(submission)
        for item in _resource_list(asc("review-submissions", "items", submission_id)):
            relationships = item.get("relationships", {}) if isinstance(item, dict) else {}
            version = relationships.get("appStoreVersion", {}) if isinstance(relationships, dict) else {}
            data = version.get("data") if isinstance(version, dict) else None
            if isinstance(data, dict) and data.get("id") == version_id:
                return submission_id
    raise TrainError(f"no completed review submission contains App Store version {version_id}")


def wait_for_version_state(asc: Callable[..., object], version_id: str, expected: str) -> None:
    for _ in range(STATE_POLL_ATTEMPTS):
        state = str(_attributes(asc("app-store-versions", "get", version_id)).get("appStoreState"))
        if state == expected:
            return
        log(f"version {version_id} is {state}; waiting for {expected}")
        time.sleep(STATE_POLL_SECONDS)
    raise TrainError(f"App Store version {version_id} did not reach {expected}")


def reject_pending_ios(asc: Callable[..., object], pending: IOSVersion) -> None:
    """Remove an approved-but-unreleased version from review (ASC: PATCH reviewSubmissions canceled=true)."""
    submission_id = review_submission_for_version(asc, pending.id)
    log(f"cancelling review submission {submission_id} for {pending.version} ({pending.state})")
    asc("review-submissions", "cancel", submission_id)
    wait_for_version_state(asc, pending.id, REJECTED_STATE)
    log(f"{pending.version} is now {REJECTED_STATE}")


def ensure_release_notes(version: str, release_date: str, *, write: bool) -> Path:
    """Fold any unreleased fragments into releases/<version>.json so notes are never empty."""
    spec = spec_from_file_location(
        "mobile_changelog", Path(__file__).resolve().parents[2] / ".github/scripts/mobile-changelog.py"
    )
    if spec is None or spec.loader is None:
        raise TrainError("mobile changelog tooling unavailable")
    changelog = module_from_spec(spec)
    spec.loader.exec_module(changelog)
    release_path = changelog.RELEASES_DIR / f"{version}.json"
    fragments = changelog.unreleased_fragment_paths()
    if not write:
        if not release_path.is_file() and not fragments:
            raise TrainError(f"no release notes for {version}: no releases/{version}.json and no unreleased fragments")
        return release_path
    try:
        changelog.collect(version, release_date)
    except changelog.ChangelogError as exc:
        raise TrainError(f"release notes for {version} are unavailable: {exc}") from exc
    if fragments:
        log(
            f"collected {len(fragments)} unreleased fragment(s) into releases/{version}.json in this checkout only; "
            f"commit the same with `python3 .github/scripts/mobile-changelog.py collect --version {version}`"
        )
    return release_path


def run_ios(*, dry_run: bool, release_date: str, asc: Callable[..., object] = asc_json) -> str:
    for name in ("APP_STORE_CONNECT_ISSUER_ID", "APP_STORE_CONNECT_KEY_IDENTIFIER", "APP_STORE_CONNECT_PRIVATE_KEY"):
        if not os.environ.get(name):
            raise TrainError(f"missing App Store Connect credential: {name}")
    state = fetch_ios_state(asc)
    plan = plan_ios(state)
    log(f"iOS live {state.live_version}; plan={plan.action}: {plan.reason}")
    if plan.submit is None:
        return f"ios={plan.action} ({plan.reason})"
    candidate = plan.submit
    release_path = ensure_release_notes(candidate.version, release_date, write=not dry_run)
    notes = promote.require_notes(release_path, candidate.version, "ios") if release_path.is_file() else "<collected at run time>"
    live = next(v for v in ios_versions_in_state(asc, LIVE_STATE) if v.version == state.live_version)
    locales = ios_live_locales(asc, live.id)
    if dry_run:
        log(f"DRY RUN: would submit build {candidate.build_number} ({candidate.version}) with notes for {len(locales)} locales")
        return f"ios=dry-run:{plan.action} {candidate.version} ({candidate.build_number})"
    if plan.reject is not None:
        reject_pending_ios(asc, plan.reject)
    build = promote.IOSBuild(candidate.build_id, candidate.version, str(candidate.build_number))
    try:
        promote.submit_ios(build, notes, locales=locales)
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    version_id = ios_build_version_id(asc, candidate.build_id)
    if version_id is None:
        raise TrainError("submission returned but the build is not attached to an App Store version")
    wait_for_version_state(asc, version_id, "WAITING_FOR_REVIEW")
    log(f"submitted {candidate.version} ({candidate.build_number}) for review; release type MANUAL")
    return f"ios={plan.action} {candidate.version} ({candidate.build_number}) WAITING_FOR_REVIEW"


# ------------------------------------------------------------------------ Android


@dataclass(frozen=True)
class PlayCandidate:
    track: str
    version: str
    version_code: str


def _releases(track: object, name: str) -> list[dict[str, object]]:
    if not isinstance(track, dict) or track.get("track") != name:
        raise TrainError(f"Play {name} track lookup failed")
    releases = track.get("releases", [])
    if not isinstance(releases, list) or any(not isinstance(release, dict) for release in releases):
        raise TrainError(f"Play {name} track releases are invalid")
    return releases


def play_live_version(production: object) -> str | None:
    versions = []
    for release in _releases(production, "production"):
        if release.get("status") not in ACTIVE_PLAY_STATUSES:
            continue
        name = release.get("name")
        version = promote.production_release_version(name) if isinstance(name, str) else None
        if version:
            versions.append(version)
    return newest_version(versions)


def pick_play_candidate(sources: dict[str, object], production: object) -> PlayCandidate | None:
    """Highest version code on the source tracks whose version is newer than live production."""
    live = play_live_version(production)
    best: PlayCandidate | None = None
    for track_name, track in sources.items():
        for release in _releases(track, track_name):
            if release.get("status") not in ACTIVE_PLAY_STATUSES:
                continue
            name = release.get("name")
            version = promote.production_release_version(name) if isinstance(name, str) else None
            if version is None:
                continue
            if live is not None and promote.version_parts(version) <= promote.version_parts(live):
                continue
            for code in promote.release_codes(release):
                if best is None or int(code) > int(best.version_code):
                    best = PlayCandidate(track_name, version, code)
    return best


def existing_production_draft(production: object) -> dict[str, object] | None:
    drafts = [release for release in _releases(production, "production") if release.get("status") == "draft"]
    return drafts[0] if drafts else None


def run_android(*, dry_run: bool, release_date: str) -> str:
    try:
        client, edit_id = promote.play_edit()
        tracks = {name: promote.play_track(client, edit_id, name) for name in PLAY_SOURCE_TRACKS}
        production = promote.play_track(client, edit_id, "production")
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    live = play_live_version(production)
    candidate = pick_play_candidate(tracks, production)
    if candidate is None:
        log(f"Android live {live}; no internal/alpha build is newer")
        return f"android=nothing (live {live})"
    draft = existing_production_draft(production)
    if draft is not None and [str(code) for code in draft.get("versionCodes", [])] == [candidate.version_code]:
        log(f"Android production draft already carries {candidate.version} ({candidate.version_code})")
        return f"android=leave draft {candidate.version} ({candidate.version_code})"
    log(
        f"Android live {live}; drafting {candidate.version} ({candidate.version_code}) from {candidate.track}"
        + (f", replacing draft {draft.get('versionCodes')}" if draft else "")
    )
    release_path = ensure_release_notes(candidate.version, release_date, write=not dry_run)
    if dry_run:
        return f"android=dry-run:draft {candidate.version} ({candidate.version_code})"
    notes = promote.require_notes(release_path, candidate.version, "android")
    try:
        promote.select_play_release(
            tracks[candidate.track], production, candidate.version, candidate.version_code, source_track=candidate.track
        )
        promote.submit_android(client, edit_id, candidate.version, candidate.version_code, notes, status="draft")
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    log(f"Android production draft now {candidate.version} ({candidate.version_code}); a human releases it in Play Console")
    return f"android=draft {candidate.version} ({candidate.version_code})"


# --------------------------------------------------------------------------- main


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", choices=("ios", "android", "both"), default="both")
    parser.add_argument("--dry-run", action="store_true", help="read store state and print the plan; mutate nothing")
    parser.add_argument("--date", default=date.today().isoformat(), help="release date for collected notes")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("--date must be YYYY-MM-DD")
    summaries = []
    failures = []
    for platform, runner in (("ios", run_ios), ("android", run_android)):
        if args.platform not in (platform, "both"):
            continue
        try:
            summaries.append(runner(dry_run=args.dry_run, release_date=args.date))
        except TrainError as exc:
            log(f"FAIL {platform}: {exc}")
            failures.append(f"{platform}=FAILED")
    print("TRAIN SUMMARY: " + " ".join(summaries + failures), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
