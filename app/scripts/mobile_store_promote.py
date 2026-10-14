#!/usr/bin/env python3
"""Promote a specifically identified, already-uploaded mobile build to store review."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

APP_ID = "6502156163"
PACKAGE_NAME = "com.friend.ios"
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
BUILD_RE = re.compile(r"^[1-9][0-9]*$")


class PromotionError(ValueError):
    pass


@dataclass(frozen=True)
class IOSBuild:
    id: str
    version: str
    build_number: str


def version_parts(version: str) -> tuple[int, int, int]:
    if not VERSION_RE.fullmatch(version):
        raise PromotionError("marketing version must be strict X.Y.Z")
    return tuple(int(part) for part in version.split("."))


def require_build(value: str | None, label: str) -> str:
    if value is None or not BUILD_RE.fullmatch(value):
        raise PromotionError(f"{label} must be a positive integer")
    return value


def require_notes(path: Path, version: str, platform: str) -> str:
    if not path.is_file():
        raise PromotionError(f"release notes file is missing: {path}")
    try:
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "mobile_changelog", Path(__file__).resolve().parents[2] / ".github/scripts/mobile-changelog.py"
        )
        if spec is None or spec.loader is None:
            raise PromotionError("mobile changelog tooling unavailable")
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        notes = module.store_notes(version, platform)
    except (ValueError, OSError) as exc:
        raise PromotionError(f"release notes are invalid: {exc}") from exc
    if not isinstance(notes, str) or not notes.strip():
        raise PromotionError("release notes must not be empty")
    limit = 4000 if platform == "ios" else 500
    if len(notes) > limit:
        raise PromotionError("store notes exceed the platform character limit")
    return notes


def check_live_ios_version(version: str) -> None:
    request = urllib.request.Request(
        f"https://itunes.apple.com/lookup?id={APP_ID}", headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            listing = json.load(response)
    except (OSError, ValueError) as exc:
        raise PromotionError("iTunes public-version lookup failed") from exc
    if not isinstance(listing, dict):
        raise PromotionError("iTunes public-version lookup returned an invalid listing")
    results = listing.get("results")
    if listing.get("resultCount") != 1 or not isinstance(results, list) or len(results) != 1:
        raise PromotionError("iTunes public-version lookup returned no unique listing")
    live = results[0]
    if not isinstance(live, dict) or str(live.get("trackId")) != APP_ID:
        raise PromotionError("iTunes listing does not match the iOS app")
    if version_parts(version) < version_parts(live.get("version", "")):
        raise PromotionError("iOS target is older than the live public version")


def cli_json(*args: str) -> object:
    command = ["app-store-connect", *args, "--json"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, ValueError) as exc:
        raise PromotionError("App Store Connect build lookup failed") from exc


def select_ios_build(payload: object, version: str, build_number: str) -> IOSBuild:
    builds = payload.get("data", payload.get("builds")) if isinstance(payload, dict) else payload
    if not isinstance(builds, list):
        raise PromotionError("App Store Connect returned an invalid build list")
    matches = []
    for build in builds:
        if not isinstance(build, dict):
            raise PromotionError("App Store Connect returned an invalid build")
        attrs = build.get("attributes", build)
        if not isinstance(attrs, dict):
            raise PromotionError("App Store Connect returned an invalid build")
        if str(attrs.get("version")) != build_number:
            continue
        state = attrs.get("processingState", attrs.get("processing_state"))
        if state != "VALID" or attrs.get("expired", False):
            raise PromotionError("iOS build is processing, invalid or expired")
        build_id = build.get("id")
        if not isinstance(build_id, str) or not build_id:
            raise PromotionError("iOS build has no App Store Connect ID")
        matches.append(IOSBuild(build_id, version, build_number))
    if len(matches) != 1:
        raise PromotionError("iOS build/version did not resolve to exactly one valid build")
    return matches[0]


def prepare_ios(version: str, build_number: str) -> IOSBuild:
    for name in ("APP_STORE_CONNECT_ISSUER_ID", "APP_STORE_CONNECT_KEY_IDENTIFIER", "APP_STORE_CONNECT_PRIVATE_KEY"):
        if not os.environ.get(name):
            raise PromotionError(f"missing Codemagic iOS integration credential: {name}")
    check_live_ios_version(version)
    builds = cli_json(
        "builds",
        "list",
        "--app-id",
        APP_ID,
        "--platform",
        "IOS",
        "--pre-release-version",
        version,
        "--build-version-number",
        build_number,
    )
    selected = select_ios_build(builds, version, build_number)
    prerelease = cli_json("builds", "pre-release-version", selected.id)
    attrs = prerelease.get("attributes", prerelease) if isinstance(prerelease, dict) else None
    if not isinstance(attrs, dict) or attrs.get("version") != version:
        raise PromotionError("iOS build marketing version does not match PROMOTE_VERSION")
    return selected


def ios_localizations(locales: Sequence[str], notes: str) -> list[dict[str, str]]:
    """What's New for every App Store locale; Apple rejects a submission when any locale lacks it."""
    unique = sorted(set(locales))
    if not unique or any(not isinstance(locale, str) or not locale for locale in unique):
        raise PromotionError("App Store locales must be a non-empty list of locale codes")
    return [{"locale": locale, "whats_new": notes} for locale in unique]


def submit_ios(
    build: IOSBuild,
    notes: str,
    *,
    locales: Sequence[str] | None = None,
    release_type: str = "MANUAL",
    phased: bool = False,
) -> None:
    """Submit a processed build for review.

    release_type MANUAL holds the approved version for an explicit developer
    release command (App Store Connect has no API to issue that command, so
    MANUAL versions pile up approved-but-unreleased); AFTER_APPROVAL lets
    Apple release on approval. phased=True (AFTER_APPROVAL only) requests the
    7-day automatic phased rollout, which is pausable from App Store Connect
    as a post-release brake.
    """
    if release_type not in ("MANUAL", "AFTER_APPROVAL"):
        raise PromotionError("iOS release type must be MANUAL or AFTER_APPROVAL")
    if phased and release_type != "AFTER_APPROVAL":
        raise PromotionError("phased release requires release type AFTER_APPROVAL")
    command = [
        "app-store-connect",
        "builds",
        "submit-to-app-store",
        "--max-build-processing-wait",
        "0",
        "--platform",
        "IOS",
        "--release-type",
        release_type,
        "--version-string",
        build.version,
    ]
    localizations_file: Path | None = None
    if locales is None:
        command += ["--whats-new", notes]
    else:
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        with handle:
            json.dump(ios_localizations(locales, notes), handle)
        localizations_file = Path(handle.name)
        command += ["--app-store-version-localizations", f"@file:{localizations_file}"]
    command += ["--phased-release"] if phased else ["--no-phased-release"]
    command.append(build.id)
    try:
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise PromotionError("App Store Connect rejected the selected build for review") from exc
    finally:
        if localizations_file is not None:
            localizations_file.unlink(missing_ok=True)


def release_codes(release: dict[str, object]) -> list[str]:
    codes = release.get("versionCodes")
    if not isinstance(codes, list) or not codes or any(not BUILD_RE.fullmatch(str(code)) for code in codes):
        raise PromotionError("Play track contains invalid version codes")
    return [str(code) for code in codes]


def select_play_release(
    source: object, production: object, version: str, build_number: str, *, source_track: str = "alpha"
) -> None:
    if not isinstance(source, dict) or source.get("track") != source_track:
        raise PromotionError(f"Play {source_track} track lookup failed")
    if not isinstance(production, dict) or production.get("track") != "production":
        raise PromotionError("Play production track lookup failed")
    source_releases = source.get("releases", [])
    production_releases = production.get("releases", [])
    if not isinstance(source_releases, list) or not isinstance(production_releases, list):
        raise PromotionError("Play track releases are invalid")
    matches = []
    for release in source_releases:
        if not isinstance(release, dict):
            raise PromotionError(f"Play {source_track} release is invalid")
        codes = release_codes(release)
        if build_number in codes:
            name = release.get("name")
            if (
                codes != [build_number]
                or not isinstance(name, str)
                or production_release_version(name) != version
                or release.get("status") not in ("completed", "inProgress")
            ):
                raise PromotionError(f"Play {source_track} build does not match the exact version and code")
            matches.append(release)
    if len(matches) != 1:
        raise PromotionError(f"Play {source_track} track has no unique matching build")
    for release in production_releases:
        if not isinstance(release, dict) or not isinstance(release.get("name"), str):
            raise PromotionError("Play public release lacks a marketing version")
        release_codes(release)
        live_version = production_release_version(release["name"])
        if live_version is not None and version_parts(version) < version_parts(live_version):
            raise PromotionError("Android target is older than the live public version")


PRODUCTION_NAME_VERSION_RE = re.compile(
    r"^\s*((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))(?:\s*\(.*\))?\s*$"
)


def production_release_version(name: str) -> str | None:
    """Return the X.Y.Z a Play production release name carries, if any.

    Play Console labels a production release by its build name and may suffix the
    version code ("1.0.552 (1246)"); older or hand-named releases may carry no
    version at all. Only a recognised version participates in the ordering check.
    """
    match = PRODUCTION_NAME_VERSION_RE.fullmatch(name)
    return match.group(1) if match else None


def play_edit() -> tuple[object, str]:
    """Authenticate with the Codemagic Google Play credentials and open an edit."""
    credentials_raw = os.environ.get("GCLOUD_SERVICE_ACCOUNT_CREDENTIALS")
    if not credentials_raw:
        raise PromotionError("missing Codemagic Google Play credentials")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(credentials_raw), scopes=["https://www.googleapis.com/auth/androidpublisher"]
        )
        client = build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)
        edit_id = client.edits().insert(packageName=PACKAGE_NAME, body={}).execute()["id"]
    except Exception as exc:
        raise PromotionError("Google Play authentication failed") from exc
    return client, edit_id


def play_track(client: object, edit_id: str, track: str) -> object:
    try:
        return client.edits().tracks().get(packageName=PACKAGE_NAME, editId=edit_id, track=track).execute()
    except Exception as exc:
        raise PromotionError(f"Google Play {track} track lookup failed") from exc


def prepare_android(version: str, build_number: str) -> tuple[object, str]:
    client, edit_id = play_edit()
    alpha = play_track(client, edit_id, "alpha")
    production = play_track(client, edit_id, "production")
    select_play_release(alpha, production, version, build_number)
    return client, edit_id


PLAY_RELEASE_STATUSES = ("completed", "draft", "inProgress", "halted")


def submit_android(
    client: object,
    edit_id: str,
    version: str,
    build_number: str,
    notes: str,
    *,
    status: str = "completed",
    user_fraction: float | None = None,
    extra_codes: Sequence[str] = (),
    base_release: dict[str, object] | None = None,
) -> None:
    """Write one production release for the given code(s).

    status "completed" = fully live; "draft" = Play Console draft; "inProgress"
    = staged rollout (with user_fraction, e.g. 0.05) that is haltable from the
    Play Console as a post-release brake. userFraction is rejected for
    completed/draft releases; a completed release cannot later be halted, so
    decide the exposure path before writing. extra_codes carries any
    additional versionCodes an existing in-flight release already had (a
    multi-APK rollout must not lose its variants when the track is rewritten).
    base_release is that existing server-returned release: advancing it keeps
    its metadata (countryTargeting, localized releaseNotes,
    inAppUpdatePriority, ...) and changes only name/codes/status/fraction —
    the derived single-locale notes are used only when it carries none.
    """
    if status not in PLAY_RELEASE_STATUSES:
        raise PromotionError("Play release status must be completed, draft, inProgress or halted")
    if user_fraction is not None and status not in ("inProgress", "halted"):
        raise PromotionError("userFraction requires a staged (inProgress) release")
    if status == "inProgress" and user_fraction is None:
        # fraction-less inProgress is the HALTED representation, not a writable
        # release; halting is an explicit Play Console (or halted) operation
        raise PromotionError("a staged (inProgress) release requires a userFraction")
    codes = [build_number, *extra_codes]
    if len(set(codes)) != len(codes):
        raise PromotionError("Play release version codes must be unique")
    existing_notes = base_release.get("releaseNotes") if isinstance(base_release, dict) else None
    preserved_notes = existing_notes if isinstance(existing_notes, list) and existing_notes else None
    release: dict[str, object] = dict(base_release) if isinstance(base_release, dict) else {}
    release["name"] = version
    release["versionCodes"] = codes
    release["status"] = status
    release["releaseNotes"] = preserved_notes if preserved_notes is not None else [
        {"language": "en-US", "text": notes}
    ]
    release.pop("userFraction", None)
    if status != "inProgress" and "countryTargeting" in release:
        # Google permits countryTargeting only on an inProgress release;
        # carrying it into a completion PUT makes tracks.update reject the
        # whole request and wedges the rollout at its final hop.
        release.pop("countryTargeting", None)
    if user_fraction is not None:
        if not 0 < float(user_fraction) < 1:
            raise PromotionError("userFraction must be strictly between 0 and 1 (full rollout is status=completed)")
        release["userFraction"] = float(user_fraction)
    try:
        client.edits().tracks().update(
            packageName=PACKAGE_NAME,
            editId=edit_id,
            track="production",
            body={"track": "production", "releases": [release]},
        ).execute()
        client.edits().commit(packageName=PACKAGE_NAME, editId=edit_id).execute()
    except Exception as exc:
        raise PromotionError("Google Play rejected exact-code promotion to production") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--platform", required=True, choices=("ios", "android", "both"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--ios-build")
    parser.add_argument("--android-build")
    args = parser.parse_args()
    try:
        if args.confirm != "submit-for-review":
            raise PromotionError("CONFIRM must be exactly submit-for-review")
        version_parts(args.version)
        ios = args.platform in ("ios", "both")
        android = args.platform in ("android", "both")
        if ios:
            require_build(args.ios_build, "PROMOTE_IOS_BUILD")
        elif args.ios_build:
            raise PromotionError("iOS build supplied for Android-only promotion")
        if android:
            require_build(args.android_build, "PROMOTE_ANDROID_BUILD")
        elif args.android_build:
            raise PromotionError("Android build supplied for iOS-only promotion")
        release = Path(__file__).resolve().parents[1] / "changelog/releases" / f"{args.version}.json"
        ios_notes = require_notes(release, args.version, "ios") if ios else ""
        android_notes = require_notes(release, args.version, "android") if android else ""
        ios_build = prepare_ios(args.version, args.ios_build) if ios else None
        android_target = prepare_android(args.version, args.android_build) if android else None
        if ios_build:
            submit_ios(ios_build, ios_notes)
        if android_target:
            submit_android(*android_target, args.version, args.android_build, android_notes)
    except PromotionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("Selected existing mobile build(s) submitted for store review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
