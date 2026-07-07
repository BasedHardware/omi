#!/usr/bin/env python3
"""Validate that a macOS GitHub Release is safe to promote to stable."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_release_metadata import fail, parse_metadata  # noqa: E402


REQUIRED_ASSETS = {"Omi.zip"}
DMG_ASSETS = {"omi.dmg", "Omi.dmg"}
TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+(?:\.\d+)?)\+(?P<build>\d+)-macos$")


def write_github_output(path: str | None, values: dict[str, str]) -> None:
    if not path:
        return

    with Path(path).open("a") as f:
        for key, value in values.items():
            print(f"{key}={value}", file=f)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--github-output")
    parser.add_argument(
        "--override-unblessed",
        action="store_true",
        help="DANGER: allow prod promotion without a blessed release",
    )
    parser.add_argument(
        "--override-confirm",
        default="",
        help="Must be I-ACCEPT-UNBLESSED-PROD-RISK when --override-unblessed is set",
    )
    args = parser.parse_args()

    release = json.loads(Path(args.release_json).read_text())
    tag_name = release.get("tagName")
    if tag_name != args.release_tag:
        fail(f"release tag mismatch: expected {args.release_tag}, got {tag_name}")
    tag_match = TAG_RE.match(tag_name or "")
    if not tag_match:
        fail(f"{tag_name!r} is not a v*-macos release tag")
    if release.get("isDraft"):
        fail(f"{tag_name} is still a draft release")
    if release.get("isPrerelease"):
        fail(f"{tag_name} is marked as a GitHub prerelease")

    metadata = parse_metadata(release.get("body") or "")
    channel = metadata.get("channel")
    if channel not in {"beta", "stable"}:
        fail(f"{tag_name} must be channel: beta or channel: stable before prod promotion, got {channel!r}")
    if not metadata.get("edSignature"):
        fail(f"{tag_name} is missing edSignature metadata")

    # A release that is not live is invisible to the Python appcast
    # (backend/routers/updates.py filters on isLive == true), so promoting
    # it would advance the prod tracking tag / backend without appcast
    # users ever seeing the build.
    is_live = metadata.get("isLive", "").strip().lower()
    if is_live not in {"true", "1", "yes"}:
        fail(f"{tag_name} must have isLive: true in release metadata before prod promotion (got {is_live!r})")

    asset_names = {asset.get("name") for asset in release.get("assets", [])}
    missing_assets = sorted(REQUIRED_ASSETS - asset_names)
    if missing_assets:
        fail(f"{tag_name} is missing required release asset(s): {', '.join(missing_assets)}")
    if not (asset_names & DMG_ASSETS):
        fail(f"{tag_name} is missing a DMG release asset")

    blessed = metadata.get("blessed", "").strip().lower()
    blessed_sha = metadata.get("blessedSha", "").strip()
    blessed_at = metadata.get("blessedAt", "").strip()
    override_unblessed = args.override_unblessed and args.override_confirm == "I-ACCEPT-UNBLESSED-PROD-RISK"
    if args.override_unblessed and not override_unblessed:
        fail("--override-unblessed requires --override-confirm I-ACCEPT-UNBLESSED-PROD-RISK")
    if not override_unblessed:
        if blessed not in {"true", "1", "yes"}:
            fail(f"{tag_name} must be blessed before prod promotion (missing blessed: true)")
        if not blessed_sha:
            fail(f"{tag_name} is missing blessedSha metadata")
        if not blessed_at:
            fail(f"{tag_name} is missing blessedAt metadata")

    write_github_output(
        args.github_output,
        {
            "release_channel": channel,
            "release_version": tag_match.group("version"),
            "release_build_number": tag_match.group("build"),
            "firestore_doc_id": f"v{tag_match.group('version')}+{tag_match.group('build')}",
            "blessed_sha": blessed_sha,
            "blessed_override": "true" if override_unblessed else "false",
        },
    )
    print(f"desktop release promotion sanity OK: {tag_name} ({channel})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
