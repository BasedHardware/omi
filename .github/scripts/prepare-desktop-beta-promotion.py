#!/usr/bin/env python3
"""Validate a qualified desktop candidate and build its control-plane manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_release_metadata import (  # noqa: E402
    desktop_qualification_from_metadata,
    fail,
    parse_metadata,
    require_desktop_qualification,
)

TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+(?:\.\d+)?)\+(?P<build>\d+)-macos$")


def _asset(release: dict, names: set[str]) -> dict:
    for asset in release.get("assets", []):
        if asset.get("name") in names:
            return asset
    fail(f"release is missing required asset: {', '.join(sorted(names))}")


def prepare_manifest(release: dict, release_tag: str, target_sha: str, zip_sha256: str, dmg_sha256: str) -> dict:
    if release.get("tagName") != release_tag:
        fail(f"release tag mismatch: expected {release_tag}, got {release.get('tagName')}")
    match = TAG_RE.match(release_tag)
    if not match:
        fail(f"invalid macOS release tag: {release_tag}")
    if release.get("isDraft") or release.get("isPrerelease"):
        fail("release must be published and not a GitHub prerelease")

    metadata = parse_metadata(release.get("body") or "")
    channel = metadata.get("channel")
    is_live = metadata.get("isLive", "").lower()
    if channel == "candidate" and is_live not in {"false", "0", "no"}:
        fail("candidate release must have isLive: false")
    if channel == "beta" and is_live not in {"true", "1", "yes"}:
        fail("beta release must have isLive: true")
    if channel not in {"candidate", "beta"}:
        fail(f"release channel must be candidate or beta, got {channel!r}")

    asset_names = {asset.get("name") for asset in release.get("assets", []) if asset.get("name")}
    qualification = desktop_qualification_from_metadata(metadata)
    require_desktop_qualification(qualification, target_sha=target_sha, asset_names=asset_names)

    zip_asset = _asset(release, {"Omi.zip"})
    dmg_asset = _asset(release, {"Omi.dmg", "omi.dmg"})
    signature = metadata.get("edSignature", "").strip()
    if not signature:
        fail("release is missing edSignature")

    changelog = [item.strip() for item in metadata.get("changelog", "").split("|") if item.strip()]
    version = match.group("version")
    build = int(match.group("build"))
    qualification_manifest = {
        "passed": True,
        "tier": "T2",
        "evidence_asset": qualification.evidence,
    }
    if qualification.source == "legacy":
        # Preserve the immutable manifest shape used by releases registered
        # before canonical qualification metadata existed. This keeps exact
        # beta-promotion retries idempotent.
        qualification_manifest["blessed_at"] = qualification.qualified_at
    else:
        qualification_manifest["qualified_at"] = qualification.qualified_at

    return {
        "release_id": release_tag,
        "platform": "macos",
        "version": f"{version}+{build}",
        "build_number": build,
        "zip_url": zip_asset.get("url"),
        "dmg_url": dmg_asset.get("url"),
        "ed_signature": signature,
        "published_at": release.get("publishedAt"),
        "changelog": changelog,
        "mandatory": metadata.get("mandatory", "false").lower() in {"true", "1", "yes"},
        "source_sha": target_sha,
        "zip_sha256": zip_sha256,
        "dmg_sha256": dmg_sha256,
        "qualification": qualification_manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--zip-sha256", required=True)
    parser.add_argument("--dmg-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    release = json.loads(Path(args.release_json).read_text())
    manifest = prepare_manifest(release, args.release_tag, args.target_sha, args.zip_sha256, args.dmg_sha256)
    Path(args.output).write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"qualified beta manifest prepared: {args.release_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
