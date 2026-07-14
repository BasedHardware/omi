#!/usr/bin/env python3
"""Validate that a nominated macOS stable candidate is safe to promote."""

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
    require_stable_candidate,
    stable_candidate_from_metadata,
)

REQUIRED_ASSETS = {"Omi.zip"}
DMG_ASSETS = {"omi.dmg", "Omi.dmg"}
TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+(?:\.\d+)?)\+(?P<build>\d+)-macos$")
BREAK_GLASS_CONFIRM = "I-ACCEPT-STABLE-PROMOTION-RISK"


def write_github_output(path: str | None, values: dict[str, str]) -> None:
    if not path:
        return
    with Path(path).open("a") as output:
        for key, value in values.items():
            print(f"{key}={value}", file=output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--github-output")
    parser.add_argument(
        "--break-glass",
        action="store_true",
        help="DANGER: bypass qualification and stable-candidate nomination gates",
    )
    parser.add_argument(
        "--break-glass-confirm",
        default="",
        help=f"Must be {BREAK_GLASS_CONFIRM} when --break-glass is set",
    )
    parser.add_argument("--break-glass-reason", default="", help="Required audit rationale for --break-glass")
    args = parser.parse_args()

    release = json.loads(Path(args.release_json).read_text(encoding="utf-8"))
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
        fail(f"{tag_name} must be channel: beta or channel: stable before promotion, got {channel!r}")
    if not metadata.get("edSignature"):
        fail(f"{tag_name} is missing edSignature metadata")
    if metadata.get("isLive", "").strip().lower() not in {"true", "1", "yes"}:
        fail(f"{tag_name} must have isLive: true before stable promotion")

    asset_names = {asset.get("name") for asset in release.get("assets", []) if asset.get("name")}
    missing_assets = sorted(REQUIRED_ASSETS - asset_names)
    if missing_assets:
        fail(f"{tag_name} is missing required release asset(s): {', '.join(missing_assets)}")
    if not (asset_names & DMG_ASSETS):
        fail(f"{tag_name} is missing a DMG release asset")

    break_glass_reason = args.break_glass_reason.strip()
    break_glass = (
        args.break_glass
        and args.break_glass_confirm == BREAK_GLASS_CONFIRM
        and bool(break_glass_reason)
        and "\n" not in break_glass_reason
        and "\r" not in break_glass_reason
    )
    if args.break_glass and not break_glass:
        fail(
            f"--break-glass requires --break-glass-confirm {BREAK_GLASS_CONFIRM} "
            "and a non-empty --break-glass-reason"
        )

    qualification = desktop_qualification_from_metadata(metadata)
    candidate = stable_candidate_from_metadata(metadata)
    if not break_glass:
        require_desktop_qualification(qualification, target_sha=args.target_sha, asset_names=asset_names)
        require_stable_candidate(
            candidate,
            release_tag=args.release_tag,
            target_sha=args.target_sha,
            qualification_evidence=qualification.evidence,
        )

    write_github_output(
        args.github_output,
        {
            "release_channel": channel,
            "release_version": tag_match.group("version"),
            "release_build_number": tag_match.group("build"),
            "firestore_doc_id": f"v{tag_match.group('version')}+{tag_match.group('build')}",
            "qualification_sha": qualification.sha,
            "qualification_source": qualification.source,
            "stable_candidate_by": candidate.nominated_by,
            "break_glass_used": "true" if break_glass else "false",
        },
    )
    mode = "break-glass" if break_glass else "nominated stable candidate"
    print(f"desktop stable promotion sanity OK: {tag_name} ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
