#!/usr/bin/env python3
"""Promote a specifically identified, already-uploaded mobile build to store review."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

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

        spec = spec_from_file_location("mobile_changelog", Path(__file__).resolve().parents[2] / ".github/scripts/mobile-changelog.py")
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
    request = urllib.request.Request(f"https://itunes.apple.com/lookup?id={APP_ID}", headers={"Accept": "application/json"})
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
        "builds", "list", "--app-id", APP_ID, "--platform", "IOS", "--pre-release-version", version,
        "--build-version-number", build_number,
    )
    selected = select_ios_build(builds, version, build_number)
    prerelease = cli_json("builds", "pre-release-version", selected.id)
    attrs = prerelease.get("attributes", prerelease) if isinstance(prerelease, dict) else None
    if not isinstance(attrs, dict) or attrs.get("version") != version:
        raise PromotionError("iOS build marketing version does not match PROMOTE_VERSION")
    return selected


def submit_ios(build: IOSBuild, notes: str) -> None:
    command = [
        "app-store-connect", "builds", "submit-to-app-store", "--max-build-processing-wait", "0",
        "--platform", "IOS", "--release-type", "MANUAL", "--version-string", build.version,
        "--whats-new", notes, build.id,
    ]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise PromotionError("App Store Connect rejected the selected build for review") from exc


def release_codes(release: dict[str, object]) -> list[str]:
    codes = release.get("versionCodes")
    if not isinstance(codes, list) or not codes or any(not BUILD_RE.fullmatch(str(code)) for code in codes):
        raise PromotionError("Play track contains invalid version codes")
    return [str(code) for code in codes]


def select_play_release(alpha: object, production: object, version: str, build_number: str) -> None:
    if not isinstance(alpha, dict) or alpha.get("track") != "alpha":
        raise PromotionError("Play alpha track lookup failed")
    if not isinstance(production, dict) or production.get("track") != "production":
        raise PromotionError("Play production track lookup failed")
    alpha_releases = alpha.get("releases", [])
    production_releases = production.get("releases", [])
    if not isinstance(alpha_releases, list) or not isinstance(production_releases, list):
        raise PromotionError("Play track releases are invalid")
    matches = []
    for release in alpha_releases:
        if not isinstance(release, dict):
            raise PromotionError("Play alpha release is invalid")
        codes = release_codes(release)
        if build_number in codes:
            if codes != [build_number] or release.get("name") != version or release.get("status") not in ("completed", "inProgress"):
                raise PromotionError("Play alpha build does not match the exact version and code")
            matches.append(release)
    if len(matches) != 1:
        raise PromotionError("Play alpha track has no unique matching build")
    for release in production_releases:
        if not isinstance(release, dict) or not isinstance(release.get("name"), str):
            raise PromotionError("Play public release lacks a marketing version")
        release_codes(release)
        if version_parts(version) < version_parts(release["name"]):
            raise PromotionError("Android target is older than the live public version")


def prepare_android(version: str, build_number: str) -> tuple[object, str]:
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
        alpha = client.edits().tracks().get(packageName=PACKAGE_NAME, editId=edit_id, track="alpha").execute()
        production = client.edits().tracks().get(packageName=PACKAGE_NAME, editId=edit_id, track="production").execute()
    except Exception as exc:
        raise PromotionError("Google Play track lookup or authentication failed") from exc
    select_play_release(alpha, production, version, build_number)
    return client, edit_id


def submit_android(client: object, edit_id: str, version: str, build_number: str, notes: str) -> None:
    release = {
        "name": version,
        "versionCodes": [build_number],
        "status": "completed",
        "releaseNotes": [{"language": "en-US", "text": notes}],
    }
    try:
        client.edits().tracks().update(
            packageName=PACKAGE_NAME, editId=edit_id, track="production",
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
