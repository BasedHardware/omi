#!/usr/bin/env python3
"""Validate a qualified desktop candidate and build its control-plane manifest."""

from __future__ import annotations

import argparse
import hashlib
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


def _require_emergency_operation_identity(evidence: dict, *, release_tag: str, target_sha: str) -> None:
    operation_id = evidence.get("operation_id")
    incident_id = evidence.get("incident_id")
    if not isinstance(operation_id, str) or not re.fullmatch(r"[0-9a-f]{64}", operation_id):
        fail("emergency evidence operation_id must be a SHA-256 digest")
    if not isinstance(incident_id, str) or not incident_id.strip():
        fail("emergency evidence incident_id is required")
    binding = f"macos-beta-emergency-forward-promotion:{release_tag}:{target_sha.lower()}:{incident_id.strip()}"
    expected = hashlib.sha256(binding.encode("utf-8")).hexdigest()
    if operation_id != expected:
        fail("emergency evidence operation_id does not bind the release decision")


def prepare_manifest(
    release: dict,
    release_tag: str,
    target_sha: str,
    zip_sha256: str,
    dmg_sha256: str,
    *,
    allow_stable_channel: bool = False,
    emergency_evidence: dict | None = None,
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

    asset_names = {asset.get("name") for asset in release.get("assets", []) if asset.get("name")}
    qualification = desktop_qualification_from_metadata(metadata)
    if emergency_evidence is None:
        require_desktop_qualification(qualification, target_sha=target_sha, asset_names=asset_names)
    elif not isinstance(emergency_evidence, dict):
        fail("emergency evidence must be an object")
    elif emergency_evidence.get("release_tag") != release_tag or emergency_evidence.get("source_sha") != target_sha:
        fail("emergency evidence does not bind the requested release tag and source SHA")
    elif emergency_evidence.get("emergencyPromotion") is not True:
        fail("emergency evidence must explicitly declare emergencyPromotion")
    else:
        _require_emergency_operation_identity(emergency_evidence, release_tag=release_tag, target_sha=target_sha)

    zip_asset = _asset(release, {"Omi.zip"})
    dmg_asset = _asset(release, {"Omi.dmg", "omi.dmg"})
    signature = metadata.get("edSignature", "").strip()
    if not signature:
        fail("release is missing edSignature")

    changelog = [item.strip() for item in metadata.get("changelog", "").split("|") if item.strip()]
    version = match.group("version")
    build = int(match.group("build"))
    if emergency_evidence is not None:
        qualification_manifest = {"passed": False, "tier": "emergency", "emergency_evidence": emergency_evidence}
    else:
        qualification_manifest = {"passed": True, "tier": "T2", "evidence_asset": qualification.evidence}
    if emergency_evidence is None and qualification.source == "legacy":
        # Preserve the immutable manifest shape used by releases registered
        # before canonical qualification metadata existed. This keeps exact
        # beta-promotion retries idempotent.
        qualification_manifest["blessed_at"] = qualification.qualified_at
    elif emergency_evidence is None:
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
    parser.add_argument("--allow-stable-channel", action="store_true")
    parser.add_argument("--emergency-evidence-json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    release = json.loads(Path(args.release_json).read_text())
    emergency_evidence = None
    if args.emergency_evidence_json:
        emergency_evidence = json.loads(Path(args.emergency_evidence_json).read_text(encoding="utf-8"))
    manifest = prepare_manifest(
        release,
        args.release_tag,
        args.target_sha,
        args.zip_sha256,
        args.dmg_sha256,
        allow_stable_channel=args.allow_stable_channel,
        emergency_evidence=emergency_evidence,
    )
    Path(args.output).write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"qualified beta manifest prepared: {args.release_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
