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
import urllib.error
import urllib.request
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
# Self-driving release posture (since 2026-10-14): submissions release on
# approval instead of piling up approved-but-unreleased versions (ASC has no
# API to issue the developer-release command, which is why MANUAL versions
# accumulated). The brake moves post-release: iOS automatic phased rollout is
# pausable in App Store Connect, Android staged rollout is haltable in Play.
# Flip RELEASE_TYPE back to "MANUAL" / PHASED_RELEASE to False /
# STAGED_ROLLOUT_FRACTION to None to restore the queue-for-human behavior.
RELEASE_TYPE = "AFTER_APPROVAL"
PHASED_RELEASE = True
STAGED_ROLLOUT_FRACTION = 0.05
# Staged-rollout ladder: each daily gate-green run promotes the live staged
# release one hop (5% -> 25% -> full). A hop is skipped only by HOLD, so a bad
# release can be halted in Play Console before the next ladder step fires; a
# halted rollout always waits for a human. Setting STAGED_ROLLOUT_FRACTION to
# None disables the ladder too (queue-for-human rollback parks any rollout
# that is already in flight).
STAGED_ROLLOUT_LADDER = (0.05, 0.25, 1.0)


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
    """Locate the completed review submission that carries an App Store version.

    Apple strips the appStoreVersion relationship from submission items when
    the container reaches COMPLETE, so items must be listed with
    include=appStoreVersion (the only API surface that still resolves the
    linkage after completion). The Codemagic CLI items action has no include
    flag, so this reads the App Store Connect REST API directly with a JWT
    minted from the APP_STORE_CONNECT_* credentials already present on the
    build machine (stdlib only: pyjwt availability is not guaranteed there).
    """
    base = "https://api.appstoreconnect.apple.com/v1"
    try:
        payload = asc("apps", "list-review-submissions", APP_ID, "--platform", "IOS", "--review-submission-state", "COMPLETE")
    except TrainError:
        raise
    submissions = sorted(
        _resource_list(payload), key=lambda r: str(_attributes(r).get("submittedDate") or ""), reverse=True
    )
    token = _asc_rest_token()
    headers = {"Authorization": f"Bearer {token}"}
    for submission in submissions:
        submission_id = _resource_id(submission)
        url = f"{base}/reviewSubmissions/{submission_id}/items?include=appStoreVersion"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
        except (urllib.error.URLError, ValueError) as exc:
            raise TrainError(f"App Store Connect items lookup failed for {submission_id}: {exc}") from exc
        for item in payload.get("included", []) or []:
            if item.get("type") == "appStoreVersions" and item.get("id") == version_id:
                return submission_id
    raise TrainError(f"no completed review submission contains App Store version {version_id}")


def _asc_rest_token() -> str:
    """ES256 JWT for the App Store Connect REST API (kid must be a JWT header)."""
    import base64

    issuer = os.environ.get("APP_STORE_CONNECT_ISSUER_ID", "")
    key_id = os.environ.get("APP_STORE_CONNECT_KEY_IDENTIFIER", "")
    pem = os.environ.get("APP_STORE_CONNECT_PRIVATE_KEY", "")
    if not (issuer and key_id and pem):
        raise TrainError("missing App Store Connect credential for REST lookup")
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    now = int(time.time())
    claims = {"iss": issuer, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"}
    encode = lambda obj: base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signing_input = f"{encode(header)}.{encode(claims)}"
    try:
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key

            key = load_pem_private_key(pem.encode(), password=None)
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes

            der = key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        except ImportError:
            # openssl CLI fallback: DER ECDSA signature over the signing input
            import subprocess
            import tempfile

            with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as key_file:
                key_file.write(pem)
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as data_file:
                data_file.write(signing_input)
            try:
                result = subprocess.run(
                    ["openssl", "dgst", "-sha256", "-sign", key_file.name, data_file.name],
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
                der = result.stdout
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                raise TrainError(f"openssl could not sign the App Store Connect REST token: {exc}") from exc
            finally:
                os.unlink(key_file.name)
                os.unlink(data_file.name)
    except TrainError:
        raise
    except Exception as exc:
        raise TrainError(f"could not sign the App Store Connect REST token: {exc}") from exc
    r, s = _der_ecdsa_sig_to_raw(der)
    return f"{signing_input}.{base64.urlsafe_b64encode(r + s).rstrip(b'=').decode()}"


def _der_ecdsa_sig_to_raw(der: bytes) -> tuple[bytes, bytes]:
    """Convert a DER ECDSA signature to the 64-byte r||s raw form Apple's ES256 expects."""
    if len(der) < 8 or der[0] != 0x30:
        raise TrainError("unexpected DER signature shape")
    index = 2
    if der[index] != 0x02:
        raise TrainError("unexpected DER signature shape")
    r_len = der[index + 1]
    r = der[index + 2 : index + 2 + r_len]
    index += 2 + r_len
    if der[index] != 0x02:
        raise TrainError("unexpected DER signature shape")
    s_len = der[index + 1]
    s = der[index + 2 : index + 2 + s_len]
    # JWS raw form: both integers left-padded to exactly 32 bytes
    return r.rjust(32, b"\x00")[-32:], s.rjust(32, b"\x00")[-32:]


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
        promote.submit_ios(build, notes, locales=locales, release_type=RELEASE_TYPE, phased=PHASED_RELEASE)
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    version_id = ios_build_version_id(asc, candidate.build_id)
    if version_id is None:
        raise TrainError("submission returned but the build is not attached to an App Store version")
    wait_for_version_state(asc, version_id, "WAITING_FOR_REVIEW")
    posture = RELEASE_TYPE + ("/phased" if PHASED_RELEASE else "")
    log(f"submitted {candidate.version} ({candidate.build_number}) for review; release type {posture}")
    return f"ios={plan.action} {candidate.version} ({candidate.build_number}) WAITING_FOR_REVIEW ({posture})"


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


def existing_production_staged(production: object) -> dict[str, object] | None:
    """A production rollout in flight: `inProgress`, or `halted` (the brake).

    Google returns an operator-halted rollout with status "halted" — it keeps
    its userFraction — so both shapes must be recognized. Treating only
    `inProgress` as staged would let the next train ignore the brake, treat the
    older completed release as live, and rewrite the production track; a
    halted rollout always waits for a human.
    """
    staged = [
        release
        for release in _releases(production, "production")
        if release.get("status") in ("inProgress", "halted")
    ]
    return staged[0] if staged else None


def _staged_release_notes(staged: dict[str, object]) -> str | None:
    """The exact en-US What's-New text Play already holds for this rollout.

    Reusing the shipped text on every ladder hop keeps the store listing
    stable mid-rollout; the durable release file is only a fallback (read
    as-is, never re-collected) when Play returns no usable text.
    """
    notes = staged.get("releaseNotes")
    if not isinstance(notes, list):
        return None
    for entry in notes:
        if not isinstance(entry, dict) or entry.get("language") != "en-US":
            continue
        text = entry.get("text")
        if isinstance(text, str) and text.strip():
            return text
    return None


def run_android(*, dry_run: bool, release_date: str) -> str:
    try:
        client, edit_id = promote.play_edit()
        tracks = {name: promote.play_track(client, edit_id, name) for name in PLAY_SOURCE_TRACKS}
        production = promote.play_track(client, edit_id, "production")
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    live = play_live_version(production)
    candidate = pick_play_candidate(tracks, production)
    staged = existing_production_staged(production)
    if staged is not None:
        # A rollout is in flight (inProgress, or halted by an operator). Play
        # allows only one staged release at a time (two inProgress in one PUT
        # -> 400), so this branch owns the train until the rollout completes:
        # hop the ladder one step per gate-green day, and never fall through
        # to the candidate path while the track is mid-rollout.
        staged_name = staged.get("name")
        staged_version = promote.production_release_version(staged_name) if isinstance(staged_name, str) else None
        codes = [str(code) for code in staged.get("versionCodes", [])]
        current = staged.get("userFraction")
        current = float(current) if isinstance(current, (int, float)) else None
        if staged_version is None or not codes:
            raise TrainError(f"production staged release has no readable identity: {staged}")
        if STAGED_ROLLOUT_FRACTION is None:
            # Staged rollouts are disabled (the queue-for-human rollback).
            # Parking is the only safe action: hopping would expand exposure
            # the rollback meant to stop, and drafting over the track would
            # discard the operator's in-flight state. A human decides in Play.
            fraction_text = f" at {current:.0%}" if current is not None else ""
            log(
                f"Android production rollout {staged_version} {codes[0]}{fraction_text} is in flight; staged "
                f"rollouts are disabled — parked for a human to resume or halt in Play Console"
            )
            at = f"@{current:.0%} " if current is not None else ""
            return f"android=staged {staged_version} {codes[0]} {at}parked (staged disabled)"
        if staged.get("status") == "halted" or current is None:
            # An operator halted the rollout (Google returns status "halted"
            # with the fraction retained) or its fraction is unreadable: the
            # brake stays on until a human resumes or halts it in Play Console.
            log(
                f"Android production staged {staged_version} {codes} is HALTED; "
                f"a human decides halt or resume in Play Console"
            )
            return f"android=staged-halted {staged_version} {codes[0]}"
        if candidate is not None:
            # A newer internal build exists, but Play allows only one staged
            # release at a time, so it starts only after this rollout
            # completes. The ladder must keep hopping meanwhile: returning
            # here would wedge the train (the rollout never finishing, the
            # candidate never starting) until a human intervenes.
            log(
                f"newer candidate {candidate.version} ({candidate.version_code}) waits for staged "
                f"{staged_version} to complete; continuing the ladder"
            )
        next_hops = [hop for hop in STAGED_ROLLOUT_LADDER if hop > current + 1e-9]
        if not next_hops:
            log(f"Android production staged {staged_version} at {current:.0%} is at or past the ladder top; nothing to do")
            return f"android=staged {staged_version} {codes[0]} @{current:.0%} (ladder done)"
        hop = next_hops[0]
        log(f"Android live {live}; promoting staged {staged_version} {codes[0]} from {current:.0%} to {hop:.0%}")
        if dry_run:
            return f"android=dry-run:staged-hop {staged_version} {codes[0]} {current:.0%}->{hop:.0%}"
        # The rollout shipped its What's-New text when it started. Re-use the
        # exact text Play already holds, falling back to the durable release
        # file WITHOUT collecting: collect() would fold the NEXT version's
        # unreleased fragments into this in-flight version and consume them.
        notes = _staged_release_notes(staged) or promote.require_notes(
            ensure_release_notes(staged_version, release_date, write=False), staged_version, "android"
        )
        try:
            if hop >= 1.0:
                promote.submit_android(client, edit_id, staged_version, codes[0], notes, status="completed")
            else:
                promote.submit_android(
                    client, edit_id, staged_version, codes[0], notes, status="inProgress", user_fraction=hop
                )
        except promote.PromotionError as exc:
            raise TrainError(str(exc)) from exc
        if hop >= 1.0:
            log(f"Android production rollout completed: {staged_version} {codes[0]} at 100%")
            return f"android=completed {staged_version} {codes[0]} 100%"
        log(f"Android production staged now {staged_version} {codes[0]} at {hop:.0%}")
        return f"android=staged {staged_version} {codes[0]} @{hop:.0%}"
    if candidate is None:
        log(f"Android live {live}; no internal/alpha build is newer")
        return f"android=nothing (live {live})"
    draft = existing_production_draft(production)
    draft_codes = promote.release_codes(draft) if draft is not None else None
    if draft is not None and draft_codes == [candidate.version_code]:
        if STAGED_ROLLOUT_FRACTION is None:
            log(f"Android production draft already carries {candidate.version} ({candidate.version_code})")
            return f"android=leave draft {candidate.version} ({candidate.version_code})"
        # A legacy queue-for-human train left the selected code sitting in a
        # Play draft. In staged posture the same code converts straight into
        # the 5% rollout (the track PUT replaces the draft) instead of being
        # idempotently re-left for a human on every run.
        log(
            f"Android production draft already carries {candidate.version} ({candidate.version_code}); "
            f"converting the draft into a staged rollout"
        )
    else:
        action = "staging" if STAGED_ROLLOUT_FRACTION is not None else "drafting"
        log(
            f"Android live {live}; {action} {candidate.version} ({candidate.version_code}) from {candidate.track}"
            + (f", replacing draft {draft.get('versionCodes')}" if draft else "")
        )
    release_path = ensure_release_notes(candidate.version, release_date, write=not dry_run)
    if dry_run:
        if STAGED_ROLLOUT_FRACTION is not None:
            return (
                f"android=dry-run:staged {candidate.version} ({candidate.version_code}) "
                f"@{STAGED_ROLLOUT_FRACTION:.0%}"
            )
        return f"android=dry-run:draft {candidate.version} ({candidate.version_code})"
    notes = promote.require_notes(release_path, candidate.version, "android")
    try:
        promote.select_play_release(
            tracks[candidate.track], production, candidate.version, candidate.version_code, source_track=candidate.track
        )
        if STAGED_ROLLOUT_FRACTION is not None:
            promote.submit_android(
                client,
                edit_id,
                candidate.version,
                candidate.version_code,
                notes,
                status="inProgress",
                user_fraction=STAGED_ROLLOUT_FRACTION,
            )
        else:
            promote.submit_android(client, edit_id, candidate.version, candidate.version_code, notes, status="draft")
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    if STAGED_ROLLOUT_FRACTION is not None:
        log(
            f"Android production staged rollout started: {candidate.version} ({candidate.version_code}) "
            f"at {STAGED_ROLLOUT_FRACTION:.0%}; haltable in Play Console"
        )
        return f"android=staged {candidate.version} ({candidate.version_code}) @{STAGED_ROLLOUT_FRACTION:.0%}"
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
