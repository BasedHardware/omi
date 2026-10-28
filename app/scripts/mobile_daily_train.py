#!/usr/bin/env python3
"""Daily mobile release train: self-drive the newest internal build through the stores.

Self-driving posture (2026-10-14): releases proceed once the stores approve.

iOS: the newest processed TestFlight build whose marketing version is newer than the live
App Store version is submitted for review with release type AFTER_APPROVAL and the automatic
phased rollout enabled (pausable in App Store Connect — the post-release brake). One
submission is in flight at a time: anything WAITING_FOR_REVIEW / IN_REVIEW is left alone. An
approved version nobody released (PENDING_DEVELOPER_RELEASE) is developer-released through
`POST /v1/appStoreVersionReleaseRequests` (verified live 2026-10-17 on 1.0.564) after its
phased rollout is attached, so the newest build still ships without discarding an approval.
Apple now phases every release itself, so the train also advances the live rollout: a
phased release that started more than IOS_PHASED_JUMP_HOURS ago and is not PAUSED is
released to everyone (PATCH appStoreVersionPhasedReleases/{id} to COMPLETE) — exposure is ~1% during the
observation window and 100% after it, matching the operator gate's ~4-hour audit cadence
(the agreed 12-hour exposure window).

Android: the newest build on the Play internal/alpha tracks that is newer than the live
production release is written to production as a staged rollout at 1% (haltable in Play
Console) and promoted one ladder hop per advancing run (1% -> 10% -> 50% -> full, one run
every ~4 hours — a full ramp in about 12 hours). Every advancing action stamps a
minute-precision gate receipt into the release name so a retry inside the observation
window cannot hop twice.

The operator release gate audits the candidate before dispatching; its audited
platform/version/build identifiers travel as TRAIN_PIN_IOS / TRAIN_PIN_ANDROID and the train
fails closed when the store no longer matches them (the self-driving posture removed the
old human queue's final interception point; the pin replaces it).

Store approval always gates everything. Exit 0 when there is nothing to do; exit 1 on a
real failure.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Callable, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mobile_capture_health as capture_health  # noqa: E402
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
PLAY_SOURCE_TRACKS = ("internal", "alpha")
ACTIVE_PLAY_STATUSES = ("completed", "inProgress")
STATE_POLL_SECONDS = 5
STATE_POLL_ATTEMPTS = 24
# Self-driving release posture (since 2026-10-14; intraday ladder since 2026-10-17):
# submissions release on approval. The brakes: iOS automatic phased rollout is
# pausable in App Store Connect, Android staged rollout is haltable in Play.
# Flip RELEASE_TYPE back to "MANUAL" / PHASED_RELEASE to False /
# STAGED_ROLLOUT_FRACTION to None to restore the queue-for-human behavior.
RELEASE_TYPE = "AFTER_APPROVAL"
PHASED_RELEASE = True
# Exposure profile agreed with the operator 2026-10-17: ~12 hours from first
# exposure to 100% on both platforms. Apple's own schedule is fixed (1% day 1,
# 100% day 7), so the IOS jump below is what delivers the 12-hour profile.
STAGED_ROLLOUT_FRACTION = 0.01
# Each gate-green run promotes the live staged release one hop (~4-hour audit
# cadence -> 1% -> 10% -> 50% -> full in about 12 hours). A hop is skipped only
# by HOLD, so a bad release can be halted in Play Console before the next hop;
# a halted rollout always waits for a human. Setting STAGED_ROLLOUT_FRACTION to
# None disables the ladder too (queue-for-human rollback parks any rollout
# that is already in flight).
STAGED_ROLLOUT_LADDER = (0.01, 0.10, 0.50, 1.0)
# Apple's phased release starts at 1% and reaches 100% only on day 7, and its
# schedule is not customizable. The train therefore releases to everyone once
# the live rollout has been observable for this many hours: PATCH
# appStoreVersionPhasedReleases/{id} to COMPLETE ("release to everyone"; the
# to-one relationship path is read-only and answers DELETE with 405). With the
# gate running every ~4 hours, a candidate gets audited at least twice inside
# this window before the jump. Only an ACTIVE rollout jumps: a PAUSED one is the
# operator brake, and completing it would end their hold on a rollout they stopped.
IOS_PHASED_JUMP_HOURS = 12.0
# Minimum gap between two advancing actions on the same staged rollout (the
# observation window between exposure steps; the operator gate audits every
# ~4 hours, so each step is audited before the next one fires).
ROLLOUT_HOP_MIN_HOURS = 4.0
# Gate receipts: the train stamps the time of every advancing action (start or
# ladder hop) into the Play release name ("1.0.554 (gate 2026-10-17-1307)") so
# a retry inside the ROLLOUT_HOP_MIN_HOURS observation window reads the
# receipt and holds position instead of hopping twice. main() runs both
# platforms before exiting nonzero, so a failed platform's retry would
# otherwise re-observe the other platform's fresh fraction and collapse the
# ladder's observation window. The receipt is server-side Play state: it
# survives ephemeral build machines, needs no repo-side storage, and
# PRODUCTION_NAME_VERSION_RE already tolerates the "(...)" suffix on names.
GATE_RECEIPT_RE = re.compile(r"\(gate (\d{4}-\d{2}-\d{2})-(\d{4})\)")
GATE_RECEIPT_LEGACY_RE = re.compile(r"\(gate (\d{4}-\d{2}-\d{2})\)")


def _gate_receipt_dt(name: str) -> datetime | None:
    """Parse a release-name gate receipt into an aware UTC datetime (None if absent)."""
    match = GATE_RECEIPT_RE.search(name)
    if match:
        return datetime.strptime(f"{match.group(1)}-{match.group(2)}", "%Y-%m-%d-%H%M").replace(tzinfo=timezone.utc)
    legacy = GATE_RECEIPT_LEGACY_RE.search(name)
    if legacy:
        return datetime.strptime(legacy.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return None


class TrainError(Exception):
    pass


def capture_health_hold(platform: str, *, build: str | None) -> str | None:
    """Why a rollout hop must hold on capture health, or None to proceed.

    Read-only PostHog check (mobile_capture_health.py), mirroring the operator
    gate's judge per (platform, build): the Android version code, or the iOS
    build attached to the live App Store version. No build holds. Fails closed; TRAIN_CAPTURE_HEALTH_OVERRIDE=<reason> lets a hop through.
    """
    verdict = capture_health.check_rollout(platform, build=build)
    log(f"{platform} capture health: {verdict.reason}")
    return verdict.reason if verdict.hold else None


def log(message: str) -> None:
    print(f"[mobile-daily-train] {message}", flush=True)


def strict_version(value: object) -> str | None:
    return value if isinstance(value, str) and VERSION_RE.fullmatch(value) else None


def newest_version(versions: Iterable[str]) -> str | None:
    strict = [version for version in versions if strict_version(version)]
    return max(strict, key=promote.version_parts) if strict else None


PIN_RE = re.compile(r"^\s*((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\s*/\s*([1-9][0-9]*)\s*$")


@dataclass(frozen=True)
class StorePin:
    """A candidate verdict the operator release gate already recorded.

    `X.Y.Z/build` pins the audited candidate; `none` records that the gate's
    audit found NO candidate for the platform (an audited no-op is still an
    audited verdict). Anything else — including an unset variable — leaves
    the platform unpinned and selection trusts the store, which is how the
    gate dispatches today; see `store_pin` for the fail-closed half of this
    contract (a set-but-mismatched pin refuses to release).
    """

    version: str | None
    build: str | None

    @property
    def is_none(self) -> bool:
        return self.version is None

    def matches(self, version: str, build: str) -> bool:
        if self.is_none:
            return False
        return (self.version, self.build) == (version, build)


def store_pin(name: str) -> StorePin | None:
    """Parse `TRAIN_PIN_*` (`X.Y.Z/build` or `none`) into a StorePin; malformed fails closed.

    `none` (the gate's audited no-candidate verdict) must match the store
    actually having no candidate: a build appearing in the audit→dispatch gap
    is unaudited and is refused, exactly like a stale X.Y.Z/build pin.
    """
    raw = os.environ.get(name, "")
    if not raw:
        return None
    if raw.strip().lower() == "none":
        return StorePin(None, None)
    match = PIN_RE.fullmatch(raw)
    if match is None:
        raise TrainError(f"{name} must be X.Y.Z/build or none (got {raw!r}); refusing to select a candidate")
    return StorePin(match.group(1), match.group(2))


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
    action: str  # hold | nothing | leave | blocked | submit
    reason: str
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
                f"{candidate.version} ({candidate.build_number}); release {pending.version} by hand, never reject it"
            )
        # Apple completes the review submission on approval and refuses to
        # cancel it (409), and the API cannot developer-reject or release the
        # version either, so only a human in App Store Connect can clear it.
        return IOSPlan(
            "blocked",
            f"ACTION REQUIRED: {pending.version} is approved but unreleased and the newer build "
            f"{candidate.build_number} ({candidate.version}) cannot be submitted until a human releases "
            f"{pending.version} or rejects its binary in App Store Connect",
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
    live_versions = ios_versions_in_state(asc, LIVE_STATE)
    live_version = newest_version(v.version for v in live_versions)
    if live_version is None:
        raise TrainError("App Store Connect reports no live (READY_FOR_SALE) iOS version")
    in_flight = tuple(v for state in IN_FLIGHT_STATES for v in ios_versions_in_state(asc, state))
    pending = tuple(ios_versions_in_state(asc, PENDING_STATE))
    candidate = ios_candidate(asc, live_version)
    candidate_version_id = ios_build_version_id(asc, candidate.build_id) if candidate and pending else None
    return IOSState(live_version, in_flight, pending, candidate, candidate_version_id)


def ios_phased_release(live_version_id: str) -> dict[str, object] | None:
    """The live version's phased-release resource, or None when it has none.

    Reads GET /v1/appStoreVersions/{id}/appStoreVersionPhasedRelease over the
    REST+JWT surface the CLI lacks. A 404 means the live
    version has no phased release at all (released before this posture or
    fully finished); so does a 200 whose `data` is null,
    which is how Apple actually answers for a version released without one. Any other lookup failure fails
    closed: a brake this train cannot read is a brake it must respect.
    """
    token = _asc_rest_token()
    url = (
        "https://api.appstoreconnect.apple.com/v1/appStoreVersions/"
        f"{live_version_id}/appStoreVersionPhasedRelease"
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise TrainError(f"App Store Connect phased-release lookup failed for {live_version_id}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise TrainError(f"App Store Connect phased-release lookup failed for {live_version_id}: {exc}") from exc
    if isinstance(payload, dict) and "data" in payload and payload["data"] is None:
        # Apple answers a to-one relationship with no phased release as 200 `"data": null`
        # (seen live 2026-10-15 for 1.0.562, released MANUAL), not 404: no rollout, no pause.
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        raise TrainError(f"App Store Connect phased-release lookup returned an invalid resource for {live_version_id}")
    return payload["data"]


def ios_version_build_number(version_id: str) -> str | None:
    """The build number (CFBundleVersion) attached to an App Store version, or None.

    Reads GET /v1/appStoreVersions/{id}/build. The capture-health hold judges
    the exact store build, never a same-version TestFlight sibling; an
    unreadable build returns None, and the hold then fails closed.
    """
    try:
        token = _asc_rest_token()
        url = f"https://api.appstoreconnect.apple.com/v1/appStoreVersions/{version_id}/build"
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        data = payload.get("data") if isinstance(payload, dict) else None
        number = _attributes(data).get("version") if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001 - any failure, including a malformed body, means "unknown build", which holds
        log(f"App Store Connect build lookup failed for {version_id}: {exc}")
        return None
    return str(number) if isinstance(number, (str, int)) and str(number).isdigit() else None


def ios_phased_release_paused(live_version_id: str) -> bool:
    """Whether the live version's phased rollout is PAUSED (the operator brake)."""
    phased = ios_phased_release(live_version_id)
    if phased is None:
        return False
    return str(_attributes(phased).get("phasedReleaseState")) == "PAUSED"


def _phased_started_at(phased: dict[str, object]) -> datetime:
    started = _attributes(phased).get("startDate")
    if not isinstance(started, str) or not started.endswith("Z"):
        raise TrainError(f"phased release has no readable startDate: {started!r}")
    return datetime.strptime(started, "%Y-%m-%dT%H:%M:%S%z")


def ios_phased_release_should_complete(live_version_id: str, *, now: datetime | None = None) -> tuple[bool, str]:
    """Whether the live phased rollout should be released to everyone right now.

    True after IOS_PHASED_JUMP_HOURS with the rollout still ACTIVE (COMPLETE is
    Apple's "release to everyone"). A PAUSED rollout is the operator brake and
    never jumps; any other state (COMPLETE, INACTIVE, or one Apple adds later)
    is not a live rollout to advance. Anything unreadable fails closed (False
    with the reason — never True on an error).
    The jump also waits on capture health for the live version's exact build
    (ios_version_build_number, capture_health_hold).
    """
    now = now or datetime.now(timezone.utc)
    try:
        phased = ios_phased_release(live_version_id)
    except TrainError as exc:
        return False, str(exc)
    if phased is None:
        return False, "no phased release"
    attrs = _attributes(phased)
    state = str(attrs.get("phasedReleaseState"))
    if state == "PAUSED":
        return False, "phased rollout is PAUSED — the operator brake"
    if state != "ACTIVE":
        return False, f"phased rollout is {state}, not ACTIVE"
    try:
        started = _phased_started_at(phased)
    except TrainError as exc:
        return False, str(exc)
    age_hours = (now - started).total_seconds() / 3600
    if age_hours < IOS_PHASED_JUMP_HOURS:
        return False, f"phased rollout is {age_hours:.1f}h old (< {IOS_PHASED_JUMP_HOURS:g}h observation window)"
    hold = capture_health_hold("ios", build=ios_version_build_number(live_version_id))
    if hold:
        return False, f"phased rollout is {age_hours:.1f}h old; held on capture health: {hold}"
    return True, f"phased rollout is {age_hours:.1f}h old; releasing to everyone"


def _complete_phased_release(live_version_id: str) -> None:
    """Release to everyone: PATCH the live version's phased rollout to COMPLETE.

    Apple's jump is an update of the appStoreVersionPhasedReleases resource by its
    own id; DELETE on that resource only cancels a rollout that has not started,
    and the version's relationship path answers DELETE with 405 (seen live
    2026-10-18 on 1.0.564). The response is read back so a 200 that did not take
    is still a failure.
    """
    phased = ios_phased_release(live_version_id)
    if phased is None or not isinstance(phased.get("id"), str):
        raise TrainError(f"App Store Connect phased release for {live_version_id} has no readable id")
    phased_id = phased["id"]
    token = _asc_rest_token()
    url = f"https://api.appstoreconnect.apple.com/v1/appStoreVersionPhasedReleases/{phased_id}"
    body = json.dumps(
        {
            "data": {
                "type": "appStoreVersionPhasedReleases",
                "id": phased_id,
                "attributes": {"phasedReleaseState": "COMPLETE"},
            }
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="PATCH",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise TrainError(
            f"App Store Connect phased-release complete failed for {live_version_id}: HTTP {exc.code}"
        ) from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise TrainError(f"App Store Connect phased-release complete failed for {live_version_id}: {exc}") from exc
    data = payload.get("data") if isinstance(payload, dict) else None
    state = _attributes(data).get("phasedReleaseState") if isinstance(data, dict) else None
    if state != "COMPLETE":
        raise TrainError(f"phased-release complete for {live_version_id} read back state {state!r}, not COMPLETE")


def _release_approved_version(version_id: str, version: str) -> None:
    """Developer-release an approved-but-unreleased (PENDING_DEVELOPER_RELEASE) version.

    POST /v1/appStoreVersionReleaseRequests ("manually release an approved
    version"; verified live 2026-10-17 on 1.0.564 after its COMPLETE review
    submission had blocked every cancel-based path). Apple documents this as
    irrevocable, so it is only called when the phased rollout is confirmed
    attached (day 1 = 1% exposure) — the brake stays available after release.
    """
    token = _asc_rest_token()
    url = "https://api.appstoreconnect.apple.com/v1/appStoreVersionReleaseRequests"
    body = json.dumps(
        {
            "data": {
                "type": "appStoreVersionReleaseRequests",
                "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}}},
            }
        }
    ).encode()
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 201:
                raise TrainError(f"release request for {version}: unexpected HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.load(exc)
            detail = str(payload.get("errors", [{}])[0].get("detail", ""))[:300]
        except Exception:
            pass
        raise TrainError(f"App Store Connect release request failed for {version}: HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise TrainError(f"App Store Connect release request failed for {version}: {exc}") from exc


def _attach_phased_release(version_id: str) -> None:
    """Enable the automatic phased rollout on a not-yet-released version (day 1 = 1%)."""
    token = _asc_rest_token()
    url = "https://api.appstoreconnect.apple.com/v1/appStoreVersionPhasedReleases"
    body = json.dumps(
        {
            "data": {
                "type": "appStoreVersionPhasedReleases",
                "attributes": {"phasedReleaseState": "ACTIVE"},
                "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": version_id}}},
            }
        }
    ).encode()
    request = urllib.request.Request(
        url, data=body, method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status != 201:
                raise TrainError(f"phased-release create for {version_id}: unexpected HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.load(exc)
            detail = str(payload.get("errors", [{}])[0].get("detail", ""))[:300]
        except Exception:
            pass
        raise TrainError(f"App Store Connect phased-release create failed for {version_id}: HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, ValueError) as exc:
        raise TrainError(f"App Store Connect phased-release create failed for {version_id}: {exc}") from exc


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


_PEM_BLOCK = re.compile(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END \1-----", re.DOTALL)


def _normalize_pem(raw: str) -> str:
    """Rebuild a well-formed PEM from the key text CI hands us.

    Codemagic's publishing CLI accepts the integration key in shapes neither
    cryptography nor `openssl dgst` will parse: newlines escaped as a literal
    backslash-n, folded to spaces, surrounding quotes, or a bare base64 body
    with no armor. Re-armor whatever is there as 64-column PKCS#8 PEM.
    """
    text = raw.strip().strip("\"'").replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
    match = _PEM_BLOCK.search(text)
    if match is None:
        # A whole .p8 file base64-encoded once more (a common way to store it in CI).
        try:
            decoded = base64.b64decode(re.sub(r"\s+", "", text), validate=True).decode("ascii")
        except (ValueError, UnicodeDecodeError):
            decoded = ""
        if "-----BEGIN" in decoded:
            return _normalize_pem(decoded)
    label, body = (match.group(1), match.group(2)) if match else ("PRIVATE KEY", text)
    body = re.sub(r"\s+", "", body)
    if not body or not re.fullmatch(r"[A-Za-z0-9+/=]+", body):
        raise TrainError("App Store Connect private key is not PEM or base64 (shape: " + _pem_shape(raw) + ")")
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"


def _resolve_key_ref(raw: str) -> str:
    """Follow a Codemagic CLI key reference to the key itself.

    The codemagic_v4 integration sets APP_STORE_CONNECT_PRIVATE_KEY to a
    reference, not key text: `@file:<path>` or `@env:<VAR>` (the convention of
    codemagic-cli-tools, which the publishing step resolves). Seen live
    2026-10-15 as a 72-character single-line value.
    """
    value = raw.strip()
    if value.startswith("@file:"):
        path = os.path.expanduser(value[len("@file:") :])
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError as exc:
            raise TrainError(f"App Store Connect key reference @file: is unreadable ({type(exc).__name__})") from exc
    if value.startswith("@env:"):
        name = value[len("@env:") :]
        resolved = os.environ.get(name, "")
        if not resolved:
            raise TrainError(f"App Store Connect key reference @env:{name} is empty")
        return _resolve_key_ref(resolved)
    return raw


def _pem_shape(raw: str) -> str:
    """Non-secret description of the key text, for a diagnosable failure line."""
    armored = "-----BEGIN" in raw
    newlines = raw.count(chr(10))
    escaped = raw.count(chr(92) + "n")
    quoted = raw[:1] in ('"', "'")
    ref = next((scheme for scheme in ("@file", "@env") if raw.strip().startswith(scheme + ":")), "none")
    return (
        f"len={len(raw)} ref={ref} armored={armored} newlines={newlines} "
        f"escaped_newlines={escaped} quoted={quoted}"
    )


def _asc_rest_token() -> str:
    """ES256 JWT for the App Store Connect REST API (kid must be a JWT header)."""
    import base64

    issuer = os.environ.get("APP_STORE_CONNECT_ISSUER_ID", "")
    key_id = os.environ.get("APP_STORE_CONNECT_KEY_IDENTIFIER", "")
    pem = os.environ.get("APP_STORE_CONNECT_PRIVATE_KEY", "")
    if not (issuer and key_id and pem):
        raise TrainError("missing App Store Connect credential for REST lookup")
    log(f"App Store Connect key text: {_pem_shape(pem)}")
    pem = _normalize_pem(_resolve_key_ref(pem))
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    now = int(time.time())
    claims = {"iss": issuer, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"}
    encode = lambda obj: base64.urlsafe_b64encode(
        json.dumps(obj, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    signing_input = f"{encode(header)}.{encode(claims)}"
    der = None
    # The cryptography path fails in more ways than ImportError: some CI
    # OpenSSL builds deserialize the import and then reject Apple's p8 EC
    # container at key-load time (unsupported key type / explicit EC
    # parameters). Any failure there must fall through to the openssl CLI,
    # which signs these keys fine — the Codemagic publishing steps use the
    # same key material successfully on the same machine.
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        key = load_pem_private_key(pem.encode(), password=None)
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes

        der = key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
    except Exception as exc:
        log(f"cryptography could not load/sign the App Store Connect key ({type(exc).__name__}); falling back to openssl CLI")
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
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as cli_exc:
            stderr = getattr(cli_exc, "stderr", b"") or b""
            detail = stderr.decode("utf-8", "replace").strip().splitlines()[:3] if isinstance(stderr, bytes) else []
            raise TrainError(
                f"could not sign the App Store Connect REST token (cryptography: {exc}; openssl: {cli_exc} {detail})"
            ) from cli_exc
        finally:
            os.unlink(key_file.name)
            os.unlink(data_file.name)
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


def _live_version_id(asc: Callable[..., object], state: IOSState) -> str:
    return next(v.id for v in ios_versions_in_state(asc, LIVE_STATE) if v.version == state.live_version)


def run_ios(*, dry_run: bool, release_date: str, advance_only: bool = False, asc: Callable[..., object] = asc_json) -> str:
    for name in ("APP_STORE_CONNECT_ISSUER_ID", "APP_STORE_CONNECT_KEY_IDENTIFIER", "APP_STORE_CONNECT_PRIVATE_KEY"):
        if not os.environ.get(name):
            raise TrainError(f"missing App Store Connect credential: {name}")
    pin = store_pin("TRAIN_PIN_IOS")
    state = fetch_ios_state(asc)
    plan = plan_ios(state)
    log(f"iOS live {state.live_version}; plan={plan.action}: {plan.reason}")
    live_id = _live_version_id(asc, state)
    jump_note = "phased release disabled"
    if PHASED_RELEASE:
        should_complete, jump_reason = ios_phased_release_should_complete(live_id)
        log(f"live phased rollout check: {jump_reason}")
        jump_note = jump_reason
        if should_complete:
            if dry_run:
                log("DRY RUN: would complete the live phased rollout (release to everyone)")
                jump_note = "would release to everyone now (dry run)"
            else:
                _complete_phased_release(live_id)
                log("released the live phased rollout to everyone (jump to 100%)")
                jump_note = "released to everyone (jump to 100%)"
    if advance_only:
        return f"ios=advance ({jump_note})"
    if plan.submit is None:
        pending = state.pending[0] if state.pending else None
        if pending is not None and plan.action in ("blocked", "leave") and PHASED_RELEASE:
            if ios_phased_release_paused(live_id):
                return (
                    f"ios=hold (live {state.live_version} phased rollout is PAUSED — the operator brake; "
                    f"releasing approved {pending.version} is deferred until it is resumed)"
                )
            if dry_run:
                return (
                    f"ios=dry-run:release-approved {pending.version} "
                    "(attach the phased rollout, then POST appStoreVersionReleaseRequests)"
                )
            try:
                _attach_phased_release(pending.id)
            except TrainError as exc:
                # Same read-back as the submit path: this train's own submit
                # already attached the phased rollout (or a retry follows an
                # attach that landed before the release request failed), so
                # Apple rejects the duplicate. Release only when a phased
                # rollout is confirmed attached; otherwise keep failing closed.
                if ios_phased_release(pending.id) is None:
                    raise TrainError(f"phased rollout is not attached to approved {pending.version}: {exc}") from exc
                log(f"phased rollout already attached to {pending.version}; the create was rejected as a duplicate")
            _release_approved_version(pending.id, pending.version)
            log(f"released approved {pending.version} with the phased rollout attached (day 1 = 1%)")
            return f"ios={plan.action}: released approved {pending.version} (phased rollout attached)"
        return f"ios={plan.action} ({plan.reason})"
    candidate = plan.submit
    if pin is not None and not pin.matches(candidate.version, str(candidate.build_number)):
        # The operator gate's audited verdict covers this platform: either a
        # pinned build that no longer matches, or an audited no-candidate that
        # the store has since contradicted. A build appearing in the
        # audit→dispatch gap is unaudited; fail closed instead of
        # self-driving it to production.
        raise TrainError(
            f"TRAIN_PIN_IOS {'none' if pin.is_none else f'{pin.version}/{pin.build}'} does not match the selected "
            f"candidate {candidate.version}/{candidate.build_number}; refusing to release an unaudited build"
        )
    if PHASED_RELEASE and ios_phased_release_paused(live_id):
        # The operator paused the live version's phased rollout in App Store
        # Connect — the documented post-release brake. Hold the whole iOS
        # train while the brake is on: submitting the candidate now would
        # release it on approval regardless of the pause.
        return (
            f"ios=hold (live {state.live_version} phased rollout is PAUSED — the operator brake; "
            f"resume it in App Store Connect to continue)"
        )
    release_path = ensure_release_notes(candidate.version, release_date, write=not dry_run)
    notes = promote.require_notes(release_path, candidate.version, "ios") if release_path.is_file() else "<collected at run time>"
    locales = ios_live_locales(asc, live_id)
    if dry_run:
        log(f"DRY RUN: would submit build {candidate.build_number} ({candidate.version}) with notes for {len(locales)} locales")
        return f"ios=dry-run:{plan.action} {candidate.version} ({candidate.build_number})"
    build = promote.IOSBuild(candidate.build_id, candidate.version, str(candidate.build_number))
    try:
        promote.submit_ios(build, notes, locales=locales, release_type=RELEASE_TYPE, phased=PHASED_RELEASE)
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    version_id = ios_build_version_id(asc, candidate.build_id)
    if version_id is None:
        raise TrainError("submission returned but the build is not attached to an App Store version")
    wait_for_version_state(asc, version_id, "WAITING_FOR_REVIEW")
    phased_note = ""
    if PHASED_RELEASE:
        try:
            _attach_phased_release(version_id)
        except TrainError as exc:
            # The submission itself succeeded; a duplicate-phased rejection is
            # fine as long as a phased rollout is really attached — the jump
            # logic and the pause brake both depend on it existing.
            if ios_phased_release(version_id) is None:
                raise TrainError(f"phased rollout is not attached to {candidate.version}: {exc}") from exc
            log("phased rollout already attached; the create was rejected as a duplicate")
        phased_note = " (phased rollout attached; day 1 = 1%)"
    posture = RELEASE_TYPE + ("/phased" if PHASED_RELEASE else "")
    log(f"submitted {candidate.version} ({candidate.build_number}) for review; release type {posture}")
    return f"ios={plan.action} {candidate.version} ({candidate.build_number}) WAITING_FOR_REVIEW ({posture}){phased_note}"


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


def _staged_name_with_receipt(version: str) -> str:
    """Play release name carrying the minute-precision gate receipt for this run."""
    return f"{version} (gate {datetime.now(timezone.utc).strftime('%Y-%m-%d-%H%M')})"


def run_android(*, dry_run: bool, release_date: str, advance_only: bool = False) -> str:
    pin = store_pin("TRAIN_PIN_ANDROID")
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
        if promote.CHANGES_NOT_SENT_FOR_REVIEW:
            # Held-changes mode: every hop would commit held (queued in Play's
            # Publishing overview, invisible to this API), so the train cannot
            # know the previous hop is live. Hopping blind stacks held hops and
            # a single Send-for-review press would then release full exposure
            # with no observation windows. Park the ladder: the operator sends
            # each held change for review and advances exposure in Play Console
            # until Play again accepts automated review submission (see
            # .github/agent-docs/mobile-release-process.md).
            log(
                f"Android production staged {staged_version} {codes[0]} @{current:.0%} parked: Play holds "
                f"committed changes for manual review submission; a human sends them and advances "
                f"exposure in Play Console"
            )
            return (
                f"android=staged {staged_version} {codes[0]} @{current:.0%} "
                f"parked (held-changes mode; manual review submission)"
            )
        receipt = _gate_receipt_dt(str(staged.get("name") or ""))
        now = datetime.now(timezone.utc)
        if receipt is None:
            # No receipt means no proof of when this fraction was reached: a
            # rollout started before receipts existed, or a name edited in Play
            # Console. Hopping now could expand exposure minutes after the last
            # step, so fail closed: stamp a receipt at the current fraction
            # (no exposure change) and let the next advance after the
            # observation window take the hop.
            log(
                f"Android production staged {staged_version} {codes[0]} at {current:.0%} has no gate receipt; "
                f"stamping one and holding for the {ROLLOUT_HOP_MIN_HOURS:g}h observation window"
            )
            try:
                notes = _staged_release_notes(staged) or promote.require_notes(
                    ensure_release_notes(staged_version, release_date, write=False), staged_version, "android"
                )
            except promote.PromotionError as exc:
                raise TrainError(f"staged {staged_version} has no usable What's-New text: {exc}") from exc
            if dry_run:
                return f"android=dry-run:staged-stamp {staged_version} {codes[0]} @{current:.0%} (no gate receipt; would stamp and hold)"
            try:
                promote.submit_android(
                    client,
                    edit_id,
                    staged_version,
                    codes[0],
                    notes,
                    status="inProgress",
                    user_fraction=current,
                    extra_codes=codes[1:],
                    base_release=staged,
                    release_name=_staged_name_with_receipt(staged_version),
                )
            except promote.PromotionError as exc:
                raise TrainError(str(exc)) from exc
            return (
                f"android=staged {staged_version} {codes[0]} @{current:.0%} "
                f"(no gate receipt; stamped, holding {ROLLOUT_HOP_MIN_HOURS:g}h)"
            )
        age_hours = (now - receipt).total_seconds() / 3600
        if age_hours < ROLLOUT_HOP_MIN_HOURS:
            # This rollout was advanced inside its observation window
            # (today's gate, or a same-day retry of a train whose other
            # platform failed — main() runs both platforms before exiting
            # nonzero). One advancing action per window keeps the exposure
            # ladder's observation gap real.
            log(
                f"Android production staged {staged_version} {codes[0]} was advanced "
                f"{age_hours:.1f}h ago; holding at {current:.0%} until the "
                f"{ROLLOUT_HOP_MIN_HOURS:g}h observation window closes"
            )
            return (
                f"android=staged {staged_version} {codes[0]} @{current:.0%} "
                f"(advanced {age_hours:.1f}h ago; window {ROLLOUT_HOP_MIN_HOURS:g}h)"
            )
        log(f"Android staged {staged_version} last advanced {age_hours:.1f}h ago; window has closed")
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
        hold = capture_health_hold("android", build=codes[0])
        if hold:
            return f"android=staged {staged_version} {codes[0]} @{current:.0%} held on capture health ({hold})"
        next_hops = [hop for hop in STAGED_ROLLOUT_LADDER if hop > current + 1e-9]
        if not next_hops:
            log(f"Android production staged {staged_version} at {current:.0%} is at or past the ladder top; nothing to do")
            return f"android=staged {staged_version} {codes[0]} @{current:.0%} (ladder done)"
        hop = next_hops[0]
        log(f"Android live {live}; promoting staged {staged_version} {codes[0]} from {current:.0%} to {hop:.0%}")
        # The staged rollout shipped its What's-New text when it started. Re-use the
        # exact text Play already holds, falling back to the durable release
        # file WITHOUT collecting: collect() would fold the NEXT version's
        # unreleased fragments into this in-flight version and consume them.
        # Resolved before the dry-run return so a plan reports a hop only
        # when the real run could actually take it. The file must exist here:
        # require_notes raises PromotionError (not TrainError), which main()
        # does not catch — a missing staged release file must surface as a
        # failed platform in TRAIN SUMMARY, not a traceback.
        try:
            notes = _staged_release_notes(staged) or promote.require_notes(
                ensure_release_notes(staged_version, release_date, write=False), staged_version, "android"
            )
        except promote.PromotionError as exc:
            raise TrainError(f"staged {staged_version} has no usable What's-New text: {exc}") from exc
        if dry_run:
            return f"android=dry-run:staged-hop {staged_version} {codes[0]} {current:.0%}->{hop:.0%}"
        try:
            if hop >= 1.0:
                promote.submit_android(
                    client,
                    edit_id,
                    staged_version,
                    codes[0],
                    notes,
                    status="completed",
                    extra_codes=codes[1:],
                    base_release=staged,
                    release_name=_staged_name_with_receipt(staged_version),
                )
            else:
                promote.submit_android(
                    client,
                    edit_id,
                    staged_version,
                    codes[0],
                    notes,
                    status="inProgress",
                    user_fraction=hop,
                    extra_codes=codes[1:],
                    base_release=staged,
                    release_name=_staged_name_with_receipt(staged_version),
                )
        except promote.PromotionError as exc:
            raise TrainError(str(exc)) from exc
        if hop >= 1.0:
            log(f"Android production rollout completed: {staged_version} {codes[0]} at 100%")
            return f"android=completed {staged_version} {codes[0]} 100%"
        log(f"Android production staged now {staged_version} {codes[0]} at {hop:.0%}")
        return f"android=staged {staged_version} {codes[0]} @{hop:.0%}"
    if advance_only:
        # The advance mode only moves a rollout that is already in flight.
        # Starting one from a candidate is the daily gate's audited job: with
        # no staged release, falling through would put an unaudited build at
        # 1% of production (the watch passes no pin).
        waiting = f"; candidate {candidate.version} ({candidate.version_code}) waits for the gate" if candidate else ""
        log(f"Android live {live}; no staged rollout in flight{waiting}")
        return f"android=advance (no staged rollout in flight{waiting})"
    if candidate is None:
        if pin is not None and not pin.is_none:
            # The gate pinned an audited build the store no longer offers;
            # failing closed beats silently skipping it.
            raise TrainError(
                f"TRAIN_PIN_ANDROID {pin.version}/{pin.build} but no internal/alpha build is newer than live "
                f"{live}; refusing to select an unaudited candidate"
            )
        log(f"Android live {live}; no internal/alpha build is newer")
        return f"android=nothing (live {live})"
    if pin is not None and not pin.matches(candidate.version, candidate.version_code):
        # Same fail-closed rule as iOS: the gate's audited verdict (a pinned
        # build, or an audited no-candidate) must still match the store; a
        # newer internal build that appeared after the audit must not be
        # self-driven to production.
        raise TrainError(
            f"TRAIN_PIN_ANDROID {'none' if pin.is_none else f'{pin.version}/{pin.build}'} does not match the selected "
            f"candidate {candidate.version}/{candidate.version_code}; refusing to release an unaudited build"
        )
    draft = existing_production_draft(production)
    draft_codes = promote.release_codes(draft) if draft is not None else None
    if draft is not None and draft_codes == [candidate.version_code]:
        if STAGED_ROLLOUT_FRACTION is None:
            log(f"Android production draft already carries {candidate.version} ({candidate.version_code})")
            return f"android=leave draft {candidate.version} ({candidate.version_code})"
        # A legacy queue-for-human train left the selected code sitting in
        # a Play draft. In staged posture the same code converts straight
        # into the 1% rollout (the track PUT replaces the draft) instead
        # of being idempotently re-left for a human on every run.
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
                release_name=_staged_name_with_receipt(candidate.version),
            )
        else:
            promote.submit_android(client, edit_id, candidate.version, candidate.version_code, notes, status="draft")
    except promote.PromotionError as exc:
        raise TrainError(str(exc)) from exc
    if STAGED_ROLLOUT_FRACTION is not None:
        if promote.CHANGES_NOT_SENT_FOR_REVIEW:
            log(
                f"Android production staged rollout started: {candidate.version} ({candidate.version_code}) "
                f"at {STAGED_ROLLOUT_FRACTION:.0%}; held for review submission — send it from Play Console "
                f"-> Publishing overview; haltable in Play Console"
            )
            return (
                f"android=staged {candidate.version} ({candidate.version_code}) "
                f"@{STAGED_ROLLOUT_FRACTION:.0%} (held; send for review in Play Console)"
            )
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
    parser.add_argument(
        "--advance-rollouts",
        action="store_true",
        help=(
            "Intraday exposure-ladder mode: never submit or stage a candidate; only advance the "
            "already-released rollouts (iOS phased jump after IOS_PHASED_JUMP_HOURS, Android ladder hop "
            "after ROLLOUT_HOP_MIN_HOURS). Used by the mobile_rollout_watch.yml schedule between gate runs."
        ),
    )
    args = parser.parse_args(argv)
    advance_only = args.advance_rollouts or str(os.environ.get("TRAIN_ADVANCE_ROLLOUTS", "")).strip().lower() == "true"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("--date must be YYYY-MM-DD")
    summaries = []
    failures = []
    for platform, runner in (("ios", run_ios), ("android", run_android)):
        if args.platform not in (platform, "both"):
            continue
        try:
            summaries.append(
                runner(dry_run=args.dry_run, release_date=args.date, advance_only=advance_only)
            )
        except TrainError as exc:
            log(f"FAIL {platform}: {exc}")
            failures.append(f"{platform}=FAILED")
    print("TRAIN SUMMARY: " + " ".join(summaries + failures), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
