#!/usr/bin/env python3
"""Tests for the desktop stable-promotion gate."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github/scripts/check-desktop-release-promotion.py"
TAG = "v11.0+11000-macos"
SHA = "a" * 40
EVIDENCE = "qualification-evidence.json"


def run_check(release: dict, *extra: str) -> subprocess.CompletedProcess[str]:
    release_path = Path("/tmp/desktop-release-test.json")
    release_path.write_text(json.dumps(release), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--release-json",
            str(release_path),
            "--release-tag",
            TAG,
            "--target-sha",
            SHA,
            *extra,
        ],
        text=True,
        capture_output=True,
    )


def base_release(metadata: dict[str, str]) -> dict:
    lines = ["KEY_VALUE_START", *[f"{key}: {value}" for key, value in metadata.items()], "KEY_VALUE_END"]
    return {
        "tagName": TAG,
        "isDraft": False,
        "isPrerelease": False,
        "body": "\n".join(lines),
        "assets": [{"name": "Omi.zip"}, {"name": "omi.dmg"}, {"name": EVIDENCE}],
    }


def common_metadata() -> dict[str, str]:
    return {"channel": "beta", "isLive": "true", "edSignature": "sig"}


def nomination_metadata() -> dict[str, str]:
    return {
        "stableCandidate": "true",
        "stableCandidateTag": TAG,
        "stableCandidateSha": SHA,
        "stableCandidateAt": "2026-07-10T12:00:00Z",
        "stableCandidateBy": "release-operator",
        "stableCandidateRationale": "beta soak and launch criteria passed",
        "stableCandidateQualificationEvidence": EVIDENCE,
        "stableCandidateSoakReview": "24h beta soak reviewed",
        "stableCandidateTelemetryReview": "crash and update telemetry reviewed",
        "stableCandidateReleaseNotesReview": "stable rollup reviewed",
    }


def test_canonical_qualification_and_nomination_pass() -> None:
    release = base_release(
        {
            **common_metadata(),
            "qualifiedBeta": "true",
            "qualifiedBetaAt": "2026-07-10T10:00:00Z",
            "qualifiedBetaSha": SHA,
            "qualifiedBetaTier": "2",
            "qualifiedBetaEvidence": EVIDENCE,
            **nomination_metadata(),
        }
    )
    result = run_check(release)
    assert result.returncode == 0, result.stderr


def test_legacy_qualification_remains_valid() -> None:
    release = base_release(
        {
            **common_metadata(),
            "blessed": "true",
            "blessedAt": "2026-07-10T10:00:00Z",
            "blessedSha": SHA,
            "blessedTier": "2",
            "blessedEvidence": EVIDENCE,
            **nomination_metadata(),
        }
    )
    result = run_check(release)
    assert result.returncode == 0, result.stderr


def test_qualified_beta_without_nomination_fails() -> None:
    release = base_release(
        {
            **common_metadata(),
            "qualifiedBeta": "true",
            "qualifiedBetaAt": "2026-07-10T10:00:00Z",
            "qualifiedBetaSha": SHA,
            "qualifiedBetaTier": "2",
            "qualifiedBetaEvidence": EVIDENCE,
        }
    )
    result = run_check(release)
    assert result.returncode != 0
    assert "nominated" in result.stderr, result.stderr


def test_break_glass_requires_confirmation_and_reason() -> None:
    release = base_release(common_metadata())
    rejected = run_check(release, "--break-glass", "--break-glass-confirm", "nope")
    assert rejected.returncode != 0
    missing_reason = run_check(
        release,
        "--break-glass",
        "--break-glass-confirm",
        "I-ACCEPT-STABLE-PROMOTION-RISK",
    )
    assert missing_reason.returncode != 0
    accepted = run_check(
        release,
        "--break-glass",
        "--break-glass-confirm",
        "I-ACCEPT-STABLE-PROMOTION-RISK",
        "--break-glass-reason",
        "urgent security release",
    )
    assert accepted.returncode == 0, accepted.stderr


if __name__ == "__main__":
    test_canonical_qualification_and_nomination_pass()
    test_legacy_qualification_remains_valid()
    test_qualified_beta_without_nomination_fails()
    test_break_glass_requires_confirmation_and_reason()
    print("check-desktop-release-promotion tests OK")
