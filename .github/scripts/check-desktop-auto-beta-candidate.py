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
EXPECTED_TEAM_ID = "9536L8KLMP"
REQUIRED_SMOKE_CHECKS = {
    "Launch + identity metadata is aligned",
    "Auth persistence prerequisites: signing identity and Keychain-compatible entitlements are sane",
    "Backend routing config has no local/dev leakage",
    "Sparkle/update metadata and authoritative ZIP artifacts are present",
    "Native helper/runtime bundle integrity passed",
    "Local storage/database package surface is present",
    "Signed desktop artifact Keychain write/read/delete canary passed",
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
    if release.get("tagName") != args.release_tag:
        fail("GitHub release tag does not match the requested candidate")
    if release.get("isDraft") or release.get("isPrerelease"):
        fail("automatic beta candidate must be a published non-prerelease GitHub release")
    if not release.get("publishedAt"):
        fail("automatic beta candidate must have a GitHub publication timestamp")

    metadata = parse_metadata(release.get("body") or "")
    if metadata.get("channel") != "candidate" or metadata.get("isLive", "").lower() not in {"false", "0", "no"}:
        fail("automatic beta qualification requires channel: candidate and isLive: false")
    if metadata.get("stableCandidate", "").lower() in {"true", "1", "yes"}:
        fail("automatic beta qualification refuses a release already nominated for stable")

    expected_version = match.group("version")
    expected_build = match.group("build")
    expected = {
        "ok": True,
        "release_tag": args.release_tag,
        "expected_channel": "beta",
        "bundle_id": EXPECTED_BUNDLE_ID,
        "version": expected_version,
        "build": expected_build,
        "team_id": EXPECTED_TEAM_ID,
    }
    for field, value in expected.items():
        if smoke.get(field) != value:
            fail(f"signed smoke result {field} mismatch: expected {value!r}, got {smoke.get(field)!r}")

    checks = set(smoke.get("checks") or [])
    missing_checks = sorted(REQUIRED_SMOKE_CHECKS - checks)
    if missing_checks:
        fail(f"signed smoke result is missing required checks: {', '.join(missing_checks)}")

    zip_release = asset_by_name(release, {"Omi.zip"})
    dmg_release = asset_by_name(release, {"Omi.dmg", "omi.dmg"})
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

    return {
        "passed": True,
        "gate": "desktop-auto-beta-candidate-v1",
        "release_tag": args.release_tag,
        "source_sha": args.tag_sha,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "artifact_digests": artifact_digests,
        "signed_smoke_checks": sorted(checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--smoke-result", required=True)
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
