#!/usr/bin/env python3
"""Validate and record a desktop stable-candidate nomination."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_release_metadata import (  # noqa: E402
    desktop_qualification_from_metadata,
    fail,
    parse_metadata,
    require_desktop_qualification,
    update_metadata,
)


def _single_line(name: str, value: str) -> str:
    value = value.strip()
    if not value:
        fail(f"{name} is required")
    if "\n" in value or "\r" in value:
        fail(f"{name} must be a single-line value")
    return value


def nominate(
    release: dict,
    *,
    release_tag: str,
    target_sha: str,
    beta_release_id: str,
    beta_source_sha: str,
    nominator: str,
    rationale: str,
    soak_review: str,
    telemetry_review: str,
    release_notes_review: str,
    nominated_at: str,
) -> str:
    if release.get("tagName") != release_tag:
        fail(f"release tag mismatch: expected {release_tag}, got {release.get('tagName')}")
    if release.get("isDraft") or release.get("isPrerelease"):
        fail("stable candidates must be published GitHub releases")
    if beta_release_id != release_tag:
        fail(f"beta pointer references {beta_release_id!r}, not requested release {release_tag!r}")
    if beta_source_sha != target_sha:
        fail(f"beta manifest source SHA {beta_source_sha!r} does not match tag commit {target_sha!r}")

    metadata = parse_metadata(release.get("body") or "")
    if metadata.get("channel") != "beta":
        fail(f"stable candidates must currently be channel: beta, got {metadata.get('channel')!r}")
    if metadata.get("isLive", "").strip().lower() not in {"true", "1", "yes"}:
        fail("stable candidates must be live on the beta channel")

    asset_names = {asset.get("name") for asset in release.get("assets", []) if asset.get("name")}
    qualification = desktop_qualification_from_metadata(metadata)
    require_desktop_qualification(qualification, target_sha=target_sha, asset_names=asset_names)

    values = {
        "stableCandidate": "true",
        "stableCandidateTag": release_tag,
        "stableCandidateSha": target_sha,
        "stableCandidateAt": _single_line("nominated_at", nominated_at),
        "stableCandidateBy": _single_line("nominator", nominator),
        "stableCandidateRationale": _single_line("rationale", rationale),
        "stableCandidateQualificationEvidence": qualification.evidence,
        "stableCandidateSoakReview": _single_line("soak_review", soak_review),
        "stableCandidateTelemetryReview": _single_line("telemetry_review", telemetry_review),
        "stableCandidateReleaseNotesReview": _single_line("release_notes_review", release_notes_review),
    }
    return update_metadata(release.get("body") or "", values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--beta-release-id", required=True)
    parser.add_argument("--beta-source-sha", required=True)
    parser.add_argument("--nominator", required=True)
    parser.add_argument("--rationale", required=True)
    parser.add_argument("--soak-review", required=True)
    parser.add_argument("--telemetry-review", required=True)
    parser.add_argument("--release-notes-review", required=True)
    parser.add_argument("--nominated-at")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    release = json.loads(Path(args.release_json).read_text(encoding="utf-8"))
    nominated_at = args.nominated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = nominate(
        release,
        release_tag=args.release_tag,
        target_sha=args.target_sha,
        beta_release_id=args.beta_release_id,
        beta_source_sha=args.beta_source_sha,
        nominator=args.nominator,
        rationale=args.rationale,
        soak_review=args.soak_review,
        telemetry_review=args.telemetry_review,
        release_notes_review=args.release_notes_review,
        nominated_at=nominated_at,
    )
    Path(args.output).write_text(body, encoding="utf-8")
    print(f"stable candidate nominated: {args.release_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
