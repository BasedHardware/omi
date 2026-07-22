#!/usr/bin/env python3
"""Validate that a signed desktop candidate is eligible for automatic beta qualification."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from desktop_release_metadata import fail, parse_metadata

TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)\+(?P<build>\d+)-macos$")
EXPECTED_BUNDLE_ID = "com.omi.computer-macos"
EXPECTED_BETA_BUNDLE_ID = "com.omi.computer-macos.beta"
EXPECTED_TEAM_ID = "9536L8KLMP"
REQUIRED_SMOKE_CHECKS = {
    "Launch + identity metadata is aligned",
    "Auth persistence prerequisites: signing identity and Keychain-compatible entitlements are sane",
    "Backend routing config matches the declared external backend",
    "Sparkle/update metadata and authoritative ZIP artifacts are present",
    "Native helper/runtime bundle integrity passed",
    "Local storage/database package surface is present",
    "Signed artifact Keychain write/read/delete canary passed",
    "UserNotifications settings callback completion canary passed",
    "Signed desktop artifact smoke completed",
}


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def asset_by_name(release: dict, names: set[str]) -> dict:
    for asset in release.get("assets", []):
        if asset.get("name") in names:
            return asset
    fail(f"release is missing asset: {', '.join(sorted(names))}")


def smoke_artifact(smoke: dict, label: str) -> dict:
    for artifact in smoke.get("artifacts", []):
        if artifact.get("label") == label:
            return artifact
    fail(f"signed smoke result is missing {label!r} artifact evidence")


def normalized_digest(asset: dict) -> str:
    digest = str(asset.get("digest") or "")
    if not digest.startswith("sha256:"):
        fail(f"release asset {asset.get('name')!r} is missing a SHA-256 digest")
    return digest.removeprefix("sha256:")


def _validate_smoke_contract(
    smoke: dict,
    *,
    bundle_id: str,
    release_tag: str,
    expected_version: str,
    expected_build: str,
    label: str,
) -> set[str]:
    """Enforce the shared success/tag/version/build/team/channel contract on a
    smoke result. The beta artifact must satisfy the same bar as stable, only
    with its own bundle id."""
    expected = {
        "ok": True,
        "release_tag": release_tag,
        "expected_channel": "beta",
        "bundle_id": bundle_id,
        "version": expected_version,
        "build": expected_build,
        "team_id": EXPECTED_TEAM_ID,
    }
    for field, value in expected.items():
        if smoke.get(field) != value:
            fail(f"{label} smoke result {field} mismatch: expected {value!r}, got {smoke.get(field)!r}")

    checks = set(smoke.get("checks") or [])
    missing_checks = sorted(REQUIRED_SMOKE_CHECKS - checks)
    if missing_checks:
        fail(f"{label} smoke result is missing required checks: {', '.join(missing_checks)}")

    _validate_callback_canary(smoke, bundle_id=bundle_id, label=label)
    return checks


def _validate_callback_canary(smoke: dict, *, bundle_id: str, label: str) -> None:
    """The UserNotifications callback canary must run inside the exact artifact
    being qualified, so its recorded bundle id must match that artifact."""
    callback_canary = smoke.get("notification_callback_canary")
    if not isinstance(callback_canary, dict):
        fail(f"{label} smoke result is missing UserNotifications callback canary evidence")
    expected_callback_canary = {
        "schema": 1,
        "event": "user-notifications-settings-callback-completed",
        "bundle_id": bundle_id,
        "main_actor": True,
        "validated": True,
    }
    for field, value in expected_callback_canary.items():
        if callback_canary.get(field) != value:
            fail(
                f"{label} smoke UserNotifications callback canary "
                f"{field} mismatch: expected {value!r}, got {callback_canary.get(field)!r}"
            )
    if not isinstance(callback_canary.get("authorization_status"), int):
        fail(f"{label} smoke UserNotifications callback canary is missing authorization status")


def validate(args: argparse.Namespace) -> dict:
    match = TAG_RE.match(args.release_tag)
    if not match:
        fail(f"invalid macOS release tag: {args.release_tag}")
    if args.release_tag != args.latest_tag:
        fail(f"automatic beta qualification requires newest tag {args.latest_tag}, got {args.release_tag}")
    if args.tag_sha != args.checkout_sha:
        fail("release tag SHA does not match the Codemagic checkout SHA")

    release = load_json(args.release_json)
    smoke = load_json(args.smoke_result)
    smoke_source_sha = smoke.get("source_sha")
    if not isinstance(smoke_source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", smoke_source_sha):
        fail("signed smoke result is missing an exact source SHA")
    if smoke_source_sha != args.tag_sha:
        fail("signed smoke source SHA does not match the candidate tag")
    if release.get("tagName") != args.release_tag:
        fail("GitHub release tag does not match the requested candidate")
    if release.get("isDraft") or release.get("isPrerelease"):
        fail("automatic beta candidate must be a published non-prerelease GitHub release")
    if not release.get("publishedAt"):
        fail("automatic beta candidate must have a GitHub publication timestamp")

    metadata = parse_metadata(release.get("body") or "")
    if metadata.get("channel") != "candidate" or metadata.get("isLive", "").lower() not in {"false", "0", "no"}:
        fail("automatic beta qualification requires channel: candidate and isLive: false")
    expected_version = match.group("version")
    expected_build = match.group("build")
    checks = _validate_smoke_contract(
        smoke,
        bundle_id=EXPECTED_BUNDLE_ID,
        release_tag=args.release_tag,
        expected_version=expected_version,
        expected_build=expected_build,
        label="signed",
    )

    callback_canary = smoke.get("notification_callback_canary")

    zip_release = asset_by_name(release, {"Omi.zip"})
    dmg_release = asset_by_name(release, {"omi.dmg"})
    zip_smoke = smoke_artifact(smoke, "sparkle_zip")
    dmg_smoke = smoke_artifact(smoke, "dmg")
    artifact_digests = {
        "Omi.zip": normalized_digest(zip_release),
        dmg_release["name"]: normalized_digest(dmg_release),
    }
    if zip_smoke.get("sha256") != artifact_digests["Omi.zip"]:
        fail("published Omi.zip digest does not match the signed artifact smoke")
    if dmg_smoke.get("sha256") != artifact_digests[dmg_release["name"]]:
        fail("published DMG digest does not match the signed artifact smoke")

    # Releases that ship the side-by-side Omi Beta identity carry a second smoke
    # result; when those assets exist the beta artifact must satisfy the same
    # contract as stable (older releases without beta assets stay valid).
    beta_assets = {a.get("name") for a in release.get("assets", [])}
    if "Omi.Beta.zip" in beta_assets:
        if not getattr(args, "beta_smoke_result", "") or not Path(args.beta_smoke_result).exists():
            fail("release ships Omi Beta assets but no beta smoke result was provided")
        beta_smoke = load_json(args.beta_smoke_result)
        _validate_smoke_contract(
            beta_smoke,
            bundle_id=EXPECTED_BETA_BUNDLE_ID,
            release_tag=args.release_tag,
            expected_version=expected_version,
            expected_build=expected_build,
            label="beta",
        )
        beta_zip_release = asset_by_name(release, {"Omi.Beta.zip"})
        beta_dmg_release = asset_by_name(release, {"omi-beta.dmg"})
        beta_zip_smoke = smoke_artifact(beta_smoke, "sparkle_zip")
        beta_dmg_smoke = smoke_artifact(beta_smoke, "dmg")
        artifact_digests["Omi.Beta.zip"] = normalized_digest(beta_zip_release)
        artifact_digests["omi-beta.dmg"] = normalized_digest(beta_dmg_release)
        if beta_zip_smoke.get("sha256") != artifact_digests["Omi.Beta.zip"]:
            fail("published Omi.Beta.zip digest does not match the beta artifact smoke")
        if beta_dmg_smoke.get("sha256") != artifact_digests["omi-beta.dmg"]:
            fail("published omi-beta.dmg digest does not match the beta artifact smoke")

    return {
        "passed": True,
        "gate": "desktop-auto-beta-candidate-v1",
        "release_tag": args.release_tag,
        "source_sha": smoke_source_sha,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "artifact_digests": artifact_digests,
        "signed_smoke_checks": sorted(checks),
        "notification_callback_canary": callback_canary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--smoke-result", required=True)
    parser.add_argument("--beta-smoke-result", default="")
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--latest-tag", required=True)
    parser.add_argument("--tag-sha", required=True)
    parser.add_argument("--checkout-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = validate(args)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"automatic beta candidate gate passed: {args.release_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
