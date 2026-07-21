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
    fail,
    parse_metadata,
)
from desktop_qualification_evidence import verify_evidence  # noqa: E402

TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+(?:\.\d+)?)\+(?P<build>\d+)-macos$")


def _asset(release: dict, names: set[str]) -> dict:
    for asset in release.get("assets", []):
        if asset.get("name") in names:
            return asset
    fail(f"release is missing required asset: {', '.join(sorted(names))}")


def prepare_manifest(
    release: dict,
    release_tag: str,
    target_sha: str,
    zip_sha256: str,
    dmg_sha256: str,
    *,
    beta_zip_sha256: str,
    beta_dmg_sha256: str,
    qualification_evidence: dict,
    allow_stable_channel: bool = False,
) -> dict:
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
    if channel == "stable" and is_live not in {"true", "1", "yes"}:
        fail("stable release must have isLive: true")
    allowed_channels = {"candidate", "beta"}
    if allow_stable_channel:
        allowed_channels.add("stable")
    if channel not in allowed_channels:
        accepted = "candidate, beta, or stable" if allow_stable_channel else "candidate or beta"
        fail(f"release channel must be {accepted}, got {channel!r}")

    zip_asset = _asset(release, {"Omi.zip"})
    dmg_asset = _asset(release, {"Omi.dmg", "omi.dmg"})
    beta_zip_asset = _asset(release, {"Omi.Beta.zip"})
    beta_dmg_asset = _asset(release, {"omi-beta.dmg"})
    signature = metadata.get("edSignature", "").strip()
    beta_signature = metadata.get("betaEdSignature", "").strip()
    if not signature or not beta_signature:
        fail("release is missing stable or beta Sparkle signature")
    try:
        verify_evidence(
            qualification_evidence,
            release,
            release_tag,
            target_sha,
            {
                "Omi.zip": zip_sha256,
                dmg_asset["name"]: dmg_sha256,
                "Omi.Beta.zip": beta_zip_sha256,
                "omi-beta.dmg": beta_dmg_sha256,
            },
        )
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    changelog = [item.strip() for item in metadata.get("changelog", "").split("|") if item.strip()]
    version = match.group("version")
    build = int(match.group("build"))
    qualification_manifest = {"passed": True, "tier": "T2", "source": "trusted_github_actions_artifact"}

    return {
        "release_id": release_tag,
        "platform": "macos",
        "version": f"{version}+{build}",
        "build_number": build,
        "zip_url": zip_asset.get("url"),
        "dmg_url": dmg_asset.get("url"),
        "beta_zip_url": beta_zip_asset.get("url"),
        "beta_dmg_url": beta_dmg_asset.get("url"),
        "ed_signature": signature,
        "beta_ed_signature": beta_signature,
        "published_at": release.get("publishedAt"),
        "changelog": changelog,
        "mandatory": metadata.get("mandatory", "false").lower() in {"true", "1", "yes"},
        "source_sha": target_sha,
        "zip_sha256": zip_sha256,
        "dmg_sha256": dmg_sha256,
        "beta_zip_sha256": beta_zip_sha256,
        "beta_dmg_sha256": beta_dmg_sha256,
        "qualification": qualification_manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--zip-sha256", required=True)
    parser.add_argument("--dmg-sha256", required=True)
    parser.add_argument("--beta-zip-sha256", required=True)
    parser.add_argument("--beta-dmg-sha256", required=True)
    parser.add_argument("--qualification-evidence", required=True)
    parser.add_argument("--allow-stable-channel", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    release = json.loads(Path(args.release_json).read_text())
    evidence = json.loads(Path(args.qualification_evidence).read_text())
    manifest = prepare_manifest(
        release,
        args.release_tag,
        args.target_sha,
        args.zip_sha256,
        args.dmg_sha256,
        beta_zip_sha256=args.beta_zip_sha256,
        beta_dmg_sha256=args.beta_dmg_sha256,
        qualification_evidence=evidence,
        allow_stable_channel=args.allow_stable_channel,
    )
    Path(args.output).write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"qualified beta manifest prepared: {args.release_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
